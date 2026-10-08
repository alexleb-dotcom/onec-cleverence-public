param([Parameter(Mandatory)][string]$PackageRoot,[Parameter(Mandatory)][string]$FixtureRoot,[string]$ProgramDataRoot)
$ErrorActionPreference='Stop'
Import-Module (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Utility') -Force
$FixtureRoot=[IO.Path]::GetFullPath($FixtureRoot)
$tempPrefix=[IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd([IO.Path]::DirectorySeparatorChar)+[IO.Path]::DirectorySeparatorChar
if(-not $FixtureRoot.StartsWith($tempPrefix,[StringComparison]::OrdinalIgnoreCase)){throw 'BOOTSTRAP_TEST_REQUIRES_TEMP_FIXTURE'}
if(-not $ProgramDataRoot){$ProgramDataRoot=Join-Path $FixtureRoot 'programdata'}
if(-not ([IO.Path]::GetFullPath($ProgramDataRoot)).StartsWith($FixtureRoot+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)){throw 'BOOTSTRAP_TEST_DATA_OUTSIDE_FIXTURE'}
$package=Join-Path $FixtureRoot 'bootstrap-package';$core=Join-Path $package 'core\OneCChatWorker.Core.psm1'
$installed=Join-Path $ProgramDataRoot 'product\OneCChatWorker.Core.psm1'
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $core),(Split-Path -Parent $installed)|Out-Null
$coreBytes=[IO.File]::ReadAllBytes((Join-Path $PackageRoot 'core\OneCChatWorker.Core.psm1'))
$lockText=[IO.File]::ReadAllText((Join-Path $PackageRoot 'runtime.lock.json'))
$lockPath=Join-Path $package 'runtime.lock.json'
$utf8=New-Object Text.UTF8Encoding($false)
# Execute the exact launcher bootstrap, ending before any operational function.
# PSScriptRoot is the temporary package; all roots are explicit fixture paths.
$launcher=[IO.File]::ReadAllText((Join-Path $PackageRoot 'OneCChatWorker.ps1'))
$end=$launcher.IndexOf("`nfunction Is-Admin {")
if($end -lt 0){throw 'BOOTSTRAP_BOUNDARY_NOT_FOUND'}
$scriptPath=Join-Path $package 'bootstrap-only.ps1'
[IO.File]::WriteAllText($scriptPath,$launcher.Substring(0,$end)+"`nWrite-Output ('BOOTSTRAP_CORE='+((Get-Command Install-OneCChatWorker).Module.Path))",$utf8)
$shell=if($env:OS -eq 'Windows_NT'){Join-Path $PSHOME 'powershell.exe'}else{Join-Path $PSHOME 'pwsh'}
function Reset-Package {
 [IO.File]::WriteAllBytes($core,$coreBytes);[IO.File]::WriteAllText($lockPath,$lockText,$utf8)
}
function Invoke-Bootstrap([string]$Mode,[string]$ExpectedError){
 $ErrorActionPreference='Continue'
 $output=& $shell -NoProfile -File $scriptPath -Mode $Mode -WorkerRoot (Join-Path $FixtureRoot 'worker') -ProgramDataRoot $ProgramDataRoot -OperatorIdentity 'isolated-operator' 2>&1
 $exit=$LASTEXITCODE;$ErrorActionPreference='Stop';$text=$output|Out-String
 if($ExpectedError){
  if($exit -eq 0 -or -not $text.Contains($ExpectedError)){throw "BOOTSTRAP_NEGATIVE_FAILED: $Mode $ExpectedError"}
 }elseif($exit -ne 0 -or -not $text.Contains('BOOTSTRAP_CORE='+$core)){throw "BOOTSTRAP_PACKAGE_OWNER_NOT_SELECTED: $Mode"}
}
# Reconstruct the previous copy/integrity/ACL layout; the tripwire detects any
# execution of installed code during package INSTALL/UPDATE or fallback.
$legacy=([Text.Encoding]::UTF8.GetString($coreBytes) -split "`n" | Where-Object{$_ -notmatch 'helper-https-pull\.mjs|https-pull-auth\.mjs'}) -join "`n"
[IO.File]::WriteAllText($installed,"throw 'STALE_INSTALLED_CORE_EXECUTED'`n"+$legacy,$utf8)
foreach($mode in @('INSTALL','UPDATE')){
 Reset-Package;Invoke-Bootstrap $mode $null;Write-Host "PASS $mode selects verified package core over stale installed core"
}
$marker=Join-Path $FixtureRoot 'unverified-core-executed.txt'
[IO.File]::WriteAllText($core,"[IO.File]::WriteAllText('"+$marker.Replace("'","''")+"','executed')`n"+[Text.Encoding]::UTF8.GetString($coreBytes),$utf8)
Invoke-Bootstrap 'UPDATE' 'PACKAGE_COMPONENT_HASH_MISMATCH'
if(Test-Path -LiteralPath $marker){throw 'UNVERIFIED_CORE_EXECUTED'}
Write-Host 'PASS corrupted package rejected before core execution'
Reset-Package;Remove-Item -LiteralPath $core
Invoke-Bootstrap 'UPDATE' 'CORE_NOT_FOUND';Write-Host 'PASS missing package core never falls back to installed core'
Reset-Package;Remove-Item -LiteralPath $lockPath
Invoke-Bootstrap 'UPDATE' 'PACKAGE_RUNTIME_LOCK_MISSING';Write-Host 'PASS missing runtime lock rejected before import'
Reset-Package;$doc=$lockText|ConvertFrom-Json;$doc.components.PSObject.Properties.Remove('core/OneCChatWorker.Core.psm1')
[IO.File]::WriteAllText($lockPath,($doc|ConvertTo-Json -Depth 30),$utf8)
Invoke-Bootstrap 'UPDATE' 'PACKAGE_CORE_LOCK_INVALID';Write-Host 'PASS missing core pin rejected before import'
Reset-Package;$doc=$lockText|ConvertFrom-Json;$doc.components.'core/OneCChatWorker.Core.psm1'='invalid'
[IO.File]::WriteAllText($lockPath,($doc|ConvertTo-Json -Depth 30),$utf8)
Invoke-Bootstrap 'UPDATE' 'PACKAGE_CORE_LOCK_INVALID';Write-Host 'PASS malformed core pin rejected before import'
Reset-Package;$doc=$lockText|ConvertFrom-Json;$doc.components.'core/OneCChatWorker.Core.psm1'=('0'*64)
[IO.File]::WriteAllText($lockPath,($doc|ConvertTo-Json -Depth 30),$utf8)
Invoke-Bootstrap 'UPDATE' 'PACKAGE_COMPONENT_HASH_MISMATCH';Write-Host 'PASS wrong core pin rejected before import'
Reset-Package
Write-Host 'PACKAGE_CORE_BOOTSTRAP_PASS checks=8; no operational launcher code executed'
