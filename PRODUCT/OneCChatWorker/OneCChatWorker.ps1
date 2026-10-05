param(
 [ValidateSet('MENU','PRECHECK','INSTALL','STATUS','LIST','ADD_PROJECT','EDIT_PROJECT','ADD_PARTICIPANT','EDIT_PARTICIPANT','SET_MAIN','ADD_EXTENSION','DEACTIVATE','APPLY','VERIFY','REPAIR','START','STOP','SETTINGS','DIAGNOSTICS','VIEW_CURRENT_OPERATION','VIEW_RECENT_OPERATIONS','VIEW_LOGS','EXPORT_DIAGNOSTICS','UNINSTALL')]
 [string]$Mode='MENU',
 [string]$ProjectId,[string]$ParticipantId,[string]$ExtensionId,[string]$SourcePath,[string]$DisplayName,[string]$Role,
 [ValidateSet('ONEC','CLEVERENCE')][string]$Platform='ONEC',[string]$TaskId,[ValidateSet('PROJECT','PARTICIPANT','MAIN','EXTENSION')][string]$Kind='PROJECT',
 [switch]$ReplaceExisting,[string]$WorkerRoot='C:\OneCChatWorker',[string]$ProgramDataRoot='C:\ProgramData\OneCChatWorker',
 [string]$ReaderName='OneCSourceReader',[string]$OperatorIdentity,[string]$RelayUrl='wss://onec-g1q1-relay.alex-lebad1.workers.dev/helper',
 [switch]$SkipDependencies,[switch]$ConfirmUninstall,[switch]$Json,[string]$DiagnosticPath,[string]$UiInputPath
)
$ErrorActionPreference='Stop'
if([string]::IsNullOrWhiteSpace($OperatorIdentity)){$OperatorIdentity=[Security.Principal.WindowsIdentity]::GetCurrent().Name}
$PackageRoot=$PSScriptRoot
$InstalledCore=Join-Path $ProgramDataRoot 'product\OneCChatWorker.Core.psm1'
$PackageCore=Join-Path $PackageRoot 'core\OneCChatWorker.Core.psm1'
$Core=if(Test-Path -LiteralPath $InstalledCore){$InstalledCore}else{$PackageCore}
if(-not(Test-Path -LiteralPath $Core -PathType Leaf)){throw "CORE_NOT_FOUND: $Core"}
Import-Module $Core -Force -DisableNameChecking
Set-WorkerReaderIdentity -ReaderName $ReaderName|Out-Null

function Is-Admin {
 $id=[Security.Principal.WindowsIdentity]::GetCurrent();$p=New-Object Security.Principal.WindowsPrincipal($id)
 $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}
function Require-AdminOrRelaunch {
 param([string]$RequestedMode)
 if(Is-Admin){return}
 $argsList=@('-NoProfile','-ExecutionPolicy','Bypass','-File',$PSCommandPath,'-Mode',$RequestedMode,'-WorkerRoot',$WorkerRoot,'-ProgramDataRoot',$ProgramDataRoot,'-ReaderName',$ReaderName,'-OperatorIdentity',$OperatorIdentity,'-RelayUrl',$RelayUrl)
 if(-not [string]::IsNullOrWhiteSpace($ProjectId)){$argsList+=@('-ProjectId',$ProjectId)}
 if($SkipDependencies){$argsList+='-SkipDependencies'}
 if($ConfirmUninstall){$argsList+='-ConfirmUninstall'}
 if($Json){$argsList+='-Json'}
 $p=Start-Process -FilePath 'powershell.exe' -Verb RunAs -ArgumentList $argsList -Wait -PassThru
 if($script:InGuidedMenu){
  if($p.ExitCode -ne 0){throw "ELEVATED_ACTION_FAILED: $RequestedMode exit=$($p.ExitCode)"}
  return $true
 }
 exit $p.ExitCode
}
function Need([string]$Value,[string]$Name){if([string]::IsNullOrWhiteSpace($Value)){throw "ARG_REQUIRED: $Name"};$Value}
function Show-JsonValue($Value){$Value|ConvertTo-Json -Depth 30}
function Show-Value($Value){
 if($Json){Show-JsonValue $Value;return}
 if($script:InGuidedMenu -and -not $script:InAdvancedMenu){return}
 if($null -eq $Value){return}
 if($Value -is [string]){Write-Host $Value;return}
 $text=$Value|Format-List *|Out-String
 Write-Host $text.TrimEnd()
}
function Error-Class([Exception]$Exception){
 $m=[string]$Exception.Message
 if([string]::IsNullOrWhiteSpace($m)){return $Exception.GetType().Name}
 (($m -split ':',2)[0] -replace '[^A-Za-z0-9_.-]','_').ToUpperInvariant()
}

function Invoke-ObservedAction {
 param(
  [Parameter(Mandatory)][string]$OperationType,
  [Parameter(Mandatory)][string]$RequestedAction,
  [Parameter(Mandatory)][int]$TotalSteps,
  [string]$Project,[string]$Participant,[string]$Artifact,
  [Parameter(Mandatory)][scriptblock]$Body,
  [scriptblock]$FinalStateResolver
 )
 $recovery=Get-OperationRecoveryClassification -ProgramDataRoot $ProgramDataRoot
 if($recovery.classification -eq 'RECOVERY_REQUIRED'){
  $previous=$recovery.operation
  if($OperationType -notin @('PRECHECK','INSTALL','REPAIR')){
   throw ("RECOVERY_REQUIRED: incomplete operation {0} type={1}. Run STATUS/DIAGNOSTICS, then explicit INSTALL/REPAIR; do not replay {2}." -f $previous.operation_id,$previous.operation_type,$OperationType)
  }
  Write-Host ("Recovery inspection: prior operation {0} ({1}) remained RUNNING." -f $previous.operation_id,$previous.operation_type)
  if($OperationType -in @('INSTALL','REPAIR')){
   $null=Complete-WorkerOperation -Operation $previous -State CANCELLED -Message 'Interrupted operation classified; superseded by explicit recover-first path, not blind replay' -RecoveryHint 'Review the new recovery operation and final verification result.' -ProgramDataRoot $ProgramDataRoot
  }
 }
 $op=Start-WorkerOperation -OperationType $OperationType -RequestedAction $RequestedAction -ProjectId $Project -ParticipantId $Participant -ArtifactId $Artifact -TotalSteps $TotalSteps -ProgramDataRoot $ProgramDataRoot
 try{
  $result=& $Body $op
  $finalState='PASS';$finalMessage='Completed'
  if($FinalStateResolver){
   $resolved=& $FinalStateResolver $result
   if($resolved){
    if($resolved.state){$finalState=[string]$resolved.state}
    if($resolved.message){$finalMessage=[string]$resolved.message}
   }
  }
  $null=Complete-WorkerOperation -Operation $op -State $finalState -Message $finalMessage -ProgramDataRoot $ProgramDataRoot
  $result
 }catch{
  $class=Error-Class $_.Exception
  $null=Complete-WorkerOperation -Operation $op -State FAIL -Message 'Operation failed' -ErrorClass $class -RecoveryHint 'Run STATUS / DIAGNOSTICS before retry. Recover first after interruption; do not blindly replay.' -ProgramDataRoot $ProgramDataRoot
  throw
 }
}

function Show-StatusReadable {
 param($Status)
 if($Json){Show-JsonValue $Status;return}
 Write-Host ''
 Write-Host 'OneCChatWorker STATUS'
 Write-Host ('  Product version : {0}' -f $Status.product_version)
 Write-Host ('  Installed       : {0}' -f $Status.installed)
 Write-Host ('  Worker root     : {0}' -f $Status.worker_root)
 Write-Host ('  Node            : {0} (required {1}) [{2}]' -f $Status.dependencies.node.actual,$Status.dependencies.node.required,$(if($Status.dependencies.node.healthy){'PASS'}else{'FAIL'}))
 Write-Host ('  ripgrep         : {0} (required {1}) [{2}]' -f $Status.dependencies.ripgrep.actual,$Status.dependencies.ripgrep.required,$(if($Status.dependencies.ripgrep.healthy){'PASS'}else{'FAIL'}))
 Write-Host ('  Python required : {0}' -f $Status.dependencies.python_required)
 Write-Host ('  Cloudflare CLI  : required={0}' -f $Status.dependencies.cloudflare_cli_required)
 Write-Host ('  MCP/helper      : {0}' -f $Status.helper.status)
 if($Status.helper.session_id){
  Write-Host ('  Session         : {0}' -f $Status.helper.session_id)
  Write-Host ('  Active project  : {0}' -f $Status.helper.project_id)
  Write-Host ('  Active task     : {0}' -f $Status.helper.task_id)
  Write-Host ('  Expires UTC     : {0}' -f $Status.helper.expires_utc)
 }
 if($Status.current_operation){
  Write-Host ('  Current/last op : {0} / {1} / {2}' -f $Status.current_operation.operation_type,$Status.current_operation.state,$Status.current_operation.message)
 }else{Write-Host '  Current/last op : none'}
 Write-Host ('  Recovery state  : {0}' -f $Status.operation_recovery.classification)
 if($Status.last_verify){Write-Host ('  Last VERIFY     : {0} / {1}' -f $Status.last_verify.state,$Status.last_verify.started_utc)}
 Write-Host ''
 Write-Host 'Projects:'
 if(-not @($Status.projects).Count){Write-Host '  (none)'}
 foreach($p in @($Status.projects)){
  Write-Host ('  - {0}  active={1}  participants={2}  verify={3}' -f $p.project_id,$p.active,$p.participant_count,$p.verification)
 }
 Write-Host ''
 Write-Host 'Output proposals:'
 foreach($o in @($Status.output)){
  $proposalCount=@($o.tasks|Where-Object{$_.status -eq 'PROPOSAL_NOT_APPLIED'}).Count
  Write-Host ('  - {0}: tasks={1}, proposal_not_applied={2}' -f $o.project_id,$o.task_count,$proposalCount)
 }
}

