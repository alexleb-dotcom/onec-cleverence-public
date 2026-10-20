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
$mainHandle=$null
try {
  $worker=Join-Path $s.path 'worker'
  $pd=Join-Path $s.path 'pd'
  New-Item -ItemType Directory -Force -Path $worker,(Join-Path $pd 'runtime'),(Join-Path $pd 'secrets'),(Join-Path $worker 'P1\Participants\main\Target\Main'),(Join-Path $worker 'P1\Output'),(Join-Path $worker 'P1\ProjectManifest')|Out-Null
  [IO.File]::WriteAllText((Join-Path $pd 'installed-state.json'),'{"product_version":"test"}',[Text.UTF8Encoding]::new($false))
  [IO.File]::WriteAllText((Join-Path $pd 'secrets\helper-secret.txt'),'not-a-real-secret-value-for-test',[Text.UTF8Encoding]::new($false))
  $catalog=[ordered]@{schema_version=1;projects=@([ordered]@{project_id='P1';display_name='Project One';active=$true;participants=@([ordered]@{participant_id='main';platform='ONEC';role='ERP';active=$true;target=[ordered]@{main=[ordered]@{active=$true;source_path='C:\External\NotReadByUi'};extensions=@()}})})}
  [IO.File]::WriteAllText((Join-Path $worker 'projects.json'),($catalog|ConvertTo-Json -Depth 20),[Text.UTF8Encoding]::new($false))
  $catalogSha=(Get-FileHash -Algorithm SHA256 (Join-Path $worker 'projects.json')).Hash.ToLowerInvariant()
  [IO.File]::WriteAllText((Join-Path $worker 'P1\Participants\main\Target\Main\Configuration.xml'),'<Configuration/>',[Text.UTF8Encoding]::new($false))
  $manifestDir=Join-Path $worker 'P1\ProjectManifest'
  $manifest=[ordered]@{
    schema_version=2;project_id='P1';catalog_sha256=$catalogSha;publication_generation=1;
    accepted_snapshot=[ordered]@{snapshot_contract='ACCEPTED_SNAPSHOT_V1';source_snapshot_id='snap-test';fingerprint_inventory_state='PRESENT'};
    participants=@([ordered]@{participant_id='main';platform='ONEC';active=$true;target=[ordered]@{main=[ordered]@{active=$true;canonical_path='Participants/main/Target/Main';tree_sha256=('0'*64);configuration_xml_sha256=('1'*64);files=1;bytes=16};extensions=@()}})
  }
  $fixtureCore=Import-Module (Join-Path $PackageRoot 'core\OneCChatWorker.Core.psm1') -Force -DisableNameChecking -PassThru
  $manifest.accepted_snapshot=& $fixtureCore {param($m) New-AcceptedSnapshot -ManifestParticipants @($m.participants) -CatalogSha256 $m.catalog_sha256 -ProofBasis 'ISOLATED_UI_FIXTURE'} $manifest
  [IO.File]::WriteAllText((Join-Path $manifestDir 'project.json'),($manifest|ConvertTo-Json -Depth 20),[Text.UTF8Encoding]::new($false))
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
  # Excludes payload reads, hashing and copies by real UI_CONTEXT owners.
  $mainHandle=[IO.File]::Open((Join-Path $worker 'P1\Participants\main\Target\Main\Configuration.xml'),[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::None)
  $before=@(Get-ChildItem -LiteralPath $s.path -Recurse -File|ForEach-Object{$_.FullName+'|'+$_.Length+'|'+$_.LastWriteTimeUtc.Ticks})
  $raw=& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $launcher -Mode UI_CONTEXT -Json -WorkerRoot $worker -ProgramDataRoot $pd
  if($LASTEXITCODE-ne0){throw "UI_CONTEXT_EXIT_$LASTEXITCODE"}
  $joined=$raw -join [Environment]::NewLine
  $ctx=$joined|ConvertFrom-Json
  Rec 'schema_exact' ($ctx.schema -eq 'UI_CONTEXT_V1') $ctx.schema
  Rec 'bounded_fast_contract' ($ctx.bounded -and $ctx.fast_only -and $ctx.state_check_contract -eq 'FAST_STATE_CHECK_V1') ''
  Rec 'relay_projection_exact_binding' ($ctx.s4.accounting_available -and $ctx.s4.projection.task_admission_id -eq $admission.task_admission_id) ''
  Rec 'accepted_policy_identity_no_invented_limit_projection' (-not $ctx.s4.limits_display_allowed -and $ctx.s4.policy_status -eq 'OPERATOR_ACCEPTED_PRODUCT_POLICY') ''
  Rec 'six_tool_surface' ([int]$ctx.safety.model_tool_surface_count -eq 6) ''
  Rec 'offline_s4_admission_never_clear_incomplete' ($ctx.recommendation.state -eq 'ACTIVE_ADMISSION_OFFLINE' -and $ctx.recommendation.action -ne 'Clear incomplete start' -and $ctx.recommendation.reason -match 'RECOVERY_ADMISSION_EXPIRED') ''
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
  Rec 'bounded_manifest_artifact_projection_only' ($block -match 'Get-ManifestArtifactRows' -and $block -match 'sourceArtifacts' -and -not ($block -match 'Get-ChildItem.+-Recurse|Get-FileHash|Invoke-SourceIntake')) ''
  Rec 'source_update_status_projection_present' ($block -match 'Get-SourceUpdateSummary' -and $block -match 'source_update=') ''
  Rec 'source_navigation_uses_project_root' ($block -match 'source_root=\$\(if\(\$selectedProjectId\)\{Join-Path \$WorkerRoot \$selectedProjectId') ''
  Rec 'ui_context_mode_is_read_only' ($launcherText -match "'UI_CONTEXT' \{Run-UiContext;break\}") ''
  # Separate isolated selection fixture. Never invokes START or any lifecycle action.
  Move-Item -LiteralPath (Join-Path $pd 'runtime\active-admission.json') -Destination (Join-Path $s.path 'saved-fixture-admission.json')
  $other=$catalog.projects[0]|ConvertTo-Json -Depth 20|ConvertFrom-Json
  $other.project_id='NeoHim';$other.display_name='NeoHim'
  $catalog.projects=@($other,$catalog.projects[0])
  [IO.File]::WriteAllText((Join-Path $worker 'projects.json'),($catalog|ConvertTo-Json -Depth 20),[Text.UTF8Encoding]::new($false))
  $manifest.catalog_sha256=(Get-FileHash -Algorithm SHA256 (Join-Path $worker 'projects.json')).Hash.ToLowerInvariant()
  $manifest.accepted_snapshot=& $fixtureCore {param($m) New-AcceptedSnapshot -ManifestParticipants @($m.participants) -CatalogSha256 $m.catalog_sha256 -ProofBasis 'ISOLATED_UI_FIXTURE'} $manifest
  [IO.File]::WriteAllText((Join-Path $manifestDir 'project.json'),($manifest|ConvertTo-Json -Depth 20),[Text.UTF8Encoding]::new($false))
  New-Item -ItemType Directory -Force -Path (Join-Path $worker 'NeoHim\ProjectManifest'),(Join-Path $worker 'NeoHim\Participants\main\Target\Main')|Out-Null
  $otherManifest=$manifest|ConvertTo-Json -Depth 20|ConvertFrom-Json
  $otherManifest.project_id='NeoHim';$otherManifest.catalog_sha256=('f'*64)
  [IO.File]::WriteAllText((Join-Path $worker 'NeoHim\ProjectManifest\project.json'),($otherManifest|ConvertTo-Json -Depth 20),[Text.UTF8Encoding]::new($false))
  $selectionBefore=@(Get-ChildItem -LiteralPath $s.path -Recurse -File|ForEach-Object{$_.FullName+'|'+$_.Length+'|'+$_.LastWriteTimeUtc.Ticks})
  $selectedRaw=& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $launcher -Mode UI_CONTEXT -ProjectId P1 -Json -WorkerRoot $worker -ProgramDataRoot $pd
  if($LASTEXITCODE-ne0){throw 'SELECTED_CONTEXT_FAILED'}
  $selected=($selectedRaw -join [Environment]::NewLine)|ConvertFrom-Json
  Rec 'second_accepted_project_drives_context' ($selected.selected_project.project_id -eq 'P1' -and $selected.recommendation.state -eq 'PROJECT_READY' -and $selected.actions.start.enabled) ''
  Rec 'first_catalog_drift_is_independent' (($selected.projects|Where-Object project_id -eq 'NeoHim').fast_state -eq 'CATALOG_DRIFT') ''
  Rec 'navigation_and_source_match_selection' ($selected.navigation.source_root -eq (Join-Path $worker 'P1') -and $selected.source.state -eq 'ACCEPTED') ''
  $unselectedRaw=& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $launcher -Mode UI_CONTEXT -Json -WorkerRoot $worker -ProgramDataRoot $pd
  $unselected=($unselectedRaw -join [Environment]::NewLine)|ConvertFrom-Json
  Rec 'multiple_projects_require_explicit_choice' ($null -eq $unselected.selected_project -and -not $unselected.actions.start.enabled -and $unselected.recommendation.state -eq 'PROJECT_SELECTION_REQUIRED') ''
  $driftRaw=& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $launcher -Mode UI_CONTEXT -ProjectId NeoHim -Json -WorkerRoot $worker -ProgramDataRoot $pd
  $drift=($driftRaw -join [Environment]::NewLine)|ConvertFrom-Json
  Rec 'selected_drift_blocks_start_with_reason' (-not $drift.actions.start.enabled -and $drift.actions.start.reason -eq 'PROJECT_NEEDS_APPLY') ''
  $ErrorActionPreference='Continue'
  try{$invalid=& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $launcher -Mode UI_CONTEXT -ProjectId UnknownFixture -Json -WorkerRoot $worker -ProgramDataRoot $pd 2>&1;$invalidExit=$LASTEXITCODE}finally{$ErrorActionPreference='Stop'}
  Rec 'invalid_project_never_falls_back' ($invalidExit -ne 0 -and ($invalid -join ' ') -match 'UI_PROJECT_SELECTION_INVALID') ''
  $selectionAfter=@(Get-ChildItem -LiteralPath $s.path -Recurse -File|ForEach-Object{$_.FullName+'|'+$_.Length+'|'+$_.LastWriteTimeUtc.Ticks})
  Rec 'selection_context_never_mutates_state' (($selectionBefore -join '|') -eq ($selectionAfter -join '|')) ''
  Rec 'main_payload_locked_through_all_context_reads' ($null -ne $mainHandle -and $mainHandle.CanRead) ''

  # FA T5/T6: real read-only launcher and canonical summaries, synthetic files only.
  $incoming=Join-Path $worker 'P1\Incoming'
  New-Item -ItemType Directory -Force -Path $incoming|Out-Null
  $statePath=Join-Path $incoming 'fixture-state.json'
  $activePath=Join-Path $incoming 'active-source-update.json'
  $promotionPath=Join-Path $incoming 'promotion-source-update.json'
  $admissionPath=Join-Path $pd 'runtime\active-admission.json'
  $operationPath=Join-Path $pd 'operations\current-operation.json'
  function Write-FixtureJson($path,$value){[IO.File]::WriteAllText($path,($value|ConvertTo-Json -Depth 20),[Text.UTF8Encoding]::new($false))}
  function Probe-UpdateGate([string]$name,[string]$stage,[string]$admissionProject,[string]$promotion,[bool]$recovery,[bool]$accept,[bool]$cancel,[string]$acceptReason,[string]$cancelReason){
    foreach($path in @($activePath,$promotionPath,$admissionPath,$operationPath)){if(Test-Path -LiteralPath $path){Remove-Item -LiteralPath $path}}
    if($stage -ne 'NONE'){
      Write-FixtureJson $statePath @{schema='SOURCE_UPDATE_V1';project_id='P1';generation_id='fixture-generation';state=$stage;selected=@();created_utc='2026-10-20T00:00:00Z'}
      Write-FixtureJson $activePath @{schema='SOURCE_UPDATE_ACTIVE_V1';project_id='P1';generation_id='fixture-generation';state_path=$statePath}
      if($stage -eq 'CORRUPT'){[IO.File]::WriteAllText($statePath,'{invalid')}
      if($stage -eq 'MISSING'){Remove-Item -LiteralPath $statePath}
    }
    if($admissionProject){$admission.project_id=$admissionProject;Write-FixtureJson $admissionPath $admission}
    if($promotion){[IO.File]::WriteAllText($promotionPath,$promotion)}
    if($recovery){New-Item -ItemType Directory -Force -Path (Split-Path $operationPath)|Out-Null;Write-FixtureJson $operationPath @{state='RUNNING';operation_type='SOURCE_UPDATE_ACCEPT';project_id='P1'}}
    $beforeGate=@(Get-ChildItem -LiteralPath $s.path -Recurse -File|ForEach-Object{$_.FullName+'|'+$_.Length+'|'+$_.LastWriteTimeUtc.Ticks})
    $gateRaw=& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $launcher -Mode UI_CONTEXT -ProjectId P1 -Json -WorkerRoot $worker -ProgramDataRoot $pd
    if($LASTEXITCODE-ne0){throw ('GATE_CONTEXT_FAILED:'+ $name)}
    $gate=($gateRaw -join [Environment]::NewLine)|ConvertFrom-Json
    Rec ($name+'_accept') ($gate.actions.accept_source_update.enabled -eq $accept -and $gate.actions.accept_source_update.reason -eq $acceptReason) ($gate.actions.accept_source_update|ConvertTo-Json -Compress)
    Rec ($name+'_cancel') ($gate.actions.cancel_source_update.enabled -eq $cancel -and $gate.actions.cancel_source_update.reason -eq $cancelReason) ($gate.actions.cancel_source_update|ConvertTo-Json -Compress)
    $afterGate=@(Get-ChildItem -LiteralPath $s.path -Recurse -File|ForEach-Object{$_.FullName+'|'+$_.Length+'|'+$_.LastWriteTimeUtc.Ticks})
    Rec ($name+'_read_only') (($beforeGate -join '|') -eq ($afterGate -join '|') -and $mainHandle.CanRead) ''
  }
  Probe-UpdateGate 'T5_prepared_same_admission_can_validate' 'PREPARED_WRITABLE' 'P1' '' $false $true $true 'AVAILABLE' 'AVAILABLE'
  Probe-UpdateGate 'T5_validated_same_admission_waits' 'SEALED_VALIDATED' 'P1' '' $false $false $true 'PROJECT_ADMISSION_ACTIVE' 'AVAILABLE'
  Probe-UpdateGate 'T5_explicit_admission_end_enables_accept' 'SEALED_VALIDATED' '' '' $false $true $true 'AVAILABLE' 'AVAILABLE'
  Probe-UpdateGate 'other_project_admission_does_not_block' 'SEALED_VALIDATED' 'NeoHim' '' $false $true $true 'AVAILABLE' 'AVAILABLE'
  foreach($stage in @('PREPARED_WRITABLE','SEALED_VALIDATED','SEALED','INVALID','NONE','CORRUPT','MISSING')){
    $valid=$stage -in @('PREPARED_WRITABLE','SEALED_VALIDATED')
    $cancelValid=$stage -in @('PREPARED_WRITABLE','SEALED_VALIDATED','SEALED')
    $reason=if($stage -eq 'NONE'){'NO_SOURCE_UPDATE'}elseif($stage -in @('CORRUPT','MISSING')){'RECOVERY_REQUIRED'}else{'SOURCE_UPDATE_STATE_INVALID'}
    Probe-UpdateGate ('stage_'+$stage) $stage '' '' $false $valid $cancelValid $(if($valid){'AVAILABLE'}else{$reason}) $(if($cancelValid){'AVAILABLE'}else{$reason})
    Probe-UpdateGate ('T6_owner_recovery_'+$stage) $stage '' '' $true $false $false 'RECOVERY_REQUIRED' 'RECOVERY_REQUIRED'
    foreach($marker in @('{"state":"PROMOTING"}','{broken')){
      Probe-UpdateGate ('T6_promotion_'+$stage+'_'+$marker.Length) $stage '' $marker $false $false $false 'RECOVERY_REQUIRED' 'RECOVERY_REQUIRED'
    }
  }

  Write-Host ("UI_CONTEXT_REGRESSION_PASS checks={0}" -f $results.Count)
  $results|ConvertTo-Json -Depth 8
} finally {
  if($mainHandle){$mainHandle.Dispose()}
  Remove-OneCTestScratch -Path $s.path -RunId $s.run_id -Base $s.base|Out-Null
}
