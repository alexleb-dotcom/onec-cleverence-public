param(
  [string]$PackageRoot=(Split-Path -Parent $PSScriptRoot),
  [string]$DotnetPath
)
$ErrorActionPreference='Stop'
if([string]::IsNullOrWhiteSpace($DotnetPath)){$DotnetPath=Join-Path $env:LOCALAPPDATA 'OneCArchitecture\dotnet-10.0.401\dotnet.exe'}
Import-Module (Join-Path $PackageRoot 'core\OneCChatWorker.Core.psm1') -Force -DisableNameChecking
Import-Module (Join-Path $PSScriptRoot 'TestScratch.psm1') -Force -DisableNameChecking
$results=@()
function Rec([string]$name,[bool]$pass,[string]$detail=''){
  $script:results+=,[pscustomobject]@{name=$name;pass=$pass;detail=$detail}
  if(-not $pass){throw ('ASSERTION_FAILED:'+$name+':'+$detail)}
}
$project=Join-Path $PackageRoot 'control-center\OneCArchitecture.ControlCenter'
$csproj=Get-Content -LiteralPath (Join-Path $project 'OneCArchitecture.ControlCenter.csproj') -Raw -Encoding UTF8
$manifest=Get-Content -LiteralPath (Join-Path $project 'app.manifest') -Raw -Encoding UTF8
$startup=Get-Content -LiteralPath (Join-Path $project 'StartupRegistration.cs') -Raw -Encoding UTF8
$app=Get-Content -LiteralPath (Join-Path $project 'App.xaml.cs') -Raw -Encoding UTF8
$main=Get-Content -LiteralPath (Join-Path $project 'MainWindow.xaml.cs') -Raw -Encoding UTF8
$xaml=Get-Content -LiteralPath (Join-Path $project 'MainWindow.xaml') -Raw -Encoding UTF8
$publishScript=Get-Content -LiteralPath (Join-Path $PackageRoot 'control-center\publish_control_center.ps1') -Raw -Encoding UTF8
$core=Get-Content -LiteralPath (Join-Path $PackageRoot 'core\OneCChatWorker.Core.psm1') -Raw -Encoding UTF8
$launcher=Get-Content -LiteralPath (Join-Path $PackageRoot 'OneCChatWorker.ps1') -Raw -Encoding UTF8
$lock=Read-RuntimeLock -PackageRoot $PackageRoot
$policy=Get-Content -LiteralPath (Join-Path (Split-Path -Parent (Split-Path -Parent $PackageRoot)) 'TOOLS\SHAREABLE_BINARY_REVIEW_POLICY.json') -Raw -Encoding UTF8|ConvertFrom-Json
$exe=Join-Path $PackageRoot 'control-center\publish\OneCArchitecture.ControlCenter.exe'
Rec 'dotnet_sdk_ready' (Test-Path -LiteralPath $DotnetPath -PathType Leaf) $DotnetPath
Rec 'self_contained_single_file_win_x64' ($csproj -match '<TargetFramework>net10\.0-windows</TargetFramework>' -and $csproj -match '<RuntimeIdentifier>win-x64</RuntimeIdentifier>' -and $csproj -match '<SelfContained>true</SelfContained>' -and $csproj -match '<PublishSingleFile>true</PublishSingleFile>') ''
Rec 'per_monitor_v2_dpi' ($csproj -match '<ApplicationManifest>app\.manifest</ApplicationManifest>' -and $csproj -match '<ApplicationHighDpiMode>PerMonitorV2</ApplicationHighDpiMode>' -and $manifest -match 'longPathAware') ''
Rec 'publish_script_fixed_contract' ($publishScript -match 'CONTROL_CENTER_PACKAGE_V1' -and $publishScript -match 'ContinuousIntegrationBuild=true' -and $publishScript -match 'UNSIGNED_INTERNAL_PILOT' -and -not ($publishScript -match 'HttpListener|Kestrel|\bpwsh\b|WindowsService|ServiceBase')) ''
Rec 'binary_exists' (Test-Path -LiteralPath $exe -PathType Leaf) $exe
$exeHash=(Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant()
$lockHash=[string]$lock.components.'control-center/publish/OneCArchitecture.ControlCenter.exe'
Rec 'binary_hash_pinned_in_runtime_lock' ($exeHash -eq $lockHash) ($exeHash+' vs '+$lockHash)
$policyRow=@($policy.reviewed_binary_files|Where-Object{$_.path -eq 'PRODUCT/OneCChatWorker/control-center/publish/OneCArchitecture.ControlCenter.exe'})|Select-Object -First 1
Rec 'binary_shareable_policy_exact' ($null -ne $policyRow -and [string]$policyRow.sha256 -eq $exeHash) $(if($policyRow){[string]$policyRow.sha256}else{'missing'})
$sig=Get-AuthenticodeSignature -LiteralPath $exe
Rec 'unsigned_internal_pilot_classified' ($sig.Status -ne 'Valid' -and [string]$lock.control_center.signing_status -eq 'UNSIGNED_INTERNAL_PILOT') ([string]$sig.Status)
Rec 'lock_no_service_webview_loopback_ps7' ($lock.control_center.service -eq $false -and $lock.control_center.loopback_listener -eq $false -and $lock.control_center.webview2 -eq $false -and $lock.control_center.powershell7_required -eq $false) ''
Rec 'lock_exact_six_model_tools' ((@($lock.control_center.model_surface) -join ',') -eq 'source_context,source_search,source_read,proposal_write,proposal_read,task_checkpoint_write') (@($lock.control_center.model_surface)-join ',')
Rec 'install_owner_wires_control_center' ($core -match 'function Install-ControlCenterArtifact' -and $core -match '\$controlCenter=Install-ControlCenterArtifact' -and $core -match "control-center\\OneCArchitecture\.ControlCenter\.exe" -and $core -match 'Get-ControlCenterStartMenuShortcutPath') ''
$update=$launcher.Substring($launcher.IndexOf('function Run-Update'),$launcher.IndexOf('function Run-AddProject')-$launcher.IndexOf('function Run-Update'))
Rec 'update_reuses_existing_install_owner' ($update -match 'Install-OneCChatWorker' -and $update -match 'network_download_performed=\$false') ''
Rec 'start_menu_shortcut_product_owned' ($core -match 'OneC Architecture Control Center\.lnk' -and $core -match 'WScript\.Shell' -and $core -match 'CONTROL_CENTER_SHORTCUT_TARGET_MISMATCH') ''
Rec 'startup_explicit_operator_choice' ($xaml -match 'Start Control Center with Windows \(operator choice\)' -and $main -match 'StartupCheckBox_Changed' -and $startup -match 'Registry\.CurrentUser' -and $startup -match 'CurrentVersion\\Run' -and -not ($app -match 'StartupRegistration\.Apply')) ''
Rec 'startup_default_disabled' ((Get-Content -LiteralPath (Join-Path $project 'PreferencesStore.cs') -Raw -Encoding UTF8) -match 'bool StartWithWindows = false') ''
Rec 'no_password_capture_in_gui' (-not (($main+$startup+$app) -match 'PasswordBox|NetworkCredential|SecureString|savecred|CredentialManager')) ''
$scratch=New-OneCTestScratch -Purpose 'ControlCenterPackaging'
try{
  $pd=Join-Path $scratch.path 'ProgramData'
  $sm=Join-Path $scratch.path 'StartMenu'
  $first=Install-ControlCenterArtifact -PackageRoot $PackageRoot -ProgramDataRoot $pd -RuntimeLock $lock -ShortcutRoot $sm
  Rec 'isolated_install_pass' ($first.status -eq 'PASS' -and $first.component.action -eq 'INSTALLED') ($first|ConvertTo-Json -Depth 5 -Compress)
  Rec 'isolated_install_hash_exact' ((Get-FileHash -LiteralPath $first.executable_path -Algorithm SHA256).Hash.ToLowerInvariant() -eq $exeHash) ''
  Rec 'isolated_shortcut_created' (Test-Path -LiteralPath $first.shortcut_path -PathType Leaf) $first.shortcut_path
  $ws=New-Object -ComObject WScript.Shell
  $lnk=$ws.CreateShortcut($first.shortcut_path)
  Rec 'isolated_shortcut_target_exact' ([string]$lnk.TargetPath -eq [string]$first.executable_path) ([string]$lnk.TargetPath)
  $second=Install-ControlCenterArtifact -PackageRoot $PackageRoot -ProgramDataRoot $pd -RuntimeLock $lock -ShortcutRoot $sm
  Rec 'isolated_update_reuses_identical_binary' ($second.component.action -eq 'REUSED') ([string]$second.component.action)
  Rec 'isolated_install_no_service_listener' ($second.service_created -eq $false -and $second.loopback_listener_created -eq $false) ''
  Rec 'isolated_paths_only' ($first.executable_path.StartsWith($scratch.path,[StringComparison]::OrdinalIgnoreCase) -and $first.shortcut_path.StartsWith($scratch.path,[StringComparison]::OrdinalIgnoreCase)) ($first.executable_path+' | '+$first.shortcut_path)
} finally {
  if($scratch){Remove-OneCTestScratch -Path $scratch.path -RunId $scratch.run_id -Base $scratch.base|Out-Null}
}
Write-Host ("CONTROL_CENTER_PACKAGING_PASS checks={0}" -f $results.Count)
$results|ConvertTo-Json -Depth 6
