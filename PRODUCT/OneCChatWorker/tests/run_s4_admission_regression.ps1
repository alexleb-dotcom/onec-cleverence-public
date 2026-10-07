$ErrorActionPreference='Stop'
if($PSVersionTable.PSVersion.Major -ne 5){throw "WINDOWS_PS51_REQUIRED: $($PSVersionTable.PSVersion)"}
$tests=$PSScriptRoot
$package=Split-Path -Parent $tests
Import-Module (Join-Path $tests 'TestScratch.psm1') -Force -DisableNameChecking
Import-Module (Join-Path $package 'core\OneCChatWorker.Core.psm1') -Force -DisableNameChecking
$s=New-OneCTestScratch -Purpose 'S4Admission'
$worker=Join-Path $s.path 'worker'
$pd=Join-Path $s.path 'pd'
$project='S4Fixture'
$manifestDir=Join-Path $worker ($project+'\ProjectManifest')
$manifest=Join-Path $manifestDir 'project.json'
$artifact=Join-Path $worker ($project+'\Participants\ut\Target\Main')
$results=New-Object Collections.Generic.List[object]
function A([string]$n,[bool]$ok,$d=''){if(-not $ok){throw "ASSERTION_FAILED: $n :: $d"};$results.Add([pscustomobject]@{name=$n;pass=$true})}
try{
 New-Item -ItemType Directory -Force -Path $manifestDir,$artifact,(Join-Path $pd 'runtime')|Out-Null
 [IO.File]::WriteAllText((Join-Path $artifact 'Configuration.xml'),'<Configuration/>',[Text.UTF8Encoding]::new($false))
 New-Item -ItemType File -Force -Path (Join-Path $pd 'runtime\rg.exe')|Out-Null
 $doc=[ordered]@{
  schema_version=2;project_id=$project;project_root=(Join-Path $worker $project);
  participants=@([ordered]@{participant_id='ut';platform='ONEC';role='UT';active=$true;target=[ordered]@{main=[ordered]@{active=$true;canonical_path='Participants/ut/Target/Main'};extensions=@()};reference=$null});
  accepted_snapshot=[ordered]@{snapshot_contract='ACCEPTED_SNAPSHOT_V1';source_snapshot_id=('f'*64);publication_generation=1}
 }
 [IO.File]::WriteAllText($manifest,($doc|ConvertTo-Json -Depth 12),[Text.UTF8Encoding]::new($false))
 $mh=(Get-FileHash -Algorithm SHA256 $manifest).Hash.ToLowerInvariant()
 $accepted=[pscustomobject]@{project_id=$project;state='ACCEPTED';manifest_sha256=$mh;source_snapshot_id=('f'*64)}
 $a=New-Admission -ProjectId $project -TaskId 'task-s4' -TaskGoal 'bounded S4 fixture' -WorkerRoot $worker -ProgramDataRoot $pd -RelayUrl 'wss://example.invalid/helper' -AcceptedState $accepted -TaskRequestLimit 96 -TaskResultByteLimit 108000 -TaskTtlMinutes 120 -EpochSoftRequestLimit 32 -EpochSoftResultByteLimit 36000
 A 'schema_v3' ($a.schema_version -eq 3)
 A 'accounting_contract' ($a.accounting_contract -eq 'S4_DURABLE_TASK_ACCOUNTING_V1')
 A 'opaque_task_admission_id' ([string]$a.task_admission_id -match '^[a-f0-9]{32}$')
 A 'stable_session_id_opaque' ([string]$a.session_id -match '^[a-f0-9]{32}$')
 A 'ids_distinct' ($a.task_admission_id -ne $a.session_id)
 A 'snapshot_bound' ($a.source_snapshot_id -eq ('f'*64) -and $a.manifest_sha256 -eq $mh)
 A 'output_task_bound' ($a.output_task_root -eq 'Output/task-s4')
 A 'task_goal_bound' ($a.task_goal_sha256 -eq (Get-Sha256Text 'bounded S4 fixture'))
 A 'task_expiry_fixed' ([datetime]::Parse($a.task_expires_utc).ToUniversalTime() -gt [datetime]::Parse($a.task_created_utc).ToUniversalTime())
 A 'durable_caps' ($a.caps.task_request_limit -eq 96 -and $a.caps.task_result_byte_limit -eq 108000)
 A 'epoch_soft_caps' ($a.caps.epoch_soft_request_limit -eq 32 -and $a.caps.epoch_soft_result_byte_limit -eq 36000 -and $a.caps.max_result_bytes -eq 3000)
 $saved=Get-Content (Join-Path $pd 'runtime\active-admission.json') -Raw -Encoding UTF8|ConvertFrom-Json
 A 'saved_exact_identity' ($saved.task_admission_id -eq $a.task_admission_id -and $saved.session_id -eq $a.session_id)
 $pred=[pscustomobject]@{
  task_admission_id=$a.task_admission_id;checkpoint_id='checkpoint-1';checkpoint_seq=1;checkpoint_sha256=('9'*64);
  task_goal_sha256=$a.task_goal_sha256;source_snapshot_id=$a.source_snapshot_id;
  activity_cursor=[pscustomobject]@{schema='S4_ACTIVITY_CURSOR_V1';task_admission_id=$a.task_admission_id;activity_seq=0;receipt_sha256=$null}
 }
 $continued=New-Admission -ProjectId $project -TaskId 'task-s4' -TaskGoal 'bounded S4 fixture' -WorkerRoot $worker -ProgramDataRoot $pd -RelayUrl 'wss://example.invalid/helper' -AcceptedState $accepted -Predecessor $pred -TaskRequestLimit 96 -TaskResultByteLimit 108000 -TaskTtlMinutes 120 -EpochSoftRequestLimit 32 -EpochSoftResultByteLimit 36000
 A 'continuation_new_budget_identity' ($continued.task_admission_id -ne $a.task_admission_id -and $continued.session_id -ne $a.session_id)
 A 'continuation_predecessor_bound' ($continued.predecessor.task_admission_id -eq $a.task_admission_id -and $continued.predecessor.checkpoint_sha256 -eq ('9'*64) -and $continued.predecessor.activity_cursor.activity_seq -eq 0)
 $goalMismatch=$false
 try{New-Admission -ProjectId $project -TaskId 'task-s4' -TaskGoal 'different goal' -WorkerRoot $worker -ProgramDataRoot $pd -AcceptedState $accepted -Predecessor $pred -TaskRequestLimit 96 -TaskResultByteLimit 108000 -TaskTtlMinutes 120 -EpochSoftRequestLimit 32 -EpochSoftResultByteLimit 36000|Out-Null}catch{$goalMismatch=$_.Exception.Message -eq 'TASK_PREDECESSOR_GOAL_MISMATCH'}
 A 'continuation_goal_mismatch_fails_closed' $goalMismatch
 $continueParams=@((Get-Command Continue-WorkerAdmission).Parameters.Keys)
 A 'continue_predecessor_not_operator_selectable' (-not($continueParams -contains 'Predecessor') -and -not($continueParams -contains 'ProjectId') -and -not($continueParams -contains 'TaskId'))
 $launcher=Get-Content (Join-Path $package 'OneCChatWorker.ps1') -Raw -Encoding UTF8
 A 'explicit_continue_operator_action_present' ($launcher.Contains("'CONTINUE' {Run-Continue;break}") -and $launcher.Contains("recommended='Continue previous task'"))
 $packagePolicy=Get-S4AdmissionPolicy
 A 'runtime_lock_package_layout_exact' ($packagePolicy.admission_schema -eq 3 -and $packagePolicy.candidate.task_request_limit -eq 2048 -and $packagePolicy.candidate.task_result_byte_limit -eq 2097152 -and $packagePolicy.candidate.task_ttl_minutes -eq 720)
 $installedProduct=Join-Path $s.path 'installed-product';New-Item -ItemType Directory -Force -Path $installedProduct|Out-Null
 $installedCore=Join-Path $installedProduct 'OneCChatWorker.Core.psm1'
 Copy-Item -LiteralPath (Join-Path $package 'core\OneCChatWorker.Core.psm1') -Destination $installedCore
 Copy-Item -LiteralPath (Join-Path $package 'runtime.lock.json') -Destination (Join-Path $installedProduct 'runtime.lock.json')
 $probe=Join-Path $s.path 'runtime-lock-probe.ps1'
 $probeText=@'
param([Parameter(Mandatory)][string]$Core,[switch]$ExpectMissing)
$ErrorActionPreference='Stop'
Import-Module $Core -Force -DisableNameChecking
try{
 $policy=Get-S4AdmissionPolicy
 if($ExpectMissing){Write-Output 'UNEXPECTED_SUCCESS';exit 7}
 $policy|ConvertTo-Json -Depth 8 -Compress
}catch{
 if($ExpectMissing){Write-Output $_.Exception.Message;exit 0}
 throw
}
'@
 [IO.File]::WriteAllText($probe,$probeText,[Text.UTF8Encoding]::new($false))
 $installedJson=& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $probe -Core $installedCore
 A 'runtime_lock_installed_layout_probe_exit' ($LASTEXITCODE -eq 0) ($installedJson -join [Environment]::NewLine)
 $installedPolicy=($installedJson -join [Environment]::NewLine)|ConvertFrom-Json
 A 'runtime_lock_installed_layout_exact' ($installedPolicy.admission_schema -eq 3 -and $installedPolicy.candidate.task_request_limit -eq 2048 -and $installedPolicy.candidate.task_result_byte_limit -eq 2097152 -and $installedPolicy.candidate.task_ttl_minutes -eq 720)
 $missingRoot=Join-Path $s.path 'missing-product';New-Item -ItemType Directory -Force -Path $missingRoot|Out-Null
 $missingCore=Join-Path $missingRoot 'OneCChatWorker.Core.psm1';Copy-Item -LiteralPath (Join-Path $package 'core\OneCChatWorker.Core.psm1') -Destination $missingCore
 $missingOutput=& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $probe -Core $missingCore -ExpectMissing
 A 'runtime_lock_missing_layout_fails_closed' ($LASTEXITCODE -eq 0 -and (($missingOutput -join [Environment]::NewLine) -match '^RUNTIME_LOCK_MISSING: expected '))
 $default=New-Admission -ProjectId $project -TaskId 'accepted-policy-default' -TaskGoal 'operator accepted S4 policy' -WorkerRoot $worker -ProgramDataRoot $pd -RelayUrl 'wss://example.invalid/helper' -AcceptedState $accepted
 A 'accepted_policy_default_exact' ($default.caps.task_request_limit -eq 2048 -and $default.caps.task_result_byte_limit -eq 2097152 -and $default.caps.ttl_minutes -eq 720)
 A 'accepted_policy_epoch_and_result_exact' ($default.caps.epoch_soft_request_limit -eq 32 -and $default.caps.epoch_soft_result_byte_limit -eq 36000 -and $default.caps.max_result_bytes -eq 3000)
 $ttlMinutes=([datetime]::Parse($default.task_expires_utc).ToUniversalTime()-[datetime]::Parse($default.task_created_utc).ToUniversalTime()).TotalMinutes
 A 'accepted_policy_ttl_720_exact' ([math]::Abs($ttlMinutes-720) -lt 0.01) $ttlMinutes

 $stateAdmission=New-Admission -ProjectId $project -TaskId 'state-next' -TaskGoal 'state transition regression' -WorkerRoot $worker -ProgramDataRoot $pd -RelayUrl 'wss://example.invalid/helper' -AcceptedState $accepted
 $statePath=Join-Path $pd 'runtime\hosted-helper-state.json';$tmpPath=$statePath+'.tmp'
 function New-StateDoc($admission,[string]$task,[string]$taskAdmission,[string]$session){
  [pscustomobject][ordered]@{schema_version=2;task_admission_id=$taskAdmission;session_id=$session;project_id=[string]$admission.project_id;task_id=$task;snapshot_id=[string]$admission.source_snapshot_id;manifest_sha256=[string]$admission.manifest_sha256;started_utc=[string]$admission.task_created_utc;expires_utc=[string]$admission.task_expires_utc;processed=[pscustomobject]@{};idempotency=[pscustomobject]@{};quality_targets=@()}
 }
 function Write-StateDoc([string]$path,$doc){[IO.File]::WriteAllText($path,($doc|ConvertTo-Json -Depth 10),[Text.UTF8Encoding]::new($false))}
 $stale=New-StateDoc $stateAdmission 'state-previous' ('1'*32) ('2'*32)
 $current=New-StateDoc $stateAdmission ([string]$stateAdmission.task_id) ([string]$stateAdmission.task_admission_id) ([string]$stateAdmission.session_id)
 Write-StateDoc $statePath $stale;Write-StateDoc $tmpPath $current
 $staleSha=Get-Sha256File $statePath
 $recovered=Repair-HelperStateForActiveAdmission -ProgramDataRoot $pd
 $published=Get-Content -LiteralPath $statePath -Raw -Encoding UTF8|ConvertFrom-Json
 A 'helper_state_stale_previous_current_tmp_promoted' ($recovered.status -eq 'RECOVERED' -and $recovered.action -eq 'CURRENT_TMP_PROMOTED' -and [string]$published.task_admission_id -eq [string]$stateAdmission.task_admission_id -and -not(Test-Path -LiteralPath $tmpPath))
 A 'helper_state_stale_evidence_preserved_first' (@($recovered.evidence).Count -eq 1 -and [string]$recovered.evidence[0].sha256 -eq $staleSha -and (Test-Path -LiteralPath ([string]$recovered.evidence[0].path) -PathType Leaf) -and (Get-Sha256File ([string]$recovered.evidence[0].path)) -eq $staleSha)

 Copy-Item -LiteralPath $statePath -Destination $tmpPath -Force
 $currentSha=Get-Sha256File $statePath
 $preserved=Repair-HelperStateForActiveAdmission -ProgramDataRoot $pd
 A 'helper_state_matching_current_preserved' ($preserved.status -eq 'CURRENT_STATE_PRESERVED' -and $preserved.action -eq 'DUPLICATE_CURRENT_TMP_REMOVED' -and (Get-Sha256File $statePath) -eq $currentSha -and -not(Test-Path -LiteralPath $tmpPath))

 $monoFinal=Get-Content -LiteralPath $statePath -Raw -Encoding UTF8|ConvertFrom-Json
 $monoFinal.processed=[pscustomobject][ordered]@{
  'mcp-final'=[pscustomobject][ordered]@{type='result';request_id='mcp-final';status='OK';metadata=[pscustomobject]@{op='read'};payload=[pscustomobject]@{value='final'}}
 }
 $monoFinal.quality_targets=@([pscustomobject]@{target_relative='old-quality'})
 Write-StateDoc $statePath $monoFinal
 $monoFinalSha=Get-Sha256File $statePath
 $monoTmp=($monoFinal|ConvertTo-Json -Depth 20|ConvertFrom-Json)
 $monoTmp.processed|Add-Member -NotePropertyName 'mcp-tmp' -NotePropertyValue ([pscustomobject][ordered]@{type='result';request_id='mcp-tmp';status='ERROR';metadata=[pscustomobject]@{op='read';error_class='EPERM'};payload=[pscustomobject]@{error='EPERM'}})
 $monoTmp.quality_targets=@([pscustomobject]@{target_relative='new-quality'})
 Write-StateDoc $tmpPath $monoTmp
 $monoTmpSha=Get-Sha256File $tmpPath
 $monoRecovered=Repair-HelperStateForActiveAdmission -ProgramDataRoot $pd
 $monoPublished=Get-Content -LiteralPath $statePath -Raw -Encoding UTF8|ConvertFrom-Json
 $evidenceShas=@($monoRecovered.evidence|ForEach-Object{[string]$_.sha256})
 A 'helper_state_current_tmp_monotonic_superset_promoted' ($monoRecovered.status -eq 'RECOVERED' -and $monoRecovered.action -eq 'CURRENT_TMP_MONOTONIC_SUPERSET_PROMOTED' -and (Get-Sha256File $statePath) -eq $monoTmpSha -and -not(Test-Path -LiteralPath $tmpPath) -and @($monoPublished.processed.PSObject.Properties).Count -eq 2)
 A 'helper_state_monotonic_archives_both_pre_states' (@($monoRecovered.evidence).Count -eq 2 -and $evidenceShas -contains $monoFinalSha -and $evidenceShas -contains $monoTmpSha -and @($monoRecovered.evidence|Where-Object{Test-Path -LiteralPath ([string]$_.path) -PathType Leaf}).Count -eq 2)

 $currentSha=Get-Sha256File $statePath
 $ambiguous=Get-Content -LiteralPath $statePath -Raw -Encoding UTF8|ConvertFrom-Json
 $ambiguous.processed.'mcp-final'.payload.value='conflicting-content'
 Write-StateDoc $tmpPath $ambiguous
 $ambiguousFailed=$false
 try{Repair-HelperStateForActiveAdmission -ProgramDataRoot $pd|Out-Null}catch{$ambiguousFailed=$_.Exception.Message -eq 'HELPER_STATE_CURRENT_TMP_AMBIGUOUS'}
 A 'helper_state_current_tmp_ambiguous_fails_closed' ($ambiguousFailed -and (Get-Sha256File $statePath) -eq $currentSha -and (Test-Path -LiteralPath $tmpPath))
 Remove-Item -LiteralPath $tmpPath -Force

 $core=Get-Content (Join-Path $package 'core\OneCChatWorker.Core.psm1') -Raw -Encoding UTF8
 A 'helper_state_recovery_has_live_process_guard' ($core.Contains('HELPER_STATE_RECOVERY_REQUIRES_STOPPED_HELPER') -and $core.Contains('Get-CimInstance Win32_Process'))
 $block=$core.Substring($core.IndexOf('function New-Admission {'),$core.IndexOf('function Test-IsAdministrator {')-$core.IndexOf('function New-Admission {'))
 A 'no_deep_verify_in_admission' (-not($block.Contains('Verify-WorkerProject')) -and -not($block.Contains('Get-TreeDigest')))
 Write-Host ("S4_ADMISSION_PS51_REGRESSION_PASS checks={0}" -f $results.Count)
}finally{
 Remove-OneCTestScratch -Path $s.path -RunId $s.run_id -Base $s.base|Out-Null
}
