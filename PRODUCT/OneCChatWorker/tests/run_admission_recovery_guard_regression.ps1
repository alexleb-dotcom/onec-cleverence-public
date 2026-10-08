param([string]$PackageRoot=(Split-Path -Parent $PSScriptRoot))
$ErrorActionPreference='Stop'
$root=Join-Path ([IO.Path]::GetTempPath()) ('onec-recovery-guard-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path (Join-Path $root 'runtime') -Force|Out-Null
$module=Import-Module (Join-Path $PackageRoot 'core/OneCChatWorker.Core.psm1') -Force -DisableNameChecking -PassThru
try{
 & $module {
  param($Root)
  $script:RecoveryChecks=0
  function Check($Ok,$Name){if(-not $Ok){throw ('ASSERTION_FAILED: '+$Name)};$script:RecoveryChecks++;Write-Host ('PASS '+$Name)}
  # No device/process or Source inspection. Actual assessment/cache owner runs;
  # host query and accepted metadata result are isolated fixture integrations.
  function Get-CimInstance {param($ClassName,$ErrorAction);if($script:CimFails){throw 'fixture unavailable'};@()}
  $script:CimFails=$false
  $script:Accepted=[pscustomobject]@{state='ACCEPTED';source_snapshot_id=('c'*64);manifest_sha256=('d'*64)}
  function Get-FastProjectState {param($ProjectId,$WorkerRoot);$script:Accepted}
  function W($Path,$Doc){[IO.File]::WriteAllText($Path,($Doc|ConvertTo-Json -Depth 30),[Text.UTF8Encoding]::new($false))}
  $admissionPath=Join-Path $Root 'runtime/active-admission.json'
  $statePath=Join-Path $Root 'runtime/hosted-helper-state.json'
  $a=[pscustomobject]@{schema_version=3;accounting_contract='S4_DURABLE_TASK_ACCOUNTING_V1';task_admission_id=('a'*32);session_id=('b'*32);project_id='P';task_id='T';source_snapshot_id=('c'*64);manifest_sha256=('d'*64);task_expires_utc=(Get-Date).ToUniversalTime().AddHours(1).ToString('o')}
  $s=[pscustomobject]@{schema_version=2;task_admission_id=$a.task_admission_id;session_id=$a.session_id;project_id='P';task_id='T';snapshot_id=$a.source_snapshot_id;manifest_sha256=$a.manifest_sha256;expires_utc=$a.task_expires_utc;pull_helper_id=[guid]::NewGuid().ToString();processed=[pscustomobject]@{};idempotency=[pscustomobject]@{keep='unchanged'}}
  W $admissionPath $a;W $statePath $s
  $originalAdmission=Get-Sha256File $admissionPath
  function Assess($Code){
   $before=@{};Get-ChildItem -LiteralPath $Root -Recurse -File|ForEach-Object{$before[$_.FullName]=Get-Sha256File $_.FullName}
   $r=Get-ActiveAdmissionRecoveryAssessment -WorkerRoot $Root -ProgramDataRoot $Root
   Check ($r.status -eq 'BLOCKED' -and -not $r.launch_allowed -and $r.admission_preserved -and $r.reason -eq $Code) ($Code+' actual='+$r.reason)
   $after=@(Get-ChildItem -LiteralPath $Root -Recurse -File);Check ($after.Count -eq $before.Count -and @($after|Where-Object{(Get-Sha256File $_.FullName) -ne $before[$_.FullName]}).Count -eq 0) ($Code+' all bytes retained')
  }
  Assess 'RELAY_RECOVERY_EVIDENCE_UNAVAILABLE'
  $a.task_expires_utc=(Get-Date).ToUniversalTime().AddSeconds(-1).ToString('o');W $admissionPath $a;Assess 'RECOVERY_ADMISSION_EXPIRED'
  $a.task_expires_utc=$s.expires_utc;W $admissionPath $a
  $s.session_id='wrong';W $statePath $s;Assess 'RECOVERY_CACHE_BINDING_MISMATCH';$s.session_id=$a.session_id;W $statePath $s
  $script:Accepted.source_snapshot_id='changed';Assess 'RECOVERY_SNAPSHOT_MISMATCH';$script:Accepted.source_snapshot_id=$a.source_snapshot_id
  W ($statePath+'.tmp') $s;Assess 'RECOVERY_TMP_REQUIRES_ADJUDICATION';Remove-Item -LiteralPath ($statePath+'.tmp')
  $s|Add-Member -NotePropertyName pull_inflight -NotePropertyValue ([pscustomobject]@{request_id='mcp-unresolved';token=[guid]::NewGuid().ToString()});W $statePath $s;Assess 'RECOVERY_EXECUTION_AMBIGUOUS'
  $s.processed|Add-Member -NotePropertyName 'mcp-unresolved' -NotePropertyValue ([pscustomobject]@{type='result';request_id='mcp-unresolved';status='OK';metadata=[pscustomobject]@{op='read'};payload='cached'});W $statePath $s;Assess 'RELAY_RECOVERY_EVIDENCE_UNAVAILABLE'
  $script:CimFails=$true;Assess 'RECOVERY_TRUSTED_LOCAL_EVIDENCE_UNAVAILABLE'
  Check ((Get-Sha256File $admissionPath) -eq $originalAdmission) 'unchanged admission no remint'
  Write-Host ('ADMISSION_RECOVERY_GUARD_PASS checks='+$script:RecoveryChecks)
 } $root
}finally{
 $resolved=[IO.Path]::GetFullPath($root)
 if((Split-Path -Parent $resolved) -ne ([IO.Path]::GetTempPath()).TrimEnd('\') -or (Split-Path -Leaf $resolved) -notlike 'onec-recovery-guard-*'){throw 'UNSAFE_FIXTURE_CLEANUP'}
 Remove-Item -LiteralPath $resolved -Recurse -Force
}
