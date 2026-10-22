param([Parameter(Mandatory)][string]$BuildRoot,[Parameter(Mandatory)][string]$EvidenceRoot,[string]$DotnetPath='dotnet')
$ErrorActionPreference='Stop'
if($env:GITHUB_ACTIONS -ne 'true'){throw 'INSTALL_SMOKE_REQUIRES_DISPOSABLE_GITHUB_WINDOWS_RUNNER'}
if(Get-LocalUser OneCSourceReader -ErrorAction SilentlyContinue){throw 'FIXTURE_READER_ALREADY_EXISTS'}
$root=Join-Path $env:RUNNER_TEMP ('orbit-install-'+[guid]::NewGuid().ToString('N'))
$app=Join-Path $root 'app';$worker=Join-Path $root 'worker';$data=Join-Path $root 'data'
New-Item -ItemType Directory -Path $root|Out-Null
New-Item -ItemType Directory -Force -Path $EvidenceRoot|Out-Null
function Check($Value,$Name){if(-not $Value){throw ('INSTALL_SMOKE_ASSERT:'+ $Name)};Write-Host ('PASS '+$Name)}
function RunProcess($Exe,$Arguments,[int]$ExpectedExit=0){
 $start=New-Object Diagnostics.ProcessStartInfo;$start.FileName=$Exe;$start.Arguments=$Arguments;$start.UseShellExecute=$false;$start.CreateNoWindow=$true
 $process=[Diagnostics.Process]::Start($start);try{if(-not $process.WaitForExit(240000)){$process.Kill();throw 'SMOKE_PROCESS_TIMEOUT'};Check ($process.ExitCode -eq $ExpectedExit) ($Exe+' exit code')}finally{$process.Dispose()}
}
try {
 RunProcess (Join-Path $BuildRoot 'OneCOrbit-Setup.exe') ('/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /DIR="'+$app+'" /WORKERROOT="'+$worker+'" /DATAROOT="'+$data+'" /LOG="'+(Join-Path $EvidenceRoot 'install.log')+'"')
 $receipt=Get-Content -LiteralPath (Join-Path $app 'install-receipt.json') -Raw -Encoding UTF8|ConvertFrom-Json
 Copy-Item -LiteralPath (Join-Path $app 'install-receipt.json') -Destination (Join-Path $EvidenceRoot 'install-receipt.json')
 $launcher=Join-Path $worker 'OneCChatWorker.ps1'
 function Context {
  $raw=& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $launcher -Mode UI_CONTEXT -Json -WorkerRoot $worker -ProgramDataRoot $data
  if($LASTEXITCODE -ne 0){throw 'SMOKE_CONTEXT_FAILED'}
  ($raw -join [Environment]::NewLine)|ConvertFrom-Json
 }
 $context=Context
 Check ($context.product.installed -and $context.product.integrity_status -eq 'PASS' -and @($context.projects).Count -eq 0) 'installed owner confirms zero projects'
 $fixtureProject=Join-Path $PSScriptRoot 'ControlCenter.UiFixture/ControlCenter.UiFixture.csproj'
 & $DotnetPath build $fixtureProject -c Release --artifacts-path (Join-Path $root 'fixtures') --nologo
 if($LASTEXITCODE -ne 0){throw 'SMOKE_UI_FIXTURE_BUILD_FAILED'}
 $fixture=Join-Path $root 'fixtures/bin/ControlCenter.UiFixture/release_win-x64/OneCArchitecture.ControlCenter.UiFixture.dll'
 $gui=Join-Path $data 'product/control-center/OneCArchitecture.ControlCenter.exe'
 & $DotnetPath $fixture --first-run $gui (Join-Path $EvidenceRoot 'first-run')
 if($LASTEXITCODE -ne 0){throw 'SMOKE_FIRST_RUN_WIZARD_FAILED'}
 Add-Type -AssemblyName System.IO.Compression.FileSystem
 function Archive($Name){
  $path=Join-Path $root ($Name+'.zip');$zip=[IO.Compression.ZipFile]::Open($path,'Create')
  try{$entry=$zip.CreateEntry('Configuration.xml');$writer=New-Object IO.StreamWriter($entry.Open());try{$writer.Write('<Configuration name="'+$Name+'"/>')}finally{$writer.Dispose()}}finally{$zip.Dispose()};$path
 }
 $request=Join-Path $root 'request.json'
 @{project_id='fixture';display_name='Project fixture';participant_id='main';role='ERP';platform='ONEC';main_archive=(Archive main);extension_archives=@((Archive extension))}|ConvertTo-Json|Set-Content -LiteralPath $request -Encoding UTF8
 & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $launcher -Mode BOOTSTRAP_PROJECT -Json -WorkerRoot $worker -ProgramDataRoot $data -UiInputPath $request | Tee-Object -FilePath (Join-Path $EvidenceRoot 'bootstrap.json')
 if($LASTEXITCODE -ne 0){throw 'SMOKE_BOOTSTRAP_FAILED'}
 $context=Context
 Check (@($context.projects).Count -eq 1 -and $context.projects[0].fast_state -eq 'ACCEPTED') 'reopened owner reads accepted project'
 $context|ConvertTo-Json -Depth 30|Set-Content -LiteralPath (Join-Path $EvidenceRoot 'readback.json') -Encoding UTF8
 & $DotnetPath $fixture --installed $gui (Join-Path $EvidenceRoot 'reopen')
 if($LASTEXITCODE -ne 0){throw 'SMOKE_REOPEN_FAILED'}
 $payload=Join-Path $worker 'fixture/Participants/main/Target/Main/Configuration.xml'
 $before=(Get-FileHash -LiteralPath $payload -Algorithm SHA256).Hash
 # Unknown runtime data must survive uninstall.
 $unknown=Join-Path $data 'unknown-user-file.txt';[IO.File]::WriteAllText($unknown,'retain me')
 RunProcess (Join-Path $app 'unins000.exe') ('/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /LOG="'+(Join-Path $EvidenceRoot 'uninstall.log')+'"')
 Check ((Get-FileHash -LiteralPath $payload -Algorithm SHA256).Hash -eq $before) 'uninstall retains MAIN fixture'
 Check (Test-Path -LiteralPath (Join-Path $worker 'fixture/Participants/main/Target/Extensions/ext-1/Configuration.xml')) 'uninstall retains EXTENSION fixture'
 Check (Test-Path -LiteralPath $unknown) 'unknown file retained'
 foreach($file in $receipt.files){Check (-not(Test-Path -LiteralPath $file.path)) ('no owned runtime orphan '+$file.path)}
 Check (-not(Test-Path -LiteralPath (Join-Path $app 'package'))) 'no installer package orphan'
 # Test deterministic rollback after the runtime has been written, then an
 # explicit journal replay as recovery from an interrupted installer process.
 Remove-LocalUser OneCSourceReader
 $rollbackApp=Join-Path $root 'rollback-app'
 New-Item -ItemType Directory -Path $rollbackApp|Out-Null
 Copy-Item -LiteralPath (Join-Path $BuildRoot 'payload') -Destination (Join-Path $rollbackApp 'package') -Recurse
 $setupScript=Join-Path $PSScriptRoot '../installer/SetupRuntime.ps1'
 $rw=Join-Path $root 'rollback-worker';$rd=Join-Path $root 'rollback-data';$rs=Join-Path $root 'rollback-shortcuts'
 RunProcess 'powershell.exe' ('-NoProfile -ExecutionPolicy Bypass -File "'+$setupScript+'" -Mode Install -AppRoot "'+$rollbackApp+'" -WorkerRoot "'+$rw+'" -DataRoot "'+$rd+'" -ShortcutRoot "'+$rs+'" -FaultInjection AFTER_RUNTIME') 1
 Check (-not(Test-Path -LiteralPath $rw) -and -not(Test-Path -LiteralPath $rd)) 'rollback leaves no owned runtime files'
 Check (-not(Get-LocalUser OneCSourceReader -ErrorAction SilentlyContinue)) 'rollback removes only transaction-owned reader'
 & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $setupScript -Mode Rollback -AppRoot $rollbackApp
 Check ($LASTEXITCODE -eq 0) 'interrupted journal recovery is idempotent'
 @{result='PASS';source_head=(& git rev-parse HEAD).Trim();build_receipt=(Get-Content -LiteralPath (Join-Path $BuildRoot 'build-receipt.json') -Raw|ConvertFrom-Json);keyboard_and_dpi='See existing real WPF RU/EN and DPI fixture artifacts';limitations=@('OS UAC human consent is not proved by elevated hosted runner.','Archive selection dialogs are not driven in this smoke; native wizard boot/cancel and real Worker import are separate checks.')}|ConvertTo-Json -Depth 15|Set-Content -LiteralPath (Join-Path $EvidenceRoot 'result.json') -Encoding UTF8
} finally {
 foreach($name in @('setup-runtime.log','install-intent.json','install-journal.json')){
  $path=Join-Path $app $name
  if(Test-Path -LiteralPath $path){Copy-Item -LiteralPath $path -Destination (Join-Path $EvidenceRoot $name) -Force}
 }
 # Disposable hosted account only. No local operator execution is permitted.
 if(Get-LocalUser OneCSourceReader -ErrorAction SilentlyContinue){Remove-LocalUser OneCSourceReader}
}
