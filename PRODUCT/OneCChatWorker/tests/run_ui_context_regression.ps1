param(
  [string]$PackageRoot=(Split-Path -Parent $PSScriptRoot)
)
$ErrorActionPreference='Stop'
Import-Module (Join-Path $PSScriptRoot 'TestScratch.psm1') -Force -DisableNameChecking
$results=@()
function Rec([string]$name,[bool]$pass,[string]$detail=''){
  $script:results+=,[pscustomobject]@{name=$name;pass=$pass;detail=$detail}
  if(-not $pass){throw "ASSERTION_FAILED:${name}:${detail}"}
}
$s=New-OneCTestScratch -Purpose 'UiContextRegression'
try {
  $worker=Join-Path $s.path 'worker'
  $pd=Join-Path $s.path 'pd'
  New-Item -ItemType Directory -Force -Path $worker,(Join-Path $pd 'runtime'),(Join-Path $pd 'secrets'),(Join-Path $worker 'P1\Source\Participants\main\Target\Main')|Out-Null
  [IO.File]::WriteAllText((Join-Path $pd 'installed-state.json'),'{"product_version":"test"}',[Text.UTF8Encoding]::new($false))
  [IO.File]::WriteAllText((Join-Path $pd 'secrets\helper-secret.txt'),'not-a-real-secret-value-for-test',[Text.UTF8Encoding]::new($false))
  $catalog=[ordered]@{schema_version=1;projects=@([ordered]@{project_id='P1';display_name='Project One';active=$true;participants=@([ordered]@{participant_id='main';platform='ONEC';role='ERP';active=$true;target=[ordered]@{main=[ordered]@{active=$true;source_path='C:\External\NotReadByUi'};extensions=@()}})})}
  [IO.File]::WriteAllText((Join-Path $worker 'projects.json'),($catalog|ConvertTo-Json -Depth 20),[Text.UTF8Encoding]::new($false))
  $catalogSha=(Get-FileHash -Algorithm SHA256 (Join-Path $worker 'projects.json')).Hash.ToLowerInvariant()
  [IO.File]::WriteAllText((Join-Path $worker 'P1\Source\Participants\main\Target\Main\Configuration.xml'),'<Configuration/>',[Text.UTF8Encoding]::new($false))
  $manifestDir=Join-Path $worker 'P1\Source'
  $manifest=[ordered]@{
    schema_version=2;project_id='P1';catalog_sha256=$catalogSha;publication_generation=1;
    accepted_snapshot=[ordered]@{snapshot_contract='ACCEPTED_SNAPSHOT_V1';source_snapshot_id='snap-test';fingerprint_inventory_state='PRESENT'};
    participants=@([ordered]@{participant_id='main';platform='ONEC';active=$true;target=[ordered]@{main=[ordered]@{active=$true;canonical_path='Participants/main/Target/Main';sha256=('0'*64)};extensions=@()}})
  }
  [IO.File]::WriteAllText((Join-Path $manifestDir 'ProjectManifest.json'),($manifest|ConvertTo-Json -Depth 20),[Text.UTF8Encoding]::new($false))
  $admission=[ordered]@{schema_version=3;accounting_contract='S4_DURABLE_TASK_ACCOUNTING_V1';task_admission_id='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';session_id='bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';project_id='P1';task_id='task-1';task_goal='Inspect current work';task_created_utc='2026-10-07T09:00:00Z';task_expires_utc='2026-10-07T15:00:00Z';source_snapshot_id='snap-test'}
  [IO.File]::WriteAllText((Join-Path $pd 'runtime\active-admission.json'),($admission|ConvertTo-Json -Depth 10),[Text.UTF8Encoding]::new($false))
  $projection=[ordered]@{
    schema='S4_UI_PROJECTION_V1';generated_utc='2026-10-07T10:00:00Z';task_admission_id=$admission.task_admission_id;session_id=$admission.session_id;project_id='P1';task_id='task-1';
    task_state='ACTIVE';task_created_utc=$admission.task_created_utc;task_expires_utc=$admission.task_expires_utc;continuation='AUTO';epoch_id='epoch-test';epoch_seq=3;
    accounting=[ordered]@{owner='relay';task_requests_used=12;task_requests_limit=480;task_requests_remaining=468;task_result_bytes_used=12345;task_result_bytes_limit=576000;task_result_bytes_remaining=563655;epoch_requests_used=2;epoch_requests_soft_limit=32;epoch_result_bytes_used=2200;epoch_result_bytes_soft_limit=36000;max_result_bytes=3000};
    activity=[ordered]@{available=$true;request_count=12;charged_result_bytes=12345;epoch_rollovers=3;operation_counts=[ordered]@{read=5;search=3};events=@([ordered]@{seq=12;op='read';state='COMMITTED';charged_bytes=800;epoch_seq=3;safe_request=[ordered]@{path='Participants/main/Target/Main/CommonModules/X/Ext/Module.bsl'};safe_result=[ordered]@{status='OK';path='Participants/main/Target/Main/CommonModules/X/Ext/Module.bsl'}});truncated=$false;receipt_identity=('c'*64)}
  }
  [IO.File]::WriteAllText((Join-Path $pd 'runtime\s4-ui-projection.json'),($projection|ConvertTo-Json -Depth 20),[Text.UTF8Encoding]::new($false))
  $launcher=Join-Path $PackageRoot 'OneCChatWorker.ps1'
  $before=@(Get-ChildItem -LiteralPath $s.path -Recurse -File|ForEach-Object{$_.FullName+'|'+$_.Length+'|'+$_.LastWriteTimeUtc.Ticks})
  $raw=& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $launcher -Mode UI_CONTEXT -Json -WorkerRoot $worker -ProgramDataRoot $pd
  if($LASTEXITCODE-ne0){throw "UI_CONTEXT_EXIT_$LASTEXITCODE"}
  $joined=$raw -join [Environment]::NewLine
  $ctx=$joined|ConvertFrom-Json
  Rec 'schema_exact' ($ctx.schema -eq 'UI_CONTEXT_V1') $ctx.schema
  Rec 'bounded_fast_contract' ($ctx.bounded -and $ctx.fast_only -and $ctx.state_check_contract -eq 'FAST_STATE_CHECK_V1') ''
  Rec 'relay_projection_exact_binding' ($ctx.s4.accounting_available -and $ctx.s4.projection.task_admission_id -eq $admission.task_admission_id) ''
  Rec 'pending_policy_hides_limits' (-not $ctx.s4.limits_display_allowed -and $ctx.s4.policy_status -eq 'PENDING_CAP_ACTIVATION') ''
  Rec 'six_tool_surface' ([int]$ctx.safety.model_tool_surface_count -eq 6) ''
  Rec 'no_side_effect_flags' (-not $ctx.safety.mcp_side_effect -and -not $ctx.safety.source_request_issued -and -not $ctx.safety.acquisition_called) ''
  Rec 'no_secret_values' (-not ($joined -match 'not-a-real-secret-value-for-test')) ''
  $after=@(Get-ChildItem -LiteralPath $s.path -Recurse -File|ForEach-Object{$_.FullName+'|'+$_.Length+'|'+$_.LastWriteTimeUtc.Ticks})
  Rec 'read_does_not_mutate_fixture' (($before -join '|') -eq ($after -join '|')) ''
  $projection.task_admission_id='cccccccccccccccccccccccccccccccc'
  [IO.File]::WriteAllText((Join-Path $pd 'runtime\s4-ui-projection.json'),($projection|ConvertTo-Json -Depth 20),[Text.UTF8Encoding]::new($false))
  $raw2=& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $launcher -Mode UI_CONTEXT -Json -WorkerRoot $worker -ProgramDataRoot $pd
  $ctx2=($raw2 -join [Environment]::NewLine)|ConvertFrom-Json
  Rec 'mismatched_projection_fails_closed' (-not $ctx2.s4.accounting_available -and $null -eq $ctx2.s4.projection) ''
  $launcherText=Get-Content -LiteralPath $launcher -Raw -Encoding UTF8
  $start=$launcherText.IndexOf('function Get-UiContext {');$end=$launcherText.IndexOf('function Run-UiContext {')
  $block=$launcherText.Substring($start,$end-$start)
  Rec 'static_no_deep_verify_or_acquisition' (-not ($block -match 'Verify-WorkerProject|Get-TreeDigest|Invoke-SourceAcquisition|source_context|source_read')) ''
  Rec 'ui_context_mode_is_read_only' ($launcherText -match "'UI_CONTEXT' \{Run-UiContext;break\}") ''
  Write-Host ("UI_CONTEXT_REGRESSION_PASS checks={0}" -f $results.Count)
  $results|ConvertTo-Json -Depth 8
} finally {
  Remove-OneCTestScratch -Path $s.path -RunId $s.run_id -Base $s.base|Out-Null
}
