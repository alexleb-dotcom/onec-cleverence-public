param(
 [ValidateSet('MENU','PRECHECK','INSTALL','STATUS','LIST','ADD_PROJECT','ADD_PARTICIPANT','SET_MAIN','ADD_EXTENSION','DEACTIVATE','APPLY','VERIFY','REPAIR','START','STOP','SETTINGS','UNINSTALL')]
 [string]$Mode='MENU',
 [string]$ProjectId,[string]$ParticipantId,[string]$ExtensionId,[string]$SourcePath,[string]$DisplayName,[string]$Role,
 [ValidateSet('ONEC','CLEVERENCE')][string]$Platform='ONEC',[string]$TaskId,[ValidateSet('PROJECT','PARTICIPANT','EXTENSION')][string]$Kind='PROJECT',
 [switch]$ReplaceExisting,[string]$WorkerRoot='C:\OneCChatWorker',[string]$ProgramDataRoot='C:\ProgramData\OneCChatWorker',[switch]$SkipDependencies
)
$ErrorActionPreference='Stop'
$PackageRoot=$PSScriptRoot
$InstalledCore=Join-Path $ProgramDataRoot 'product\OneCChatWorker.Core.psm1'
$PackageCore=Join-Path $PackageRoot 'core\OneCChatWorker.Core.psm1'
$Core=if(Test-Path -LiteralPath $InstalledCore){$InstalledCore}else{$PackageCore}
if(-not(Test-Path -LiteralPath $Core -PathType Leaf)){throw "CORE_NOT_FOUND: $Core"}
Import-Module $Core -Force

function Is-Admin {
 $id=[Security.Principal.WindowsIdentity]::GetCurrent();$p=New-Object Security.Principal.WindowsPrincipal($id)
 $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}
function Require-AdminOrRelaunch {
 param([string]$RequestedMode)
 if(Is-Admin){return}
 $argsList=@('-NoProfile','-ExecutionPolicy','Bypass','-File',$PSCommandPath,'-Mode',$RequestedMode,'-WorkerRoot',$WorkerRoot,'-ProgramDataRoot',$ProgramDataRoot)
 if($SkipDependencies){$argsList+='-SkipDependencies'}
 $p=Start-Process -FilePath 'powershell.exe' -Verb RunAs -ArgumentList $argsList -Wait -PassThru
 exit $p.ExitCode
}
function Need([string]$Value,[string]$Name){if([string]::IsNullOrWhiteSpace($Value)){throw "ARG_REQUIRED: $Name"};$Value}
function Show-Json($Value){$Value|ConvertTo-Json -Depth 30}

