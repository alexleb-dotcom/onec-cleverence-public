$ErrorActionPreference='Stop'
if($PSVersionTable.PSVersion.Major -ne 5){throw "WINDOWS_PS51_REQUIRED: $($PSVersionTable.PSVersion)"}
$Product=Split-Path -Parent $PSScriptRoot
$Repo=Split-Path -Parent (Split-Path -Parent $Product)

$node=Get-Command node.exe -ErrorAction Stop
& $node.Source (Join-Path $PSScriptRoot 'local-quality-adapter-regression.mjs') --windows-live
if($LASTEXITCODE -ne 0){throw "LOCAL_QUALITY_NODE_REGRESSION_FAILED:$LASTEXITCODE"}

$core=Get-Content -LiteralPath (Join-Path $Product 'core\OneCChatWorker.Core.psm1') -Raw -Encoding UTF8
$launcher=Get-Content -LiteralPath (Join-Path $Product 'OneCChatWorker.ps1') -Raw -Encoding UTF8
$helper=Get-Content -LiteralPath (Join-Path $Product 'runtime\hosted-helper.mjs') -Raw -Encoding UTF8
$adapter=Get-Content -LiteralPath (Join-Path $Product 'runtime\local-quality-adapter.mjs') -Raw -Encoding UTF8
$lock=Get-Content -LiteralPath (Join-Path $Product 'runtime.lock.json') -Raw -Encoding UTF8|ConvertFrom-Json

function Assert([bool]$Condition,[string]$Name){if(-not $Condition){throw "ASSERT_FAILED:$Name"};Write-Host "PASS $Name"}

Assert (($lock.hosted_mcp.model_surface -join ',') -eq 'source_context,source_search,source_read,proposal_write,proposal_read,task_checkpoint_write') 'helper_six_ops_exact'
Assert ($helper.Contains("quality.runConfirmed(rel,v.sha256)")) 'quality_only_after_successful_source_read'
Assert (-not $helper.Substring($helper.IndexOf("async function sourceSearch"),$helper.IndexOf("async function exec")-$helper.IndexOf("async function sourceSearch")).Contains('runConfirmed')) 'source_search_never_runs_quality'
Assert ($adapter.Contains("shell:false") -and $adapter.Contains("POWERSHELL51='C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe'")) 'fixed_ps51_shell_false'
Assert (($adapter.Contains("maxBytes=1200")) -and ($helper.Contains('quality_targets')) -and ($helper.Contains('.slice(0,2)'))) 'prepared_quality_and_cache_bounded'

$start=$launcher.Substring($launcher.IndexOf('function Run-Start {'),$launcher.IndexOf('function Run-Continue {')-$launcher.IndexOf('function Run-Start {'))
$status=$core.Substring($core.IndexOf('function Get-WorkerStatus {'),$core.IndexOf('function Get-WorkerDiagnostics {')-$core.IndexOf('function Get-WorkerStatus {'))
$admission=$core.Substring($core.IndexOf('function New-Admission {'),$core.IndexOf('function Test-IsAdministrator {')-$core.IndexOf('function New-Admission {'))
Assert (([regex]::Matches($start,'Get-FastProjectState').Count -eq 1) -and (-not $start.Contains('Get-TreeDigest')) -and (-not $start.Contains('Verify-WorkerProject'))) 'start_fast_path_preserved'
Assert (-not $status.Contains('Get-TreeDigest') -and -not $status.Contains('Verify-WorkerProject')) 'status_fast_path_preserved'
Assert (-not $admission.Contains('Get-TreeDigest') -and -not $admission.Contains('Verify-WorkerProject')) 'admission_fast_path_preserved'
Assert ($admission.Contains('task_goal_sha256') -and $admission.Contains('Get-Sha256Text $TaskGoal') -and $admission.Contains('TASK_GOAL_BYTE_CAP')) 'task_goal_bounded_hash_bound'
Assert (-not $start.Contains('TaskGoal') -or -not $start.Contains('SafeDetails @{task_goal')) 'task_goal_not_durable_logged'
Assert ($helper.Contains("'PROPOSAL_NOT_APPLIED'") -and $helper.Contains("_proposal_provenance.json")) 'proposal_semantics_preserved'
Assert ($adapter.Contains('SOURCE_CHANGED_DURING_RUN') -and $helper.Contains('state.quality_targets=[]')) 'source_drift_discards_cache'
Assert ($adapter.Contains("FORM_HANDLER_MISSING") -and $adapter.Contains("FORM_HANDLER_DUPLICATE") -and $adapter.Contains("FORM_HANDLER_CONTEXT_MISMATCH") -and $adapter.Contains("FORM_VALUE_CONVERSION_CONTEXT")) 'tiny_overlay_exact_scope'

Write-Host "LOCAL_QUALITY_WINDOWS_PS51_REGRESSION_PASS"
