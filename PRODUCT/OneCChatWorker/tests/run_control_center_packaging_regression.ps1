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
$launcherPath=Join-Path $PackageRoot 'OneCChatWorker.ps1'
$launcher=Get-Content -LiteralPath $launcherPath -Raw -Encoding UTF8
$launcherBytes=[IO.File]::ReadAllBytes($launcherPath)
Rec 'ps51_launcher_utf8_bom' ($launcherBytes.Length -ge 3 -and $launcherBytes[0] -eq 0xef -and $launcherBytes[1] -eq 0xbb -and $launcherBytes[2] -eq 0xbf) 'UTF-8 BOM required for non-ASCII PowerShell 5.1 script'
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
Rec 'start_menu_shortcut_product_owned' ($core -match 'OneC Orbit\.lnk' -and $core -match 'WScript\.Shell' -and $core -match 'CONTROL_CENTER_SHORTCUT_TARGET_MISMATCH') ''
Rec 'startup_explicit_operator_choice' ($xaml -match 'Start Control Center with Windows \(operator choice\)' -and $main -match 'StartupCheckBox_Changed' -and $startup -match 'Registry\.CurrentUser' -and $startup -match 'CurrentVersion\\Run' -and -not ($app -match 'StartupRegistration\.Apply')) ''
Rec 'startup_default_disabled' ((Get-Content -LiteralPath (Join-Path $project 'PreferencesStore.cs') -Raw -Encoding UTF8) -match 'bool StartWithWindows = false') ''
Rec 'no_password_capture_in_gui' (-not (($main+$startup+$app) -match 'PasswordBox|NetworkCredential|SecureString|savecred|CredentialManager')) ''
$scratch=New-OneCTestScratch -Purpose 'ControlCenterPackaging'
$previousLocalAppData=$env:LOCALAPPDATA
$env:LOCALAPPDATA=Join-Path $scratch.path 'LocalAppData'
New-Item -ItemType Directory -Force -Path $env:LOCALAPPDATA|Out-Null
try{
  $fallback=Get-WorkerOperationRoot -ProgramDataRoot (Join-Path $scratch.path 'AbsentData')
  Rec 'orbit_local_operation_fallback' ($fallback -eq (Join-Path $env:LOCALAPPDATA 'OneCOrbit\operations')) $fallback
  $module=Get-Module OneCChatWorker.Core
  $identity=& $module { @($script:DefaultWorkerRoot,$script:DefaultProgramDataRoot) }
  Rec 'orbit_core_default_identity' (($identity -join '|') -eq 'C:\OneCOrbit|C:\ProgramData\OneCOrbit') ($identity -join '|')
  Rec 'orbit_native_defaults' ($launcher -match "WorkerRoot='C:\\OneCOrbit'" -and $launcher -match "ProgramDataRoot='C:\\ProgramData\\OneCOrbit'") ''
  Rec 'orbit_launcher_partial_fallback_guard' ($launcher -match '\$hasCatalog -xor \$hasInstalledState') ''
  Rec 'orbit_preferences_default' ((Get-Content (Join-Path $project 'PreferencesStore.cs') -Raw -Encoding UTF8) -match '"OneCOrbit"') ''
  Rec 'orbit_run_value_name' ($startup -match 'ValueName = "OneC Orbit"') ''
  $proof=& $module {
    param($base,$package,$launcherText)
    $saved=@($script:DefaultWorkerRoot,$script:DefaultProgramDataRoot,$script:LegacyWorkerRoot,$script:LegacyProgramDataRoot)
    try{
      $script:DefaultWorkerRoot=Join-Path $base 'OneCOrbit'
      $script:DefaultProgramDataRoot=Join-Path $base 'OrbitData'
      $script:LegacyWorkerRoot=Join-Path $base 'OneCChatWorker'
      $script:LegacyProgramDataRoot=Join-Path $base 'LegacyData'
      $worker=$script:DefaultWorkerRoot;$pd=$script:DefaultProgramDataRoot
      if((Get-InstallRootDisposition) -ne 'NEW_INSTALL'){throw 'DEFAULT_NEW_INSTALL_FAILED'}
      # Independent negative cases: neither legacy root exists at this point.
      # An interrupted Orbit install must hold, with zero admin/install/Source side effects.
      $tokens=$null;$errors=$null
      $ast=[Management.Automation.Language.Parser]::ParseInput($launcherText,[ref]$tokens,[ref]$errors)
      foreach($name in @('Get-LauncherRootDisposition','Get-LauncherRootHoldReason','Get-UiContext','Get-GuidedContext','Show-StatusReadable')){
        $fn=$ast.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name},$true)
        . ([scriptblock]::Create($fn.Extent.Text))
      }
      $WorkerRoot=$worker;$ProgramDataRoot=$pd;$ProjectId=$null;$Json=$false
      New-Item -ItemType Directory -Path $worker,$pd|Out-Null
      foreach($partial in @('worker_only','installed_state_only')){
        $catalogMarker=Join-Path $worker 'projects.json'
        $installedMarker=Join-Path $pd 'installed-state.json'
        $marker=if($partial -eq 'worker_only'){$catalogMarker}else{$installedMarker}
        [IO.File]::WriteAllText($marker,('{"partial":"' + $partial + '"}'))
        $before=[IO.File]::ReadAllText($marker)
        if((Test-Path -LiteralPath $script:LegacyWorkerRoot) -or (Test-Path -LiteralPath $script:LegacyProgramDataRoot)){throw 'PARTIAL_NO_LEGACY_FIXTURE_INVALID'}
        if((Get-InstallRootDisposition) -ne 'MIGRATION_REQUIRED'){throw ('PARTIAL_ORBIT_NOT_HELD_'+$partial)}
        try{Install-OneCChatWorker -PackageRoot $package;throw ('PARTIAL_INSTALL_NOT_BLOCKED_'+$partial)}catch{if($_.Exception.Message -notlike 'MIGRATION_REQUIRED:*'){throw}}
        $partialStatus=Get-WorkerStatus
        if($partialStatus.state -ne 'MIGRATION_REQUIRED' -or $partialStatus.source_scan_performed -ne $false){throw ('PARTIAL_STATUS_HOLD_MISSING_'+$partial)}
        if($partialStatus.root_hold_reason -ne 'ORBIT_PARTIAL_INSTALL'){throw ('PARTIAL_REASON_INCORRECT_'+$partial)}
        $readablePartial=Show-StatusReadable $partialStatus 6>&1|Out-String
        if($readablePartial -notlike '*Incomplete OneC Orbit*' -or $readablePartial -like '*Legacy installation retained*'){throw ('PARTIAL_STATUS_COPY_FALSE_'+$partial)}
        $partialUi=Get-UiContext
        if($partialUi.recommendation.state -ne 'MIGRATION_REQUIRED' -or @($partialUi.actions.PSObject.Properties|Where-Object{$_.Value.enabled}).Count){throw ('PARTIAL_UI_MUTATION_ENABLED_'+$partial)}
        if($partialUi.recommendation.reason_code -ne 'ORBIT_PARTIAL_INSTALL' -or $partialUi.recommendation.reason -notlike '*Incomplete OneC Orbit*' -or $partialUi.recommendation.reason -like '*Legacy installation*'){throw ('PARTIAL_UI_COPY_FALSE_'+$partial)}
        $partialGuided=Get-GuidedContext
        if($partialGuided.state -ne 'MIGRATION_REQUIRED' -or $partialGuided.reason -notlike '*Incomplete OneC Orbit*' -or $partialGuided.reason -like '*Legacy installation*'){throw ('PARTIAL_GUIDED_COPY_FALSE_'+$partial)}
        if([IO.File]::ReadAllText($marker) -ne $before -or
          @(Get-ChildItem -LiteralPath $worker -Force).Count -ne $(if($partial -eq 'worker_only'){1}else{0}) -or
          @(Get-ChildItem -LiteralPath $pd -Force).Count -ne $(if($partial -eq 'installed_state_only'){1}else{0})){
          throw ('PARTIAL_MARKER_OR_DIRECTORY_MUTATED_'+$partial)
        }
        Remove-Item -LiteralPath $marker
      }
      Remove-Item -LiteralPath $worker,$pd -Force
      if((Test-Path -LiteralPath $worker) -or (Test-Path -LiteralPath $pd)){throw 'PARTIAL_ROOTS_NOT_CLEANED'}
      New-Item -ItemType Directory -Path $script:LegacyWorkerRoot|Out-Null
      $legacyCatalog=Join-Path $script:LegacyWorkerRoot 'projects.json'
      [IO.File]::WriteAllText($legacyCatalog,'{"schema_version":1,"projects":[]}')
      $legacyBefore=[IO.File]::ReadAllText($legacyCatalog)
      if((Get-InstallRootDisposition) -ne 'MIGRATION_REQUIRED'){throw 'LEGACY_COLLISION_NOT_BLOCKED'}
      # Fail-closed install must stop before admin/dependency/ACL/logging owners.
      try{Install-OneCChatWorker -PackageRoot $package;throw 'INSTALL_NOT_BLOCKED'}catch{if($_.Exception.Message -notlike 'MIGRATION_REQUIRED:*'){throw}}
      $status=Get-WorkerStatus
      if($status.state -ne 'MIGRATION_REQUIRED' -or $status.source_scan_performed -ne $false){throw 'STATUS_HOLD_MISSING'}
      if($status.root_hold_reason -ne 'LEGACY_INSTALL_PRESENT'){throw 'LEGACY_REASON_INCORRECT'}
      # Execute the actual launcher projection/guided owners against synthetic defaults.
      $tokens=$null;$errors=$null
      $ast=[Management.Automation.Language.Parser]::ParseInput($launcherText,[ref]$tokens,[ref]$errors)
      foreach($name in @('Get-LauncherRootDisposition','Get-LauncherRootHoldReason','Get-UiContext','Get-GuidedContext','Show-StatusReadable')){
        $fn=$ast.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name},$true)
        . ([scriptblock]::Create($fn.Extent.Text))
      }
      $WorkerRoot=$worker;$ProgramDataRoot=$pd;$ProjectId=$null
      $Json=$false
      $readable=Show-StatusReadable $status 6>&1|Out-String
      if($readable -notlike '*MIGRATION_REQUIRED*' -or $readable -like '*Projects:*'){throw 'READABLE_STATUS_HOLD_MISSING'}
      $context=Get-UiContext
      if($context.recommendation.state -ne 'MIGRATION_REQUIRED' -or @($context.actions.PSObject.Properties|Where-Object{$_.Value.enabled}).Count){throw 'UI_HOLD_NOT_BLOCKED'}
      if($context.recommendation.reason_code -ne 'LEGACY_INSTALL_PRESENT' -or $context.recommendation.reason -notlike '*Legacy installation retained*'){throw 'LEGACY_UI_COPY_INCORRECT'}
      if((Get-GuidedContext).state -ne 'MIGRATION_REQUIRED'){throw 'GUIDED_HOLD_MISSING'}
      if((Test-Path -LiteralPath $worker) -or (Test-Path -LiteralPath $pd)){throw 'SURPRISE_NEW_ROOT_CREATED'}
      if([IO.File]::ReadAllText($legacyCatalog) -ne $legacyBefore){throw 'LEGACY_MUTATED'}
      # An explicit legacy pair is an operating deployment, not a migration request.
      $explicit=Get-InstallRootDisposition -WorkerRoot $script:LegacyWorkerRoot -ProgramDataRoot $script:LegacyProgramDataRoot
      if($explicit -ne 'EXPLICIT_ROOTS'){throw 'EXPLICIT_LEGACY_REJECTED'}
      $legacyStatus=Get-WorkerStatus -WorkerRoot $script:LegacyWorkerRoot -ProgramDataRoot $script:LegacyProgramDataRoot
      if($legacyStatus.root_disposition -ne 'EXPLICIT_ROOTS' -or $legacyStatus.catalog_path -ne $legacyCatalog){throw 'EXPLICIT_LEGACY_STATUS_FAILED'}
      New-Item -ItemType Directory -Path $worker,$pd|Out-Null
      [IO.File]::WriteAllText((Join-Path $worker 'projects.json'),'{}')
      if((Get-InstallRootDisposition) -ne 'MIGRATION_REQUIRED'){throw 'PARTIAL_INSTALL_BYPASSED_HOLD'}
      [IO.File]::WriteAllText((Join-Path $pd 'installed-state.json'),'{}')
      if((Get-InstallRootDisposition) -ne 'ORBIT_INSTALLED'){throw 'COMPLETE_ORBIT_NOT_RECOGNIZED'}
      'synthetic defaults/collision/install/STATUS/UI/guided/partial/explicit legacy preserved'
    }finally{
      $script:DefaultWorkerRoot=$saved[0];$script:DefaultProgramDataRoot=$saved[1]
      $script:LegacyWorkerRoot=$saved[2];$script:LegacyProgramDataRoot=$saved[3]
    }
  } $scratch.path $PackageRoot $launcher
  Rec 'orbit_synthetic_legacy_hold_and_explicit_compatibility' ($proof -like '*explicit legacy preserved*') ($proof -join ' ')
  $pd=Join-Path $scratch.path 'ProgramData'
  $sm=Join-Path $scratch.path 'StartMenu'
  $first=Install-ControlCenterArtifact -PackageRoot $PackageRoot -ProgramDataRoot $pd -RuntimeLock $lock -ShortcutRoot $sm
  Rec 'isolated_install_pass' ($first.status -eq 'PASS' -and $first.component.action -eq 'INSTALLED') ($first|ConvertTo-Json -Depth 5 -Compress)
  Rec 'isolated_install_hash_exact' ((Get-FileHash -LiteralPath $first.executable_path -Algorithm SHA256).Hash.ToLowerInvariant() -eq $exeHash) ''
  Rec 'orbit_shortcut_display_name' ((Split-Path -Leaf $first.shortcut_path) -eq 'OneC Orbit.lnk') $first.shortcut_path
  Rec 'isolated_shortcut_created' (Test-Path -LiteralPath $first.shortcut_path -PathType Leaf) $first.shortcut_path
  $ws=New-Object -ComObject WScript.Shell
  $lnk=$ws.CreateShortcut($first.shortcut_path)
  Rec 'isolated_shortcut_target_exact' ([string]$lnk.TargetPath -eq [string]$first.executable_path) ([string]$lnk.TargetPath)
  $second=Install-ControlCenterArtifact -PackageRoot $PackageRoot -ProgramDataRoot $pd -RuntimeLock $lock -ShortcutRoot $sm
  Rec 'isolated_update_reuses_identical_binary' ($second.component.action -eq 'REUSED') ([string]$second.component.action)
  Rec 'isolated_install_no_service_listener' ($second.service_created -eq $false -and $second.loopback_listener_created -eq $false) ''
  Rec 'isolated_paths_only' ($first.executable_path.StartsWith($scratch.path,[StringComparison]::OrdinalIgnoreCase) -and $first.shortcut_path.StartsWith($scratch.path,[StringComparison]::OrdinalIgnoreCase)) ($first.executable_path+' | '+$first.shortcut_path)
} finally {
  $env:LOCALAPPDATA=$previousLocalAppData
  if($scratch){Remove-OneCTestScratch -Path $scratch.path -RunId $scratch.run_id -Base $scratch.base|Out-Null}
}
Write-Host ("CONTROL_CENTER_PACKAGING_PASS checks={0}" -f $results.Count)
$results|ConvertTo-Json -Depth 6