function Invoke-CommandMode {
 switch($Mode){
  'PRECHECK' {Show-Json (Invoke-Precheck);break}
  'INSTALL' {Require-AdminOrRelaunch 'INSTALL';Show-Json (Install-OneCChatWorker -PackageRoot $PackageRoot -WorkerRoot $WorkerRoot -ProgramDataRoot $ProgramDataRoot -SkipDependencies:$SkipDependencies);break}
  'STATUS' {Show-Json (Get-WorkerStatus -WorkerRoot $WorkerRoot -ProgramDataRoot $ProgramDataRoot);break}
  'LIST' {Show-Json (Read-WorkerCatalog -WorkerRoot $WorkerRoot -AllowMissing);break}
  'ADD_PROJECT' {Show-Json (New-WorkerProject -ProjectId (Need $ProjectId ProjectId) -DisplayName $DisplayName -WorkerRoot $WorkerRoot);break}
  'ADD_PARTICIPANT' {Show-Json (Add-WorkerParticipant -ProjectId (Need $ProjectId ProjectId) -ParticipantId (Need $ParticipantId ParticipantId) -Platform $Platform -Role $Role -WorkerRoot $WorkerRoot);break}
  'SET_MAIN' {Show-Json (Set-WorkerMain -ProjectId (Need $ProjectId ProjectId) -ParticipantId (Need $ParticipantId ParticipantId) -SourcePath (Need $SourcePath SourcePath) -ReplaceExisting:$ReplaceExisting -WorkerRoot $WorkerRoot);break}
  'ADD_EXTENSION' {Show-Json (Add-WorkerExtension -ProjectId (Need $ProjectId ProjectId) -ParticipantId (Need $ParticipantId ParticipantId) -ExtensionId (Need $ExtensionId ExtensionId) -SourcePath (Need $SourcePath SourcePath) -ReplaceExisting:$ReplaceExisting -WorkerRoot $WorkerRoot);break}
  'DEACTIVATE' {Disable-WorkerCatalogItem -Kind $Kind -ProjectId (Need $ProjectId ProjectId) -ParticipantId $ParticipantId -ExtensionId $ExtensionId -WorkerRoot $WorkerRoot;Show-Json (Read-WorkerCatalog $WorkerRoot);break}
  'APPLY' {Show-Json (Apply-WorkerProject -ProjectId (Need $ProjectId ProjectId) -WorkerRoot $WorkerRoot);break}
  'VERIFY' {Show-Json (Verify-WorkerProject -ProjectId (Need $ProjectId ProjectId) -WorkerRoot $WorkerRoot);break}
  'REPAIR' {Show-Json (Repair-WorkerProject -ProjectId (Need $ProjectId ProjectId) -WorkerRoot $WorkerRoot);break}
  'START' {Show-Json (Start-WorkerAdmission -ProjectId (Need $ProjectId ProjectId) -TaskId (Need $TaskId TaskId) -WorkerRoot $WorkerRoot -ProgramDataRoot $ProgramDataRoot);break}
  'STOP' {Require-AdminOrRelaunch 'STOP';Show-Json (Stop-WorkerAdmission -ProgramDataRoot $ProgramDataRoot);break}
  'SETTINGS' {Require-AdminOrRelaunch 'SETTINGS';Set-HelperEnrollmentSecret -ProgramDataRoot $ProgramDataRoot;Write-Host 'SETTINGS_UPDATED';break}
  'UNINSTALL' {Show-Json (Get-UninstallPlan -WorkerRoot $WorkerRoot -ProgramDataRoot $ProgramDataRoot);break}
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
  Write-Host '';Write-Host 'PROJECTS';Write-Host '[1] LIST  [2] ADD PROJECT  [3] ADD PARTICIPANT  [4] SET/REPLACE MAIN';Write-Host '[5] ADD EXTENSION  [6] DEACTIVATE  [7] APPLY  [8] VERIFY  [0] BACK'
  switch(Read-Host 'Select'){
   '1' {Show-Json (Read-WorkerCatalog -WorkerRoot $WorkerRoot -AllowMissing)}
   '2' {$id=Read-Host 'Project id';$name=Read-Host 'Display name';Show-Json (New-WorkerProject $id $name $WorkerRoot)}
   '3' {$pid=Ask-Project;$part=Read-Host 'Participant id';$role=Read-Host 'Role';Show-Json (Add-WorkerParticipant $pid $part 'ONEC' $role $WorkerRoot)}
   '4' {$pid=Ask-Project;$part=Read-Host 'Participant id';$src=Read-Host 'Direct unpacked 1C Main folder';$rep=(Read-Host 'Replace existing on APPLY? y/N') -match '^[Yy]$';Show-Json (Set-WorkerMain $pid $part $src -ReplaceExisting:$rep -WorkerRoot $WorkerRoot)}
   '5' {$pid=Ask-Project;$part=Read-Host 'Participant id';$eid=Read-Host 'Extension id';$src=Read-Host 'Direct unpacked extension folder';Show-Json (Add-WorkerExtension $pid $part $eid $src -WorkerRoot $WorkerRoot)}
   '6' {$pid=Ask-Project;$kind=(Read-Host 'PROJECT/PARTICIPANT/EXTENSION').ToUpperInvariant();$part=if($kind -ne 'PROJECT'){Read-Host 'Participant id'}else{$null};$eid=if($kind -eq 'EXTENSION'){Read-Host 'Extension id'}else{$null};Disable-WorkerCatalogItem $kind $pid $part $eid $WorkerRoot;Write-Host 'DEACTIVATED_IN_CATALOG'}
   '7' {$pid=Ask-Project;Show-Json (Apply-WorkerProject $pid $WorkerRoot)}
   '8' {$pid=Ask-Project;Show-Json (Verify-WorkerProject $pid $WorkerRoot)}
   '0' {return}
  }
 }
}
function Main-Menu {
 while($true){
  Write-Host '';Write-Host 'OneCChatWorker';Write-Host '[1] START PROJECT  [2] STOP  [3] STATUS  [4] PROJECTS';Write-Host '[5] VERIFY/REPAIR  [6] SETTINGS/DIAGNOSTICS  [7] INSTALL/UPDATE  [8] UNINSTALL GUIDANCE  [0] EXIT'
  switch(Read-Host 'Select'){
   '1' {$pid=Ask-Project;$task=Read-Host 'Task id';Show-Json (Start-WorkerAdmission $pid $task $WorkerRoot $ProgramDataRoot)}
   '2' {if(!(Is-Admin)){Write-Host 'STOP requires elevation; use: OneCChatWorker.ps1 -Mode STOP'}else{Show-Json (Stop-WorkerAdmission $ProgramDataRoot)}}
   '3' {Show-Json (Get-WorkerStatus $WorkerRoot $ProgramDataRoot)}
   '4' {Projects-Menu}
   '5' {$pid=Ask-Project;$v=Verify-WorkerProject $pid $WorkerRoot;Show-Json $v;if($v.status -ne 'READY' -and (Read-Host 'Run bounded repair? y/N') -match '^[Yy]$'){Show-Json (Repair-WorkerProject $pid $WorkerRoot)}}
   '6' {Show-Json (Invoke-Precheck);Write-Host 'For remote enrollment use: OneCChatWorker.ps1 -Mode SETTINGS'}
   '7' {Write-Host 'Use: OneCChatWorker.ps1 -Mode INSTALL'}
   '8' {Show-Json (Get-UninstallPlan $WorkerRoot $ProgramDataRoot)}
   '0' {return}
  }
 }
}

if($Mode -eq 'MENU'){Main-Menu}else{Invoke-CommandMode}