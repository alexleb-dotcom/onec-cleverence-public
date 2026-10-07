param(
  [string]$PackageRoot=(Split-Path -Parent $PSScriptRoot),
  [string]$DotnetPath
)
$ErrorActionPreference='Stop'
if([string]::IsNullOrWhiteSpace($DotnetPath)){$DotnetPath=Join-Path $env:LOCALAPPDATA 'OneCArchitecture\dotnet-10.0.401\dotnet.exe'}
$project=Join-Path $PackageRoot 'control-center\OneCArchitecture.ControlCenter'
$results=@()
function Rec([string]$name,[bool]$pass,[string]$detail=''){
  $script:results+=,[pscustomobject]@{name=$name;pass=$pass;detail=$detail}
  if(-not $pass){throw ('ASSERTION_FAILED:'+$name+':'+$detail)}
}
$csproj=Get-Content -LiteralPath (Join-Path $project 'OneCArchitecture.ControlCenter.csproj') -Raw -Encoding UTF8
$xaml=Get-Content -LiteralPath (Join-Path $project 'MainWindow.xaml') -Raw -Encoding UTF8
$main=Get-Content -LiteralPath (Join-Path $project 'MainWindow.xaml.cs') -Raw -Encoding UTF8
$appXaml=Get-Content -LiteralPath (Join-Path $project 'App.xaml') -Raw -Encoding UTF8
$app=Get-Content -LiteralPath (Join-Path $project 'App.xaml.cs') -Raw -Encoding UTF8
$client=Get-Content -LiteralPath (Join-Path $project 'WorkerClient.cs') -Raw -Encoding UTF8
$prefs=Get-Content -LiteralPath (Join-Path $project 'PreferencesStore.cs') -Raw -Encoding UTF8
$theme=Get-Content -LiteralPath (Join-Path $project 'ThemeService.cs') -Raw -Encoding UTF8
$startup=Get-Content -LiteralPath (Join-Path $project 'StartupRegistration.cs') -Raw -Encoding UTF8
$manifest=Get-Content -LiteralPath (Join-Path $project 'app.manifest') -Raw -Encoding UTF8
$en=Get-Content -LiteralPath (Join-Path $project 'Resources\Strings.resx') -Raw -Encoding UTF8
$ru=Get-Content -LiteralPath (Join-Path $project 'Resources\Strings.ru.resx') -Raw -Encoding UTF8
$all=$xaml+$main+$appXaml+$app+$client+$prefs+$theme
Rec 'dotnet10_wpf_self_contained' ($csproj -match '<TargetFramework>net10.0-windows</TargetFramework>' -and $csproj -match '<UseWPF>true</UseWPF>' -and $csproj -match '<RuntimeIdentifier>win-x64</RuntimeIdentifier>' -and $csproj -match '<SelfContained>true</SelfContained>') ''
Rec 'no_webview_loopback_service' (-not ($all -match 'WebView2|HttpListener|Kestrel|WindowsService|ServiceBase')) ''
Rec 'no_ps7_dependency' (-not ($client -match 'pwsh|PowerShell 7')) ''
Rec 'typed_worker_allowlist' ($client -match 'enum WorkerAction' -and $client -match 'IReadOnlyDictionary<WorkerAction, string>' -and $client -match 'ArgumentList\.Add' -and -not ($client -match 'cmd\.exe|/c |CommandLine=')) ''
Rec 'final_lifecycle_mutations_enabled' ($main -match '_mutationsEnabled = true') ''
$close=$main.Substring($main.IndexOf('private void Window_Closing'))
Rec 'close_hides_only' ($main -match 'Window_Closing' -and $main -match 'e\.Cancel = true;\s*Hide\(\);' -and -not ($close -match 'WorkerAction\.Stop')) ''
Rec 'tray_exit_is_ui_only' ($app -match 'NotifyIcon' -and $app -match 'IsExplicitExit' -and $app -match 'Shutdown\(\)' -and -not ($app -match 'WorkerAction|STOP|Stop-Worker')) ''
$sections=@('HomePage','ProjectsPage','WorkPage','ActivityPage','MaintenancePage','SettingsPage','AdvancedPage')
Rec 'seven_navigation_sections' (@($sections|Where-Object{$xaml -match ('x:Name="'+[regex]::Escape($_)+'"')}).Count -eq 7) ''
$cards=@('McpTitleLabel','CheckpointTitleLabel','SourceTitleLabel','OutputTitleLabel')
Rec 'home_cards_present' (@($cards|Where-Object{$xaml -match ('x:Name="'+[regex]::Escape($_)+'"')}).Count -eq 4) ''
Rec 'activity_timeline_present' ($xaml -match 'x:Name="ActivityList"' -and $xaml -match 'Recent MCP activity') ''
Rec 'advanced_owns_technical_json' ($xaml -match 'x:Name="AdvancedText"' -and $main -match 'AdvancedText\.Text = ctx\.ToJsonString') ''
Rec 'theme_system_light_dark' ($theme -match 'AppsUseLightTheme' -and $xaml -match 'ThemeCombo' -and $xaml -match 'Tag="system"' -and $xaml -match 'Tag="light"' -and $xaml -match 'Tag="dark"') ''
$enXml=[xml]$en;$ruXml=[xml]$ru;$enHome=[string](($enXml.root.data|Where-Object{$_.name -eq 'NavHome'}).value);$ruHome=[string](($ruXml.root.data|Where-Object{$_.name -eq 'NavHome'}).value)
$enKeys=@($enXml.root.data|ForEach-Object{[string]$_.name}|Sort-Object);$ruKeys=@($ruXml.root.data|ForEach-Object{[string]$_.name}|Sort-Object)
Rec 'ru_en_resources' ($enHome -eq 'Home' -and -not [string]::IsNullOrWhiteSpace($ruHome) -and $ruHome -ne $enHome) ''
Rec 'ru_en_key_parity' (($enKeys -join ',') -eq ($ruKeys -join ',')) ('en='+$enKeys.Count+' ru='+$ruKeys.Count)
Rec 'per_monitor_v2_dpi' ($csproj -match '<ApplicationHighDpiMode>PerMonitorV2</ApplicationHighDpiMode>' -and $manifest -match 'longPathAware' -and $csproj -match '<ApplicationManifest>app\.manifest</ApplicationManifest>') ''
Rec 'startup_explicit_only' ($xaml -match 'Start Control Center with Windows \(operator choice\)' -and $startup -match 'Registry\.CurrentUser' -and $main -match 'StartupCheckBox_Changed' -and -not ($app -match 'StartupRegistration\.Apply')) ''
Rec 'ui_preferences_only' ($prefs -match 'Language' -and $prefs -match 'Theme' -and $prefs -match 'StartWithWindows' -and -not ($prefs -match 'project|task|account|admission|secret|credential')) ''
Rec 'no_password_capture' (-not ($all -match 'PasswordBox|OneCSourceReader password|savecred|CredentialManager|NetworkCredential')) ''
Rec 'worker_context_poll_only' ($main -match 'GetContextAsync' -and $main -match 'DispatcherTimer' -and -not ($main -match 'source_context|source_read|Invoke-SourceAcquisition')) ''
Rec 'accepted_s4_policy_no_invented_ui_limits' ($main -match 'AccountingPending' -and $en -match 'Finite S4 task policy is accepted' -and -not ($main -match 'task_requests_limit|task_result_bytes_limit|task_requests_remaining|task_result_bytes_remaining')) ''
Rec 'open_source_output_human_only' ($main -match 'OpenSource_Click' -and $main -match 'OpenOutput_Click' -and $main -match 'explorer\.exe') ''
Rec 'dpi_keyboard_accessibility_basics' ($xaml -match 'UseLayoutRounding="True"' -and $xaml -match 'KeyboardNavigation\.TabNavigation="Cycle"' -and $xaml -match 'AutomationProperties\.Name') ''
Rec 'source_update_typed_ui_only' ($client -match 'PrepareSourceUpdate' -and $client -match 'AcceptSourceUpdate' -and $client -match 'CancelSourceUpdate' -and $main -match 'WorkerAction\.PrepareSourceUpdate' -and $main -match 'WorkerAction\.AcceptSourceUpdate' -and $main -match 'WorkerAction\.CancelSourceUpdate' -and $xaml -match 'PrepareSourceUpdateButton' -and $xaml -match 'OpenIncomingButton') ''
Rec 'source_update_no_ui_filesystem_publish' (-not ($main -match 'File\.Move|Directory\.Move|File\.Copy|CopyTo|MoveTo') -and $main -match 'OpenIncoming_Click' -and $main -match 'explorer\.exe') ''
Rec 'dark_combo_popup_explicit_contrast' ($appXaml -match 'PopupBrush' -and $appXaml -match 'ComboBoxItem' -and $appXaml -match 'IsDropDownOpen' -and $appXaml -match 'Foreground="\{DynamicResource TextBrush\}"' -and $theme -match 'PopupBrush' -and $theme -match 'HoverBrush' -and $theme -match 'SelectionBrush') ''
Rec 'activity_datagrid_explicit_contrast' ($xaml -match '<DataGrid Grid.Row="1" x:Name="ActivityList"' -and $appXaml -match 'DataGridColumnHeader' -and $appXaml -match 'DataGridCell' -and $appXaml -match 'SelectionBrush') ''
$launcherText=Get-Content -LiteralPath (Join-Path $PackageRoot 'OneCChatWorker.ps1') -Raw -Encoding UTF8
Rec 'utf8_ps51_process_boundary' ($client -match 'StandardOutputEncoding = new UTF8Encoding\(false\)' -and $client -match 'StandardErrorEncoding = new UTF8Encoding\(false\)' -and $launcherText -match '\[Console\]::OutputEncoding=\$utf8' -and $launcherText -match '\$OutputEncoding=\$utf8') ''
Rec 'bounded_home_error_advanced_raw' ($main -match 'ShowContextFailure' -and $main -match 'UiContextReason' -and $main -match 'Bound\(raw, 4000\)' -and $main -match 'AdvancedText\.Text' -and -not ($main -match 'RecommendationReasonText\.Text = result\.StandardError')) ''
Rec 'full_operator_localization_surface' ($main -match 'SourceUpdateTitleLabel\.Text = Localization\.Get' -and $main -match 'WorkPromptLabel\.Text = Localization\.Get' -and $main -match 'CurrentOperationLabel\.Text = Localization\.Get' -and $main -match 'ActivityList\.Columns\[0\]\.Header = Localization\.Get' -and $main -match 'StartupCheckBox\.Content = Localization\.Get' -and $enKeys.Count -ge 80 -and $ruKeys.Count -eq $enKeys.Count -and $ru -match '[\u0400-\u04FF]' -and -not $ru.Contains([char]0xfffd)) ''
Rec 'typography_dpi_closure' ($appXaml -match 'Segoe UI Variable Text, Segoe UI' -and $appXaml -match 'TextOptions\.TextFormattingMode' -and $csproj -match '<ApplicationHighDpiMode>PerMonitorV2</ApplicationHighDpiMode>') ''
Rec 'build_tool_available' (Test-Path -LiteralPath $DotnetPath -PathType Leaf) $DotnetPath
$env:DOTNET_CLI_TELEMETRY_OPTOUT='1';$env:DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1'
& $DotnetPath build (Join-Path $project 'OneCArchitecture.ControlCenter.csproj') -c Release --nologo --no-restore | Out-Host
Rec 'release_build_pass' ($LASTEXITCODE -eq 0) ("exit="+$LASTEXITCODE)
Write-Host ("CONTROL_CENTER_FINAL_UI_PASS checks={0}" -f $results.Count)
$results|ConvertTo-Json -Depth 6
