param([string]$PackageRoot=(Split-Path -Parent $PSScriptRoot))
$ErrorActionPreference='Stop'
Import-Module (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Utility') -Force
$PackageRoot=[IO.Path]::GetFullPath($PackageRoot)
$previousLocalAppData=$env:LOCALAPPDATA
$fixtureBase=Join-Path ([IO.Path]::GetTempPath()) ('onec-installer-'+[guid]::NewGuid().ToString('N'))
$env:LOCALAPPDATA=$fixtureBase
Import-Module (Join-Path $PSScriptRoot 'TestScratch.psm1') -Force -DisableNameChecking
$scratch=New-OneCTestScratch -Purpose 'HelperInstallerImports'
$module=Import-Module (Join-Path $PackageRoot 'core\OneCChatWorker.Core.psm1') -Force -DisableNameChecking -PassThru
try {
 & $module {
  param($PackageRoot,$FixtureRoot)
  $script:FixtureRoot=$FixtureRoot
  $worker=Join-Path $FixtureRoot 'worker';$data=Join-Path $FixtureRoot 'programdata'
  # Read-only SID lookup. No account is created or changed; a stock Windows
  # identity covers a development machine where OneCSourceReader is absent.
  try{$readerSid=(New-Object Security.Principal.NTAccount("$env:COMPUTERNAME\$script:ReaderName")).Translate([Security.Principal.SecurityIdentifier]).Value}
  catch{$readerSid='S-1-5-19'}
  $script:FixtureIdentity=[pscustomobject]@{
   account='isolated-test-operator';sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
   icacls_identity=('*'+[Security.Principal.WindowsIdentity]::GetCurrent().User.Value)
   reader_sid=$readerSid;reader_icacls_identity=('*'+$readerSid)
  }
  $script:RealIcacls=(Get-Command Invoke-IcaclsChecked).ScriptBlock
  $script:AclCalls=@()
  # Mock host integration only. No account creation, dependency installation or
  # external shortcut. Copier, integrity and ACL owners remain actual functions.
  function script:Test-IsAdministrator {$true}
  function script:Get-LocalUser {param($Name,$ErrorAction) [pscustomobject]@{Name=$Name}}
  function script:New-LocalUser {throw 'TEST_MUST_NOT_CREATE_ACCOUNT'}
  function script:Ensure-PinnedDependencies {
   [pscustomobject]@{node=[pscustomobject]@{version='fixture';sha256='fixture'};ripgrep=[pscustomobject]@{version='fixture';sha256='fixture'}}
  }
  function script:Resolve-WorkerOperatorIdentity {$script:FixtureIdentity}
  function script:Get-ControlCenterStartMenuShortcutPath {Join-Path $script:FixtureRoot 'fixture-shortcut.lnk'}
  function script:Invoke-IcaclsChecked {
   param($Path,[string[]]$Arguments)
   if(-not ([IO.Path]::GetFullPath($Path)).StartsWith($script:FixtureRoot+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'TEST_ACL_OUTSIDE_FIXTURE'}
   $script:AclCalls+=,[pscustomobject]@{path=$Path;arguments=$Arguments}
  }
  function Check([bool]$Condition,[string]$Name){if(-not $Condition){throw "ASSERTION_FAILED: $Name"};Write-Host "PASS $Name"}
  $lock=Read-RuntimeLock $PackageRoot
  $modules=@('helper-https-pull.mjs','https-pull-auth.mjs','task-checkpoint-store.mjs')
  $sentinels=@{}
  foreach($phase in @('clean','update')){
   $script:AclCalls=@()
   $install=Install-OneCChatWorker -PackageRoot $PackageRoot -WorkerRoot $worker -ProgramDataRoot $data -SkipDependencies
   Check ($install.installed_integrity.status -eq 'PASS') ($phase+' actual installer/integrity owner')
   foreach($name in $modules){
    $target=Join-Path $data ('helper\'+$name)
    Check ((Get-Sha256File $target) -eq $lock.components.('runtime/'+$name)) ($phase+' installed SHA '+$name)
    $grants=@($script:AclCalls|Where-Object{$_.path -eq $target -and $_.arguments[0] -eq '/grant:r'})
    Check ($grants.Count -eq 1 -and $grants[0].arguments -contains ($script:FixtureIdentity.reader_icacls_identity+':RX')) ($phase+' ACL wiring reader RX '+$name)
   }
   & node --experimental-vm-modules (Join-Path $PackageRoot 'tests\helper-import-link.mjs') $data
   Check ($LASTEXITCODE -eq 0) ($phase+' installed helper imports link without execution')
   if($phase -eq 'update'){
    foreach($file in $sentinels.Keys){Check ((Get-Sha256File $file) -eq $sentinels[$file]) 'update preserves fixture state/project bytes'}
    break
   }
   foreach($name in $modules){
    $target=Join-Path $data ('helper\'+$name);$bytes=[IO.File]::ReadAllBytes($target)
    foreach($damage in @('missing','corrupt')){
     if($damage -eq 'missing'){Remove-Item -LiteralPath $target}else{[IO.File]::WriteAllText($target,'changed fixture bytes')}
     $rejected=$false
     try{Test-InstalledProductIntegrity -WorkerRoot $worker -ProgramDataRoot $data|Out-Null}
     catch{if($_.Exception.Message -ne ('INSTALLED_COMPONENT_HASH_MISMATCH: runtime/'+$name)){throw};$rejected=$true}
     Check $rejected ('actual integrity fails closed '+$damage+' '+$name)
     [IO.File]::WriteAllBytes($target,$bytes)
    }
   }
   foreach($rel in @('runtime\active-admission.json','runtime\hosted-helper-state.json','secrets\helper-secret.txt','task-state\existing.json')){
    $file=Join-Path $data $rel;[IO.File]::WriteAllText($file,'isolated preserved bytes');$sentinels[$file]=Get-Sha256File $file
   }
   foreach($rel in @('P\Participants\fixture.txt','P\Output\fixture.txt')){
    $file=Join-Path $worker $rel;New-Item -ItemType Directory -Force -Path (Split-Path -Parent $file)|Out-Null
    [IO.File]::WriteAllText($file,'isolated preserved project bytes');$sentinels[$file]=Get-Sha256File $file
   }
   $sentinels[(Get-CatalogPath $worker)]=Get-Sha256File (Get-CatalogPath $worker)
   # INSTALL and UPDATE share this owner. Model the previous installed layout;
   # never invoke launcher UPDATE or a task lifecycle operation.
   Remove-Item -LiteralPath (Join-Path $data 'helper\helper-https-pull.mjs')
   [IO.File]::WriteAllText((Join-Path $data 'helper\https-pull-auth.mjs'),'previous module bytes')
  }
  $badSource=Join-Path $FixtureRoot 'tampered-module.mjs';[IO.File]::WriteAllText($badSource,'tampered package bytes')
  $badDestination=Join-Path $FixtureRoot 'must-not-copy.mjs';$rejected=$false
  try{Copy-ProductComponent -Source $badSource -Destination $badDestination -ExpectedSha256 $lock.components.'runtime/https-pull-auth.mjs'|Out-Null}
  catch{if($_.Exception.Message -notlike 'PACKAGE_COMPONENT_HASH_MISMATCH:*'){throw};$rejected=$true}
  Check ($rejected -and -not(Test-Path -LiteralPath $badDestination)) 'tampered package rejected before copy'
  # Real Windows ACL API, only isolated module files. Identity lookup changes
  # no account or production OneCSourceReader permissions.
  Set-Item -Path Function:script:Invoke-IcaclsChecked -Value $script:RealIcacls
  foreach($name in $modules){
   $target=Join-Path $data ('helper\'+$name)
   Protect-WorkerRuntimeFile -Path $target -Identity $script:FixtureIdentity
   $acl=Get-Acl -LiteralPath $target
   $rules=@($acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier]))
   $reader=@($rules|Where-Object{$_.IdentityReference.Value -eq $script:FixtureIdentity.reader_sid})
   $allowedRights=[Security.AccessControl.FileSystemRights]::ReadAndExecute -bor [Security.AccessControl.FileSystemRights]::Synchronize
   Check ($acl.AreAccessRulesProtected -and $reader.Count -eq 1 -and $reader[0].AccessControlType -eq 'Allow' -and ($reader[0].FileSystemRights -band [Security.AccessControl.FileSystemRights]::ReadAndExecute) -eq [Security.AccessControl.FileSystemRights]::ReadAndExecute -and ($reader[0].FileSystemRights -band (-bnot $allowedRights)) -eq 0) ('real Windows ACL reader RX only '+$name)
   Check (@($rules|Where-Object{$_.IsInherited -or $_.IdentityReference.Value -in @('S-1-1-0','S-1-5-11','S-1-5-32-545')}).Count -eq 0) ('real Windows ACL no inherited/broad grants '+$name)
  }
  Write-Host 'HELPER_INSTALLER_WINDOWS_PASS clean/update/hash/imports/ACL; production untouched'
 } $PackageRoot $scratch.path
} finally {
 $classification=Get-OneCTestScratchClassification -Path $scratch.path -Base $scratch.base
 if(-not $classification.owned -or $classification.run_id -ne $scratch.run_id){throw 'SCRATCH_BINDING_INVALID'}
 # Native PowerShell deletion only, bounded to this fresh fixture owner root.
 if(-not ([IO.Path]::GetFullPath($scratch.path)).StartsWith([IO.Path]::GetFullPath($fixtureBase)+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'SCRATCH_OUTSIDE_FIXTURE_BASE'}
 # Restore creator cleanup rights on our fixture after deliberate RX tests,
 # including a partially applied ACL if an assertion or ACL operation failed.
 & icacls.exe $fixtureBase /grant:r ('*'+[Security.Principal.WindowsIdentity]::GetCurrent().User.Value+':F') /T /C | Out-Null
 if($LASTEXITCODE -ne 0){throw 'FIXTURE_ACL_CLEANUP_FAILED'}
 Remove-Item -LiteralPath $fixtureBase -Recurse -Force
 $env:LOCALAPPDATA=$previousLocalAppData
 Remove-Module $module.Name -ErrorAction SilentlyContinue
}
