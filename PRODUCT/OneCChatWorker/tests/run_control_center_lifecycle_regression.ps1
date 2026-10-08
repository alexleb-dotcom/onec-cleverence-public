param([string]$PackageRoot=(Split-Path -Parent $PSScriptRoot))
$ErrorActionPreference='Stop'
$project=Join-Path $PackageRoot 'control-center\OneCArchitecture.ControlCenter'
$launcher=Get-Content -LiteralPath (Join-Path $PackageRoot 'OneCChatWorker.ps1') -Raw -Encoding UTF8
$client=Get-Content -LiteralPath (Join-Path $project 'WorkerClient.cs') -Raw -Encoding UTF8
$main=Get-Content -LiteralPath (Join-Path $project 'MainWindow.xaml.cs') -Raw -Encoding UTF8
$wizard=Get-Content -LiteralPath (Join-Path $project 'ProjectWizardWindow.xaml.cs') -Raw -Encoding UTF8
$r=@()
function Rec($n,$p,$d=''){$script:r+=,[pscustomobject]@{name=$n;pass=[bool]$p;detail=$d};if(-not $p){throw ('ASSERTION_FAILED:'+$n+':'+$d)}}
Rec 'launcher_update_mode_exact' ($launcher -match "'UPDATE'" -and $launcher -match 'function Run-Update') ''
$update=$launcher.Substring($launcher.IndexOf('function Run-Update'),$launcher.IndexOf('function Run-AddProject')-$launcher.IndexOf('function Run-Update'))
Rec 'update_reuses_install_owner' ($update.Contains('Install-OneCChatWorker') -and $update.Contains('network_download_performed=$false')) ''
Rec 'update_no_remote_downloader' (-not ($update -match 'Invoke-WebRequest|Start-BitsTransfer|curl|wget|HttpClient')) ''
$expected=@('UI_CONTEXT','APPLY','VERIFY','REPAIR','START','CONTINUE','STOP','UPDATE','ADD_PROJECT','ADD_PARTICIPANT','SET_MAIN','ADD_EXTENSION','PREPARE_SOURCE_UPDATE','ACCEPT_SOURCE_UPDATE','CANCEL_SOURCE_UPDATE')
foreach($m in $expected){Rec ('typed_mode_'+$m) ($client -match ('"'+$m+'"')) ''}
Rec 'no_generic_mode_parameter' (-not ($client -match 'string mode|RequestedMode|Mode = args')) ''
Rec 'argumentlist_no_shell_concat' ($client -match 'ArgumentList\.Add' -and -not ($client -match 'cmd\.exe| -Command |ProcessStartInfo\("pwsh')) ''
Rec 'source_update_args_are_fixed_typed' ($client -match 'ArtifactSelection' -and $client -match 'SelectedArtifactFullSafeImport' -and $main -match 'new\(ProjectId: projectId, ArtifactSelection: artifact\.Key\)') ''
Rec 'mutations_enabled_after_readonly_gate' ($main -match '_mutationsEnabled = true') ''
Rec 'wizard_fixed_sequence' ($main -match 'WorkerAction\.AddProject' -and $main -match 'WorkerAction\.AddParticipant' -and $main -match 'WorkerAction\.SetMain' -and $main -match 'WorkerAction\.AddExtension' -and $main -match 'WorkerAction\.Apply') ''
Rec 'wizard_stop_on_failure' ($main -match 'if \(result\.ExitCode != 0\)' -and $main -match 'if \(ext\.ExitCode != 0\)') ''
Rec 'worker_revalidates_main_path' ($launcher -match 'Set-WorkerMain' -and $wizard -match 'Configuration\.xml') ''
Rec 'ascii_technical_ids' ($client -match 'c <= 127' -and $wizard -match 'c <= 127' -and $wizard -match 'SHA256') ''
Rec 'no_password_capture' (-not (($client+$main+$wizard) -match 'PasswordBox|NetworkCredential|SecureString|OneCSourceReader password|savecred')) ''
$close=$main.Substring($main.IndexOf('private void Window_Closing'))
Rec 'gui_close_never_stop' (-not ($close -match 'WorkerAction\.Stop|STOP|Stop-Worker')) ''
Write-Host ("CONTROL_CENTER_LIFECYCLE_PASS checks={0}" -f $r.Count)
$r|ConvertTo-Json -Depth 5
