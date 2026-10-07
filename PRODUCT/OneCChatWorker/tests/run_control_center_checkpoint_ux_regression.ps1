param([string]$PackageRoot=(Split-Path -Parent $PSScriptRoot))
$ErrorActionPreference='Stop'
$launcher=Get-Content -LiteralPath (Join-Path $PackageRoot 'OneCChatWorker.ps1') -Raw -Encoding UTF8
$core=Get-Content -LiteralPath (Join-Path $PackageRoot 'core\OneCChatWorker.Core.psm1') -Raw -Encoding UTF8
$main=Get-Content -LiteralPath (Join-Path $PackageRoot 'control-center\OneCArchitecture.ControlCenter\MainWindow.xaml.cs') -Raw -Encoding UTF8
$xaml=Get-Content -LiteralPath (Join-Path $PackageRoot 'control-center\OneCArchitecture.ControlCenter\MainWindow.xaml') -Raw -Encoding UTF8
$client=Get-Content -LiteralPath (Join-Path $PackageRoot 'control-center\OneCArchitecture.ControlCenter\WorkerClient.cs') -Raw -Encoding UTF8
$r=@()
function Rec($n,$p,$d=''){$script:r+=,[pscustomobject]@{name=$n;pass=[bool]$p;detail=$d};if(-not $p){throw ('ASSERTION_FAILED:'+$n+':'+$d)}}
Rec 'ui_context_uses_verified_checkpoint_owner' ($launcher -match 'Read-TaskCheckpointContinuationHead' -and $launcher -match 'checkpoint=\$checkpoint') ''
Rec 'continue_visibility_worker_state' ($main -match 'state == "CONTINUE_AVAILABLE"' -and $xaml -match 'x:Name="ContinueButton"') ''
Rec 'continue_action_fixed_typed' ($main -match 'WorkerAction\.Continue' -and $client -match '\[WorkerAction\.Continue\] = "CONTINUE"') ''
Rec 'continue_core_exact_owner' ($core -match 'function Continue-WorkerAdmission' -and $core -match 'Read-TaskCheckpointContinuationHead') ''
Rec 'checkpoint_card_present' ($xaml -match 'CheckpointTitleLabel' -and $main -match 'CheckpointStateText' -and $main -match 'WorkCheckpointText') ''
Rec 'ui_checkpoint_read_only' (-not ($main -match 'task_checkpoint_write|TASK_CHECKPOINT_V1.*Write|checkpointStore\.write')) ''
Rec 'no_ui_predecessor_id_input' (-not ($xaml -match 'predecessor|checkpoint_sha|task_admission_id')) ''
Rec 'source_drift_owner_remains_worker' ($core -match 'source_snapshot_id' -and $core -match 'TASK_PREDECESSOR') ''
Rec 'no_chat_paste_recovery' (-not ($main -match 'paste.*conversation|chat transcript|conversation history')) ''
Rec 'technical_checkpoint_hash_advanced_only' ($main -match 'AdvancedText\.Text = ctx\.ToJsonString' -and -not ($xaml -match 'head_checkpoint_sha256')) ''
Write-Host ("CONTROL_CENTER_CHECKPOINT_UX_PASS checks={0}" -f $r.Count)
$r|ConvertTo-Json -Depth 5
