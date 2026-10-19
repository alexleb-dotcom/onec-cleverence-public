#requires -Version 5.1
# Real Windows security regression. Run ONLY on isolated disposable CI Windows runner.
$ErrorActionPreference='Stop'
if($PSVersionTable.PSVersion.Major -ne 5){throw 'Q113_PS51_REQUIRED'}
$principal=New-Object Security.Principal.WindowsPrincipal ([Security.Principal.WindowsIdentity]::GetCurrent())
if(-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'Q113_REAL_ACL_TEST_REQUIRES_ELEVATED_ISOLATED_WINDOWS_RUNNER'}
$module=Import-Module (Join-Path (Split-Path -Parent $PSScriptRoot) 'core/OneCChatWorker.Core.psm1') -Force -PassThru -DisableNameChecking
$root=Join-Path $env:RUNNER_TEMP ('q113-acl-'+[guid]::NewGuid().ToString('N').Substring(0,10))
$operator='q113op'+[guid]::NewGuid().ToString('N').Substring(0,7)
$reader='OneCSourceReader'
$createdOperator=$false;$createdReader=$false
function Check($Condition,$Message){if(-not $Condition){throw ('Q113_REAL_ACL_FAIL: '+$Message)};Write-Host ('PASS '+$Message)}
function New-FixtureUser([string]$Name,[string]$Password){
    if(Get-LocalUser -Name $Name -ErrorAction SilentlyContinue){throw ('Q113_ACCOUNT_COLLISION: '+$Name)}
    New-LocalUser -Name $Name -Password (ConvertTo-SecureString $Password -AsPlainText -Force) -PasswordNeverExpires -AccountNeverExpires | Out-Null
}
try {
    if(-not (Test-Path -LiteralPath $env:RUNNER_TEMP -PathType Container)){throw 'Q113_WINDOWS_RUNNER_TEMP_REQUIRED'}
    $oneTimeFixtureKey=('Q113!'+[guid]::NewGuid().ToString('N')+'z')
    New-FixtureUser $operator $oneTimeFixtureKey;$createdOperator=$true
    New-FixtureUser $reader $oneTimeFixtureKey;$createdReader=$true
    $credOperator=New-Object System.Management.Automation.PSCredential ("$env:COMPUTERNAME\$operator",(ConvertTo-SecureString $oneTimeFixtureKey -AsPlainText -Force))
    $credReader=New-Object System.Management.Automation.PSCredential ("$env:COMPUTERNAME\$reader",(ConvertTo-SecureString $oneTimeFixtureKey -AsPlainText -Force))
    $nested=Join-Path $root 'Catalogs\Document\Ext'
    New-Item -Path $nested -ItemType Directory -Force | Out-Null
    $file=Join-Path $nested 'Module.bsl'
    [IO.File]::WriteAllText($file,'sealed example')
    $metadata=Join-Path $root 'metadata'
    New-Item -ItemType Directory -Path $metadata | Out-Null
    [IO.File]::WriteAllText((Join-Path $metadata 'state.json'),'{"state":"sealed"}')
    $probePath=Join-Path $env:RUNNER_TEMP ('q113-access-probe-'+[guid]::NewGuid().ToString('N').Substring(0,8)+'.ps1')
    $probe=@'
param([string]$Root,[string]$Mode)
$ErrorActionPreference='Stop'
$file=Join-Path $Root 'Catalogs\Document\Ext\Module.bsl'
$nested=Split-Path -Parent $file
function MustDeny([scriptblock]$Action){
    try{& $Action;return $false}catch [System.UnauthorizedAccessException]{return $true}catch [System.IO.IOException]{return $true}
}
if([IO.File]::ReadAllText($file) -ne 'sealed example'){exit 10}
if([IO.File]::ReadAllText((Join-Path $Root 'metadata\state.json')) -ne '{"state":"sealed"}'){exit 11}
if($Mode -eq 'reader'){exit 0}
if(-not (MustDeny {[IO.File]::WriteAllText($file,'BAD')})){exit 20}
if(-not (MustDeny {[IO.File]::WriteAllText((Join-Path $nested 'new.txt'),'BAD')})){exit 21}
if(-not (MustDeny {[IO.Directory]::CreateDirectory((Join-Path $nested 'newdir'))|Out-Null})){exit 22}
if(-not (MustDeny {[IO.File]::Delete($file)})){exit 23}
if(-not (MustDeny {[IO.File]::Move($file,(Join-Path $nested 'renamed.bsl'))})){exit 24}
if(-not (MustDeny {[IO.Directory]::Delete($nested)})){exit 25}
if(-not (MustDeny {[IO.Directory]::Move($nested,(Join-Path $Root 'renamed'))})){exit 26}
if(-not (MustDeny {[IO.File]::WriteAllText((Join-Path $Root 'metadata\new.json'),'BAD')})){exit 27}
exit 0
'@
    [IO.File]::WriteAllText($probePath,$probe,(New-Object Text.UTF8Encoding($false)))
    # Reproduce the historical invocation shape, and assert it is forbidden
    # even when icacls would report exit code 0 with failed descendants.
    & $module {
        param($p)
        $blocked=$false
        try{Invoke-IcaclsChecked -Path ('\\?\'+$p) -Arguments @('/T','/C','/remove:g','*S-1-5-32-545')}catch{
            $blocked=$_.Exception.Message -like 'ACL_REPAIR_CONTINUE_ON_ERROR_FORBIDDEN:*'
        }
        if(-not $blocked){throw 'Q113_UNSAFE_RECURSIVE_CONTINUE_ACCEPTED'}
    } $root
    Write-Host 'PASS rejected recursive /T /C partial-failure contour'
    & $module {
        param($p,$m,$op)
        Set-SourceUpdateTreeAcl -Path $p -OperatorIdentity $op
        Protect-SourceUpdateMetadata -Path $m -OperatorIdentity $op
    } $root $metadata $operator
    $args=@('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',('"{0}"' -f $probePath),('"{0}"' -f $root),'operator')
    $p=Start-Process -FilePath 'powershell.exe' -Credential $credOperator -ArgumentList $args -Wait -PassThru -WindowStyle Hidden
    Check ($p.ExitCode -eq 0) ('non-admin operator RX and denied mutations; exit='+$p.ExitCode)
    $args[-1]='reader'
    $p=Start-Process -FilePath 'powershell.exe' -Credential $credReader -ArgumentList $args -Wait -PassThru -WindowStyle Hidden
    Check ($p.ExitCode -eq 0) ('non-admin reader RX; exit='+$p.ExitCode)
    Check (([IO.File]::ReadAllText($file)) -eq 'sealed example') 'unchanged sealed file'
    Check (-not(Test-Path (Join-Path $nested 'new.txt'))) 'no unvalidated child added'
    # Administrators can still perform maintenance.
    [IO.File]::AppendAllText($file,';admin')
    Check ([IO.File]::ReadAllText($file) -eq 'sealed example;admin') 'administrators preserve full control'
    Write-Host 'Q113_REAL_WINDOWS_ACL_SEAL_PASS'
}finally{
    if($probePath -and (Test-Path $probePath)){Remove-Item -LiteralPath $probePath -Force -ErrorAction SilentlyContinue}
    if($root -and (Test-Path $root)){Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue}
    if($createdReader){Remove-LocalUser -Name $reader -ErrorAction SilentlyContinue}
    if($createdOperator){Remove-LocalUser -Name $operator -ErrorAction SilentlyContinue}
}
