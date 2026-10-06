$ErrorActionPreference='Stop'
if($PSVersionTable.PSVersion.Major -ne 5){throw "WINDOWS_PS51_REQUIRED: $($PSVersionTable.PSVersion)"}
Import-Module (Join-Path $PSScriptRoot 'TestScratch.psm1') -Force -DisableNameChecking
$s=New-OneCTestScratch -Purpose 'TaskCheckpoint92'
$old=$env:ONEC_TEST_SCRATCH_ROOT
try{
 $env:ONEC_TEST_SCRATCH_ROOT=$s.path
 & node.exe (Join-Path $PSScriptRoot 'task-checkpoint-regression.mjs')
 if($LASTEXITCODE -ne 0){throw "TASK_CHECKPOINT_NODE_REGRESSION_FAILED: $LASTEXITCODE"}
 $package=Split-Path -Parent $PSScriptRoot
 Import-Module (Join-Path $package 'core\OneCChatWorker.Core.psm1') -Force -DisableNameChecking
 $retPd=Join-Path $s.path 'retention-pd'
 $ret=Invoke-TaskStateRetention -ProgramDataRoot $retPd -RetentionDays 30
 if(Test-Path -LiteralPath (Join-Path $retPd 'task-state\P92\old-abandoned')){throw 'RETENTION_OLD_ABANDONED_NOT_REMOVED'}
 if(-not(Test-Path -LiteralPath (Join-Path $retPd 'task-state\P92\old-active'))){throw 'RETENTION_ACTIVE_REMOVED'}
 if(-not(Test-Path -LiteralPath (Join-Path $retPd 'task-state\P92\fresh-task'))){throw 'RETENTION_FRESH_REMOVED'}
 if(-not(Test-Path -LiteralPath (Join-Path $retPd 'task-state\P92\corrupt-old'))){throw 'RETENTION_CORRUPT_NOT_FAIL_CLOSED'}
 if(@($ret.removed|Where-Object{$_ -like '*old-abandoned'}).Count -ne 1){throw 'RETENTION_REMOVED_LIST_INVALID'}
 if(@($ret.invalid|Where-Object{$_ -like '*corrupt-old'}).Count -ne 1){throw 'RETENTION_INVALID_LIST_MISSING'}
 Write-Host 'TASK_STATE_RETENTION_PS51_PASS'
 Write-Host 'TASK_CHECKPOINT_PS51_WRAPPER_PASS'
}finally{
 $env:ONEC_TEST_SCRATCH_ROOT=$old
 Remove-OneCTestScratch -Path $s.path -RunId $s.run_id -Base $s.base|Out-Null
}
