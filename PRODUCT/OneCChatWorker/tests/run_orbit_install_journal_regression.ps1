param([string]$PackageRoot=(Split-Path -Parent $PSScriptRoot))
$ErrorActionPreference='Stop'
Import-Module (Join-Path $PSScriptRoot 'TestScratch.psm1') -Force -DisableNameChecking
$scratch=New-OneCTestScratch -Purpose OrbitInstallJournal
$module=Import-Module (Join-Path $PackageRoot 'core/OneCChatWorker.Core.psm1') -Force -DisableNameChecking -PassThru
try {
    # Import only the rollback helpers from the reviewed script AST. Do not run
    # setup, inventory operator roots, provision accounts or invoke a real install.
    $tokens=$null;$errors=$null
    $ast=[Management.Automation.Language.Parser]::ParseFile((Join-Path $PackageRoot 'installer/SetupRuntime.ps1'),[ref]$tokens,[ref]$errors)
    if($errors.Count){throw 'SETUP_SCRIPT_PARSE_ERRORS'}
    foreach($function in $ast.FindAll({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst]},$false)){
        if($function.Name -in @('Assert-PlainPath','EmptyDirectories','Rollback')){. ([scriptblock]::Create($function.Extent.Text))}
    }
    function Get-LocalUser {param($Name,$ErrorAction) return $null}
    function Check($Value,$Name){if(-not $Value){throw ('JOURNAL_ASSERT:'+ $Name)};Write-Host ('PASS '+$Name)}
    $AppRoot=Join-Path $scratch.path 'app';$worker=Join-Path $scratch.path 'worker';$data=Join-Path $scratch.path 'data'
    New-Item -ItemType Directory -Path $AppRoot,$worker,$data|Out-Null
    $journal=Join-Path $AppRoot 'install-journal.json'
    Write-JsonAtomic @{schema='ORBIT_INSTALL_JOURNAL_V1';transaction_id=[guid]::NewGuid().ToString('N');worker_root=$worker;data_root=$data;shortcut_path=(Join-Path $scratch.path 'shortcut.lnk');files=@()} $journal
    & $module {param($Path) $script:InstallJournalPath=$Path} $journal
    $owned=Join-Path $data 'owned.json';$changed=Join-Path $data 'changed.json';$unknown=Join-Path $data 'unknown.txt'
    Write-JsonAtomic @{fixture='owned'} $owned
    Write-JsonAtomic @{fixture='changed'} $changed
    [IO.File]::WriteAllText($changed,'changed outside installation')
    [IO.File]::WriteAllText($unknown,'unknown user data')
    $intent=Get-Content -LiteralPath $journal -Raw -Encoding UTF8|ConvertFrom-Json
    Check (@($intent.files).Count -eq 2) 'only explicit install writes are journaled'
    Check ($intent.files[0].sha256 -eq (Get-FileHash -LiteralPath $owned -Algorithm SHA256).Hash.ToLowerInvariant()) 'journal digest matches actual atomic bytes'
    $held=$false;try{Rollback}catch{$held=$_.Exception.Message -eq 'SETUP_ROLLBACK_CHANGED_FILE_RETAINED'}
    Check $held 'changed owned file produces recovery hold'
    Check (-not(Test-Path -LiteralPath $owned)) 'matching transaction write rolled back'
    Check ((Get-Content -LiteralPath $changed -Raw) -eq 'changed outside installation') 'changed owned file retained'
    Check ((Get-Content -LiteralPath $unknown -Raw) -eq 'unknown user data') 'unknown file retained'
} finally {
    & $module {$script:InstallJournalPath=$null}
    Remove-OneCTestScratch -Path $scratch.path|Out-Null
}
