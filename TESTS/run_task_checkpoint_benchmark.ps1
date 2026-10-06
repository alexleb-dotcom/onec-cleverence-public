$ErrorActionPreference='Stop'
if($PSVersionTable.PSVersion.Major -ne 5){throw "WINDOWS_PS51_REQUIRED: $($PSVersionTable.PSVersion)"}
$tests=Join-Path (Split-Path -Parent $PSScriptRoot) 'PRODUCT\OneCChatWorker\tests'
Import-Module (Join-Path $tests 'TestScratch.psm1') -Force -DisableNameChecking
$s=New-OneCTestScratch -Purpose 'TaskCheckpointBench'
$old=$env:ONEC_TEST_SCRATCH_ROOT
try{
 $env:ONEC_TEST_SCRATCH_ROOT=$s.path
 & node.exe (Join-Path $PSScriptRoot 'benchmark_task_checkpoint_recovery.mjs')
 if($LASTEXITCODE -ne 0){throw "TASK_CHECKPOINT_BENCHMARK_FAILED: $LASTEXITCODE"}
}finally{
 $env:ONEC_TEST_SCRATCH_ROOT=$old
 Remove-OneCTestScratch -Path $s.path -RunId $s.run_id -Base $s.base|Out-Null
}
