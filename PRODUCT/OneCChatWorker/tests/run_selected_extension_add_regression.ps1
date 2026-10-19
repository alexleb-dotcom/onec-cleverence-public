#requires -Version 5.1
param([string]$PackageRoot=(Split-Path -Parent $PSScriptRoot),[string]$BaselineCorePath)
$ErrorActionPreference='Stop'
if($PSVersionTable.PSVersion.Major -ne 5){throw 'WINDOWS_POWERSHELL_51_REQUIRED'}
# All dummy data stays beneath this checkout; no installed Worker or account changes.
$checkout=Split-Path -Parent (Split-Path -Parent $PackageRoot)
$root=Join-Path $checkout ('.q113-'+[guid]::NewGuid().ToString('N').Substring(0,8))
New-Item -ItemType Directory -Path $root|Out-Null
$baseline=$null
if($BaselineCorePath){$baseline=Import-Module $BaselineCorePath -Force -DisableNameChecking -PassThru}
$module=Import-Module (Join-Path $PackageRoot 'core/OneCChatWorker.Core.psm1') -Force -DisableNameChecking -PassThru
try {
 & $module {
  param($Root,$old)
  function script:Test-IsAdministrator {$true}
  function script:Apply-ProjectAcl {param($ProjectRoot)}
  $script:Seals=0;$script:Protection=0
  function script:Set-SourceUpdateTreeAcl {param($Path,$OperatorIdentity,[switch]$Writable)if(-not $Writable){$script:Seals++}}
  function script:Protect-SourceUpdateMetadata {param($Path,$OperatorIdentity)$script:Protection++}
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
   $bitdo=Join-Path $external 'bitdo';W (Join-Path $bitdo 'Configuration.xml') '<Configuration name="new-bitdo"/>';W (Join-Path $bitdo 'ConfigDumpInfo.xml') '<ConfigDumpInfo/>'
   Add-WorkerExtension -ProjectId RetailGroup -ParticipantId do -ExtensionId bitdo -SourcePath $bitdo -WorkerRoot $worker|Out-Null
   Check ((Get-FastProjectState RetailGroup $worker).state -eq 'CATALOG_DRIFT') ($Name+' global drift remains visible')
   [pscustomobject]@{worker=$worker;data=$data;before=$before;sha=$sha}
  }

  function Prepare($F,$Keys=@('do|EXTENSION|bitdo')){Prepare-SourceUpdate -ProjectId RetailGroup -Selections $Keys -WorkerRoot $F.worker -ProgramDataRoot $F.data -OperatorIdentity fixture}
  function Fill($P){W (Join-Path $P.slots[0].slot_path 'Configuration.xml') '<Configuration name="new-bitdo"/>';W (Join-Path $P.slots[0].slot_path 'ConfigDumpInfo.xml') '<ConfigDumpInfo revision="2"/>'}
  function Accept($F,$P,$Fault=''){Accept-SourceUpdate -ExpectedGenerationId $P.generation_id -ExpectedArtifactKey @($P.slots.key) -ProjectId RetailGroup -WorkerRoot $F.worker -ProgramDataRoot $F.data -OperatorIdentity fixture -FaultInjection $Fault}
  function Target($F){Join-Path $F.worker 'RetailGroup/Participants/do/Target/Extensions/bitdo'}
  function Recover($F){Recover-SourceUpdatePromotion -ProjectId RetailGroup -WorkerRoot $F.worker -ProgramDataRoot $F.data -OperatorIdentity fixture}
  function Reject($Action,$Code,$Label){$got='';try{& $Action|Out-Null}catch{$got=$_.Exception.Message};Check ($got -like $Code) ($Label+' ['+$got+']')}
  function LockMains($F){
   $handles=@()
   foreach($pidKey in @('do','un')){
    foreach($dir in @((Join-Path $F.worker ('RetailGroup/Participants/'+$pidKey+'/Target/Main')),(Join-Path (Split-Path $F.worker -Parent) ('external/'+$pidKey)))){
     foreach($file in Get-ChildItem -LiteralPath $dir -File -Recurse){$handles+=,[IO.File]::Open($file.FullName,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::None)}
    }
   }
   $handles
  }
  function Unchanged($F){
   $after=Manifest $F.worker
   foreach($key in @('do|MAIN|main','un|MAIN|main','un|EXTENSION|bit')){
    $old=@($F.before.accepted_snapshot.artifacts|Where-Object {(Get-SnapshotArtifactKey $_) -ceq $key})[0]
    $new=@($after.accepted_snapshot.artifacts|Where-Object {(Get-SnapshotArtifactKey $_) -ceq $key})[0]
    Check (($old|ConvertTo-Json -Depth 20 -Compress) -ceq ($new|ConvertTo-Json -Depth 20 -Compress)) ($key+' exact snapshot/fingerprint row')
   }
   foreach($pidKey in @('do','un')){
    $a=@($F.before.participants|Where-Object {$_.participant_id -ceq $pidKey})[0];$b=@($after.participants|Where-Object {$_.participant_id -ceq $pidKey})[0]
    Check (($a.target.main|ConvertTo-Json -Compress) -ceq ($b.target.main|ConvertTo-Json -Compress)) ($pidKey+' exact Main manifest/source/canonical paths')
   }
   Check (($F.before.participants[1].target.extensions|ConvertTo-Json -Compress) -ceq ($after.participants[1].target.extensions|ConvertTo-Json -Compress)) 'un/bit exact old manifest'
  }
  $f=Fixture 'positive';$handles=@(LockMains $f)
  try{
   $p=Prepare $f;Fill $p
   Check (@($f.before.accepted_snapshot.artifacts|Where-Object {$_.artifact_id -eq 'bitdo'}).Count -eq 0) 'ADD starts without row or fingerprint inventory'
   $admission=Join-Path $f.data 'runtime/active-admission.json';W $admission '{"project_id":"RetailGroup"}'
   $blocked=Accept $f $p
   Check ($blocked.status -eq 'SEALED_VALIDATED' -and $blocked.reason -eq 'PROJECT_ADMISSION_ACTIVE' -and -not(Test-Path (Target $f)) -and (Get-Sha256File (Get-ProjectManifestPath RetailGroup $f.worker)) -eq $f.sha) 'admission seals selected ADD without publication'
   Check ($script:Seals -gt 0 -and $script:Protection -ge 5) 'existing seal and metadata protection owners invoked'
   $sealed=Read-SourceUpdateState -ProjectId RetailGroup -WorkerRoot $f.worker
   Reject {Invoke-SelectedArtifactFullSafeImportFallback -ProjectId RetailGroup -State $sealed -BaseManifest $f.before -Changed @($sealed.selected) -WorkerRoot $f.worker -OperatorIdentity fixture} 'SOURCE_UPDATE_ADD_REQUIRES_ZERO_COPY' 'ADD cannot enter copy fallback'
   Check (-not(Test-Path (Get-SourceUpdatePaths RetailGroup $f.worker).promotion_path)) 'unsupported ADD fallback leaves no promotion marker'
   Remove-Item -LiteralPath $admission
   $result=Accept $f $p
   Check ($result.status -eq 'READY' -and $result.zero_copy -and $result.copied_content_bytes -eq 0 -and $result.stage_content_rehash -eq 0) 'ADD same-volume zero-copy publication'
   Check ($result.main_content_bytes_read -eq 0 -and $result.main_hashed_bytes -eq 0 -and $result.main_copied_bytes -eq 0) 'both canonical/external Main payloads locked: zero read/hash/copy'
   Unchanged $f
   $after=Manifest $f.worker;$new=@($after.accepted_snapshot.artifacts|Where-Object {$_.artifact_id -eq 'bitdo'})[0]
   Check ($new.fingerprint_inventory_state -eq 'PRESENT' -and $new.configuration_xml_sha256 -eq (Get-Sha256File (Join-Path (Target $f) 'Configuration.xml'))) 'new candidate row and versioned inventory constructed'
   Check ((Get-FastProjectState RetailGroup $f.worker).state -eq 'ACCEPTED' -and $after.catalog_sha256 -eq (Get-CatalogHash $f.worker) -and $after.accepted_snapshot.publication_generation -eq ($f.before.accepted_snapshot.publication_generation+1)) 'one catalog/snapshot publication generation'
   Check (@(Get-ChildItem (Join-Path $f.worker 'RetailGroup/Detached') -File -Recurse).Count -eq 0) 'ADD detaches no existing artifact'
  }finally{foreach($h in $handles){$h.Dispose()}}
  # Full post-publication integrity only after the exclusive Main handles close.
  $verify=Verify-WorkerProject -ProjectId RetailGroup -WorkerRoot $f.worker
  Check ($verify.status -eq 'READY') 'post-snapshot full payload integrity'

  if($old){
   & $old {
    function script:Test-IsAdministrator {$true}
    function script:Set-SourceUpdateTreeAcl {param($Path,$OperatorIdentity,[switch]$Writable)}
    function script:Protect-SourceUpdateMetadata {param($Path,$OperatorIdentity)}
   }
   $handles=@(LockMains $f)
   try{
    $p=& $old {param($F)Prepare-SourceUpdate -ProjectId RetailGroup -Selections @('un|EXTENSION|bit') -WorkerRoot $F.worker -ProgramDataRoot $F.data -OperatorIdentity fixture} $f
    Fill $p
    $state=Read-SourceUpdateState -ProjectId RetailGroup -WorkerRoot $f.worker
    Check ($state.selected[0].PSObject.Properties.Name -notcontains 'action') 'actual baseline filled generation has original state shape'
    $legacy=Accept $f $p
    Check ($legacy.status -eq 'READY' -and $legacy.main_content_bytes_read -eq 0 -and $legacy.main_hashed_bytes -eq 0 -and $legacy.main_copied_bytes -eq 0) 'new Core accepts actual baseline filled UPDATE generation with Main locked'
   }finally{foreach($h in $handles){$h.Dispose()}}
  }

  foreach($damage in @('unselected-add','main-path','bit-path','removed-bit','duplicate','case-duplicate','participant-case','selection-case','selection-duplicate','target-exists','target-case','target-file','inventory','new-source-collision','canonical-source','inactive-duplicate','reserved-id')){
   $f=Fixture $damage;$cat=Read-WorkerCatalog $f.worker;$keys=@('do|EXTENSION|bitdo')
   switch($damage){
    'unselected-add' {$cat.projects[0].participants[0].target.extensions+=,[pscustomobject]@{extension_id='extra';active=$true;source_path='C:\dummy-only'};Write-WorkerCatalog $cat $f.worker}
    'main-path' {$cat.projects[0].participants[0].target.main.source_path+='-changed';Write-WorkerCatalog $cat $f.worker}
    'bit-path' {$cat.projects[0].participants[1].target.extensions[0].source_path+='-changed';Write-WorkerCatalog $cat $f.worker}
    'removed-bit' {$cat.projects[0].participants[1].target.extensions=@();Write-WorkerCatalog $cat $f.worker}
    'duplicate' {$cat.projects[0].participants[0].target.extensions+=,$cat.projects[0].participants[0].target.extensions[0];Write-WorkerCatalog $cat $f.worker}
    'case-duplicate' {$extra=$cat.projects[0].participants[0].target.extensions[0]|ConvertTo-Json|ConvertFrom-Json;$extra.extension_id='BITDO';$cat.projects[0].participants[0].target.extensions+=,$extra;Write-WorkerCatalog $cat $f.worker}
    'participant-case' {$cat.projects[0].participants[0].participant_id='DO';Write-WorkerCatalog $cat $f.worker}
    'selection-case' {$keys=@('do|EXTENSION|BITDO')}
    'selection-duplicate' {$keys=@('do|EXTENSION|bitdo','do|EXTENSION|bitdo')}
    'target-exists' {W (Join-Path (Target $f) 'sentinel') 'keep'}
    'target-case' {W (Join-Path ((Target $f) -replace 'bitdo$','BITDO') 'sentinel') 'keep'}
    'target-file' {W (Target $f) 'keep'}
    'inventory' {W (Join-Path (Split-Path (Get-ProjectManifestPath RetailGroup $f.worker) -Parent) $f.before.accepted_snapshot.artifacts[0].fingerprint_inventory_path) 'corrupt'}
    'new-source-collision' {$cat.projects[0].participants[0].target.extensions[0].source_path=$cat.projects[0].participants[0].target.main.source_path;Write-WorkerCatalog $cat $f.worker}
    'canonical-source' {$cat.projects[0].participants[0].target.extensions[0].source_path=Join-Path $f.worker 'RetailGroup/Participants/do/Target/Main';Write-WorkerCatalog $cat $f.worker}
    'inactive-duplicate' {$extra=$cat.projects[0].participants[0].target.extensions[0]|ConvertTo-Json|ConvertFrom-Json;$extra.active=$false;$cat.projects[0].participants[0].target.extensions+=,$extra;Write-WorkerCatalog $cat $f.worker}
    'reserved-id' {$cat.projects[0].participants[0].target.extensions[0].extension_id='NUL';$keys=@('do|EXTENSION|NUL');Write-WorkerCatalog $cat $f.worker}
   }
   $handles=@(LockMains $f)
   try{Reject {Prepare $f $keys} 'SOURCE_UPDATE_*' ($damage+' fails closed');Check ((Get-Sha256File (Get-ProjectManifestPath RetailGroup $f.worker)) -eq $f.sha) ($damage+' preserves manifest')}finally{foreach($h in $handles){$h.Dispose()}}
  }
  foreach($damage in @('generation','catalog','manifest','target-race','sealed-drift')){
   $f=Fixture $damage;$p=Prepare $f;Fill $p;$expected='SOURCE_UPDATE_*'
   switch($damage){
    'generation' {$p.generation_id='update-0000000000000000';$expected='SOURCE_UPDATE_GENERATION_MISMATCH'}
    'catalog' {$cat=Read-WorkerCatalog $f.worker;$cat.projects[0].display_name='stale';Write-WorkerCatalog $cat $f.worker;$expected='SOURCE_UPDATE_STALE_CATALOG'}
    'manifest' {Add-Content -LiteralPath (Get-ProjectManifestPath RetailGroup $f.worker) -Value ' ';$expected='SOURCE_UPDATE_STALE_BASE'}
    'target-race' {W (Join-Path (Target $f) 'sentinel') 'keep';$expected='SOURCE_UPDATE_NEW_TARGET_EXISTS'}
    'sealed-drift' {Reject {Accept $f $p 'AFTER_VALIDATION'} 'SOURCE_UPDATE_TEST_FAULT_AFTER_VALIDATION' 'sealed fixture';W (Join-Path $p.slots[0].slot_path 'Configuration.xml') '<Changed/>';$expected='SEALED_SOURCE_DRIFT:*'}
   }
   $sha=Get-Sha256File (Get-ProjectManifestPath RetailGroup $f.worker)
   Reject {Accept $f $p} $expected ($damage+' rejected before publication')
   Check ((Get-Sha256File (Get-ProjectManifestPath RetailGroup $f.worker)) -eq $sha) ($damage+' no manifest mutation')
  }
  # Real junctions, confined to the fixture; avoid recursive cleanup across an alias.
  foreach($alias in @('target-parent','source')){
   $f=Fixture $alias;$link=Join-Path $f.worker 'RetailGroup/Participants/do/Target/Extensions';$destination=Join-Path (Split-Path $f.worker -Parent) 'alias-destination';New-Item -ItemType Directory -Path $destination|Out-Null
   if($alias -eq 'source'){
    $link=Join-Path (Split-Path $f.worker -Parent) 'source-alias';$cat=Read-WorkerCatalog $f.worker;$cat.projects[0].participants[0].target.extensions[0].source_path=$link;Write-WorkerCatalog $cat $f.worker
   }elseif(Test-Path $link){Remove-Item -LiteralPath $link -Force}
   New-Item -ItemType Junction -Path $link -Target $destination|Out-Null
   try{Reject {Prepare $f} 'SOURCE_UPDATE_*ALIAS' ($alias+' junction rejected')}finally{[IO.Directory]::Delete($link)}
  }
  foreach($fault in @('AFTER_MARKER','AFTER_FIRST_PROMOTE','AFTER_ALL_PROMOTED','AFTER_MANIFEST_COMMIT','AFTER_MARKER_REMOVAL')){
   $f=Fixture $fault;$handles=@(LockMains $f)
   try{
    $p=Prepare $f;Fill $p;Reject {Accept $f $p $fault} ('SOURCE_UPDATE_TEST_FAULT_'+$fault) ($fault+' injected')
    if($fault -eq 'AFTER_FIRST_PROMOTE'){
     $markerPath=(Get-SourceUpdatePaths RetailGroup $f.worker).promotion_path
     $marker=Get-Content -LiteralPath $markerPath -Raw -Encoding UTF8|ConvertFrom-Json;$marker.items[0].phase='PENDING';Write-JsonAtomic $marker $markerPath
     Check ((Test-Path (Target $f)) -and -not(Test-Path $p.slots[0].slot_path)) 'physical rename before journal phase write is recoverable'
    }
    $committed=$fault -in @('AFTER_MANIFEST_COMMIT','AFTER_MARKER_REMOVAL')
    if(-not $committed){
     Reject {Accept $f $p} 'SOURCE_UPDATE_RECOVERY_REQUIRED' 'accept requires recovery first'
     Reject {Prepare $f} 'SOURCE_UPDATE_RECOVERY_REQUIRED' 'prepare requires recovery first'
     W (Join-Path $f.data 'runtime/active-admission.json') '{"project_id":"RetailGroup"}'
     Reject {Recover $f} 'SOURCE_UPDATE_RECOVERY_ADMISSION_ACTIVE' 'admission blocks rollback mutation'
     Remove-Item -LiteralPath (Join-Path $f.data 'runtime/active-admission.json')
    }
    $recovered=Recover $f
    Check ($recovered.status -eq 'RECOVERED') ($fault+' recovered')
    if($committed){Check ((Get-FastProjectState RetailGroup $f.worker).state -eq 'ACCEPTED' -and (Test-Path (Target $f))) ($fault+' finalizes new publication')}
    else{Check ((Get-Sha256File (Get-ProjectManifestPath RetailGroup $f.worker)) -eq $f.sha -and -not(Test-Path (Target $f)) -and (Get-FastProjectState RetailGroup $f.worker).state -eq 'CATALOG_DRIFT') ($fault+' exact old manifest and absent new target');$p=Prepare $f;Fill $p;Check ((Accept $f $p).status -eq 'READY') ($fault+' fresh ADD after rollback')}
    Unchanged $f
   }finally{foreach($h in $handles){$h.Dispose()}}
  }
  # Contradictory physical evidence is retained for explicit recovery, never overwritten.
  $f=Fixture 'contradictory';$p=Prepare $f;Fill $p;Reject {Accept $f $p 'AFTER_FIRST_PROMOTE'} 'SOURCE_UPDATE_TEST_FAULT_*' 'contradictory fixture'
  W (Join-Path $p.slots[0].slot_path 'sentinel') 'contradiction'
  Reject {Recover $f} 'SOURCE_UPDATE_RECOVERY_CONTRADICTORY_STATE' 'ADD target plus slot fails recovery closed'
  Check ((Test-Path (Target $f)) -and (Test-Path (Get-SourceUpdatePaths RetailGroup $f.worker).promotion_path) -and (Get-Sha256File (Get-ProjectManifestPath RetailGroup $f.worker)) -eq $f.sha) 'contradictory evidence and old manifest retained'
  Write-Host ('SELECTED_EXTENSION_ADD_PS51_PASS checks='+$script:Checks+' main_read_hash_copy=0 production_mutation=false')
 } $root $baseline
}finally{
 $expectedParent=[IO.Path]::GetFullPath($checkout).TrimEnd('\')+'\'
 if(-not ([IO.Path]::GetFullPath($root)).StartsWith($expectedParent,[StringComparison]::OrdinalIgnoreCase)){throw 'FIXTURE_CLEANUP_OUTSIDE_CHECKOUT'}
 Remove-Item -LiteralPath $root -Recurse -Force
}