function Show-CurrentOperation {
 $op=Get-CurrentWorkerOperation -ProgramDataRoot $ProgramDataRoot
 if($Json){Show-JsonValue $op;return}
 if(!$op){Write-Host 'No recorded operation.';return}
 Write-Host ('Operation {0}' -f $op.operation_id)
 Write-Host ('  Type     : {0}' -f $op.operation_type)
 Write-Host ('  State    : {0}' -f $op.state)
 Write-Host ('  Progress : {0}/{1}' -f $op.current_step,$op.total_steps)
 Write-Host ('  Project  : {0}' -f $op.project_id)
 Write-Host ('  Message  : {0}' -f $op.message)
 Write-Host ('  Started  : {0}' -f $op.started_utc)
 Write-Host ('  Ended    : {0}' -f $op.ended_utc)
 if($op.error_class){Write-Host ('  Error    : {0}' -f $op.error_class)}
 if($op.recovery_hint){Write-Host ('  Recovery : {0}' -f $op.recovery_hint)}
}
function Show-RecentOperations {
 $ops=@(Get-RecentWorkerOperations -Limit 20 -ProgramDataRoot $ProgramDataRoot)
 if($Json){Show-JsonValue $ops;return}
 if(-not $ops.Count){Write-Host 'No completed operations.';return}
 foreach($op in $ops){
  Write-Host ('{0}  {1,-18} {2,-16} {3}' -f $op.started_utc,$op.operation_type,$op.state,$op.message)
 }
}
function Show-OperationLogs {
 $lines=@(Get-WorkerOperationLog -Tail 100 -ProgramDataRoot $ProgramDataRoot)
 if($Json){Show-JsonValue $lines}else{if($lines.Count){$lines|ForEach-Object{Write-Host $_}}else{Write-Host 'No operation log entries.'}}
}

