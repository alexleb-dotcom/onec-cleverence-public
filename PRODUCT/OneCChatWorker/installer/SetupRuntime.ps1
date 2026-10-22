param([ValidateSet('Install','Uninstall')][string]$Mode,[string]$AppRoot,[string]$WorkerRoot,[string]$DataRoot,[string]$ShortcutRoot)
$ErrorActionPreference='Stop'
$receiptPath=Join-Path $AppRoot 'install-receipt.json'
function Assert-PlainPath([string]$Path){
    $full=[IO.Path]::GetFullPath($Path)
    if($full.StartsWith('\\') -or $full.Length -lt 8){throw 'SETUP_PATH_INVALID'}
    $cursor=$full
    while($cursor){
        if((Test-Path -LiteralPath $cursor) -and ((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'SETUP_REPARSE_POINT'}
        $parent=Split-Path -Parent $cursor;if($parent -eq $cursor){break};$cursor=$parent
    }
    $full.TrimEnd('\')
}
function Inventory([string[]]$Roots){
    $rows=@()
    foreach($root in $Roots){
        if(-not(Test-Path -LiteralPath $root)){continue}
        foreach($file in Get-ChildItem -LiteralPath $root -Recurse -File -Force){
            Assert-PlainPath $file.FullName|Out-Null
            $rows+=,@{path=$file.FullName;sha256=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
        }
    }
    $rows
}
$AppRoot=Assert-PlainPath $AppRoot
if($Mode -eq 'Install'){
    $WorkerRoot=Assert-PlainPath $WorkerRoot;$DataRoot=Assert-PlainPath $DataRoot
    foreach($root in @($WorkerRoot,$DataRoot)){
        if(Test-Path -LiteralPath $root){throw 'SETUP_FOREIGN_OR_EXISTING_ROOT'}
        if($root.StartsWith($AppRoot+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'SETUP_ROOT_OVERLAP'}
    }
    if($WorkerRoot.StartsWith($DataRoot+'\',[StringComparison]::OrdinalIgnoreCase) -or $DataRoot.StartsWith($WorkerRoot+'\',[StringComparison]::OrdinalIgnoreCase) -or $WorkerRoot -ieq $DataRoot){throw 'SETUP_ROOT_OVERLAP'}
    if(Get-LocalUser -Name OneCSourceReader -ErrorAction SilentlyContinue){throw 'SETUP_EXISTING_READER_MIGRATION_REQUIRED'}
    $package=Join-Path $AppRoot 'package'
    Import-Module (Join-Path $package 'core/OneCChatWorker.Core.psm1') -Force -DisableNameChecking
    Test-ProductPackageIntegrity $package|Out-Null
    # These roots are reserved exclusively, never borrowed from an existing install.
    New-Item -ItemType Directory -Path $WorkerRoot,$DataRoot|Out-Null
    Write-JsonAtomic @{schema='ORBIT_SETUP_INTENT_V1';worker_root=$WorkerRoot;data_root=$DataRoot;state='INSTALLING';retention='PROJECTS_BY_DEFAULT'} (Join-Path $AppRoot 'install-intent.json')
    try {
        $result=Install-OneCChatWorker -PackageRoot $package -WorkerRoot $WorkerRoot -ProgramDataRoot $DataRoot -GenerateReaderPassword -SkipDependencies -ShortcutRoot $ShortcutRoot
        $gui=Join-Path $DataRoot 'product/control-center'
        Write-JsonAtomic @{schema='ORBIT_INSTALL_CONFIG_V1';worker_root=$WorkerRoot;program_data_root=$DataRoot} (Join-Path $gui 'orbit-install.json')
        # Runtime files only. projects.json and future project trees are retained.
        $owned=@(Inventory @($DataRoot)) + @(@{path=(Join-Path $WorkerRoot 'OneCChatWorker.ps1');sha256=(Get-FileHash -LiteralPath (Join-Path $WorkerRoot 'OneCChatWorker.ps1') -Algorithm SHA256).Hash.ToLowerInvariant()})
        $owned+=,@{path=$result.control_center.shortcut_path;sha256=(Get-FileHash -LiteralPath $result.control_center.shortcut_path -Algorithm SHA256).Hash.ToLowerInvariant()}
        $receipt=@{schema='ORBIT_INSTALL_RECEIPT_V1';worker_root=$WorkerRoot;data_root=$DataRoot;shortcut_path=$result.control_center.shortcut_path;created_utc=[DateTime]::UtcNow.ToString('o');files=$owned;reader_identity_retained=$true;project_retention='ALWAYS';package_lock_sha256=(Get-FileHash -LiteralPath (Join-Path $package 'runtime.lock.json') -Algorithm SHA256).Hash.ToLowerInvariant();status='INSTALLED_WAITING_FOR_REMOTE_AUTH'}
        Write-JsonAtomic $receipt $receiptPath
        Write-JsonAtomic @{schema='ORBIT_SETUP_INTENT_V1';worker_root=$WorkerRoot;data_root=$DataRoot;state='COMMITTED'} (Join-Path $AppRoot 'install-intent.json')
    } catch {
        # Preserve incomplete state for explicit recovery. Inno rollback removes
        # its own package only; unknown data is never recursively deleted.
        Write-JsonAtomic @{schema='ORBIT_SETUP_INTENT_V1';worker_root=$WorkerRoot;data_root=$DataRoot;state='RECOVERY_REQUIRED';reason=$_.Exception.Message} (Join-Path $AppRoot 'install-intent.json')
        throw
    }
} else {
    if(-not(Test-Path -LiteralPath $receiptPath)){throw 'SETUP_RECEIPT_REQUIRED_RECOVERY_HOLD'}
    $receipt=Get-Content -LiteralPath $receiptPath -Raw -Encoding UTF8|ConvertFrom-Json
    if($receipt.schema -ne 'ORBIT_INSTALL_RECEIPT_V1'){throw 'SETUP_RECEIPT_INVALID'}
    $WorkerRoot=Assert-PlainPath $receipt.worker_root;$DataRoot=Assert-PlainPath $receipt.data_root
    if(Test-Path -LiteralPath (Join-Path $DataRoot 'runtime/active-admission.json')){throw 'SETUP_ACTIVE_ADMISSION_HOLD'}
    if(Test-Path -LiteralPath (Join-Path $DataRoot 'runtime/hosted-helper-state.json')){throw 'SETUP_HELPER_STATE_REQUIRES_ADJUDICATION'}
    # Validate the complete removal plan before deleting the first owned file.
    foreach($file in $receipt.files){
        $path=Assert-PlainPath $file.path
        if(-not($path.StartsWith($DataRoot+'\',[StringComparison]::OrdinalIgnoreCase) -or $path -ieq (Join-Path $WorkerRoot 'OneCChatWorker.ps1') -or $path -ieq $receipt.shortcut_path)){throw 'SETUP_RECEIPT_PATH_INVALID'}
        if((Test-Path -LiteralPath $path) -and (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $file.sha256){throw ('SETUP_OWNED_FILE_CHANGED_HOLD: '+$path)}
    }
    foreach($file in $receipt.files){if(Test-Path -LiteralPath $file.path){Remove-Item -LiteralPath $file.path -Force}}
    # Remove empty directories only, without crossing reparse points.
    foreach($root in @($DataRoot)){
        Get-ChildItem -LiteralPath $root -Directory -Recurse -Force | Sort-Object {$_.FullName.Length} -Descending | ForEach-Object {
            Assert-PlainPath $_.FullName|Out-Null
            if(-not @(Get-ChildItem -LiteralPath $_.FullName -Force).Count){[IO.Directory]::Delete($_.FullName)}
        }
        if(-not @(Get-ChildItem -LiteralPath $root -Force).Count){[IO.Directory]::Delete($root)}
    }
    $receipt.status='UNINSTALLED_PROJECTS_RETAINED'
    $receipt|ConvertTo-Json -Depth 30|Set-Content -LiteralPath $receiptPath -Encoding UTF8
}
