param([string]$PackageRoot=(Split-Path -Parent $PSScriptRoot))
$ErrorActionPreference='Stop'
Import-Module (Join-Path $PSScriptRoot 'TestScratch.psm1') -Force -DisableNameChecking
$scratch=New-OneCTestScratch -Purpose OrbitBootstrap
$module=Import-Module (Join-Path $PackageRoot 'core/OneCChatWorker.Core.psm1') -Force -DisableNameChecking -PassThru
try {
 & $module {
  param($Root)
  function script:Test-IsAdministrator {$true}
  function script:Apply-ProjectAcl {param($ProjectRoot)}
  function script:Set-SourceUpdateTreeAcl {param($Path,$OperatorIdentity,[switch]$Writable)}
  function script:Protect-SourceUpdateMetadata {param($Path,$OperatorIdentity)}
  function Check($Value,$Name){if(-not $Value){throw ('ASSERTION_FAILED:'+ $Name)};Write-Host ('PASS '+$Name)}
  Add-Type -AssemblyName System.IO.Compression.FileSystem
  function Zip($Name,$Entries){
   $path=Join-Path $Root ($Name+'.zip');$zip=[IO.Compression.ZipFile]::Open($path,'Create')
   try{foreach($key in $Entries.Keys){$entry=$zip.CreateEntry($key);$writer=New-Object IO.StreamWriter($entry.Open());try{$writer.Write($Entries[$key])}finally{$writer.Dispose()}}}finally{$zip.Dispose()}
   $path
  }
  $main=Zip main @{'Configuration.xml'='<Configuration name="main"/>'; 'CommonModules/Test/Ext/Module.bsl'='Procedure Test() Export EndProcedure'}
  $ext=Zip ext @{'Configuration.xml'='<Configuration name="extension"/>'}
  foreach($bad in @('../escaped.xml','C:/escape.xml','x:ads.xml','CON.xml','trailing. /file.xml','Module.exe')){
   $path=Zip ([guid]::NewGuid().ToString('N')) @{'Configuration.xml'='<Configuration/>'; $bad='bad'}
   $rejected=$false;try{Expand-OrbitXmlArchive $path (Join-Path $Root ([guid]::NewGuid().ToString('N')))}catch{$rejected=$_.Exception.Message -like 'BOOTSTRAP_*'}
   Check $rejected ('reject ZIP '+$bad)
  }
  $worker=Join-Path $Root 'worker';$data=Join-Path $Root 'data'
  Write-WorkerCatalog ([pscustomobject]@{schema_version=1;projects=@()}) $worker
  $bad=Zip invalid @{'Configuration.xml'='<broken'}
  try{New-OrbitBootstrapProject -ProjectId rejected -DisplayName rejected -MainArchive $bad -WorkerRoot $worker -ProgramDataRoot $data|Out-Null;throw 'EXPECTED_FAILURE'}catch{if($_.Exception.Message -eq 'EXPECTED_FAILURE'){throw}}
  Check (@((Read-WorkerCatalog $worker).projects).Count -eq 0) 'failed XML import leaves zero registered projects'
  Check (-not(Test-Path -LiteralPath (Join-Path $worker 'rejected'))) 'failed import has no canonical project'
  $recoverWorker=Join-Path $Root 'recover-worker'
  Write-WorkerCatalog ([pscustomobject]@{schema_version=1;projects=@()}) $recoverWorker
  $fault=$false
  try{New-OrbitBootstrapProject -ProjectId recovery -DisplayName recovery -MainArchive $main -WorkerRoot $recoverWorker -ProgramDataRoot $data -FaultInjection AFTER_MOVE|Out-Null}catch{$fault=$_.Exception.Message -eq 'BOOTSTRAP_TEST_FAULT_AFTER_MOVE'}
  Check ($fault -and @((Read-WorkerCatalog $recoverWorker).projects).Count -eq 0) 'interrupted promotion leaves no partial catalog project'
  $resumed=New-OrbitBootstrapProject -ProjectId recovery -DisplayName recovery -MainArchive $main -WorkerRoot $recoverWorker -ProgramDataRoot $data
  Check ($resumed.recovered -and $resumed.fast_state.state -eq 'ACCEPTED') 'retry resumes exact prepared promotion'
  $driftWorker=Join-Path $Root 'drift-worker'
  Write-WorkerCatalog ([pscustomobject]@{schema_version=1;projects=@()}) $driftWorker
  try{New-OrbitBootstrapProject -ProjectId drift -DisplayName drift -MainArchive $main -WorkerRoot $driftWorker -ProgramDataRoot $data -FaultInjection AFTER_MOVE|Out-Null}catch{if($_.Exception.Message -ne 'BOOTSTRAP_TEST_FAULT_AFTER_MOVE'){throw}}
  [IO.File]::WriteAllText((Join-Path $driftWorker 'drift/Participants/main/Target/Main/Configuration.xml'),'<Changed/>')
  $held=$false
  try{New-OrbitBootstrapProject -ProjectId drift -DisplayName drift -MainArchive $main -WorkerRoot $driftWorker -ProgramDataRoot $data|Out-Null}catch{$held=$_.Exception.Message -eq 'BOOTSTRAP_RECOVERY_SOURCE_DRIFT_HOLD'}
  Check ($held -and @((Read-WorkerCatalog $driftWorker).projects).Count -eq 0) 'changed prepared Source is never published on recovery'
  $result=New-OrbitBootstrapProject -ProjectId fixture -DisplayName 'Проект / Project' -MainArchive $main -ExtensionArchives @($ext) -WorkerRoot $worker -ProgramDataRoot $data
  Check ($result.status -eq 'READY' -and $result.fast_state.state -eq 'ACCEPTED') 'MAIN plus EXTENSION accepted through real owner'
  $manifest=Get-Content -LiteralPath (Get-ProjectManifestPath fixture $worker) -Raw -Encoding UTF8|ConvertFrom-Json
  Check (@($manifest.accepted_snapshot.artifacts).Count -eq 2) 'readback contains both accepted artifacts'
  Check ($manifest.accepted_snapshot.fingerprint_inventory_state -eq 'PRESENT') 'fingerprint evidence retained'
  Check (Test-Path -LiteralPath (Read-WorkerCatalog $worker).projects[0].participants[0].target.main.source_path) 'published source reference remains valid'
  $rejected=$false;try{New-OrbitBootstrapProject -ProjectId another -DisplayName another -MainArchive $main -WorkerRoot $worker -ProgramDataRoot $data}catch{$rejected=$_.Exception.Message -eq 'BOOTSTRAP_REQUIRES_CONFIRMED_ZERO_PROJECTS'}
  Check $rejected 'nonzero catalog never treated as zero'
  $additional=New-OrbitBootstrapProject -ProjectId second -DisplayName second -MainArchive $main -WorkerRoot $worker -ProgramDataRoot $data -RequireZeroProjects $false
  Check ($additional.status -eq 'READY' -and @((Read-WorkerCatalog $worker).projects).Count -eq 2) 'explicit Add Project retains existing catalog entries'

 } $scratch.path
} finally {Remove-OneCTestScratch -Path $scratch.path|Out-Null}
