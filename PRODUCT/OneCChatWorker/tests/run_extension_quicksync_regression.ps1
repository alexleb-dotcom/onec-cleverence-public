#requires -Version 5.1
param([string]$PackageRoot=(Split-Path -Parent $PSScriptRoot))
$ErrorActionPreference='Stop'
if($PSVersionTable.PSVersion.Major -ne 5){throw 'Q113_QUICK_SYNC_PS51_REQUIRED'}
$checkout=Split-Path -Parent (Split-Path -Parent $PackageRoot)
$root=Join-Path $checkout ('.q113-quick-'+[guid]::NewGuid().ToString('N').Substring(0,8))
New-Item -ItemType Directory -Path $root|Out-Null
$module=Import-Module (Join-Path $PackageRoot 'core/OneCChatWorker.Core.psm1') -Force -DisableNameChecking -PassThru
try {
 & $module {
  param($Root)
  # Stub only UAC/ACL account integration. Native accepted snapshot, hashes,
  # selected Source generation/promotion/rollback and Node remain real.
  function script:Test-IsAdministrator {$true}
  function script:Apply-ProjectAcl {param($ProjectRoot)}
  function script:Set-SourceUpdateTreeAcl {param($Path,$OperatorIdentity,[switch]$Writable)}
  function script:Protect-SourceUpdateMetadata {param($Path,$OperatorIdentity)}
  $script:Checks=0
  function Check($Test,$Name){if(-not $Test){throw ('Q113_QUICK_SYNC_ASSERTION_FAILED: '+$Name)};$script:Checks++;Write-Host ('PASS '+$Name)}
  function W($Path,$Content){New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Path)|Out-Null;[IO.File]::WriteAllText($Path,$Content,[Text.UTF8Encoding]::new($false))}
  function ReadManifest($Worker){Get-Content -LiteralPath (Get-ProjectManifestPath RetailGroup $Worker) -Raw -Encoding UTF8|ConvertFrom-Json}
  function Sync($Fixture,$Part='do',$Id='bitdo'){Sync-ExistingWorkerExtension -ProjectId RetailGroup -ParticipantId $Part -ExtensionId $Id -WorkerRoot $Fixture.worker -ProgramDataRoot $Fixture.data -OperatorIdentity fixture}
  function Fixture($Name){
   $worker=Join-Path $Root ($Name+'\worker');$data=Join-Path $Root ($Name+'\data');$external=Join-Path $Root ($Name+'\external')
   New-WorkerProject -ProjectId RetailGroup -DisplayName RetailGroup -WorkerRoot $worker|Out-Null
   foreach($part in @('do','un')){
    $main=Join-Path $external $part;W (Join-Path $main 'Configuration.xml') '<Configuration/>';W (Join-Path $main 'sealed-main.bin') 'keep both Main untouched'
    Add-WorkerParticipant -ProjectId RetailGroup -ParticipantId $part -Platform ONEC -Role Main -WorkerRoot $worker|Out-Null
    Set-WorkerMain -ProjectId RetailGroup -ParticipantId $part -SourcePath $main -WorkerRoot $worker|Out-Null
   }
   foreach($tuple in @(@('do','bitdo'),@('un','bit'))){
    $source=Join-Path $external $tuple[1]
    W (Join-Path $source 'Configuration.xml') ('<Configuration name="'+$tuple[1]+'"/>')
    W (Join-Path $source 'ConfigDumpInfo.xml') '<ConfigDumpInfo/>'
    W (Join-Path $source 'CommonModules\Test\Ext\Module.bsl') 'Процедура Тест() Экспорт'
    Add-WorkerExtension -ProjectId RetailGroup -ParticipantId $tuple[0] -ExtensionId $tuple[1] -SourcePath $source -WorkerRoot $worker|Out-Null
   }
   Check ((Apply-WorkerProject -ProjectId RetailGroup -WorkerRoot $worker).status -eq 'READY') ($Name+' accepted fixture')
   [pscustomobject]@{worker=$worker;data=$data;external=$external}
  }
  function Rejected($Code,[scriptblock]$Action){
   $errorValue=$null
   try{& $Action|Out-Null}catch{$errorValue=[string]$_.Exception.Message}
   Check ($errorValue -like ($Code+'*')) ('blocked '+$Code)
  }
  $f=Fixture 'updated'
  $before=ReadManifest $f.worker
  $manifestPath=Get-ProjectManifestPath RetailGroup $f.worker
  $originalSha=Get-Sha256File $manifestPath
  $handles=New-Object 'System.Collections.Generic.List[object]'
  try{
   foreach($part in @('do','un')){
    foreach($base in @((Join-Path $f.worker ('RetailGroup\Participants\'+$part+'\Target\Main')),(Join-Path $f.external $part))){
     foreach($file in @(Get-ChildItem -LiteralPath $base -File -Recurse)){
      $handles.Add([IO.File]::Open($file.FullName,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::None))
     }
    }
   }
   $same=Sync $f
   Check ($same.status -eq 'NO_CHANGE' -and $same.generation_id -eq $null -and (Get-Sha256File $manifestPath) -eq $originalSha) 'unchanged bitdo returns without staging'
   Check ((Get-SourceUpdateSummary RetailGroup $f.worker).status -eq 'NONE') 'no Incoming for unchanged extension'
   $source=Join-Path $f.external 'bitdo'
   W (Join-Path $source 'Configuration.xml') '<Configuration name="bitdo" revision="2"/>'
   W (Join-Path $source 'CommonModules\Test\Ext\NewModule.bsl') 'Функция Новая() Экспорт'
   New-Item -ItemType Directory -Force -Path (Join-Path $source 'EmptyFolder')|Out-Null
   $changed=Sync $f
   Check ($changed.status -eq 'READY' -and $changed.copied_content_bytes -eq 0 -and $changed.source_snapshot_id -ne $before.accepted_snapshot.source_snapshot_id) 'changed extension publishes via selected zero-copy'
   Check ($changed.main_content_bytes_read -eq 0 -and $changed.main_hashed_bytes -eq 0 -and $changed.main_copied_bytes -eq 0) 'both locked Main content untouched'
   Check ((Get-FastProjectState RetailGroup $f.worker).state -eq 'ACCEPTED' -and (Get-SourceUpdateSummary RetailGroup $f.worker).status -eq 'NONE') 'new generation accepted and Incoming consumed'
   $after=ReadManifest $f.worker
   foreach($part in @('do','un')){
    $oldMain=@($before.accepted_snapshot.artifacts|Where-Object {$_.participant_id -eq $part -and $_.artifact_type -eq 'MAIN'})[0]
    $newMain=@($after.accepted_snapshot.artifacts|Where-Object {$_.participant_id -eq $part -and $_.artifact_type -eq 'MAIN'})[0]
    Check (($oldMain|ConvertTo-Json -Compress) -ceq ($newMain|ConvertTo-Json -Compress)) ($part+' unchanged Main fingerprint row')
   }
   $oldBit=@($before.accepted_snapshot.artifacts|Where-Object {$_.artifact_id -eq 'bit'})[0]
   $newBit=@($after.accepted_snapshot.artifacts|Where-Object {$_.artifact_id -eq 'bit'})[0]
   Check (($oldBit|ConvertTo-Json -Compress) -ceq ($newBit|ConvertTo-Json -Compress)) 'un/bit unchanged'
   $target=Join-Path $f.worker 'RetailGroup\Participants\do\Target\Extensions\bitdo'
   Check ((Get-Sha256File (Join-Path $source 'Configuration.xml')) -eq (Get-Sha256File (Join-Path $target 'Configuration.xml'))) 'bitdo canonical SHA matches source'
   Check ((Test-Path -LiteralPath (Join-Path $target 'EmptyFolder') -PathType Container)) 'empty directory transferred'
   $second=Sync $f
   Check ($second.status -eq 'NO_CHANGE' -and $second.source_snapshot_id -eq $changed.source_snapshot_id) 'idempotent repeat does not remint snapshot'
  }finally{foreach($h in $handles){$h.Dispose()}}
  $f=Fixture 'admission'
  $adm=Join-Path $f.data 'runtime\active-admission.json'
  W $adm '{"project_id":"RetailGroup"}'
  $sha=Get-Sha256File (Get-ProjectManifestPath RetailGroup $f.worker)
  Rejected 'QUICK_SYNC_ACTIVE_ADMISSION_STOP_REQUIRED' {Sync $f}
  Check ((Get-SourceUpdateSummary RetailGroup $f.worker).status -eq 'NONE' -and (Get-Sha256File (Get-ProjectManifestPath RetailGroup $f.worker)) -eq $sha) 'live admission failure no slot nor manifest write'
  Remove-Item -LiteralPath $adm -Force
  $f=Fixture 'new'
  $newExt=Join-Path $f.external 'new-added';W (Join-Path $newExt 'Configuration.xml') '<Configuration/>'
  Add-WorkerExtension -ProjectId RetailGroup -ParticipantId do -ExtensionId newadded -SourcePath $newExt -WorkerRoot $f.worker|Out-Null
  Rejected 'QUICK_SYNC_NEW_EXTENSION_USE_SELECTED_ADD' {Sync $f do newadded}
  Check ((Get-SourceUpdateSummary RetailGroup $f.worker).status -eq 'NONE') 'new extension cannot create quick sync slot'
  $f=Fixture 'pending'
  $prep=Prepare-SourceUpdate -ProjectId RetailGroup -Selections @('do|EXTENSION|bitdo') -WorkerRoot $f.worker -ProgramDataRoot $f.data -OperatorIdentity fixture
  Rejected 'QUICK_SYNC_EXISTING_INCOMING_RECOVER_FIRST' {Sync $f}
  Check ((Get-SourceUpdateSummary RetailGroup $f.worker).generation_id -eq $prep.generation_id) 'preserves occupied exact generation'
  Cancel-SourceUpdate -ProjectId RetailGroup -ExpectedGenerationId $prep.generation_id -ExpectedArtifactKey @('do|EXTENSION|bitdo') -WorkerRoot $f.worker -OperatorIdentity fixture|Out-Null
  Write-Host ('Q113_EXTENSION_QUICK_SYNC_PASS checks='+$script:Checks+' main_content_read_hash_copy=0 production_mutation=false')
 } $root
}finally{
 if(-not ([IO.Path]::GetFullPath($root)).StartsWith(([IO.Path]::GetFullPath($checkout)).TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'Q113_QUICK_SYNC_FIXTURE_OUTSIDE_CHECKOUT'}
 Remove-Item -LiteralPath $root -Recurse -Force
}
