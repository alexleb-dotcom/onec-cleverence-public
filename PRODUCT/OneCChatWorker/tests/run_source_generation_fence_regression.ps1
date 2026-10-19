param(
 [Parameter(Mandatory)][string]$OldPackageRoot,
 [string]$PackageRoot,
 [Parameter(Mandatory)][string]$ReportPath
)
$ErrorActionPreference='Stop'
if([string]::IsNullOrWhiteSpace($PackageRoot)){$PackageRoot=Split-Path -Parent $PSScriptRoot}
Import-Module (Join-Path $PSScriptRoot 'TestScratch.psm1') -Force -DisableNameChecking
$scratch=New-OneCTestScratch -Purpose 'GenerationFence'
$root=$scratch.path
$script:FixtureShortcutRoot=Join-Path $root 'shortcut'
$script:Checks=@()
function Check($Ok,$Name){if(-not $Ok){throw ('ASSERTION_FAILED: '+$Name)};$script:Checks+=,$Name;Write-Host ('PASS '+$Name)}
function W($Path,$Text){New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Path)|Out-Null;[IO.File]::WriteAllText($Path,$Text,[Text.UTF8Encoding]::new($false))}
function Sha($Path){(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()}
function ProjectProof($Worker){
 $project=Join-Path $Worker 'RetailGroup'
 $paths=@((Join-Path $Worker 'projects.json'),(Join-Path $project 'Incoming'),(Join-Path $project 'ProjectManifest'),(Join-Path $project 'Participants/un/Target/Extensions'),(Join-Path $project 'Detached'))
 @($paths|Where-Object {Test-Path -LiteralPath $_}|ForEach-Object {Get-Item -LiteralPath $_;if(Test-Path -LiteralPath $_ -PathType Container){Get-ChildItem -LiteralPath $_ -Force -Recurse}}|Sort-Object FullName|ForEach-Object {
  [ordered]@{path=$_.FullName;directory=$_.PSIsContainer;hash=$(if(-not $_.PSIsContainer){Sha $_.FullName}else{$null});acl=(Get-Acl -LiteralPath $_.FullName).Sddl}
 })|ConvertTo-Json -Depth 8 -Compress
}
$osIntegrationMocks={
 function script:Test-IsAdministrator {$true}
 function script:Apply-ProjectAcl {param($ProjectRoot)}
 function script:Set-SourceUpdateTreeAcl {param($Path,$OperatorIdentity,[switch]$Writable)}
 function script:Protect-SourceUpdateMetadata {param($Path,$OperatorIdentity)}
 function script:Get-ControlCenterStartMenuShortcutPath {param($ShortcutRoot)Join-Path $script:FixtureShortcutRoot 'ControlCenter.lnk'}
 function script:Get-LocalUser {param($Name)[pscustomobject]@{Name=$Name}}
 function script:Ensure-PinnedDependencies {param($PackageRoot,$ProgramDataRoot,[switch]$NoInstall)
  [pscustomobject]@{node=[pscustomobject]@{version='fixture';sha256='fixture'};ripgrep=[pscustomobject]@{version='fixture';sha256='fixture'}}
 }
 function script:Set-WorkerOperatorAcl {param($WorkerRoot,$ProgramDataRoot,$OperatorIdentity)[pscustomobject]@{operator_identity=$OperatorIdentity;status='FIXTURE_OS_ACL'}}
}
# Exact accepted Core copied under a distinct module name in its baseline layout.
$distinct=Join-Path $OldPackageRoot 'core/Accepted.Core.psm1'
Copy-Item -LiteralPath (Join-Path $OldPackageRoot 'core/OneCChatWorker.Core.psm1') -Destination $distinct
$old=Import-Module $distinct -Force -DisableNameChecking -PassThru
$new=Import-Module (Join-Path $PackageRoot 'core/OneCChatWorker.Core.psm1') -Force -DisableNameChecking -PassThru
& $old $osIntegrationMocks
& $new $osIntegrationMocks
$shortcutPath=(Join-Path $root 'shortcut/ControlCenter.lnk').Replace("'","''")
$shortcutMock=[scriptblock]::Create(('function script:Get-ControlCenterStartMenuShortcutPath {{param($ShortcutRoot) ''{0}''}}' -f $shortcutPath))
& $old $shortcutMock
& $new $shortcutMock
function OldFixture($Name){
 & $old {
  param($Root,$Name,$OldPackage)
  function W($Path,$Text){New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Path)|Out-Null;[IO.File]::WriteAllText($Path,$Text,[Text.UTF8Encoding]::new($false))}
  $base=Join-Path $Root $Name;$worker=Join-Path $base 'worker';$data=Join-Path $base 'data';$external=Join-Path $base 'external'
  New-WorkerProject -ProjectId RetailGroup -DisplayName RetailGroup -WorkerRoot $worker|Out-Null
  foreach($part in @('do','un')){
   $source=Join-Path $external $part;W (Join-Path $source 'Configuration.xml') '<Configuration/>';W (Join-Path $source 'payload.bin') 'unchanged Main'
   Add-WorkerParticipant -ProjectId RetailGroup -ParticipantId $part -Platform ONEC -Role Main -WorkerRoot $worker|Out-Null
   Set-WorkerMain -ProjectId RetailGroup -ParticipantId $part -SourcePath $source -WorkerRoot $worker|Out-Null
  }
  $bit=Join-Path $external 'bit';W (Join-Path $bit 'Configuration.xml') '<Configuration name="old-bit"/>';W (Join-Path $bit 'ConfigDumpInfo.xml') '<ConfigDumpInfo/>'
  Add-WorkerExtension -ProjectId RetailGroup -ParticipantId un -ExtensionId bit -SourcePath $bit -WorkerRoot $worker|Out-Null
  $ap=Apply-WorkerProject -ProjectId RetailGroup -WorkerRoot $worker
  if($ap.status -ne 'READY'){throw 'BASELINE_FIXTURE_NOT_READY'}
  $null=Install-OneCChatWorker -PackageRoot $OldPackage -WorkerRoot $worker -ProgramDataRoot $data -OperatorIdentity fixture -SkipDependencies
  [pscustomobject]@{base=$base;worker=$worker;data=$data;external=$external;manifest=(Get-Content (Get-ProjectManifestPath RetailGroup $worker) -Raw -Encoding UTF8|ConvertFrom-Json)}
 } $root $Name $OldPackageRoot
}
function OldPrepare($F){
 & $old {param($F)Prepare-SourceUpdate -ProjectId RetailGroup -Selections @('un|EXTENSION|bit') -WorkerRoot $F.worker -ProgramDataRoot $F.data -OperatorIdentity fixture} $F
}
function NewAccept($F,$P){
 & $new {param($F,$P)Accept-SourceUpdate -ProjectId RetailGroup -ExpectedGenerationId $P.generation_id -ExpectedArtifactKey 'un|EXTENSION|bit' -WorkerRoot $F.worker -ProgramDataRoot $F.data -OperatorIdentity fixture} $F $P
}
function NewCancel($F,$P){
 & $new {param($F,$P)Cancel-SourceUpdate -ProjectId RetailGroup -ExpectedGenerationId $P.generation_id -ExpectedArtifactKey 'un|EXTENSION|bit' -WorkerRoot $F.worker -OperatorIdentity fixture} $F $P
}
function Fill($P){W (Join-Path $P.slots[0].slot_path 'Configuration.xml') '<Configuration name="new-bit"/>';W (Join-Path $P.slots[0].slot_path 'ConfigDumpInfo.xml') '<ConfigDumpInfo revision="2"/>'}
function Reject($F,$Action,$Expected,$Key,$Code){
 $before=ProjectProof $F.worker;$got=''
 try{
  & $new {param($F,$Action,$Expected,$Key)
   $args=@{ProjectId='RetailGroup';WorkerRoot=$F.worker;OperatorIdentity='fixture';ExpectedGenerationId=$Expected;ExpectedArtifactKey=$Key}
   if($Action -eq 'Accept'){$args.ProgramDataRoot=$F.data;Accept-SourceUpdate @args|Out-Null}else{Cancel-SourceUpdate @args|Out-Null}
  } $F $Action $Expected $Key
 }catch{$got=$_.Exception.Message}
 Check ($got -eq $Code) ($Action+' '+$Code)
 Check ((ProjectProof $F.worker) -ceq $before) ($Action+' '+$Code+' no Source/Incoming/manifest/ACL change')
}
$handles=@()
try{
 Check ((Sha (Join-Path $OldPackageRoot 'core/OneCChatWorker.Core.psm1')) -eq '9337988bd7add8876aac2f5c3f06ca77bad03aa44399045c1532ffb77cfe17ab') 'accepted old Core exact SHA'
 $f=OldFixture 'compatibility'
 foreach($part in @('do','un')){
  foreach($dir in @((Join-Path $f.worker ('RetailGroup/Participants/'+$part+'/Target/Main')),(Join-Path $f.external $part))){
   foreach($file in Get-ChildItem -LiteralPath $dir -File -Recurse){$handles+=,[IO.File]::Open($file.FullName,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::None)}
  }
 }
 $p=OldPrepare $f;Fill $p;$proof=ProjectProof $f.worker
 $update=& $new {param($F,$P)Install-OneCChatWorker -PackageRoot $P -WorkerRoot $F.worker -ProgramDataRoot $F.data -OperatorIdentity fixture -SkipDependencies} $f $PackageRoot
 Check ($update.installed_integrity.status -eq 'PASS') 'isolated product update actual component integrity'
 Check ((ProjectProof $f.worker) -ceq $proof) 'product update preserves filled Incoming and accepted Source'
 $read=Read-SourceUpdateState -ProjectId RetailGroup -WorkerRoot $f.worker
 Check ($read.generation_id -ceq $p.generation_id -and $read.state -eq 'PREPARED_WRITABLE') 'old prepared generation rehydrated without PREPARE or recopy'
 $r=NewAccept $f $p
 Check ($r.status -eq 'READY' -and $r.generation_id -ceq $p.generation_id) 'new Core accepts exact old filled generation'
 Check ($r.main_content_bytes_read -eq 0 -and $r.main_hashed_bytes -eq 0 -and $r.main_copied_bytes -eq 0) 'both Main external/canonical payload locks held: zero content IO'
 $after=Get-Content (Get-ProjectManifestPath RetailGroup $f.worker) -Raw -Encoding UTF8|ConvertFrom-Json
 foreach($part in @('do','un')){
  $a=@($f.manifest.accepted_snapshot.artifacts|Where-Object {$_.participant_id -eq $part -and $_.artifact_type -eq 'MAIN'})[0]
  $b=@($after.accepted_snapshot.artifacts|Where-Object {$_.participant_id -eq $part -and $_.artifact_type -eq 'MAIN'})[0]
  Check (($a|ConvertTo-Json -Depth 8 -Compress) -ceq ($b|ConvertTo-Json -Depth 8 -Compress)) ($part+' exact Main accepted identity preserved')
 }
 $detached=@(Get-ChildItem -LiteralPath (Join-Path $f.worker 'RetailGroup/Detached') -Recurse -Filter Configuration.xml)
 Check ($detached.Count -eq 1 -and (Sha $detached[0].FullName) -eq $f.manifest.participants[1].target.extensions[0].configuration_xml_sha256) 'previous bit preserved in Detached'
 $p=OldPrepare $f
 $target=Join-Path $f.worker 'RetailGroup/Participants/un/Target/Extensions/bit'
 Get-ChildItem -LiteralPath $target -Force|ForEach-Object {Copy-Item -LiteralPath $_.FullName -Destination $p.slots[0].slot_path -Recurse}
 $manifestSha=Sha (Get-ProjectManifestPath RetailGroup $f.worker);$r=NewAccept $f $p
 Check ($r.status -eq 'NO_CHANGE' -and (Sha (Get-ProjectManifestPath RetailGroup $f.worker)) -eq $manifestSha -and $r.source_snapshot_id -eq $after.accepted_snapshot.source_snapshot_id) 'old PREPARE filled generation NO_CHANGE preserves exact manifest/snapshot'
 foreach($h in $handles){$h.Dispose()};$handles=@()
 $f=OldFixture 'stale';$g1=OldPrepare $f;Fill $g1;$null=NewCancel $f $g1
 $g2=OldPrepare $f;Fill $g2
 foreach($action in @('Accept','Cancel')){
  Reject $f $action $g1.generation_id 'un|EXTENSION|bit' 'SOURCE_UPDATE_GENERATION_MISMATCH'
  Reject $f $action $g2.generation_id 'do|EXTENSION|bit' 'SOURCE_UPDATE_ARTIFACT_MISMATCH'
  Reject $f $action $g2.generation_id 'un|extension|bit' 'SOURCE_UPDATE_EXPECTED_IDENTITY_INVALID'
  Reject $f $action '' 'un|EXTENSION|bit' 'SOURCE_UPDATE_EXPECTED_IDENTITY_REQUIRED'
  Reject $f $action $g2.generation_id @() 'SOURCE_UPDATE_EXPECTED_IDENTITY_REQUIRED'
  Reject $f $action $g2.generation_id @('un|EXTENSION|bit','un|EXTENSION|bit') 'SOURCE_UPDATE_EXPECTED_IDENTITY_INVALID'
  Reject $f $action $g2.generation_id @('un|EXTENSION|bit','do|MAIN|main') 'SOURCE_UPDATE_ARTIFACT_MISMATCH'
 }
 # A real separate Windows process owns the same project mutex during the check.
 $child=Join-Path $root 'hold-source-update.ps1';$signal=Join-Path $root 'held.txt';$release=Join-Path $root 'release.txt'
 W $child @'
param($PackageRoot,$WorkerRoot,$Signal,$Release)
$ErrorActionPreference='Stop'
Import-Module (Join-Path $PackageRoot 'core/OneCChatWorker.Core.psm1') -Force -DisableNameChecking
$m=Enter-SourceUpdateMutation -ProjectId RetailGroup -WorkerRoot $WorkerRoot
try{
 [IO.File]::WriteAllText($Signal,'held')
 for($i=0;$i -lt 150 -and -not(Test-Path -LiteralPath $Release);$i++){Start-Sleep -Milliseconds 100}
}finally{$m.ReleaseMutex();$m.Dispose()}
'@
 $childProcess=Start-Process powershell.exe -WindowStyle Hidden -PassThru -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',$child,'-PackageRoot',$PackageRoot,'-WorkerRoot',$f.worker,'-Signal',$signal,'-Release',$release)
 try{
  for($i=0;$i -lt 50 -and -not(Test-Path -LiteralPath $signal);$i++){Start-Sleep -Milliseconds 100}
  Check (Test-Path -LiteralPath $signal) 'separate Windows process holds exact project mutation mutex'
  Reject $f 'Accept' $g2.generation_id 'un|EXTENSION|bit' 'SOURCE_UPDATE_BUSY'
  Reject $f 'Cancel' $g2.generation_id 'un|EXTENSION|bit' 'SOURCE_UPDATE_BUSY'
  foreach($fn in @('Prepare-SourceUpdate','Recover-SourceUpdatePromotion')){
   $before=ProjectProof $f.worker;$got=''
   try{
    & $new {param($F,$Fn)
     $a=@{ProjectId='RetailGroup';WorkerRoot=$F.worker;ProgramDataRoot=$F.data;OperatorIdentity='fixture'}
     if($Fn -eq 'Prepare-SourceUpdate'){$a.Selections=@('un|EXTENSION|bit')}
     & $Fn @a|Out-Null
    } $f $fn
   }catch{$got=$_.Exception.Message}
   Check ($got -eq 'SOURCE_UPDATE_BUSY' -and (ProjectProof $f.worker) -ceq $before) ($fn+' shares lock and cannot replace generation during fenced mutation')
  }
 }finally{
  W $release 'release'
  if(-not $childProcess.WaitForExit(5000)){$childProcess.Kill();throw 'FIXTURE_LOCK_PROCESS_TIMEOUT'}
  $childProcess.Dispose()
 }
 $r=NewCancel $f $g2;Check ($r.status -eq 'CANCELLED' -and $r.generation_id -ceq $g2.generation_id) 'matching cancel removes only exact unaccepted G2'
 $f=OldFixture 'active';$p=OldPrepare $f;Fill $p;$manifestSha=Sha (Get-ProjectManifestPath RetailGroup $f.worker)
 Write-JsonAtomic ([ordered]@{project_id='RetailGroup';task_id='fixture-active'}) (Join-Path $f.data 'runtime/active-admission.json')
 $r=NewAccept $f $p
 Check ($r.status -eq 'SEALED_VALIDATED' -and $r.reason -eq 'PROJECT_ADMISSION_ACTIVE' -and -not $r.publication_performed) 'active task blocks publication'
 Check ((Sha (Get-ProjectManifestPath RetailGroup $f.worker)) -eq $manifestSha) 'active task preserves previous accepted manifest'
 Remove-Item -LiteralPath (Join-Path $f.data 'runtime/active-admission.json')
 Check ((NewAccept $f $p).status -eq 'READY') 'same sealed old generation resumes after fixture admission ends'
 $report=[ordered]@{result='PASS';checks=$script:Checks.Count;cases=$script:Checks;old_core_sha256=(Sha (Join-Path $OldPackageRoot 'core/OneCChatWorker.Core.psm1'));new_core_sha256=(Sha (Join-Path $PackageRoot 'core/OneCChatWorker.Core.psm1'));production_access=$false;os_integration='admin/account/ACL/dependency-install mocked; actual Node/hash/promotion/manifest/recovery/package integrity';main_payload_locks=8}
 W $ReportPath ($report|ConvertTo-Json -Depth 8)
 Write-Host ('SOURCE_GENERATION_FENCE_PASS checks='+$script:Checks.Count)
}finally{
 foreach($h in $handles){$h.Dispose()}
 Remove-OneCTestScratch -Path $scratch.path -RunId $scratch.run_id -Base $scratch.base|Out-Null
}