function Run-Precheck {
 $r=Invoke-ObservedAction -OperationType PRECHECK -RequestedAction 'Check prerequisites and dependency state' -TotalSteps 2 -Body {
  param($op)
  $null=Update-WorkerOperation -Operation $op -Message 'Checking PowerShell, elevation and WinGet availability' -Step 1 -Total 2 -State RUNNING -ProgramDataRoot $ProgramDataRoot
  $pre=Invoke-Precheck
  $null=Update-WorkerOperation -Operation $op -Message 'Checking pinned Node/ripgrep versions; Python/Cloudflare CLI are not product dependencies' -Step 2 -Total 2 -State RUNNING -ProgramDataRoot $ProgramDataRoot
  $pre
 }
 Show-Value $r
}
function Run-Install {
 if(Require-AdminOrRelaunch 'INSTALL'){return}
 $r=Invoke-ObservedAction -OperationType INSTALL -RequestedAction 'Install or repair OneCChatWorker machine runtime' -TotalSteps 4 -Body {
  param($op)
  $null=Update-WorkerOperation -Operation $op -Message 'Checking prerequisites' -Step 1 -Total 4 -State RUNNING -ProgramDataRoot $ProgramDataRoot
  $pre=Invoke-Precheck
  $null=Update-WorkerOperation -Operation $op -Message 'Installing/reusing pinned dependencies, restricted worker identity, runtime and ACLs' -Step 2 -Total 4 -State RUNNING -ProgramDataRoot $ProgramDataRoot
  $install=Install-OneCChatWorker -PackageRoot $PackageRoot -WorkerRoot $WorkerRoot -ProgramDataRoot $ProgramDataRoot -OperatorIdentity $OperatorIdentity -SkipDependencies:$SkipDependencies
  $null=Update-WorkerOperation -Operation $op -Message 'Verifying installed runtime and dependency health' -Step 3 -Total 4 -State RUNNING -ProgramDataRoot $ProgramDataRoot
  $status=Get-WorkerStatus -WorkerRoot $WorkerRoot -ProgramDataRoot $ProgramDataRoot
  $secretReady=Test-Path -LiteralPath (Join-Path $ProgramDataRoot 'secrets\helper-secret.txt') -PathType Leaf
  $state=if($secretReady){'PASS'}else{'WAITING_FOR_USER'}
  $msg=if($secretReady){'Runtime installed and local enrollment material is present'}else{'Runtime installed; complete ChatGPT app authorization and local helper enrollment'}
  $null=Update-WorkerOperation -Operation $op -Message $msg -Step 4 -Total 4 -State $state -ProgramDataRoot $ProgramDataRoot
  [pscustomobject]@{precheck=$pre;install=$install;status=$status;remote_auth_ready=$secretReady}
 } -FinalStateResolver {
  param($x)
  if($x.remote_auth_ready){[pscustomobject]@{state='PASS';message='Installation verified'}}else{[pscustomobject]@{state='WAITING_FOR_USER';message='Installation complete; remote authorization/enrollment checkpoint remains'}}
 }
 if($Json){Show-JsonValue $r}else{Write-Host '';Write-Host 'INSTALL result:';Write-Host ('  Installed state : {0}' -f $r.install.installed_state);Write-Host ('  Remote auth     : {0}' -f $(if($r.remote_auth_ready){'READY'}else{'WAITING_FOR_USER'}))}
}
function Run-AddProject {
 $projectKey=Need $ProjectId ProjectId
 $r=Invoke-ObservedAction -OperationType ADD_PROJECT -RequestedAction 'Add project to desired-state catalog' -TotalSteps 2 -Project $projectKey -Body {
  param($op)
  $null=Update-WorkerOperation -Operation $op -Message ("Adding project '{0}' to projects.json" -f $projectKey) -Step 1 -Total 2 -State RUNNING -SafeDetails @{catalog=(Get-CatalogPath $WorkerRoot)} -ProgramDataRoot $ProgramDataRoot
  $x=New-WorkerProject -ProjectId $projectKey -DisplayName $DisplayName -WorkerRoot $WorkerRoot
  $null=Update-WorkerOperation -Operation $op -Message 'Catalog updated; no Source bytes copied yet' -Step 2 -Total 2 -State PASS -ProgramDataRoot $ProgramDataRoot
  $x
 }
 Show-Value $r
}
function Run-EditProject {
 $projectKey=Need $ProjectId ProjectId;$name=Need $DisplayName DisplayName
 $r=Invoke-ObservedAction -OperationType EDIT_PROJECT -RequestedAction 'Edit project display metadata in desired-state catalog' -TotalSteps 2 -Project $projectKey -Body {
  param($op)
  $null=Update-WorkerOperation -Operation $op -Message ("Updating project '{0}' display metadata" -f $projectKey) -Step 1 -Total 2 -State RUNNING -ProgramDataRoot $ProgramDataRoot
  $x=Edit-WorkerProject -ProjectId $projectKey -DisplayName $name -WorkerRoot $WorkerRoot
  $null=Update-WorkerOperation -Operation $op -Message 'Catalog updated; APPLY required to refresh generated manifest metadata' -Step 2 -Total 2 -State PASS -ProgramDataRoot $ProgramDataRoot
  $x
 }
 Show-Value $r
}
function Run-AddParticipant {
 $projectKey=Need $ProjectId ProjectId;$part=Need $ParticipantId ParticipantId
 $r=Invoke-ObservedAction -OperationType ADD_PARTICIPANT -RequestedAction 'Add participant to desired-state catalog' -TotalSteps 2 -Project $projectKey -Participant $part -Body {
  param($op)
  $null=Update-WorkerOperation -Operation $op -Message ("Adding participant '{0}' platform={1}" -f $part,$Platform) -Step 1 -Total 2 -State RUNNING -ProgramDataRoot $ProgramDataRoot
  $x=Add-WorkerParticipant -ProjectId $projectKey -ParticipantId $part -Platform $Platform -Role $Role -WorkerRoot $WorkerRoot
  $null=Update-WorkerOperation -Operation $op -Message 'Catalog updated; APPLY required before runtime admission' -Step 2 -Total 2 -State PASS -ProgramDataRoot $ProgramDataRoot
  $x
 }
 Show-Value $r
}
function Run-EditParticipant {
 $projectKey=Need $ProjectId ProjectId;$part=Need $ParticipantId ParticipantId
 $r=Invoke-ObservedAction -OperationType EDIT_PARTICIPANT -RequestedAction 'Edit participant role metadata in desired-state catalog' -TotalSteps 2 -Project $projectKey -Participant $part -Body {
  param($op)
  $null=Update-WorkerOperation -Operation $op -Message ("Updating participant '{0}' role metadata" -f $part) -Step 1 -Total 2 -State RUNNING -ProgramDataRoot $ProgramDataRoot
  $x=Edit-WorkerParticipant -ProjectId $projectKey -ParticipantId $part -Role $Role -WorkerRoot $WorkerRoot
  $null=Update-WorkerOperation -Operation $op -Message 'Catalog updated; participant id/platform and Source bytes unchanged' -Step 2 -Total 2 -State PASS -ProgramDataRoot $ProgramDataRoot
  $x
 }
 Show-Value $r
}
function Run-SetMain {
 $projectKey=Need $ProjectId ProjectId;$part=Need $ParticipantId ParticipantId;$src=Need $SourcePath SourcePath
 $target="Participants/$part/Target/Main"
 $r=Invoke-ObservedAction -OperationType SET_MAIN -RequestedAction 'Set or replace Target Main source input' -TotalSteps 2 -Project $projectKey -Participant $part -Artifact main -Body {
  param($op)
  $null=Update-WorkerOperation -Operation $op -Message ("Validating 1C Main input '{0}' -> '{1}'" -f $src,$target) -Step 1 -Total 2 -State RUNNING -SafeDetails @{source_input=$src;target_canonical_path=$target;replace_existing=[bool]$ReplaceExisting} -ProgramDataRoot $ProgramDataRoot
  $x=Set-WorkerMain -ProjectId $projectKey -ParticipantId $part -SourcePath $src -ReplaceExisting:$ReplaceExisting -WorkerRoot $WorkerRoot
  $null=Update-WorkerOperation -Operation $op -Message 'Catalog updated; authoritative external Source was not modified' -Step 2 -Total 2 -State PASS -ProgramDataRoot $ProgramDataRoot
  $x
 }
 Show-Value $r
}
function Run-AddExtension {
 $projectKey=Need $ProjectId ProjectId;$part=Need $ParticipantId ParticipantId;$eid=Need $ExtensionId ExtensionId;$src=Need $SourcePath SourcePath
 $target="Participants/$part/Target/Extensions/$eid"
 $r=Invoke-ObservedAction -OperationType ADD_EXTENSION -RequestedAction 'Add extension source input' -TotalSteps 2 -Project $projectKey -Participant $part -Artifact $eid -Body {
  param($op)
  $null=Update-WorkerOperation -Operation $op -Message ("Validating extension input '{0}' -> '{1}'" -f $src,$target) -Step 1 -Total 2 -State RUNNING -SafeDetails @{source_input=$src;target_canonical_path=$target;replace_existing=[bool]$ReplaceExisting} -ProgramDataRoot $ProgramDataRoot
  $x=Add-WorkerExtension -ProjectId $projectKey -ParticipantId $part -ExtensionId $eid -SourcePath $src -ReplaceExisting:$ReplaceExisting -WorkerRoot $WorkerRoot
  $null=Update-WorkerOperation -Operation $op -Message 'Catalog updated; APPLY required; external Source retained' -Step 2 -Total 2 -State PASS -ProgramDataRoot $ProgramDataRoot
  $x
 }
 Show-Value $r
}
function Run-Deactivate {
 $projectKey=Need $ProjectId ProjectId
 $artifact=if($Kind -eq 'EXTENSION'){$ExtensionId}elseif($Kind -eq 'PARTICIPANT'){$ParticipantId}else{$null}
 $r=Invoke-ObservedAction -OperationType DEACTIVATE -RequestedAction ("Deactivate {0}" -f $Kind) -TotalSteps 2 -Project $projectKey -Participant $ParticipantId -Artifact $artifact -Body {
  param($op)
  $null=Update-WorkerOperation -Operation $op -Message ("Deactivating logical {0}; authoritative external Source will not be deleted" -f $Kind) -Step 1 -Total 2 -State RUNNING -ProgramDataRoot $ProgramDataRoot
  Disable-WorkerCatalogItem -Kind $Kind -ProjectId $projectKey -ParticipantId $ParticipantId -ExtensionId $ExtensionId -WorkerRoot $WorkerRoot
  $null=Update-WorkerOperation -Operation $op -Message 'Catalog deactivated; APPLY will detach managed copy instead of deleting Source bytes' -Step 2 -Total 2 -State PASS -ProgramDataRoot $ProgramDataRoot
  Read-WorkerCatalog -WorkerRoot $WorkerRoot
 }
 Show-Value $r
}
function Run-Apply {
 $projectKey=Need $ProjectId ProjectId
 $r=Invoke-ObservedAction -OperationType APPLY -RequestedAction 'Apply desired-state catalog to canonical project tree' -TotalSteps 3 -Project $projectKey -Body {
  param($op)
  $null=Update-WorkerOperation -Operation $op -Message 'Inspecting catalog/manifest state and planned canonical paths' -Step 1 -Total 3 -State RUNNING -ProgramDataRoot $ProgramDataRoot
  $before=try{Verify-WorkerProject -ProjectId $projectKey -WorkerRoot $WorkerRoot}catch{[pscustomobject]@{status='APPLY_REQUIRED';reason=$_.Exception.Message}}
  $null=Update-WorkerOperation -Operation $op -Message 'Applying catalog: copy/verify artifacts, detach replacements/deactivations, generate manifest and ACLs' -Step 2 -Total 3 -State RUNNING -SafeDetails @{before_status=$before.status;source_bytes_policy='external source immutable; managed replacements detached'} -ProgramDataRoot $ProgramDataRoot
  $applied=Apply-WorkerProject -ProjectId $projectKey -WorkerRoot $WorkerRoot
  $null=Update-WorkerOperation -Operation $op -Message ("Post-apply verification = {0}" -f $applied.status) -Step 3 -Total 3 -State $(if($applied.status -eq 'READY'){'PASS'}else{'FAIL'}) -ProgramDataRoot $ProgramDataRoot
  $applied
 } -FinalStateResolver {param($x);if($x.status -eq 'READY'){[pscustomobject]@{state='PASS';message='Catalog applied and project verified READY'}}else{[pscustomobject]@{state='FAIL';message=("APPLY completed with verification state "+$x.status)}}}
 Show-Value $r
}
function Run-Verify {
 $projectKey=Need $ProjectId ProjectId
 $r=Invoke-ObservedAction -OperationType VERIFY -RequestedAction 'Verify catalog, manifest, physical tree and hashes' -TotalSteps 2 -Project $projectKey -Body {
  param($op)
  $null=Update-WorkerOperation -Operation $op -Message 'Hashing canonical artifacts and checking catalog/manifest binding' -Step 1 -Total 2 -State RUNNING -ProgramDataRoot $ProgramDataRoot
  $v=Verify-WorkerProject -ProjectId $projectKey -WorkerRoot $WorkerRoot
  $null=Update-WorkerOperation -Operation $op -Message ("Verification result = {0}" -f $v.status) -Step 2 -Total 2 -State $(if($v.status -eq 'READY'){'PASS'}else{'FAIL'}) -ProgramDataRoot $ProgramDataRoot
  $v
 } -FinalStateResolver {param($x);if($x.status -eq 'READY'){[pscustomobject]@{state='PASS';message='Project verification READY'}}else{[pscustomobject]@{state='FAIL';message=("Project verification "+$x.status)}}}
 Show-Value $r
}
function Run-Repair {
 $projectKey=Need $ProjectId ProjectId
 if(Require-AdminOrRelaunch 'REPAIR'){return}
 $null=Set-WorkerOperatorAcl -WorkerRoot $WorkerRoot -ProgramDataRoot $ProgramDataRoot -OperatorIdentity $OperatorIdentity
 $r=Invoke-ObservedAction -OperationType REPAIR -RequestedAction 'Bounded recover-first project repair' -TotalSteps 3 -Project $projectKey -Body {
  param($op)
  $null=Update-WorkerOperation -Operation $op -Message 'Classifying current state before repair; no blind replay' -Step 1 -Total 3 -State RUNNING -ProgramDataRoot $ProgramDataRoot
  $before=Verify-WorkerProject -ProjectId $projectKey -WorkerRoot $WorkerRoot
  $null=Update-WorkerOperation -Operation $op -Message ("Repair policy for state {0}" -f $before.status) -Step 2 -Total 3 -State RUNNING -ProgramDataRoot $ProgramDataRoot
  $x=Repair-WorkerProject -ProjectId $projectKey -WorkerRoot $WorkerRoot
  $null=Update-WorkerOperation -Operation $op -Message ("Repair verification = {0}" -f $x.status) -Step 3 -Total 3 -State $(if($x.status -eq 'READY'){'RECOVERED'}else{'FAIL'}) -ProgramDataRoot $ProgramDataRoot
  $x
 } -FinalStateResolver {param($x);if($x.status -eq 'READY'){[pscustomobject]@{state='RECOVERED';message='Bounded repair completed and project is READY'}}else{[pscustomobject]@{state='FAIL';message='Repair did not reach READY'}}}
 Show-Value $r
}
function Run-Start {
 $projectKey=Need $ProjectId ProjectId;$task=Need $TaskId TaskId
 $r=Invoke-ObservedAction -OperationType START -RequestedAction 'Start one bounded project/task admission' -TotalSteps 4 -Project $projectKey -Artifact $task -Body {
  param($op)
  $null=Update-WorkerOperation -Operation $op -Message 'Verifying selected project before admission' -Step 1 -Total 4 -State RUNNING -ProgramDataRoot $ProgramDataRoot
  $v=Verify-WorkerProject -ProjectId $projectKey -WorkerRoot $WorkerRoot
  if($v.status -ne 'READY'){throw "PROJECT_NOT_READY: $($v.status)"}
  $null=Update-WorkerOperation -Operation $op -Message ("Binding admission to project={0}, task={1}; no runtime project/task switching" -f $projectKey,$task) -Step 2 -Total 4 -State RUNNING -ProgramDataRoot $ProgramDataRoot
  $null=Update-WorkerOperation -Operation $op -Message 'Enter the local OneCSourceReader password in the Windows runas prompt' -Step 3 -Total 4 -State WAITING_FOR_USER -ProgramDataRoot $ProgramDataRoot
  $start=Start-WorkerAdmission -ProjectId $projectKey -TaskId $task -WorkerRoot $WorkerRoot -ProgramDataRoot $ProgramDataRoot -RelayUrl $RelayUrl
  $null=Update-WorkerOperation -Operation $op -Message 'Waiting for helper connection evidence' -Step 4 -Total 4 -State RUNNING -ProgramDataRoot $ProgramDataRoot
  $helper=$null
  for($i=0;$i -lt 10;$i++){
   $helper=Get-HelperConnectionState -ProgramDataRoot $ProgramDataRoot
   if($helper.status -eq 'CONNECTED'){break}
   Start-Sleep -Seconds 1
  }
  [pscustomobject]@{start=$start;helper=$helper}
 } -FinalStateResolver {
  param($x)
  if($x.helper.status -eq 'CONNECTED'){[pscustomobject]@{state='PASS';message='Bounded helper admission connected'}}else{[pscustomobject]@{state='WAITING_FOR_USER';message=("Helper start requested; connectivity state="+$x.helper.status+". Check STATUS/DIAGNOSTICS.")}}
 }
 if($Json){Show-JsonValue $r}else{Write-Host ('START: project={0} task={1} helper={2}' -f $projectKey,$task,$r.helper.status)}
}
function Run-Stop {
 if(Require-AdminOrRelaunch 'STOP'){return}
 $r=Invoke-ObservedAction -OperationType STOP -RequestedAction 'Stop current helper/admission without deleting project data' -TotalSteps 2 -Body {
  param($op)
  $null=Update-WorkerOperation -Operation $op -Message 'Stopping restricted helper and clearing active admission' -Step 1 -Total 2 -State RUNNING -ProgramDataRoot $ProgramDataRoot
  $x=Stop-WorkerAdmission -ProgramDataRoot $ProgramDataRoot
  $helper=Get-HelperConnectionState -ProgramDataRoot $ProgramDataRoot
  $null=Update-WorkerOperation -Operation $op -Message ("Helper state = {0}; project/catalog/Source/Output retained" -f $helper.status) -Step 2 -Total 2 -State $(if($helper.status -eq 'OFFLINE'){'PASS'}else{'FAIL'}) -ProgramDataRoot $ProgramDataRoot
  [pscustomobject]@{stop=$x;helper=$helper}
 } -FinalStateResolver {param($x);if($x.helper.status -eq 'OFFLINE'){[pscustomobject]@{state='PASS';message='Admission stopped; data retained'}}else{[pscustomobject]@{state='FAIL';message='Helper still appears active'}}}
 Show-Value $r
}
function Run-Settings {
 if(Require-AdminOrRelaunch 'SETTINGS'){return}
 $r=Invoke-ObservedAction -OperationType SETTINGS -RequestedAction 'Update local helper enrollment secret' -TotalSteps 2 -Body {
  param($op)
  $null=Update-WorkerOperation -Operation $op -Message 'Waiting for locally entered helper enrollment secret; value will not be logged' -Step 1 -Total 2 -State WAITING_FOR_USER -ProgramDataRoot $ProgramDataRoot
  Set-HelperEnrollmentSecret -ProgramDataRoot $ProgramDataRoot
  $null=Update-WorkerOperation -Operation $op -Message 'Enrollment secret stored with restricted ACL; secret value not logged' -Step 2 -Total 2 -State PASS -ProgramDataRoot $ProgramDataRoot
  [pscustomobject]@{status='SETTINGS_UPDATED';secret_value_logged=$false}
 }
 Show-Value $r
}

