param([string]$PackageRoot=(Split-Path -Parent $PSScriptRoot))
$ErrorActionPreference='Stop'
$root=Join-Path ([IO.Path]::GetTempPath()) ('onec-selected-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $root|Out-Null
$module=Import-Module (Join-Path $PackageRoot 'core/OneCChatWorker.Core.psm1') -Force -DisableNameChecking -PassThru
try {
 & $module {
  param($Root)
  # OS/account integration only: actual catalog, snapshot, Node acquisition,
  # promotion, atomic JSON publication and recovery owners remain unchanged.
  function script:Test-IsAdministrator {$true}
  function script:Apply-ProjectAcl {param($ProjectRoot)}
  function script:Set-SourceUpdateTreeAcl {param($Path,$OperatorIdentity,[switch]$Writable)}
  function script:Protect-SourceUpdateMetadata {param($Path,$OperatorIdentity)}
  function W($Path,$Text){New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Path)|Out-Null;[IO.File]::WriteAllText($Path,$Text,[Text.UTF8Encoding]::new($false))}
  $script:Checks=0
  function Check($Ok,$Name){if(-not $Ok){throw ('ASSERTION_FAILED: '+$Name)};$script:Checks++;Write-Host ('PASS '+$Name)}
  function Manifest($Worker){Get-Content (Get-ProjectManifestPath RetailGroup $Worker) -Raw -Encoding UTF8|ConvertFrom-Json}
  function Fixture($Name){
   $worker=Join-Path $Root ($Name+'/worker');$data=Join-Path $Root ($Name+'/data');$external=Join-Path $Root ($Name+'/external')
   New-WorkerProject -ProjectId RetailGroup -DisplayName RetailGroup -WorkerRoot $worker|Out-Null
   foreach($participantKey in @('do','un')){
    $source=Join-Path $external $participantKey;W (Join-Path $source 'Configuration.xml') '<Configuration/>';W (Join-Path $source 'payload.bin') 'unchanged Main fixture'
    Add-WorkerParticipant -ProjectId RetailGroup -ParticipantId $participantKey -Platform ONEC -Role Main -WorkerRoot $worker|Out-Null
    Set-WorkerMain -ProjectId RetailGroup -ParticipantId $participantKey -SourcePath $source -WorkerRoot $worker|Out-Null
   }
   $bit=Join-Path $external 'bit';W (Join-Path $bit 'Configuration.xml') '<Configuration name="old-bit"/>';W (Join-Path $bit 'ConfigDumpInfo.xml') '<ConfigDumpInfo/>'
   Add-WorkerExtension -ProjectId RetailGroup -ParticipantId un -ExtensionId bit -SourcePath $bit -WorkerRoot $worker|Out-Null
   $ap=Apply-WorkerProject -ProjectId RetailGroup -WorkerRoot $worker
   Check ($ap.status -eq 'READY') ($Name+' fixture accepted')
   $before=Manifest $worker;$sha=Get-Sha256File (Get-ProjectManifestPath RetailGroup $worker)
   $cat=Read-WorkerCatalog $worker;$cat.projects[0].display_name='new display metadata';Write-WorkerCatalog $cat $worker
   Check ((Get-FastProjectState RetailGroup $worker).state -eq 'CATALOG_DRIFT') ($Name+' global drift remains visible')
   [pscustomobject]@{worker=$worker;data=$data;before=$before;sha=$sha}
  }
  function Prepare($F){Prepare-SourceUpdate -ProjectId RetailGroup -Selections @('un|EXTENSION|bit') -WorkerRoot $F.worker -ProgramDataRoot $F.data -OperatorIdentity fixture}
  function Fill($Prep){W (Join-Path $Prep.slots[0].slot_path 'Configuration.xml') '<Configuration name="new-bit"/>';W (Join-Path $Prep.slots[0].slot_path 'ConfigDumpInfo.xml') '<ConfigDumpInfo revision="2"/>'}
  $f=Fixture 'changed';$before=$f.before
  # Exclusive handles prevent payload reads/hash/copy of BOTH accepted and
  # external Main trees throughout PREPARE/ACCEPT/NO_CHANGE (not just counters).
  $handles=@()
  try {
   foreach($participantKey in @('do','un')){
    foreach($dir in @((Join-Path $f.worker ('RetailGroup/Participants/'+$participantKey+'/Target/Main')),(Join-Path (Split-Path $f.worker -Parent) ('external/'+$participantKey)))){
     foreach($file in Get-ChildItem -LiteralPath $dir -File -Recurse){$handles+=,[IO.File]::Open($file.FullName,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::None)}
    }
   }
   $prep=Prepare $f;Fill $prep
   Check ((Get-FastProjectState RetailGroup $f.worker).state -eq 'CATALOG_DRIFT') 'prepare does not fake ACCEPTED'
   $result=Accept-SourceUpdate -ProjectId RetailGroup -WorkerRoot $f.worker -ProgramDataRoot $f.data -OperatorIdentity fixture
   Check ($result.status -eq 'READY' -and $result.main_content_bytes_read -eq 0 -and $result.main_hashed_bytes -eq 0 -and $result.main_copied_bytes -eq 0) 'two locked Main trees read/hash/copy zero'
   Check ($result.copied_content_bytes -eq 0 -and $result.stage_content_rehash -eq 0) 'selected same-volume rename no copy or rehash'
   $after=Manifest $f.worker
   foreach($participantKey in @('do','un')){
    $old=@($before.accepted_snapshot.artifacts|Where-Object {$_.participant_id -eq $participantKey -and $_.artifact_type -eq 'MAIN'})[0]
    $new=@($after.accepted_snapshot.artifacts|Where-Object {$_.participant_id -eq $participantKey -and $_.artifact_type -eq 'MAIN'})[0]
    Check (($old|ConvertTo-Json -Compress) -ceq ($new|ConvertTo-Json -Compress)) ($participantKey+' exact Main row/fingerprint identity')
   }
   Check ($after.catalog_sha256 -eq (Get-CatalogHash $f.worker) -and $after.accepted_snapshot.publication_generation -eq ($before.accepted_snapshot.publication_generation+1)) 'single atomic catalog/snapshot generation publication'
   $target=Join-Path $f.worker 'RetailGroup/Participants/un/Target/Extensions/bit'
   Check ((Get-Sha256File (Join-Path $target 'Configuration.xml')) -eq $after.participants[1].target.extensions[0].configuration_xml_sha256) 'new bit exact SHA'
   $oldBits=@(Get-ChildItem (Join-Path $f.worker 'RetailGroup/Detached') -Filter Configuration.xml -Recurse)
   Check ($oldBits.Count -eq 1 -and (Get-Sha256File $oldBits[0].FullName) -eq $before.participants[1].target.extensions[0].configuration_xml_sha256) 'old bit preserved in Detached'
   $sha=Get-Sha256File (Get-ProjectManifestPath RetailGroup $f.worker);$prep=Prepare $f
   Get-ChildItem $target -Force|ForEach-Object {Copy-Item -LiteralPath $_.FullName -Destination $prep.slots[0].slot_path -Recurse}
   $no=Accept-SourceUpdate -ProjectId RetailGroup -WorkerRoot $f.worker -ProgramDataRoot $f.data -OperatorIdentity fixture
   Check ($no.status -eq 'NO_CHANGE' -and $no.source_snapshot_id -eq $after.accepted_snapshot.source_snapshot_id -and (Get-Sha256File (Get-ProjectManifestPath RetailGroup $f.worker)) -eq $sha) 'repeat NO_CHANGE exact manifest/snapshot'
  } finally {foreach($handle in $handles){$handle.Dispose()}}
  foreach($damage in @('main-path','participant','inventory','snapshot','no-change')){
   $f=Fixture $damage;$cat=Read-WorkerCatalog $f.worker
   if($damage -eq 'main-path'){$cat.projects[0].participants[0].target.main.source_path+='-changed';Write-WorkerCatalog $cat $f.worker}
   if($damage -eq 'participant'){$cat.projects[0].participants[0].active=$false;Write-WorkerCatalog $cat $f.worker}
   if($damage -eq 'inventory'){$fp=$f.before.accepted_snapshot.artifacts[0].fingerprint_inventory_path;W (Join-Path (Split-Path (Get-ProjectManifestPath RetailGroup $f.worker) -Parent) $fp) 'damaged metadata'}
   if($damage -eq 'snapshot'){$m=Manifest $f.worker;$m.accepted_snapshot.source_snapshot_id='invalid';Write-JsonAtomic $m (Get-ProjectManifestPath RetailGroup $f.worker)}
   $manifestSha=Get-Sha256File (Get-ProjectManifestPath RetailGroup $f.worker);$failed=$false
   try {
    $prep=Prepare $f
    if($damage -eq 'no-change'){
     $target=Join-Path $f.worker 'RetailGroup/Participants/un/Target/Extensions/bit';Get-ChildItem $target -Force|ForEach-Object {Copy-Item -LiteralPath $_.FullName -Destination $prep.slots[0].slot_path -Recurse}
     Accept-SourceUpdate -ProjectId RetailGroup -WorkerRoot $f.worker -ProgramDataRoot $f.data -OperatorIdentity fixture|Out-Null
    }
   } catch {$failed=$_.Exception.Message -like 'SOURCE_UPDATE_*'}
   Check ($failed -and (Get-Sha256File (Get-ProjectManifestPath RetailGroup $f.worker)) -eq $manifestSha -and (Get-FastProjectState RetailGroup $f.worker).state -ne 'ACCEPTED') ($damage+' fails closed without publication')
  }
  foreach($fault in @('AFTER_MARKER','AFTER_FIRST_DETACH','AFTER_FIRST_PROMOTE','AFTER_ALL_PROMOTED','AFTER_MANIFEST_COMMIT','AFTER_MARKER_REMOVAL')){
   $f=Fixture $fault;$prep=Prepare $f;Fill $prep;$failed=$false
   try{Accept-SourceUpdate -ProjectId RetailGroup -WorkerRoot $f.worker -ProgramDataRoot $f.data -OperatorIdentity fixture -FaultInjection $fault|Out-Null}catch{$failed=$_.Exception.Message -like 'SOURCE_UPDATE_TEST_FAULT_*'}
   Check $failed ($fault+' injected')
   $recovery=Recover-SourceUpdatePromotion -ProjectId RetailGroup -WorkerRoot $f.worker -ProgramDataRoot $f.data -OperatorIdentity fixture
   $fast=Get-FastProjectState RetailGroup $f.worker
   $committed=$fault -in @('AFTER_MANIFEST_COMMIT','AFTER_MARKER_REMOVAL')
   Check ($recovery.status -eq 'RECOVERED' -and (($committed -and $fast.state -eq 'ACCEPTED') -or (-not $committed -and $fast.state -eq 'CATALOG_DRIFT' -and (Get-Sha256File (Get-ProjectManifestPath RetailGroup $f.worker)) -eq $f.sha))) ($fault+' recover-first coherent old/new, never fake accepted')
  }
  Write-Host ('SELECTED_CATALOG_UPDATE_PASS checks='+$script:Checks+' main_content_read_hash_copy=0 production_mutation=false')
 } $root
} finally {
 if(-not ([IO.Path]::GetFullPath($root)).StartsWith(([IO.Path]::GetFullPath([IO.Path]::GetTempPath())).TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'FIXTURE_CLEANUP_OUTSIDE_TEMP'}
 Remove-Item -LiteralPath $root -Recurse -Force
}
