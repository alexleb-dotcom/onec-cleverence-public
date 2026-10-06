param(
 [ValidateSet('RUN','SETUP','OPERATOR','RECOVER_POST_VERIFY','CLEANUP')][string]$Mode='RUN',
 [string]$PackageRoot=(Split-Path -Parent $PSScriptRoot),
 [string]$WorkerRoot,
 [string]$ProgramDataRoot,
 [string]$ScratchRoot,
 [string]$ScratchRunId,
 [string]$ScratchBase,
 [string]$OperatorIdentity,
 [string]$HelperSecretSource,
 [switch]$IncludeStart,
 [string]$ReaderName='OneCSourceReader'
)
$ErrorActionPreference='Stop'
$PackageRoot=[IO.Path]::GetFullPath($PackageRoot)
$testScratchModule=Join-Path $PSScriptRoot 'TestScratch.psm1'
Import-Module $testScratchModule -Force -DisableNameChecking
if([string]::IsNullOrWhiteSpace($OperatorIdentity)){$OperatorIdentity=[Security.Principal.WindowsIdentity]::GetCurrent().Name}
$launcher=Join-Path $PackageRoot 'OneCChatWorker.ps1'
$autoScratch=$null
if($Mode -eq 'RUN'){
 $id=[Security.Principal.WindowsIdentity]::GetCurrent()
 if((New-Object Security.Principal.WindowsPrincipal($id)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'RUN_PHASE_EXPECTS_NON_ADMIN'}
 if([string]::IsNullOrWhiteSpace($WorkerRoot) -and [string]::IsNullOrWhiteSpace($ProgramDataRoot)){
  $autoScratch=New-OneCTestScratch -Purpose 'AclRegression'
  $ScratchRoot=$autoScratch.path;$ScratchRunId=$autoScratch.run_id;$ScratchBase=$autoScratch.base
  $WorkerRoot=Join-Path $ScratchRoot 'worker';$ProgramDataRoot=Join-Path $ScratchRoot 'programdata'
 }elseif([string]::IsNullOrWhiteSpace($WorkerRoot) -or [string]::IsNullOrWhiteSpace($ProgramDataRoot)){
  throw 'ACL_REGRESSION_ROOTS_MUST_BE_PAIRED'
 }elseif([string]::IsNullOrWhiteSpace($ScratchRoot) -or [string]::IsNullOrWhiteSpace($ScratchRunId) -or [string]::IsNullOrWhiteSpace($ScratchBase)){
  throw 'ACL_REGRESSION_CUSTOM_ROOTS_REQUIRE_SCRATCH_OWNER'
 }
}else{
 if([string]::IsNullOrWhiteSpace($WorkerRoot) -or [string]::IsNullOrWhiteSpace($ProgramDataRoot) -or [string]::IsNullOrWhiteSpace($ScratchRoot) -or [string]::IsNullOrWhiteSpace($ScratchRunId) -or [string]::IsNullOrWhiteSpace($ScratchBase)){throw 'ACL_REGRESSION_SCRATCH_BINDING_REQUIRED'}
}
$oldLocalAppData=$env:LOCALAPPDATA
$env:LOCALAPPDATA=Join-Path $ScratchRoot 'localappdata'
New-Item -ItemType Directory -Force -Path $env:LOCALAPPDATA|Out-Null
$fixture=Join-Path $ScratchRoot 'fixture'
$main=Join-Path $fixture 'Main'
$ext=Join-Path $fixture 'Extension'
function Is-Admin {
 $id=[Security.Principal.WindowsIdentity]::GetCurrent()
 (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}
function Write-Utf8NoBom([string]$Path,[string]$Value){
 New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Path)|Out-Null
 [IO.File]::WriteAllText($Path,$Value,[Text.UTF8Encoding]::new($false))
}
function Ensure-Fixture {
 Remove-Item $fixture -Recurse -Force -ErrorAction SilentlyContinue
 New-Item -ItemType Directory -Force -Path (Join-Path $main 'CommonModules\AclRegression'),(Join-Path $ext 'CommonModules\AclRegressionExt')|Out-Null
 Write-Utf8NoBom (Join-Path $main 'Configuration.xml') '<Configuration name="AclRegressionMain" />'
 Write-Utf8NoBom (Join-Path $main 'CommonModules\AclRegression\Module.bsl') "Procedure Ping() Export`r`nEndProcedure`r`n"
 Write-Utf8NoBom (Join-Path $ext 'Configuration.xml') '<Configuration name="AclRegressionExtension" />'
 Write-Utf8NoBom (Join-Path $ext 'CommonModules\AclRegressionExt\Module.bsl') "Procedure PingExt() Export`r`nEndProcedure`r`n"
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
 if(Test-Path -LiteralPath $Path){throw "TEST_ROOT_CLEANUP_FAILED: $Path"}
}
function Invoke-Launcher([string[]]$Arguments){
 & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $launcher @Arguments
 if($LASTEXITCODE -ne 0){throw "LAUNCHER_STEP_FAILED: $($Arguments -join ' ') exit=$LASTEXITCODE"}
}
function Assert-Denied([string]$Name,[scriptblock]$Action){
 try{& $Action;throw "NEGATIVE_ASSERTION_FAILED: $Name unexpectedly succeeded"}
 catch{
  if($_.Exception.Message -like 'NEGATIVE_ASSERTION_FAILED:*'){throw}
  Write-Host "PASS $Name denied"
 }
}
function Assert-ReaderSourceAcl {
 $managed=Join-Path $WorkerRoot 'AclRegression\Participants\aclbase\Target\Main\CommonModules\AclRegression\Module.bsl'
 if(-not(Test-Path -LiteralPath $managed -PathType Leaf)){throw "MANAGED_SOURCE_MISSING: $managed"}
 $reader=New-Object Security.Principal.NTAccount("$env:COMPUTERNAME\$ReaderName")
 $readerSid=$reader.Translate([Security.Principal.SecurityIdentifier]).Value
 $acl=Get-Acl -LiteralPath $managed
 $rules=@($acl.Access|Where-Object{$_.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value -eq $readerSid -and $_.AccessControlType -eq 'Allow'})
 $writeMask=[Security.AccessControl.FileSystemRights]::WriteData -bor [Security.AccessControl.FileSystemRights]::AppendData -bor [Security.AccessControl.FileSystemRights]::WriteExtendedAttributes -bor [Security.AccessControl.FileSystemRights]::WriteAttributes -bor [Security.AccessControl.FileSystemRights]::DeleteSubdirectoriesAndFiles -bor [Security.AccessControl.FileSystemRights]::Delete -bor [Security.AccessControl.FileSystemRights]::ChangePermissions -bor [Security.AccessControl.FileSystemRights]::TakeOwnership
 if(@($rules|Where-Object{([int64]$_.FileSystemRights -band [int64]$writeMask) -ne 0}).Count){throw 'READER_SOURCE_WRITE_RIGHT_PRESENT'}
 Write-Host 'PASS reader managed Source ACL has no Write/Modify/FullControl'
}
function Invoke-PostVerifyAclProof {
 if(Is-Admin){throw 'POST_VERIFY_PROOF_MUST_BE_NON_ADMIN'}
 $events=Join-Path $ProgramDataRoot 'operations\events.jsonl'
 if(-not(Test-Path -LiteralPath $events -PathType Leaf)){throw 'OPERATION_JOURNAL_MISSING'}
 Add-Content -LiteralPath $events -Value '' -Encoding UTF8
 Write-Host 'PASS operator operation journal append'

 $secret=Join-Path $ProgramDataRoot 'secrets\helper-secret.txt'
 if(Test-Path -LiteralPath $secret -PathType Leaf){Assert-Denied 'operator_secret_read' {$s=[IO.File]::Open($secret,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::ReadWrite);try{}finally{$s.Dispose()}}}
 foreach($binary in @((Join-Path $WorkerRoot 'OneCChatWorker.ps1'),(Join-Path $ProgramDataRoot 'provider\source-reader-integration.mjs'),(Join-Path $ProgramDataRoot 'runtime\rg.exe'))){
  Assert-Denied ("operator_binary_write_"+[IO.Path]::GetFileName($binary)) {
   $s=[IO.File]::Open($binary,[IO.FileMode]::Open,[IO.FileAccess]::Write,[IO.FileShare]::Read)
   try{}finally{$s.Dispose()}
  }
 }
 Assert-ReaderSourceAcl

 Import-Module (Join-Path $ProgramDataRoot 'product\OneCChatWorker.Core.psm1') -Force -DisableNameChecking
 Set-WorkerReaderIdentity -ReaderName $ReaderName|Out-Null
 $admission=New-Admission -ProjectId 'AclRegression' -TaskId 'acl-regression-task' -WorkerRoot $WorkerRoot -ProgramDataRoot $ProgramDataRoot
 $providerConfig=Join-Path $ProgramDataRoot 'provider\provider-config.json'
 $activeAdmission=Join-Path $ProgramDataRoot 'runtime\active-admission.json'
 if(-not(Test-Path -LiteralPath $providerConfig -PathType Leaf)){throw 'START_PROVIDER_CONFIG_WRITE_FAILED'}
 if(-not(Test-Path -LiteralPath $activeAdmission -PathType Leaf)){throw 'START_ADMISSION_WRITE_FAILED'}
 $admissionDoc=Get-Content -LiteralPath $activeAdmission -Raw -Encoding UTF8|ConvertFrom-Json
 if($admissionDoc.project_id -ne 'AclRegression' -or $admissionDoc.task_id -ne 'acl-regression-task'){throw 'START_ADMISSION_BINDING_MISMATCH'}
 Remove-Item -LiteralPath $activeAdmission -Force
 if(Test-Path -LiteralPath $activeAdmission){throw 'START_ADMISSION_CLEANUP_FAILED'}
 Write-Host 'PASS deterministic non-admin START admission writes provider/runtime and can clean admission'

 [pscustomobject]@{
  status='PASS'
  operation_journal='WRITABLE'
  provider_config='WRITABLE'
  runtime_admission='WRITABLE'
  secret='DENIED'
  protected_binaries='DENIED'
  reader_source_write='DENIED_BY_ACL'
  project_id=$admission.project_id
  task_id=$admission.task_id
 }
}
switch($Mode){
 'RUN' {
  $runError=$null
  try{
   Ensure-Fixture
   $scratchArgs=@('-ScratchRoot',$ScratchRoot,'-ScratchRunId',$ScratchRunId,'-ScratchBase',$ScratchBase)
   $args=@('-NoProfile','-ExecutionPolicy','Bypass','-File',$PSCommandPath,'-Mode','SETUP','-PackageRoot',$PackageRoot,'-WorkerRoot',$WorkerRoot,'-ProgramDataRoot',$ProgramDataRoot,'-OperatorIdentity',$OperatorIdentity,'-ReaderName',$ReaderName)+$scratchArgs
   if($HelperSecretSource){$args+=@('-HelperSecretSource',$HelperSecretSource)}
   $p=Start-Process powershell.exe -Verb RunAs -ArgumentList $args -Wait -PassThru
   if($p.ExitCode -ne 0){throw "SETUP_PHASE_FAILED: $($p.ExitCode)"}
   $opArgs=@('-Mode','OPERATOR','-PackageRoot',$PackageRoot,'-WorkerRoot',$WorkerRoot,'-ProgramDataRoot',$ProgramDataRoot,'-OperatorIdentity',$OperatorIdentity,'-ReaderName',$ReaderName)+$scratchArgs
   if($IncludeStart){$opArgs+='-IncludeStart'}
   & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $PSCommandPath @opArgs
   if($LASTEXITCODE -ne 0){throw "OPERATOR_PHASE_FAILED: $LASTEXITCODE"}
  }catch{$runError=$_.Exception}finally{
   if($null -ne $autoScratch){
    $cleanupArgs=@('-NoProfile','-ExecutionPolicy','Bypass','-File',$PSCommandPath,'-Mode','CLEANUP','-PackageRoot',$PackageRoot,'-WorkerRoot',$WorkerRoot,'-ProgramDataRoot',$ProgramDataRoot,'-OperatorIdentity',$OperatorIdentity,'-ReaderName',$ReaderName,'-ScratchRoot',$ScratchRoot,'-ScratchRunId',$ScratchRunId,'-ScratchBase',$ScratchBase)
    $cleanup=Start-Process powershell.exe -Verb RunAs -ArgumentList $cleanupArgs -Wait -PassThru
    if($cleanup.ExitCode -ne 0 -and $null -eq $runError){$runError=New-Object Exception("CLEANUP_PHASE_FAILED: $($cleanup.ExitCode)")}
   }
  }
  $env:LOCALAPPDATA=$oldLocalAppData
  if($null -ne $runError){throw $runError}
  Write-Host 'OPERATOR ACL REGRESSION RUN PASS'
 }
 'SETUP' {
  if(-not(Is-Admin)){throw 'SETUP_PHASE_REQUIRES_ADMIN'}
  Remove-TestRoot $WorkerRoot
  Remove-TestRoot $ProgramDataRoot
  Invoke-Launcher @('-Mode','INSTALL','-WorkerRoot',$WorkerRoot,'-ProgramDataRoot',$ProgramDataRoot,'-ReaderName',$ReaderName,'-OperatorIdentity',$OperatorIdentity,'-SkipDependencies')
  if($HelperSecretSource){
   if(-not(Test-Path -LiteralPath $HelperSecretSource -PathType Leaf)){throw 'HELPER_SECRET_SOURCE_MISSING'}
   $dest=Join-Path $ProgramDataRoot 'secrets\helper-secret.txt'
   Copy-Item -LiteralPath $HelperSecretSource -Destination $dest -Force
   Import-Module (Join-Path $ProgramDataRoot 'product\OneCChatWorker.Core.psm1') -Force -DisableNameChecking
   Set-WorkerReaderIdentity -ReaderName $ReaderName|Out-Null
   $identity=Resolve-WorkerOperatorIdentity $OperatorIdentity
   Protect-WorkerRuntimeFile -Path $dest -Identity $identity -Secret
  }
  Write-Host 'SETUP PASS'
 }
 'OPERATOR' {
  if(Is-Admin){throw 'OPERATOR_PHASE_MUST_BE_NON_ADMIN'}
  if(-not(Test-Path -LiteralPath $main)){Ensure-Fixture}
  Invoke-Launcher @('-Mode','ADD_PROJECT','-WorkerRoot',$WorkerRoot,'-ProgramDataRoot',$ProgramDataRoot,'-ReaderName',$ReaderName,'-ProjectId','AclRegression','-DisplayName','ACL Regression')
  Invoke-Launcher @('-Mode','ADD_PARTICIPANT','-WorkerRoot',$WorkerRoot,'-ProgramDataRoot',$ProgramDataRoot,'-ReaderName',$ReaderName,'-ProjectId','AclRegression','-ParticipantId','aclbase','-Role','ACL regression','-Platform','ONEC')
  Invoke-Launcher @('-Mode','SET_MAIN','-WorkerRoot',$WorkerRoot,'-ProgramDataRoot',$ProgramDataRoot,'-ReaderName',$ReaderName,'-ProjectId','AclRegression','-ParticipantId','aclbase','-SourcePath',$main)
  Invoke-Launcher @('-Mode','ADD_EXTENSION','-WorkerRoot',$WorkerRoot,'-ProgramDataRoot',$ProgramDataRoot,'-ReaderName',$ReaderName,'-ProjectId','AclRegression','-ParticipantId','aclbase','-ExtensionId','acl-ext','-SourcePath',$ext)
  Invoke-Launcher @('-Mode','APPLY','-WorkerRoot',$WorkerRoot,'-ProgramDataRoot',$ProgramDataRoot,'-ReaderName',$ReaderName,'-ProjectId','AclRegression')
  Invoke-Launcher @('-Mode','VERIFY','-WorkerRoot',$WorkerRoot,'-ProgramDataRoot',$ProgramDataRoot,'-ReaderName',$ReaderName,'-ProjectId','AclRegression')
  $proof=Invoke-PostVerifyAclProof
  if($proof.status -ne 'PASS'){throw 'POST_VERIFY_ACL_PROOF_FAILED'}
  if($IncludeStart){
   Invoke-Launcher @('-Mode','START','-WorkerRoot',$WorkerRoot,'-ProgramDataRoot',$ProgramDataRoot,'-ReaderName',$ReaderName,'-ProjectId','AclRegression','-TaskId','acl-regression-task')
   Import-Module (Join-Path $ProgramDataRoot 'product\OneCChatWorker.Core.psm1') -Force -DisableNameChecking
   $deadline=(Get-Date).AddSeconds(60)
   do{$helper=Get-HelperConnectionState -ProgramDataRoot $ProgramDataRoot;if($helper.status -eq 'CONNECTED'){break};Start-Sleep -Seconds 2}while((Get-Date)-lt $deadline)
   if($helper.status -ne 'CONNECTED'){throw "HELPER_NOT_CONNECTED: $($helper.status)"}
   Write-Host 'PASS START helper CONNECTED'
  }
  Write-Host 'OPERATOR ACL REGRESSION PASS'
 }
 'RECOVER_POST_VERIFY' {
  if(Is-Admin){throw 'RECOVER_POST_VERIFY_MUST_BE_NON_ADMIN'}
  $vCore=Join-Path $ProgramDataRoot 'product\OneCChatWorker.Core.psm1'
  if(-not(Test-Path -LiteralPath $vCore -PathType Leaf)){throw 'RECOVERY_INSTALLED_CORE_MISSING'}
  Import-Module $vCore -Force -DisableNameChecking
  Set-WorkerReaderIdentity -ReaderName $ReaderName|Out-Null
  $v=Verify-WorkerProject -ProjectId 'AclRegression' -WorkerRoot $WorkerRoot
  if($v.status -ne 'READY'){throw "RECOVERY_PROJECT_NOT_READY: $($v.status)"}
  $proof=Invoke-PostVerifyAclProof
  if($proof.status -ne 'PASS'){throw 'POST_VERIFY_ACL_PROOF_FAILED'}
  $proof|ConvertTo-Json -Depth 8
 }
 'CLEANUP' {
  if(-not(Is-Admin)){throw 'CLEANUP_PHASE_REQUIRES_ADMIN'}
  $testHelper=Join-Path $ProgramDataRoot 'helper\hosted-helper.mjs'
  $live=@(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue|Where-Object{$_.Name-eq'node.exe' -and $_.CommandLine -and $_.CommandLine.Contains($testHelper)})
  if($live.Count -and (Test-Path -LiteralPath $launcher -PathType Leaf)){
   Invoke-Launcher @('-Mode','STOP','-WorkerRoot',$WorkerRoot,'-ProgramDataRoot',$ProgramDataRoot,'-ReaderName',$ReaderName)
  }
  Remove-OneCTestScratch -Path $ScratchRoot -RunId $ScratchRunId -Base $ScratchBase|Out-Null
  Write-Host 'CLEANUP PASS'
 }
}