function Run-Uninstall {
 $plan=Get-UninstallPlan -WorkerRoot $WorkerRoot -ProgramDataRoot $ProgramDataRoot
 if(-not $ConfirmUninstall){
  if($Json){Show-JsonValue ([pscustomobject]@{status='WAITING_FOR_USER';plan=$plan})}
  else{
   Write-Host 'SAFE UNINSTALL PLAN — no changes made.'
   Write-Host 'Will remove:'
   @($plan.remove)|ForEach-Object{Write-Host ("  REMOVE  "+$_)}
   Write-Host 'Will retain:'
   @($plan.retain)|ForEach-Object{Write-Host ("  RETAIN  "+$_)}
   Write-Host ''
   Write-Host 'Re-run with -Mode UNINSTALL -ConfirmUninstall to remove runtime only.'
  }
  return
 }
 if(Require-AdminOrRelaunch 'UNINSTALL'){return}
 $r=Invoke-ObservedAction -OperationType UNINSTALL -RequestedAction 'Remove OneCChatWorker-owned runtime while retaining project Source copies and Output evidence' -TotalSteps 3 -Body {
  param($op)
  $null=Update-WorkerOperation -Operation $op -Message 'Reviewing safe uninstall boundaries; project Source/Output/Detached and external Source will be retained' -Step 1 -Total 3 -State RUNNING -ProgramDataRoot $ProgramDataRoot
  $null=Update-WorkerOperation -Operation $op -Message 'Stopping admission and removing runtime/provider/helper/secrets/product files' -Step 2 -Total 3 -State RUNNING -ProgramDataRoot $ProgramDataRoot
  $x=Invoke-SafeUninstall -WorkerRoot $WorkerRoot -ProgramDataRoot $ProgramDataRoot -ConfirmRuntimeRemoval
  $null=Update-WorkerOperation -Operation $op -Message 'Runtime removed; catalog, Participants, Output, Detached, audit and operation logs retained' -Step 3 -Total 3 -State PASS -ProgramDataRoot $ProgramDataRoot
  $x
 }
 Show-Value $r
}

function Invoke-CommandMode {
 switch($Mode){
  'PRECHECK' {Run-Precheck;break}
  'INSTALL' {Run-Install;break}
  'STATUS' {Show-StatusReadable (Get-WorkerStatus -WorkerRoot $WorkerRoot -ProgramDataRoot $ProgramDataRoot);break}
  'LIST' {Show-Value (Read-WorkerCatalog -WorkerRoot $WorkerRoot -AllowMissing);break}
  'ADD_PROJECT' {Run-AddProject;break}
  'EDIT_PROJECT' {Run-EditProject;break}
  'ADD_PARTICIPANT' {Run-AddParticipant;break}
  'EDIT_PARTICIPANT' {Run-EditParticipant;break}
  'SET_MAIN' {Run-SetMain;break}
  'ADD_EXTENSION' {Run-AddExtension;break}
  'DEACTIVATE' {Run-Deactivate;break}
  'APPLY' {Run-Apply;break}
  'VERIFY' {Run-Verify;break}
  'REPAIR' {Run-Repair;break}
  'START' {Run-Start;break}
  'STOP' {Run-Stop;break}
  'SETTINGS' {Run-Settings;break}
  'DIAGNOSTICS' {Show-Value (Get-WorkerDiagnostics -WorkerRoot $WorkerRoot -ProgramDataRoot $ProgramDataRoot);break}
  'VIEW_CURRENT_OPERATION' {Show-CurrentOperation;break}
  'VIEW_RECENT_OPERATIONS' {Show-RecentOperations;break}
  'VIEW_LOGS' {Show-OperationLogs;break}
  'EXPORT_DIAGNOSTICS' {Show-Value (Export-WorkerDiagnosticBundle -WorkerRoot $WorkerRoot -ProgramDataRoot $ProgramDataRoot -Destination $DiagnosticPath);break}
  'UNINSTALL' {Run-Uninstall;break}
 }
}

