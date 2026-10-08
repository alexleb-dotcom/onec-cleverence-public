param([string]$PackageRoot=(Split-Path -Parent $PSScriptRoot))
$ErrorActionPreference='Stop'
$fixture=Join-Path ([IO.Path]::GetTempPath()) ('onec-node-pin-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $fixture|Out-Null
$module=Import-Module (Join-Path $PackageRoot 'core/OneCChatWorker.Core.psm1') -Force -DisableNameChecking -PassThru
try {
 & $module {
  param($Root)
  $script:Checks=0
  function Check($Ok,$Name){if(-not $Ok){throw ('ASSERTION_FAILED: '+$Name)};$script:Checks++;Write-Host ('PASS '+$Name)}
  Check ((Get-HelperNodeExecutablePath) -ceq 'C:\Program Files\nodejs\node.exe') 'production fixed launch path unchanged'
  $script:NodeFixture=Join-Path $Root 'fixed-node.ps1'
  $script:RgFixture=Join-Path $Root 'rg.ps1'
  $script:GoodNode=Join-Path $Root 'pinned-node.ps1'
  $script:WrongPathNode=Join-Path $Root 'path-node.ps1'
  function W($Path,$Text){[IO.File]::WriteAllText($Path,$Text,[Text.UTF8Encoding]::new($false))}
  W $script:GoodNode "Write-Output 'v26.7.0'"
  W $script:WrongPathNode "Write-Output 'v26.7.0'"
  W $script:RgFixture "Write-Output 'ripgrep 15.2.0'"
  $script:FixtureLock=[pscustomobject]@{dependencies=[pscustomobject]@{
   node=[pscustomobject]@{version='26.7.0';reference_sha256=(Get-Sha256File $script:GoodNode);winget_id='OpenJS.NodeJS'}
   ripgrep=[pscustomobject]@{version='15.2.0';reference_sha256=(Get-Sha256File $script:RgFixture);winget_id='fixture'}
  }}
  $script:InstallCalls=0;$script:InstallBroken=$false;$script:PathLookups=0
  # Host integration is replaced; actual Ensure-PinnedDependencies, version
  # invocation, SHA checks, rg destination read-back and launcher owner execute.
  # No real Program Files/PATH executable, winget or helper is accessed.
  function script:Test-IsAdministrator {$true}
  function script:Get-HelperNodeExecutablePath {$script:NodeFixture}
  function script:Read-RuntimeLock {param($PackageRoot) $script:FixtureLock}
  function script:Find-RipgrepExecutable {$script:RgFixture}
  function script:Get-Command {
   param($Name,$ErrorAction)
   if($Name -eq 'node.exe'){$script:PathLookups++;return [pscustomobject]@{Source=$script:WrongPathNode}}
   if($Name -eq 'winget.exe'){return [pscustomobject]@{Source='fixture'}}
   Microsoft.PowerShell.Core\Get-Command -Name $Name
  }
  function script:winget.exe {
   $script:InstallCalls++;$script:LASTEXITCODE=0
   if(-not $script:InstallBroken){Copy-Item -LiteralPath $script:GoodNode -Destination $script:NodeFixture -Force}
  }
  function Verify([switch]$AllowInstall){Ensure-PinnedDependencies -PackageRoot $Root -ProgramDataRoot (Join-Path $Root 'data') -NoInstall:(-not $AllowInstall)}
  function Reject($Prefix){$message='';try{Verify|Out-Null}catch{$message=$_.Exception.Message};Check ($message.StartsWith($Prefix)) ('fail closed '+$Prefix)}
  Reject 'NODE_LAUNCH_PATH_MISSING:'
  Check ($script:InstallCalls -eq 0) 'NoInstall never invokes winget'
  Copy-Item $script:GoodNode $script:NodeFixture
  $health=Get-WorkerDependencyHealth -ProgramDataRoot (Join-Path $Root 'data')
  Check ($health.node.healthy -and $health.node.path -ceq $script:NodeFixture -and $script:PathLookups -eq 0) 'dependency status uses fixed path, not PATH'
  $valid=Verify
  Check ($valid.node.path -ceq $script:NodeFixture -and $valid.node.version -eq 'v26.7.0' -and $valid.node.sha256 -eq $script:FixtureLock.dependencies.node.reference_sha256 -and $valid.node.action -eq 'REUSED' -and $script:PathLookups -eq 0) 'correct fixed Node verified despite other pinned PATH Node'
  $launch=New-HelperRunAsCommand -HelperPath (Join-Path $Root 'helper.mjs') -ProgramDataRoot (Join-Path $Root 'data')
  $decoded=[Text.Encoding]::Unicode.GetString([Convert]::FromBase64String(($launch -split ' ')[-1]))
  Check ($decoded.Contains("& '$($valid.node.path)' ") -and -not $decoded.Contains($script:WrongPathNode)) 'verified and launched Node share exact path'
  W $script:NodeFixture "Write-Output 'v26.7.0' # modified bytes"
  Reject 'NODE_HASH_MISMATCH:'
  W $script:NodeFixture "Write-Output 'v22.0.0'"
  Reject 'NODE_VERSION_MISMATCH:'
  $updated=Verify -AllowInstall
  Check ($updated.node.action -eq 'UPDATED' -and $updated.node.sha256 -eq $script:FixtureLock.dependencies.node.reference_sha256 -and $script:InstallCalls -eq 1) 'allowed pinned update checked at fixed path'
  Remove-Item -LiteralPath $script:NodeFixture
  $installed=Verify -AllowInstall
  Check ($installed.node.action -eq 'INSTALLED' -and $installed.node.path -ceq $script:NodeFixture -and $script:InstallCalls -eq 2) 'allowed pinned install checked at fixed path'
  Remove-Item -LiteralPath $script:NodeFixture;$script:InstallBroken=$true;$message=''
  try{Verify -AllowInstall|Out-Null}catch{$message=$_.Exception.Message}
  Check ($message -eq 'NODE_NOT_FOUND_AFTER_INSTALL') 'successful winget without fixed binary cannot PASS'
  Write-Host ('NODE_LAUNCH_PATH_REGRESSION_PASS checks='+$script:Checks+' production_access=false')
 } $fixture
} finally {
 if(-not ([IO.Path]::GetFullPath($fixture)).StartsWith(([IO.Path]::GetFullPath([IO.Path]::GetTempPath())).TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'FIXTURE_OUTSIDE_TEMP'}
 Remove-Item -LiteralPath $fixture -Recurse -Force
}
