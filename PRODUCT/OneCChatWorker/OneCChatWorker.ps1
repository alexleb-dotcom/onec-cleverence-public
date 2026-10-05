param(
 [ValidateSet('MENU','PRECHECK','INSTALL','STATUS','LIST','ADD_PROJECT','EDIT_PROJECT','ADD_PARTICIPANT','EDIT_PARTICIPANT','SET_MAIN','ADD_EXTENSION','DEACTIVATE','APPLY','VERIFY','REPAIR','START','STOP','SETTINGS','DIAGNOSTICS','VIEW_CURRENT_OPERATION','VIEW_RECENT_OPERATIONS','VIEW_LOGS','EXPORT_DIAGNOSTICS','UNINSTALL')]
 [string]$Mode='MENU',
 [string]$ProjectId,[string]$ParticipantId,[string]$ExtensionId,[string]$SourcePath,[string]$DisplayName,[string]$Role,
 [ValidateSet('ONEC','CLEVERENCE')][string]$Platform='ONEC',[string]$TaskId,[ValidateSet('PROJECT','PARTICIPANT','MAIN','EXTENSION')][string]$Kind='PROJECT',
 [switch]$ReplaceExisting,[string]$WorkerRoot='C:\OneCChatWorker',[string]$ProgramDataRoot='C:\ProgramData\OneCChatWorker',
 [string]$ReaderName='OneCSourceReader',[string]$OperatorIdentity,[string]$RelayUrl='wss://onec-g1q1-relay.alex-lebad1.workers.dev/helper',
 [switch]$SkipDependencies,[switch]$ConfirmUninstall,[switch]$Json,[string]$DiagnosticPath
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
 exit $p.ExitCode
}
function Need([string]$Value,[string]$Name){if([string]::IsNullOrWhiteSpace($Value)){throw "ARG_REQUIRED: $Name"};$Value}
function Show-JsonValue($Value){$Value|ConvertTo-Json -Depth 30}
function Show-Value($Value){
 if($Json){Show-JsonValue $Value;return}
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
 Require-AdminOrRelaunch 'INSTALL'
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
 Require-AdminOrRelaunch 'REPAIR'
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
 Require-AdminOrRelaunch 'STOP'
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
 Require-AdminOrRelaunch 'SETTINGS'
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
 Require-AdminOrRelaunch 'UNINSTALL'
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

function Ask-Project {
 $c=Read-WorkerCatalog -WorkerRoot $WorkerRoot -AllowMissing
 if(-not @($c.projects).Count){throw 'NO_PROJECTS'}
 Write-Host '';for($i=0;$i -lt @($c.projects).Count;$i++){Write-Host ("[{0}] {1} ({2})" -f ($i+1),$c.projects[$i].display_name,$c.projects[$i].project_id)}
 $n=[int](Read-Host 'Project number');if($n -lt 1 -or $n -gt @($c.projects).Count){throw 'INVALID_SELECTION'}
 $c.projects[$n-1].project_id
}
function Projects-Menu {
 while($true){
  Write-Host '';Write-Host 'PROJECTS';Write-Host '[1] LIST  [2] ADD PROJECT  [3] EDIT PROJECT  [4] ADD PARTICIPANT';Write-Host '[5] EDIT PARTICIPANT  [6] SET/REPLACE MAIN  [7] ADD/REPLACE EXTENSION';Write-Host '[8] REMOVE/DEACTIVATE  [9] APPLY CATALOG  [10] VERIFY PROJECT  [0] BACK'
  switch(Read-Host 'Select'){
   '1' {Show-Value (Read-WorkerCatalog -WorkerRoot $WorkerRoot -AllowMissing)}
   '2' {$script:ProjectId=Read-Host 'Project id';$script:DisplayName=Read-Host 'Display name';Run-AddProject}
   '3' {$script:ProjectId=Ask-Project;$script:DisplayName=Read-Host 'New display name';Run-EditProject}
   '4' {$script:ProjectId=Ask-Project;$script:ParticipantId=Read-Host 'Participant id';$script:Role=Read-Host 'Role';$script:Platform='ONEC';Run-AddParticipant}
   '5' {$script:ProjectId=Ask-Project;$script:ParticipantId=Read-Host 'Participant id';$script:Role=Read-Host 'New role';Run-EditParticipant}
   '6' {$script:ProjectId=Ask-Project;$script:ParticipantId=Read-Host 'Participant id';$script:SourcePath=Read-Host 'Direct unpacked 1C Main folder';$script:ReplaceExisting=(Read-Host 'Replace managed copy on APPLY? y/N') -match '^[Yy]$';Run-SetMain}
   '7' {$script:ProjectId=Ask-Project;$script:ParticipantId=Read-Host 'Participant id';$script:ExtensionId=Read-Host 'Extension id';$script:SourcePath=Read-Host 'Direct unpacked extension folder';$script:ReplaceExisting=(Read-Host 'Replace/reactivate existing extension on APPLY? y/N') -match '^[Yy]$';Run-AddExtension}
   '8' {$script:ProjectId=Ask-Project;$script:Kind=(Read-Host 'PROJECT/PARTICIPANT/MAIN/EXTENSION').ToUpperInvariant();$script:ParticipantId=if($script:Kind -ne 'PROJECT'){Read-Host 'Participant id'}else{$null};$script:ExtensionId=if($script:Kind -eq 'EXTENSION'){Read-Host 'Extension id'}else{$null};Run-Deactivate}
   '9' {$script:ProjectId=Ask-Project;Run-Apply}
   '10' {$script:ProjectId=Ask-Project;Run-Verify}
   '0' {return}
  }
 }
}
function Diagnostics-Menu {
 while($true){
  Write-Host '';Write-Host 'SETTINGS / DIAGNOSTICS';Write-Host '[1] STATUS  [2] VIEW CURRENT OPERATION  [3] VIEW RECENT OPERATIONS';Write-Host '[4] VIEW LOGS  [5] SHOW COMPONENT/HELPER STATE  [6] EXPORT DIAGNOSTIC BUNDLE';Write-Host '[7] UPDATE HELPER ENROLLMENT SECRET  [0] BACK'
  switch(Read-Host 'Select'){
   '1' {Show-StatusReadable (Get-WorkerStatus -WorkerRoot $WorkerRoot -ProgramDataRoot $ProgramDataRoot)}
   '2' {Show-CurrentOperation}
   '3' {Show-RecentOperations}
   '4' {Show-OperationLogs}
   '5' {Show-Value (Get-WorkerDiagnostics -WorkerRoot $WorkerRoot -ProgramDataRoot $ProgramDataRoot)}
   '6' {Show-Value (Export-WorkerDiagnosticBundle -WorkerRoot $WorkerRoot -ProgramDataRoot $ProgramDataRoot)}
   '7' {if(Is-Admin){Run-Settings}else{Write-Host 'Use OneCChatWorker.ps1 -Mode SETTINGS to elevate securely.'}}
   '0' {return}
  }
 }
}
function FirstRun-Menu {
 while($true){
  Write-Host '';Write-Host 'OneCChatWorker — not installed or incomplete';Write-Host '[1] PRECHECK  [2] INSTALL / REPAIR  [0] EXIT'
  switch(Read-Host 'Select'){
   '1' {Run-Precheck}
   '2' {if(Is-Admin){Run-Install}else{Write-Host 'INSTALL will request Windows elevation.';Run-Install}}
   '0' {return}
  }
 }
}
function Main-Menu {
 while($true){
  Write-Host '';Write-Host 'OneCChatWorker';Write-Host '[1] START PROJECT  [2] STOP  [3] STATUS  [4] PROJECTS';Write-Host '[5] VERIFY / REPAIR  [6] SETTINGS / DIAGNOSTICS  [7] UPDATE / REINSTALL  [8] UNINSTALL  [0] EXIT'
  switch(Read-Host 'Select'){
   '1' {$script:ProjectId=Ask-Project;$script:TaskId=Read-Host 'Task id';Run-Start}
   '2' {if(Is-Admin){Run-Stop}else{Write-Host 'STOP requires elevation; use OneCChatWorker.ps1 -Mode STOP'}}
   '3' {Show-StatusReadable (Get-WorkerStatus -WorkerRoot $WorkerRoot -ProgramDataRoot $ProgramDataRoot)}
   '4' {Projects-Menu}
   '5' {$script:ProjectId=Ask-Project;Run-Verify;$v=Verify-WorkerProject -ProjectId $script:ProjectId -WorkerRoot $WorkerRoot;if($v.status -ne 'READY' -and (Read-Host 'Run bounded recover-first REPAIR? y/N') -match '^[Yy]$'){Run-Repair}}
   '6' {Diagnostics-Menu}
   '7' {Write-Host 'Re-run INSTALL from the same pinned product package/repository checkout to update safely.'}
   '8' {
    $plan=Get-UninstallPlan -WorkerRoot $WorkerRoot -ProgramDataRoot $ProgramDataRoot
    Write-Host 'Safe uninstall retains catalog, project Source copies, Output, Detached, audit/logs and reader account.'
    @($plan.remove)|ForEach-Object{Write-Host ("  REMOVE  "+$_)}
    if((Read-Host 'Proceed with runtime-only uninstall? type YES') -ceq 'YES'){$script:ConfirmUninstall=$true;Run-Uninstall}else{Write-Host 'CANCELLED — no changes made.'}
   }
   '0' {return}
  }
 }
}

if($Mode -eq 'MENU'){
 if(Test-Path -LiteralPath (Join-Path $ProgramDataRoot 'installed-state.json') -PathType Leaf){Main-Menu}else{FirstRun-Menu}
}else{Invoke-CommandMode}
