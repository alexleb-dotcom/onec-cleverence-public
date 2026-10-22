#ifndef Payload
  #error Payload must be an explicit built package directory
#endif
[Setup]
AppId=OneCOrbit.SliceA
AppName=OneC Orbit
AppVersion=1.0.0-preview1
DefaultDirName={autopf}\OneCOrbit
DefaultGroupName=OneC Orbit
OutputBaseFilename=OneCOrbit-Setup
OutputDir={#Output}
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
UninstallDisplayName=OneC Orbit
UninstallDisplayIcon={app}\package\control-center\publish\OneCArchitecture.ControlCenter.exe
CloseApplications=no
SetupLogging=yes

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"
[Files]
Source: "{#Payload}\*"; DestDir: "{app}\package"; Flags: recursesubdirs createallsubdirs
Source: "SetupRuntime.ps1"; DestDir: "{app}"
[UninstallDelete]
Type: files; Name: "{app}\setup-runtime.log"
Type: files; Name: "{app}\install-receipt.json"
Type: files; Name: "{app}\install-intent.json"
Type: files; Name: "{app}\install-journal.json"
Type: files; Name: "{app}\install-journal.json.tmp"
Type: files; Name: "{app}\setup-shortcut.lnk"
Type: dirifempty; Name: "{group}"
Type: dirifempty; Name: "{app}"
[Messages]
WelcomeLabel2=This setup installs the WPF interface and Worker runtime with zero projects. UAC is required for protected runtime and Source ownership. Existing and legacy installations require separately authorized recovery or migration. Projects are retained on uninstall. Remote Helper authorization remains a separate step.
[Code]
var RuntimeInstalled: Boolean;
function GetCustomSetupExitCode(): Integer;
begin
  if RuntimeInstalled then Result := 0 else Result := 10;
end;
function WorkerRoot(Param: String): String;
begin Result := ExpandConstant('{param:WORKERROOT|C:\OneCOrbit}'); end;
function DataRoot(Param: String): String;
begin
  Result := ExpandConstant('{param:DATAROOT|}');
  if Result = '' then Result := ExpandConstant('{commonappdata}\OneCOrbit');
end;
function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if DirExists(ExpandConstant('{app}')) or DirExists(WorkerRoot('')) or DirExists(DataRoot('')) or
     DirExists('C:\OneCChatWorker') or DirExists('C:\ProgramData\OneCChatWorker') or
     DirExists(ExpandConstant('{localappdata}\Programs\OneCOrbit')) then
    Result := 'MIGRATION_REQUIRED: Existing or legacy paths are retained. Installation cannot overwrite them.';
end;
procedure CurStepChanged(CurStep: TSetupStep);
var ExitCode: Integer; Args: String;
begin
  if CurStep = ssPostInstall then begin
    Args := '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{app}\SetupRuntime.ps1') + '" -Mode Install -AppRoot "' + ExpandConstant('{app}') + '" -WorkerRoot "' + WorkerRoot('') + '" -DataRoot "' + DataRoot('') + '" -ShortcutRoot "' + ExpandConstant('{group}') + '"';
    RuntimeInstalled := Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'), Args, '', SW_HIDE, ewWaitUntilTerminated, ExitCode);
    Log('Runtime setup exit code: ' + IntToStr(ExitCode));
    RuntimeInstalled := RuntimeInstalled and (ExitCode = 0) and FileExists(ExpandConstant('{app}\install-receipt.json'));
    if not RuntimeInstalled then
      RaiseException('Runtime installation failed. See setup-runtime.log; recovery state is retained.');
  end;
end;
function InitializeUninstall(): Boolean;
var ExitCode: Integer;
begin
  Result := Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'), '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{app}\SetupRuntime.ps1') + '" -Mode Uninstall -AppRoot "' + ExpandConstant('{app}') + '"', '', SW_HIDE, ewWaitUntilTerminated, ExitCode) and (ExitCode = 0);
  if not Result then MsgBox('Uninstall is on hold: active state, changed owned files or missing receipt requires recovery. Projects are retained.', mbError, MB_OK);
end;
