param(
 [ValidateSet('RUN','SETUP')][string]$Mode='RUN',
 [string]$PackageRoot=(Split-Path -Parent $PSScriptRoot),
 [string]$WorkerRoot,
 [string]$ProgramDataRoot,
 [string]$ScratchRoot,
 [string]$ScratchRunId,
 [string]$ScratchBase,
 [string]$OperatorIdentity,
 [string]$ReaderName='OneCSourceReader',
 [string]$ReportPath
)
$ErrorActionPreference='Stop'
$PackageRoot=[IO.Path]::GetFullPath($PackageRoot)
$testScratchModule=Join-Path $PSScriptRoot 'TestScratch.psm1'
Import-Module $testScratchModule -Force -DisableNameChecking
$launcher=Join-Path $PackageRoot 'OneCChatWorker.ps1'
$packageCore=Join-Path $PackageRoot 'core\OneCChatWorker.Core.psm1'
$packageLock=Join-Path $PackageRoot 'runtime.lock.json'
if([string]::IsNullOrWhiteSpace($OperatorIdentity)){$OperatorIdentity=[Security.Principal.WindowsIdentity]::GetCurrent().Name}
$autoScratch=$null
if($Mode -eq 'RUN'){
 $id=[Security.Principal.WindowsIdentity]::GetCurrent()
 if((New-Object Security.Principal.WindowsPrincipal($id)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'RUN_PHASE_EXPECTS_NON_ADMIN'}
 if([string]::IsNullOrWhiteSpace($WorkerRoot) -and [string]::IsNullOrWhiteSpace($ProgramDataRoot)){
  $autoScratch=New-OneCTestScratch -Purpose 'UpdateBootstrap'
  $ScratchRoot=$autoScratch.path;$ScratchRunId=$autoScratch.run_id;$ScratchBase=$autoScratch.base
  $WorkerRoot=Join-Path $ScratchRoot 'worker';$ProgramDataRoot=Join-Path $ScratchRoot 'programdata'
  if([string]::IsNullOrWhiteSpace($ReportPath)){$ReportPath=Join-Path $ScratchRoot 'report.json'}
 }elseif([string]::IsNullOrWhiteSpace($WorkerRoot) -or [string]::IsNullOrWhiteSpace($ProgramDataRoot)){
  throw 'UPDATE_REGRESSION_ROOTS_MUST_BE_PAIRED'
 }elseif([string]::IsNullOrWhiteSpace($ScratchRoot) -or [string]::IsNullOrWhiteSpace($ScratchRunId) -or [string]::IsNullOrWhiteSpace($ScratchBase)){
  throw 'UPDATE_REGRESSION_CUSTOM_ROOTS_REQUIRE_SCRATCH_OWNER'
 }
 if([string]::IsNullOrWhiteSpace($ReportPath)){throw 'UPDATE_REGRESSION_REPORT_PATH_REQUIRED'}
}else{
 if([string]::IsNullOrWhiteSpace($WorkerRoot) -or [string]::IsNullOrWhiteSpace($ProgramDataRoot) -or [string]::IsNullOrWhiteSpace($ScratchRoot) -or [string]::IsNullOrWhiteSpace($ScratchRunId) -or [string]::IsNullOrWhiteSpace($ScratchBase) -or [string]::IsNullOrWhiteSpace($ReportPath)){throw 'UPDATE_REGRESSION_SCRATCH_BINDING_REQUIRED'}
 $c=Get-OneCTestScratchClassification -Path $ScratchRoot -Base $ScratchBase
 if(-not $c.owned -or $c.run_id -ne $ScratchRunId){throw 'UPDATE_REGRESSION_SCRATCH_BINDING_INVALID'}
}

$oldLocalAppData=$env:LOCALAPPDATA
$env:LOCALAPPDATA=Join-Path $ScratchRoot 'localappdata'
New-Item -ItemType Directory -Force -Path $env:LOCALAPPDATA|Out-Null

function Is-Admin {
 $id=[Security.Principal.WindowsIdentity]::GetCurrent()
 (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}
function Sha([string]$Path){(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()}
function Write-Utf8NoBom([string]$Path,[string]$Value){
 New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Path)|Out-Null
 [IO.File]::WriteAllText($Path,$Value,[Text.UTF8Encoding]::new($false))
}
function Remove-TestRoot([string]$Path){
 if(-not(Test-Path -LiteralPath $Path)){return}
 try{Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop}
 catch{
  if(-not(Is-Admin)){throw}
  & takeown.exe /F $Path /R /D Y | Out-Null
  & icacls.exe $Path /grant '*S-1-5-32-544:F' /T /C | Out-Null
  & icacls.exe $Path /grant '*S-1-5-18:F' /T /C | Out-Null
  Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
 }
}
function Invoke-PackageInstall {
 & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $launcher -Mode INSTALL -WorkerRoot $WorkerRoot -ProgramDataRoot $ProgramDataRoot -ReaderName $ReaderName -OperatorIdentity $OperatorIdentity -SkipDependencies
 if($LASTEXITCODE -ne 0){throw "PACKAGE_INSTALL_FAILED: exit=$LASTEXITCODE"}
}
function Assert-Equal([string]$Name,$Actual,$Expected){
 if($Actual -ne $Expected){throw "ASSERTION_FAILED: $Name actual=$Actual expected=$Expected"}
}
function Get-AccountSid([string]$Account){
 (New-Object Security.Principal.NTAccount($Account)).Translate([Security.Principal.SecurityIdentifier]).Value
}
function Get-AllowRights([string]$Path,[string]$Sid){
 $acl=Get-Acl -LiteralPath $Path
 $rights=[int64]0
 foreach($rule in @($acl.Access)){
  try{$ruleSid=$rule.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value}catch{continue}
  if($ruleSid -eq $Sid -and $rule.AccessControlType -eq 'Allow'){$rights=$rights -bor [int64]$rule.FileSystemRights}
 }
 $rights
}
function Assert-HasModify([string]$Name,[string]$Path,[string]$Sid){
 $rights=Get-AllowRights $Path $Sid
 $need=[int64][Security.AccessControl.FileSystemRights]::Modify
 if(($rights -band $need) -ne $need){throw "ASSERTION_FAILED: $Name operator Modify missing path=$Path rights=$rights"}
}
function Assert-NoWrite([string]$Name,[string]$Path,[string]$Sid){
 $rights=Get-AllowRights $Path $Sid
 $mask=[int64](
  [Security.AccessControl.FileSystemRights]::WriteData -bor
  [Security.AccessControl.FileSystemRights]::AppendData -bor
  [Security.AccessControl.FileSystemRights]::CreateFiles -bor
  [Security.AccessControl.FileSystemRights]::CreateDirectories -bor
  [Security.AccessControl.FileSystemRights]::Delete -bor
  [Security.AccessControl.FileSystemRights]::DeleteSubdirectoriesAndFiles -bor
  [Security.AccessControl.FileSystemRights]::ChangePermissions -bor
  [Security.AccessControl.FileSystemRights]::TakeOwnership
 )
 if(($rights -band $mask) -ne 0){throw "ASSERTION_FAILED: $Name unexpected operator write path=$Path rights=$rights"}
}
function New-StaleInstalledCore {
 $source=[IO.File]::ReadAllText($packageCore,[Text.Encoding]::UTF8)
 $old='param([Parameter(Mandatory)][string]$PackageRoot,[string]$WorkerRoot=$script:DefaultWorkerRoot,[string]$ProgramDataRoot=$script:DefaultProgramDataRoot,[string]$OperatorIdentity,[switch]$SkipDependencies)'
 $new='param([Parameter(Mandatory)][string]$PackageRoot,[string]$WorkerRoot=$script:DefaultWorkerRoot,[string]$ProgramDataRoot=$script:DefaultProgramDataRoot,[switch]$SkipDependencies)'
 if(-not $source.Contains($old)){throw 'STALE_CORE_SIGNATURE_SOURCE_NOT_FOUND'}
 $stale=$source.Replace($old,$new)
 $dest=Join-Path $ProgramDataRoot 'product\OneCChatWorker.Core.psm1'
 [IO.File]::WriteAllText($dest,$stale,[Text.UTF8Encoding]::new($true))
 $cmd=Get-Command Install-OneCChatWorker -ErrorAction SilentlyContinue
 Remove-Module OneCChatWorker.Core -Force -ErrorAction SilentlyContinue
 Import-Module $dest -Force -DisableNameChecking
 $cmd=Get-Command Install-OneCChatWorker -ErrorAction Stop
 if($cmd.Parameters.ContainsKey('OperatorIdentity')){throw 'STALE_CORE_RECONSTRUCTION_FAILED'}
 Remove-Module OneCChatWorker.Core -Force -ErrorAction SilentlyContinue
}

if($Mode -eq 'RUN'){
 try{
  if(-not(Test-Path -LiteralPath $launcher -PathType Leaf)){throw "PACKAGE_LAUNCHER_MISSING: $launcher"}
  $args=@(
   '-NoProfile','-ExecutionPolicy','Bypass','-File',$PSCommandPath,
   '-Mode','SETUP','-PackageRoot',$PackageRoot,
   '-WorkerRoot',$WorkerRoot,'-ProgramDataRoot',$ProgramDataRoot,
   '-ScratchRoot',$ScratchRoot,'-ScratchRunId',$ScratchRunId,'-ScratchBase',$ScratchBase,
   '-OperatorIdentity',$OperatorIdentity,'-ReaderName',$ReaderName,
   '-ReportPath',$ReportPath
  )
  $p=Start-Process powershell.exe -Verb RunAs -ArgumentList $args -Wait -PassThru
  if($p.ExitCode -ne 0){throw "UPDATE_BOOTSTRAP_SETUP_FAILED: $($p.ExitCode)"}
  if(-not(Test-Path -LiteralPath $ReportPath -PathType Leaf)){throw 'UPDATE_BOOTSTRAP_REPORT_MISSING'}
  $report=Get-Content -LiteralPath $ReportPath -Raw -Encoding UTF8|ConvertFrom-Json
  if($report.result -ne 'PASS'){throw "UPDATE_BOOTSTRAP_REGRESSION_FAILED: $($report|ConvertTo-Json -Compress)"}
  Write-Host ("UPDATE_BOOTSTRAP_REGRESSION_PASS checks={0} stale_core_sha256={1} package_core_sha256={2}" -f $report.checks,$report.stale_core_sha256,$report.package_core_sha256)
 }finally{
  $env:LOCALAPPDATA=$oldLocalAppData
  if($null -ne $autoScratch -and (Test-Path -LiteralPath $ScratchRoot)){
   Remove-OneCTestScratch -Path $ScratchRoot -RunId $ScratchRunId -Base $ScratchBase|Out-Null
  }
 }
 exit 0
}

if(-not(Is-Admin)){throw 'SETUP_PHASE_REQUIRES_ADMIN'}
$result=[ordered]@{result='FAIL';checks=0}
try{
 Remove-TestRoot $WorkerRoot
 Remove-TestRoot $ProgramDataRoot
 Remove-Item -LiteralPath $ReportPath -Force -ErrorAction SilentlyContinue

 if(-not(Get-LocalUser -Name $ReaderName -ErrorAction SilentlyContinue)){throw "READER_ACCOUNT_REQUIRED_FOR_NONINTERACTIVE_REGRESSION: $ReaderName"}

 # Establish an accepted installed baseline on isolated roots.
 Invoke-PackageInstall
 $result.checks++

 $catalog=Join-Path $WorkerRoot 'projects.json'
 $projectRoot=Join-Path $WorkerRoot 'PreserveProject'
 $sourceSentinel=Join-Path $projectRoot 'Source\sentinel.txt'
 $outputSentinel=Join-Path $projectRoot 'Output\sentinel.txt'
 $secret=Join-Path $ProgramDataRoot 'secrets\helper-secret.txt'
 Write-Utf8NoBom $sourceSentinel 'preserve-source-v1'
 Write-Utf8NoBom $outputSentinel 'preserve-output-v1'
 Write-Utf8NoBom $secret 'preserve-secret-v1'

 Import-Module (Join-Path $ProgramDataRoot 'product\OneCChatWorker.Core.psm1') -Force -DisableNameChecking
 Set-WorkerReaderIdentity -ReaderName $ReaderName|Out-Null
 $identity=Resolve-WorkerOperatorIdentity $OperatorIdentity
 Protect-WorkerRuntimeFile -Path $secret -Identity $identity -Secret
 Remove-Module OneCChatWorker.Core -Force -ErrorAction SilentlyContinue

 $preserveBefore=[ordered]@{
  catalog=Sha $catalog
  source=Sha $sourceSentinel
  output=Sha $outputSentinel
  secret=Sha $secret
 }
 $result.checks+=4

 # Reconstruct the proven pre-#74 version-skew discriminator.
 New-StaleInstalledCore
 $staleCore=Join-Path $ProgramDataRoot 'product\OneCChatWorker.Core.psm1'
 $staleHash=Sha $staleCore
 Write-Utf8NoBom (Join-Path $WorkerRoot 'OneCChatWorker.ps1') 'STALE_PRE_74_LAUNCHER'
 Write-Utf8NoBom (Join-Path $ProgramDataRoot 'product\runtime.lock.json') '{"schema_version":1,"product_version":"stale-pre-74"}'
 $result.checks++

 # If INSTALL still prefers installed core, this call fails on unknown -OperatorIdentity.
 Invoke-PackageInstall
 $result.checks++

 $expectedLauncher=Sha $launcher
 $expectedCore=Sha $packageCore
 $expectedLock=Sha $packageLock
 Assert-Equal 'installed_launcher_refreshed' (Sha (Join-Path $WorkerRoot 'OneCChatWorker.ps1')) $expectedLauncher
 Assert-Equal 'installed_core_refreshed' (Sha (Join-Path $ProgramDataRoot 'product\OneCChatWorker.Core.psm1')) $expectedCore
 Assert-Equal 'installed_runtime_lock_refreshed' (Sha (Join-Path $ProgramDataRoot 'product\runtime.lock.json')) $expectedLock
 $result.checks+=3

 Assert-Equal 'catalog_preserved' (Sha $catalog) $preserveBefore.catalog
 Assert-Equal 'source_preserved' (Sha $sourceSentinel) $preserveBefore.source
 Assert-Equal 'output_preserved' (Sha $outputSentinel) $preserveBefore.output
 Assert-Equal 'secret_preserved' (Sha $secret) $preserveBefore.secret
 $result.checks+=4

 $operatorSid=Get-AccountSid $OperatorIdentity
 Assert-HasModify 'worker_root_acl' $WorkerRoot $operatorSid
 Assert-HasModify 'operations_acl' (Join-Path $ProgramDataRoot 'operations') $operatorSid
 Assert-HasModify 'provider_acl' (Join-Path $ProgramDataRoot 'provider') $operatorSid
 Assert-HasModify 'runtime_acl' (Join-Path $ProgramDataRoot 'runtime') $operatorSid
 Assert-NoWrite 'product_acl' (Join-Path $ProgramDataRoot 'product') $operatorSid
 Assert-NoWrite 'helper_acl' (Join-Path $ProgramDataRoot 'helper') $operatorSid
 Assert-NoWrite 'secret_acl' $secret $operatorSid
 $result.checks+=7

 # Idempotent repeat: no uninstall/root wipe and preserved bytes remain exact.
 Invoke-PackageInstall
 Assert-Equal 'idempotent_launcher' (Sha (Join-Path $WorkerRoot 'OneCChatWorker.ps1')) $expectedLauncher
 Assert-Equal 'idempotent_core' (Sha (Join-Path $ProgramDataRoot 'product\OneCChatWorker.Core.psm1')) $expectedCore
 Assert-Equal 'idempotent_lock' (Sha (Join-Path $ProgramDataRoot 'product\runtime.lock.json')) $expectedLock
 Assert-Equal 'idempotent_catalog_preserved' (Sha $catalog) $preserveBefore.catalog
 Assert-Equal 'idempotent_source_preserved' (Sha $sourceSentinel) $preserveBefore.source
 Assert-Equal 'idempotent_output_preserved' (Sha $outputSentinel) $preserveBefore.output
 Assert-Equal 'idempotent_secret_preserved' (Sha $secret) $preserveBefore.secret
 $result.checks+=8

 $result.result='PASS'
 $result.stale_core_sha256=$staleHash
 $result.package_core_sha256=$expectedCore
 $result.package_launcher_sha256=$expectedLauncher
 $result.package_runtime_lock_sha256=$expectedLock
 $result.operator_identity=$OperatorIdentity
 $result.worker_root=$WorkerRoot
 $result.program_data_root=$ProgramDataRoot
} catch {
 $result.error=$_.Exception.Message
 throw
} finally {
 try{
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $ReportPath)|Out-Null
  [IO.File]::WriteAllText($ReportPath,($result|ConvertTo-Json -Depth 8),[Text.UTF8Encoding]::new($false))
 }catch{}
 try{Remove-TestRoot $WorkerRoot}catch{}
 try{Remove-TestRoot $ProgramDataRoot}catch{}
}