$script:UiInputs=New-Object 'System.Collections.Generic.Queue[string]'
if(-not [string]::IsNullOrWhiteSpace($UiInputPath)){
 if(-not(Test-Path -LiteralPath $UiInputPath -PathType Leaf)){throw "UI_INPUT_FILE_NOT_FOUND: $UiInputPath"}
 foreach($line in @(Get-Content -LiteralPath $UiInputPath -Encoding UTF8)){$script:UiInputs.Enqueue([string]$line)}
}
function Read-Ui {
 param([string]$Prompt)
 if($script:UiInputs.Count -gt 0){
  $value=$script:UiInputs.Dequeue()
  Write-Host ("{0}: {1}" -f $Prompt,$value)
  return $value
 }
 Read-Host $Prompt
}
function Show-FieldHelp {
 param([string]$Label,[string]$What,[string]$Why,[string]$Allowed,[string]$Example,[bool]$Required,[string]$Default)
 Write-Host ''
 Write-Host $Label
 Write-Host ("  What: {0}" -f $What)
 Write-Host ("  Why : {0}" -f $Why)
 Write-Host ("  Form: {0}" -f $Allowed)
 Write-Host ("  Example: {0}" -f $Example)
 Write-Host ("  Required: {0}" -f $(if($Required){'yes'}else{'no'}))
 if(-not [string]::IsNullOrWhiteSpace($Default)){Write-Host ("  Default: {0}  (press Enter to accept)" -f $Default)}
 Write-Host "  Type ? or help to show this explanation again."
}
function Read-GuidedValue {
 param(
  [Parameter(Mandatory)][string]$Label,
  [Parameter(Mandatory)][string]$What,
  [Parameter(Mandatory)][string]$Why,
  [Parameter(Mandatory)][string]$Allowed,
  [Parameter(Mandatory)][string]$Example,
  [string]$Default,
  [switch]$Optional,
  [scriptblock]$Validate
 )
 Show-FieldHelp -Label $Label -What $What -Why $Why -Allowed $Allowed -Example $Example -Required:(-not $Optional) -Default $Default
 while($true){
  $suffix=if(-not [string]::IsNullOrWhiteSpace($Default)){" [$Default]"}else{''}
  $value=[string](Read-Ui ($Label+$suffix))
  if($value -match '^(?i:\?|help)$'){Show-FieldHelp -Label $Label -What $What -Why $Why -Allowed $Allowed -Example $Example -Required:(-not $Optional) -Default $Default;continue}
  if([string]::IsNullOrWhiteSpace($value)){
   if(-not [string]::IsNullOrWhiteSpace($Default)){return $Default}
   if($Optional){return ''}
   Write-Host 'FAIL: This field is required.'
   Write-Host ("Next: enter a value for {0}, or type ? for help." -f $Label)
   continue
  }
  if($Validate){
   $problem=& $Validate $value
   if(-not [string]::IsNullOrWhiteSpace([string]$problem)){
    Write-Host ("FAIL: {0}" -f $problem)
    Write-Host ("Next: correct {0}; your previous answers are kept." -f $Label)
    continue
   }
  }
  return $value
 }
}
function Read-GuidedYesNo {
 param([string]$Prompt,[bool]$DefaultNo=$true,[string]$Help='Answer yes or no.')
 while($true){
  $suffix=if($DefaultNo){' [y/N]'}else{' [Y/n]'}
  $v=[string](Read-Ui ($Prompt+$suffix))
  if($v -match '^(?i:\?|help)$'){Write-Host $Help;continue}
  if([string]::IsNullOrWhiteSpace($v)){return (-not $DefaultNo)}
  if($v -match '^(?i:y|yes|да|д)$'){return $true}
  if($v -match '^(?i:n|no|нет|н)$'){return $false}
  Write-Host 'FAIL: Please answer yes or no.'
 }
}
function ConvertTo-SafeTechnicalId {
 param([Parameter(Mandatory)][string]$Text,[string]$Fallback='item')
 $map=@{
  'а'='a';'б'='b';'в'='v';'г'='g';'д'='d';'е'='e';'ё'='e';'ж'='zh';'з'='z';'и'='i';'й'='y';'к'='k';'л'='l';'м'='m';'н'='n';'о'='o';'п'='p';'р'='r';'с'='s';'т'='t';'у'='u';'ф'='f';'х'='h';'ц'='c';'ч'='ch';'ш'='sh';'щ'='sch';'ъ'='';'ы'='y';'ь'='';'э'='e';'ю'='yu';'я'='ya'
 }
 $b=New-Object Text.StringBuilder
 foreach($ch in $Text.ToLowerInvariant().ToCharArray()){
  $s=[string]$ch
  if($s -match '^[a-z0-9]$'){$null=$b.Append($s)}
  elseif($map.ContainsKey($s)){$null=$b.Append($map[$s])}
  else{$null=$b.Append('-')}
 }
 $id=($b.ToString() -replace '-+','-').Trim('-','.')
 if([string]::IsNullOrWhiteSpace($id)){$id=$Fallback}
 if($id.Length -gt 56){$id=$id.Substring(0,56).TrimEnd('-','.')}
 if($id -notmatch '^[a-z0-9]'){$id=$Fallback+'-'+$id}
 $id
}
function Get-UniqueProjectId {
 param([string]$DisplayName)
 $base=ConvertTo-SafeTechnicalId $DisplayName 'project'
 $c=Read-WorkerCatalog -WorkerRoot $WorkerRoot -AllowMissing
 $id=$base;$n=2
 while(Find-Project $c $id){$id=("{0}-{1}" -f $base,$n);$n++}
 $id
}
function Get-UniqueParticipantId {
 param([string]$ProjectId,[string]$Name)
 $base=ConvertTo-SafeTechnicalId $Name 'system'
 $c=Read-WorkerCatalog -WorkerRoot $WorkerRoot -AllowMissing
 $p=Find-Project $c $ProjectId
 $id=$base;$n=2
 while($p -and @($p.participants|Where-Object{$_.participant_id -eq $id}).Count){$id=("{0}-{1}" -f $base,$n);$n++}
 $id
}
function Get-UniqueExtensionId {
 param([string]$ProjectId,[string]$ParticipantId,[string]$Name)
 $base=ConvertTo-SafeTechnicalId $Name 'extension'
 $c=Read-WorkerCatalog -WorkerRoot $WorkerRoot -AllowMissing
 $p=Find-Project $c $ProjectId
 $part=if($p){@($p.participants|Where-Object{$_.participant_id -eq $ParticipantId})|Select-Object -First 1}else{$null}
 $id=$base;$n=2
 while($part -and @($part.target.extensions|Where-Object{$_.extension_id -eq $id}).Count){$id=("{0}-{1}" -f $base,$n);$n++}
 $id
}
function Get-UniqueTaskId {
 param([string]$ProjectId,[string]$Description)
 $base=ConvertTo-SafeTechnicalId $Description 'task'
 $out=Join-Path (Join-Path $WorkerRoot $ProjectId) 'Output'
 $id=$base;$n=2
 while(Test-Path -LiteralPath (Join-Path $out $id)){$id=("{0}-{1}" -f $base,$n);$n++}
 $id
}
function Test-GuidedExportPath {
 param([string]$Path)
 if(-not(Test-Path -LiteralPath $Path -PathType Container)){return 'That folder does not exist.'}
 if(-not(Test-Path -LiteralPath (Join-Path $Path 'Configuration.xml') -PathType Leaf)){return 'Configuration.xml must be directly inside this folder. Choose the root folder of the XML export.'}
 try{Assert-OneCExportRoot $Path;return $null}catch{return 'This folder is not a usable direct 1C XML export root.'}
}
function Get-GuidedErrorInfo {
 param([Exception]$Exception)
 $m=[string]$Exception.Message
 $class=Error-Class $Exception
 switch -Regex ($m){
  '^SOURCE_FOLDER_NOT_FOUND' {return [pscustomobject]@{message='The selected 1C export folder does not exist.';next='Choose the root folder that directly contains Configuration.xml.';code=$class}}
  '^ONEC_CONFIGURATION_XML_MISSING' {return [pscustomobject]@{message='Configuration.xml was not found directly inside the selected folder.';next='Choose the root folder of the unpacked 1C XML export.';code=$class}}
  '^NO_PROJECTS' {return [pscustomobject]@{message='No projects exist yet.';next='Choose Add local project in the guided menu.';code=$class}}
  '^PROJECT_NOT_READY' {return [pscustomobject]@{message='The project is not ready to start work.';next='Use the recommended setup/repair action shown by the guided menu.';code=$class}}
  '^REMOTE_AUTH_REQUIRED' {return [pscustomobject]@{message='ChatGPT connection is not configured yet.';next='Choose Connect ChatGPT and enter the enrollment value locally.';code=$class}}
  '^RUNAS_FAILED_OR_CANCELLED' {return [pscustomobject]@{message='Windows did not confirm that the restricted source reader started.';next='The menu will detect the incomplete start. Clear it safely before retrying; use Diagnostics if it repeats.';code=$class}}
  '^ELEVATED_ACTION_FAILED' {return [pscustomobject]@{message='The Windows administrator step was cancelled or failed.';next='Run the recommended action again and approve the Windows elevation prompt.';code=$class}}
  '^RECOVERY_REQUIRED' {return [pscustomobject]@{message='A previous operation was interrupted and needs recovery first.';next='Use the recommended Recover safely action; do not reinstall unless it specifically says Install.';code=$class}}
  '^UI_SCRIPT_INPUT_EXHAUSTED' {return [pscustomobject]@{message='The scripted UI test ran out of input.';next='Fix the regression input script.';code=$class}}
  default {return [pscustomobject]@{message=("The action could not be completed ({0})." -f $class);next='Follow the recommended action shown by the guided menu, or open Advanced > Diagnostics for details.';code=$class}}
 }
}
function Show-GuidedFailure {
 param([Exception]$Exception)
 $info=Get-GuidedErrorInfo $Exception
 $op=$null
 try{$op=Get-CurrentWorkerOperation -ProgramDataRoot $ProgramDataRoot}catch{}
 Write-Host ''
 Write-Host ("FAIL: {0}" -f $info.message)
 Write-Host ("Next: {0}" -f $info.next)
 if($op -and $op.operation_id){Write-Host ("Details: operation {0}; Advanced > Diagnostics" -f $op.operation_id)}
 else{Write-Host ("Details: {0}; Advanced > Diagnostics" -f $info.code)}
}
function Invoke-GuidedAction {
 param([Parameter(Mandatory)][scriptblock]$Action,[switch]$ShowOutput)
 try{
  if($script:InGuidedMenu -and -not $script:InAdvancedMenu -and -not $ShowOutput){& $Action 6>$null}
  else{& $Action}
  return $true
 }catch{Show-GuidedFailure $_.Exception;return $false}
}
function Get-GuidedContext {
 $installed=Test-Path -LiteralPath (Join-Path $ProgramDataRoot 'installed-state.json') -PathType Leaf
 if(-not $installed){return [pscustomobject]@{state='NOT_INSTALLED';recommended='Install OneCChatWorker';project=$null;participant=$null;reason='Product runtime is not installed.'}}
 $preferredCurrent=Join-Path $ProgramDataRoot 'operations\current-operation.json'
 $recovery=if(Test-Path -LiteralPath $preferredCurrent -PathType Leaf){try{Get-OperationRecoveryClassification -ProgramDataRoot $ProgramDataRoot}catch{$null}}else{[pscustomobject]@{classification='NOT_STARTED';operation=$null}}
 if($recovery -and $recovery.classification -eq 'RECOVERY_REQUIRED'){
  return [pscustomobject]@{state='RECOVERY_REQUIRED';recommended='Recover safely';project=$null;participant=$null;reason='A previous operation was interrupted.';recovery=$recovery}
 }
 $secretReady=Test-Path -LiteralPath (Join-Path $ProgramDataRoot 'secrets\helper-secret.txt') -PathType Leaf
 if(-not $secretReady){return [pscustomobject]@{state='REMOTE_AUTH_MISSING';recommended='Connect ChatGPT';project=$null;participant=$null;reason='Local ChatGPT enrollment is not configured.'}}
 $helper=try{Get-HelperConnectionState -ProgramDataRoot $ProgramDataRoot}catch{$null}
 $admission=Join-Path $ProgramDataRoot 'runtime\active-admission.json'
 $hasAdmission=Test-Path -LiteralPath $admission -PathType Leaf
 $active=$null;if($hasAdmission){try{$active=Get-Content -LiteralPath $admission -Raw -Encoding UTF8|ConvertFrom-Json}catch{}}
 if($helper -and $helper.status -eq 'CONNECTED'){
  return [pscustomobject]@{state='RUNNING';recommended='Show current work status';project=$null;participant=$null;reason='The restricted Source helper is connected for a bounded ChatGPT work session.';helper=$helper;active=$active}
 }
 if($helper -and $helper.status -eq 'RUNNING_NO_CONNECT_EVIDENCE'){
  return [pscustomobject]@{state='STARTING';recommended='Check connection status';project=$null;participant=$null;reason='The restricted Source helper is running but connection evidence is not ready yet.';helper=$helper;active=$active}
 }
 if($hasAdmission){
  return [pscustomobject]@{state='START_INCOMPLETE';recommended='Clear incomplete start';project=$null;participant=$null;reason='A task admission was written, but no restricted helper process is running. Clear only this incomplete admission before retrying.';helper=$helper;active=$active}
 }
 $c=Read-WorkerCatalog -WorkerRoot $WorkerRoot -AllowMissing
 $projects=@($c.projects|Where-Object{$_.active -ne $false})
 if(-not $projects.Count){return [pscustomobject]@{state='NO_PROJECTS';recommended='Add local project';project=$null;participant=$null;reason='No local projects are configured yet.'}}
 $p=$null
 if($script:GuidedProjectId){$p=Find-Project $c $script:GuidedProjectId}
 if(-not $p){$p=$projects[0];$script:GuidedProjectId=$p.project_id}
 $parts=@($p.participants|Where-Object{$_.active -ne $false -and $_.platform -eq 'ONEC'})
 if(-not $parts.Count){return [pscustomobject]@{state='PROJECT_DRAFT';recommended='Complete project setup';project=$p;participant=$null;reason='Add the 1C system/base and its main XML export.'}}
 $part=$parts[0]
 if(-not $part.target.main -or $part.target.main.active -eq $false){return [pscustomobject]@{state='PROJECT_DRAFT';recommended='Complete project setup';project=$p;participant=$part;reason='The main 1C configuration folder is still missing.'}}
 $v=try{Verify-WorkerProject -ProjectId $p.project_id -WorkerRoot $WorkerRoot}catch{[pscustomobject]@{status='FAIL';reason=$_.Exception.Message}}
 if($v.status -in @('APPLY_REQUIRED','DRIFT_APPLY_REQUIRED')){return [pscustomobject]@{state='PROJECT_NEEDS_APPLY';recommended='Finish project setup';project=$p;participant=$part;reason='Setup answers are saved; the managed project copy must now be built and checked.';verification=$v}}
 if($v.status -eq 'READY'){return [pscustomobject]@{state='PROJECT_READY';recommended='Start work';project=$p;participant=$part;reason='The project is ready for a bounded ChatGPT task.';verification=$v}}
 [pscustomobject]@{state='PROJECT_NEEDS_VERIFY';recommended='Check and repair project';project=$p;participant=$part;reason='The managed project copy needs attention before work can start.';verification=$v}
}
function Get-GuidedStateLabel {
 param([string]$State)
 switch($State){
  'NOT_INSTALLED' {'Not installed'}
  'REMOTE_AUTH_MISSING' {'ChatGPT connection required'}
  'NO_PROJECTS' {'Ready for first project'}
  'PROJECT_DRAFT' {'Project setup incomplete'}
  'PROJECT_NEEDS_APPLY' {'Project setup saved'}
  'PROJECT_NEEDS_VERIFY' {'Project needs checking'}
  'PROJECT_READY' {'Project ready'}
  'RUNNING' {'Work session running'}
  'STARTING' {'Work session starting'}
  'START_INCOMPLETE' {'Start incomplete'}
  'RECOVERY_REQUIRED' {'Recovery required'}
  default {$State}
 }
}
function Select-GuidedProject {
 $c=Read-WorkerCatalog -WorkerRoot $WorkerRoot -AllowMissing
 $projects=@($c.projects|Where-Object{$_.active -ne $false})
 if(-not $projects.Count){return $null}
 if($projects.Count -eq 1){$script:GuidedProjectId=$projects[0].project_id;return $projects[0]}
 while($true){
  Write-Host ''
  Write-Host 'Choose the local project you want to work with:'
  for($i=0;$i -lt $projects.Count;$i++){Write-Host ("  [{0}] {1}" -f ($i+1),$projects[$i].display_name)}
  $raw=[string](Read-Ui 'Project number')
  $n=0
  if([int]::TryParse($raw,[ref]$n) -and $n -ge 1 -and $n -le $projects.Count){$script:GuidedProjectId=$projects[$n-1].project_id;return $projects[$n-1]}
  Write-Host 'FAIL: Choose one of the displayed project numbers.'
 }
}
function Show-SetupSummary {
 param($Answers,[bool]$ExistingProject)
 Write-Host ''
 Write-Host 'Setup summary'
 Write-Host ("  Project : {0}" -f $Answers.project_name)
 Write-Host ("  1C base : {0}" -f $Answers.system_name)
 if(-not [string]::IsNullOrWhiteSpace($Answers.role)){Write-Host ("  Purpose : {0}" -f $Answers.role)}
 Write-Host ("  Main XML: {0}" -f $Answers.main_path)
 if(@($Answers.extensions).Count){
  Write-Host '  Extensions:'
  foreach($e in @($Answers.extensions)){Write-Host ("    - {0}: {1}" -f $e.name,$e.path)}
 }else{Write-Host '  Extensions: none'}
 if($ExistingProject){Write-Host '  Existing valid setup is kept; only missing/new answers above will be added.'}
}
function Read-ProjectSetupAnswers {
 param($ExistingProject,$ExistingParticipant,$Defaults)
 $a=[ordered]@{}
 $isNew=($null -eq $ExistingProject)
 if($isNew){
  $a.project_name=Read-GuidedValue -Label 'Project name' -What 'The human-readable name of this customer or local project.' -Why 'It is shown in the menu so you can recognize the project. A safe technical id is created automatically.' -Allowed 'Any short human name.' -Example 'NeoHim' -Default $Defaults.project_name
  $a.project_id=if($Defaults.project_id){$Defaults.project_id}else{Get-UniqueProjectId $a.project_name}
 }else{
  $a.project_name=[string]$ExistingProject.display_name
  $a.project_id=[string]$ExistingProject.project_id
 }
 if($ExistingParticipant){
  $a.system_name=if($ExistingParticipant.role){[string]$ExistingParticipant.role}else{[string]$ExistingParticipant.participant_id}
  $a.participant_id=[string]$ExistingParticipant.participant_id
  $a.role=[string]$ExistingParticipant.role
 }else{
  $a.system_name=Read-GuidedValue -Label 'System / base name' -What 'The name you use for this logical 1C system/base inside the project.' -Why 'It lets ChatGPT distinguish this base from other systems in the same project. A technical id is created automatically.' -Allowed 'A short human name.' -Example 'ERP or Управление торговлей' -Default $(if($Defaults.system_name){$Defaults.system_name}else{'Основная база 1С'})
  $a.participant_id=if($Defaults.participant_id){$Defaults.participant_id}else{Get-UniqueParticipantId $a.project_id $a.system_name}
  $a.role=Read-GuidedValue -Label 'Role / purpose' -What 'A human description of what this 1C base is used for.' -Why 'It is context for people and ChatGPT; it does not change runtime permissions.' -Allowed 'Free text; optional.' -Example 'ERP, Управление торговлей, Бухгалтерия' -Default $Defaults.role -Optional
 }
 if($ExistingParticipant -and $ExistingParticipant.target.main -and $ExistingParticipant.target.main.active -ne $false){
  $a.main_path=[string]$ExistingParticipant.target.main.source_path
  $mainAlready=$true
 }else{
  $a.main_path=Read-GuidedValue -Label 'Main configuration folder' -What 'The root folder of an unpacked XML export of the main 1C configuration.' -Why 'OneCChatWorker copies this export into the managed read-only Source tree.' -Allowed 'A local folder path; Configuration.xml must be directly inside it.' -Example 'C:\1CExports\NeoHim\Main' -Default $Defaults.main_path -Validate {param($v);Test-GuidedExportPath $v}
  $mainAlready=$false
 }
 $existingExt=@()
 if($ExistingParticipant){$existingExt=@($ExistingParticipant.target.extensions|Where-Object{$_.active -ne $false})}
 $a.extensions=@()
 $addExt=Read-GuidedYesNo -Prompt $(if($existingExt.Count){'Add another extension XML export?'}else{'Does this base have an extension XML export to add?'}) -DefaultNo $true -Help 'Answer No if there are no extensions. You can add one later without repeating the main setup.'
 while($addExt){
  $ename=Read-GuidedValue -Label 'Extension name' -What 'A short human name for this 1C extension.' -Why 'It identifies the extension inside this base; a technical id is created automatically.' -Allowed 'A short name.' -Example 'CRM additions'
  $eid=Get-UniqueExtensionId $a.project_id $a.participant_id $ename
  $epath=Read-GuidedValue -Label 'Extension folder' -What 'The root folder of an unpacked XML export of this 1C extension.' -Why 'It will be copied beside the main configuration in the managed Source tree.' -Allowed 'A local folder path; Configuration.xml must be directly inside it.' -Example 'C:\1CExports\NeoHim\Extensions\CRM' -Validate {param($v);Test-GuidedExportPath $v}
  $a.extensions+=,[pscustomobject]@{name=$ename;id=$eid;path=$epath}
  $addExt=Read-GuidedYesNo -Prompt 'Add one more extension?' -DefaultNo $true -Help 'Answer Yes to add another extension export, or No to continue.'
 }
 $a.main_already=$mainAlready
 [pscustomobject]$a
}
function Complete-GuidedProject {
 param([string]$ProjectKey)
 $script:ProjectId=$ProjectKey
 Write-Host ''
 Write-Host 'Building and checking the managed project copy...'
 $ok=Invoke-GuidedAction {Run-Apply;Run-Verify}
 if(-not $ok){return $false}
 $v=try{Verify-WorkerProject -ProjectId $ProjectKey -WorkerRoot $WorkerRoot}catch{$null}
 if(-not $v -or $v.status -ne 'READY'){
  Write-Host 'FAIL: The project did not reach Ready state.'
  Write-Host 'Next: choose Check and repair project from the guided menu.'
  return $false
 }
 Write-Host 'SUCCESS: Project is ready.'
 Write-Host 'Next: Start work now, or return to the menu and start later.'
 return $true
}
function Invoke-GuidedStart {
 param([string]$ProjectKey)
 $description=Read-GuidedValue -Label 'Task description' -What 'A human description of the specific work you want ChatGPT to do now.' -Why 'Each bounded work session has its own Output folder. A technical task id is created automatically.' -Allowed 'A short sentence describing the task.' -Example 'Исправить проведение документа Заказ клиента'
 $script:ProjectId=$ProjectKey
 $script:TaskId=Get-UniqueTaskId $ProjectKey $description
 Write-Host ''
 Write-Host 'Windows will ask for the local OneCSourceReader password. This starts the restricted read-only Source helper.'
 $ok=Invoke-GuidedAction {Run-Start}
 if($ok){
  $h=try{Get-HelperConnectionState -ProgramDataRoot $ProgramDataRoot}catch{$null}
  if($h -and $h.status -eq 'CONNECTED'){Write-Host 'SUCCESS: ChatGPT work session is connected.';Write-Host 'Next: work in ChatGPT; proposals will appear in this task Output folder.'}
  else{Write-Host 'Next: use Show current work status. The helper may still be connecting.'}
 }
}
function Invoke-GuidedProjectSetup {
 param($Context)
 $existing=$null;$part=$null
 if($Context -and $Context.project){$existing=$Context.project;$part=$Context.participant}
 $defaults=[pscustomobject]@{project_name=$(if($existing){$existing.display_name}else{$null});project_id=$(if($existing){$existing.project_id}else{$null});system_name=$null;participant_id=$(if($part){$part.participant_id}else{$null});role=$(if($part){$part.role}else{$null});main_path=$(if($part -and $part.target.main){$part.target.main.source_path}else{$null})}
 while($true){
  $answers=Read-ProjectSetupAnswers -ExistingProject $existing -ExistingParticipant $part -Defaults $defaults
  Show-SetupSummary -Answers $answers -ExistingProject:($null -ne $existing)
  $choice=[string](Read-Ui 'Choose [C] Confirm, [B] Back/Edit, or [Q] Cancel')
  if([string]::IsNullOrWhiteSpace($choice) -or $choice -match '^(?i:c|confirm)$'){break}
  if($choice -match '^(?i:q|quit|cancel)$'){Write-Host 'CANCELLED: no new setup changes were committed.';return}
  if($choice -match '^(?i:b|back|e|edit)$'){$defaults=$answers;continue}
  Write-Host 'FAIL: Choose Confirm, Back/Edit, or Cancel.'
 }
 $script:Platform='ONEC'
 if(-not $existing){
  $script:ProjectId=$answers.project_id;$script:DisplayName=$answers.project_name
  if(-not (Invoke-GuidedAction {Run-AddProject})){return}
  $existing=(Read-WorkerCatalog -WorkerRoot $WorkerRoot|ForEach-Object{Find-Project $_ $answers.project_id})
  $script:GuidedProjectId=$answers.project_id
 }
 if(-not $part){
  $script:ProjectId=$answers.project_id;$script:ParticipantId=$answers.participant_id;$script:Role=$answers.role
  if(-not (Invoke-GuidedAction {Run-AddParticipant})){return}
 }
 if(-not $answers.main_already){
  $script:ProjectId=$answers.project_id;$script:ParticipantId=$answers.participant_id;$script:SourcePath=$answers.main_path;$script:ReplaceExisting=$false
  if(-not (Invoke-GuidedAction {Run-SetMain})){return}
 }
 foreach($e in @($answers.extensions)){
  $script:ProjectId=$answers.project_id;$script:ParticipantId=$answers.participant_id;$script:ExtensionId=$e.id;$script:SourcePath=$e.path;$script:ReplaceExisting=$false
  if(-not (Invoke-GuidedAction {Run-AddExtension})){return}
 }
 if(Complete-GuidedProject $answers.project_id){
  if(Read-GuidedYesNo -Prompt 'Project is ready. Start work now?' -DefaultNo $false -Help 'Yes starts a bounded ChatGPT task. No returns to the menu; setup stays saved.'){Invoke-GuidedStart $answers.project_id}
 }
}
function Invoke-GuidedRecovery {
 param($Context)
 $op=if($Context.recovery){$Context.recovery.operation}else{$null}
 if($op -and $op.operation_type -eq 'INSTALL'){
  Write-Host 'Recovering the interrupted installation without wiping project data.'
  $null=Invoke-GuidedAction {Run-Install}
  return
 }
 $projectKey=if($op -and $op.project_id){[string]$op.project_id}else{$script:GuidedProjectId}
 if($projectKey){
  $script:ProjectId=$projectKey
  Write-Host ("Recovering project {0} from authoritative catalog/manifest state; completed work will not be blindly replayed." -f $projectKey)
  $null=Invoke-GuidedAction {Run-Repair}
 }else{
  Write-Host 'FAIL: Recovery needs diagnostics before a safe project can be selected.'
  Write-Host 'Next: open Advanced > Diagnostics and review the current operation.'
 }
}
function Show-GuidedHeader {
 param($Context)
 Write-Host ''
 Write-Host 'OneCChatWorker'
 Write-Host ('State: {0}' -f (Get-GuidedStateLabel $Context.state))
 if($Context.project){Write-Host ('Project: {0}' -f $Context.project.display_name)}
 if($Context.state -eq 'RUNNING' -and $Context.active){
  Write-Host ('Project: {0}' -f $Context.active.project_id)
  Write-Host ('Task   : {0}' -f $Context.active.task_id)
 }
 Write-Host ('Why: {0}' -f $Context.reason)
 Write-Host ('Recommended: {0}' -f $Context.recommended)
}
function Show-GuidedOutput {
 param($Context)
 $projectKey=$null;$task=$null
 if($Context.active){$projectKey=[string]$Context.active.project_id;$task=[string]$Context.active.task_id}
 elseif($Context.project){$projectKey=[string]$Context.project.project_id}
 if(-not $projectKey){Write-Host 'No project Output folder is available yet.';return}
 $path=Join-Path (Join-Path $WorkerRoot $projectKey) 'Output'
 if($task){$path=Join-Path $path $task}
 Write-Host ("Output folder: {0}" -f $path)
 if(Test-Path -LiteralPath $path -PathType Container){
  try{Start-Process explorer.exe -ArgumentList @($path)|Out-Null;Write-Host 'Opened in File Explorer.'}catch{Write-Host 'Could not open File Explorer; the path above is still available.'}
 }
}
function Ask-Project {
 $p=Select-GuidedProject
 if($p){return $p.project_id}
 return $null
}
function Advanced-ProjectsMenu {
 while($true){
  Write-Host '';Write-Host 'ADVANCED — PROJECT LIFECYCLE';Write-Host '[1] LIST  [2] ADD PROJECT  [3] EDIT PROJECT  [4] ADD PARTICIPANT';Write-Host '[5] EDIT PARTICIPANT  [6] SET/REPLACE MAIN  [7] ADD/REPLACE EXTENSION';Write-Host '[8] REMOVE/DEACTIVATE  [9] APPLY CATALOG  [10] VERIFY PROJECT  [0] BACK'
  $choice=Read-Ui 'Select'
  switch($choice){
   '1' {$null=Invoke-GuidedAction {Show-Value (Read-WorkerCatalog -WorkerRoot $WorkerRoot -AllowMissing)}}
   '2' {$script:ProjectId=Read-Ui 'Technical project id';$script:DisplayName=Read-Ui 'Display name';$null=Invoke-GuidedAction {Run-AddProject}}
   '3' {$script:ProjectId=Ask-Project;$script:DisplayName=Read-Ui 'New display name';$null=Invoke-GuidedAction {Run-EditProject}}
   '4' {$script:ProjectId=Ask-Project;$script:ParticipantId=Read-Ui 'Technical participant id';$script:Role=Read-Ui 'Role';$script:Platform='ONEC';$null=Invoke-GuidedAction {Run-AddParticipant}}
   '5' {$script:ProjectId=Ask-Project;$script:ParticipantId=Read-Ui 'Technical participant id';$script:Role=Read-Ui 'New role';$null=Invoke-GuidedAction {Run-EditParticipant}}
   '6' {$script:ProjectId=Ask-Project;$script:ParticipantId=Read-Ui 'Technical participant id';$script:SourcePath=Read-Ui 'Direct unpacked 1C Main folder';$script:ReplaceExisting=(Read-Ui 'Replace managed copy on APPLY? y/N') -match '^[Yy]$';$null=Invoke-GuidedAction {Run-SetMain}}
   '7' {$script:ProjectId=Ask-Project;$script:ParticipantId=Read-Ui 'Technical participant id';$script:ExtensionId=Read-Ui 'Technical extension id';$script:SourcePath=Read-Ui 'Direct unpacked extension folder';$script:ReplaceExisting=(Read-Ui 'Replace/reactivate existing extension on APPLY? y/N') -match '^[Yy]$';$null=Invoke-GuidedAction {Run-AddExtension}}
   '8' {$script:ProjectId=Ask-Project;$script:Kind=(Read-Ui 'PROJECT/PARTICIPANT/MAIN/EXTENSION').ToUpperInvariant();$script:ParticipantId=if($script:Kind -ne 'PROJECT'){Read-Ui 'Technical participant id'}else{$null};$script:ExtensionId=if($script:Kind -eq 'EXTENSION'){Read-Ui 'Technical extension id'}else{$null};$null=Invoke-GuidedAction {Run-Deactivate}}
   '9' {$script:ProjectId=Ask-Project;$null=Invoke-GuidedAction {Run-Apply}}
   '10' {$script:ProjectId=Ask-Project;$null=Invoke-GuidedAction {Run-Verify}}
   '0' {return}
   default {Write-Host 'FAIL: Unknown Advanced action. Choose one of the displayed numbers.'}
  }
 }
}
function Advanced-DiagnosticsMenu {
 while($true){
  Write-Host '';Write-Host 'ADVANCED — SETTINGS / DIAGNOSTICS';Write-Host '[1] STATUS  [2] CURRENT OPERATION  [3] RECENT OPERATIONS';Write-Host '[4] LOGS  [5] COMPONENT/HELPER STATE  [6] EXPORT DIAGNOSTICS';Write-Host '[7] UPDATE CHATGPT ENROLLMENT  [0] BACK'
  switch(Read-Ui 'Select'){
   '1' {$null=Invoke-GuidedAction {Show-StatusReadable (Get-WorkerStatus -WorkerRoot $WorkerRoot -ProgramDataRoot $ProgramDataRoot)}}
   '2' {$null=Invoke-GuidedAction {Show-CurrentOperation}}
   '3' {$null=Invoke-GuidedAction {Show-RecentOperations}}
   '4' {$null=Invoke-GuidedAction {Show-OperationLogs}}
   '5' {$null=Invoke-GuidedAction {Show-Value (Get-WorkerDiagnostics -WorkerRoot $WorkerRoot -ProgramDataRoot $ProgramDataRoot)}}
   '6' {$null=Invoke-GuidedAction {Show-Value (Export-WorkerDiagnosticBundle -WorkerRoot $WorkerRoot -ProgramDataRoot $ProgramDataRoot)}}
   '7' {$null=Invoke-GuidedAction {Run-Settings}}
   '0' {return}
   default {Write-Host 'FAIL: Unknown Advanced action. Choose one of the displayed numbers.'}
  }
 }
}
function Advanced-Menu {
 $oldAdvanced=$script:InAdvancedMenu
 $script:InAdvancedMenu=$true
 try{
 while($true){
  Write-Host ''
  Write-Host 'ADVANCED — technical lifecycle and diagnostics'
  Write-Host '[1] Project lifecycle  [2] Diagnostics / settings  [3] Verify / repair  [4] Safe uninstall  [0] Back'
  switch(Read-Ui 'Select'){
   '1' {Advanced-ProjectsMenu}
   '2' {Advanced-DiagnosticsMenu}
   '3' {$script:ProjectId=Ask-Project;if($script:ProjectId){$null=Invoke-GuidedAction {Run-Verify};$v=try{Verify-WorkerProject -ProjectId $script:ProjectId -WorkerRoot $WorkerRoot}catch{$null};if($v -and $v.status -ne 'READY' -and (Read-GuidedYesNo -Prompt 'Run bounded recover-first repair?' -DefaultNo $true)){$null=Invoke-GuidedAction {Run-Repair}}}}
   '4' {$plan=Get-UninstallPlan -WorkerRoot $WorkerRoot -ProgramDataRoot $ProgramDataRoot;Write-Host 'Runtime-only uninstall retains catalog, project Source copies, Output, Detached, audit/logs and reader account.';@($plan.remove)|ForEach-Object{Write-Host ("  REMOVE  "+$_)};if((Read-Ui 'Proceed? type YES') -ceq 'YES'){$script:ConfirmUninstall=$true;$null=Invoke-GuidedAction {Run-Uninstall}}else{Write-Host 'CANCELLED: no changes made.'}}
   '0' {return}
   default {Write-Host 'FAIL: Unknown Advanced action. Choose one of the displayed numbers.'}
  }
 }
 }finally{$script:InAdvancedMenu=$oldAdvanced}
}
function Guided-MainMenu {
 $script:InGuidedMenu=$true
 while($true){
  $ctx=$null
  try{$ctx=Get-GuidedContext}catch{Show-GuidedFailure $_.Exception;$ctx=[pscustomobject]@{state='UNKNOWN';recommended='Open Advanced diagnostics';project=$null;reason='State could not be read safely.'}}
  Show-GuidedHeader $ctx
  if($ctx.state -eq 'RUNNING'){
   Write-Host '[Enter] Show current work status   [S] Stop work   [O] Open Output   [A] Advanced   [Q] Exit'
  }elseif($ctx.state -eq 'STARTING'){
   Write-Host '[Enter] Check connection status   [S] Stop / clear start   [A] Advanced   [Q] Exit'
  }else{
   Write-Host '[Enter] Do recommended action   [P] Choose project   [A] Advanced   [Q] Exit'
  }
  $choice=[string](Read-Ui 'Select')
  if($choice -match '^(?i:q|quit|0)$'){return}
  if($choice -match '^(?i:a|advanced)$'){Advanced-Menu;continue}
  if($choice -match '^(?i:p|project)$'){
   $p=Select-GuidedProject
   if($p){Write-Host ("Selected project: {0}" -f $p.display_name)}
   continue
  }
  if($ctx.state -eq 'RUNNING'){
   if($choice -match '^(?i:s|stop)$'){$null=Invoke-GuidedAction {Run-Stop};continue}
   if($choice -match '^(?i:o|output)$'){Show-GuidedOutput $ctx;continue}
   if(-not [string]::IsNullOrWhiteSpace($choice)){Write-Host 'FAIL: Choose Enter, S, O, A, or Q.';continue}
   $null=Invoke-GuidedAction -ShowOutput {Show-StatusReadable (Get-WorkerStatus -WorkerRoot $WorkerRoot -ProgramDataRoot $ProgramDataRoot)}
   continue
  }
  if($ctx.state -eq 'STARTING'){
   if($choice -match '^(?i:s|stop)$'){$null=Invoke-GuidedAction {Run-Stop};continue}
   if(-not [string]::IsNullOrWhiteSpace($choice)){Write-Host 'FAIL: Choose Enter, S, A, or Q.';continue}
   $null=Invoke-GuidedAction -ShowOutput {Show-StatusReadable (Get-WorkerStatus -WorkerRoot $WorkerRoot -ProgramDataRoot $ProgramDataRoot)}
   continue
  }
  if(-not [string]::IsNullOrWhiteSpace($choice)){Write-Host 'FAIL: Choose Enter for the recommended action, P, A, or Q.';continue}
  switch($ctx.state){
   'NOT_INSTALLED' {
    Write-Host 'This installs the local runtime and may ask for Windows administrator approval.'
    if(Invoke-GuidedAction {Run-Install}){Write-Host 'SUCCESS: Installation step completed.';Write-Host 'Next: the menu will show the next required action.'}
   }
   'REMOTE_AUTH_MISSING' {
    Write-Host 'Connect ChatGPT stores the enrollment value locally with restricted permissions; it is never printed or logged.'
    if(Invoke-GuidedAction {Run-Settings}){Write-Host 'SUCCESS: ChatGPT connection settings were saved.'}
   }
   'NO_PROJECTS' {Invoke-GuidedProjectSetup $ctx}
   'PROJECT_DRAFT' {Invoke-GuidedProjectSetup $ctx}
   'PROJECT_NEEDS_APPLY' {
    if(Complete-GuidedProject $ctx.project.project_id){
     if(Read-GuidedYesNo -Prompt 'Project is ready. Start work now?' -DefaultNo $false -Help 'Yes starts a bounded ChatGPT task. No keeps the ready project for later.'){Invoke-GuidedStart $ctx.project.project_id}
    }
   }
   'PROJECT_NEEDS_VERIFY' {
    $script:ProjectId=$ctx.project.project_id
    Write-Host 'Checking the managed project copy and attempting only bounded recover-first repair if needed.'
    $null=Invoke-GuidedAction {Run-Repair}
   }
   'PROJECT_READY' {Invoke-GuidedStart $ctx.project.project_id}
   'START_INCOMPLETE' {
    Write-Host 'Clearing only the incomplete local start/admission state. Project Source and Output are retained.'
    if(Invoke-GuidedAction {Run-Stop}){Write-Host 'SUCCESS: Incomplete start state was cleared.';Write-Host 'Next: Start work again and enter the OneCSourceReader password.'}
   }
   'RECOVERY_REQUIRED' {Invoke-GuidedRecovery $ctx}
   default {Write-Host 'FAIL: Guided state is unavailable.';Write-Host 'Next: open Advanced > Diagnostics.'}
  }
 }
}

if($Mode -eq 'MENU'){Guided-MainMenu}else{Invoke-CommandMode}
