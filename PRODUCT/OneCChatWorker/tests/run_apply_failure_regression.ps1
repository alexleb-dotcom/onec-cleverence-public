param(
 [string]$PackageRoot=(Split-Path -Parent $PSScriptRoot)
)
$ErrorActionPreference='Stop'
$PackageRoot=[IO.Path]::GetFullPath($PackageRoot)
$launcher=Join-Path $PackageRoot 'OneCChatWorker.ps1'
$core=Join-Path $PackageRoot 'core\OneCChatWorker.Core.psm1'
$root=Join-Path $env:TEMP ('OneCChatWorker-ApplyFailure-'+[Guid]::NewGuid().ToString('N'))
$worker=Join-Path $root 'worker'
$pd=Join-Path $root 'programdata'
$source=Join-Path $root 'source-main'
$oldLocalAppData=$env:LOCALAPPDATA
$env:LOCALAPPDATA=Join-Path $root 'localappdata'
$results=New-Object Collections.Generic.List[object]

function Rec([string]$Name,[bool]$Ok,[string]$Detail=''){
 $results.Add([pscustomobject]@{name=$Name;pass=$Ok;detail=$Detail})
 if(-not $Ok){throw "ASSERTION_FAILED: $Name :: $Detail"}
}
function Write-Utf8([string]$Path,[string]$Value){
 New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Path)|Out-Null
 [IO.File]::WriteAllText($Path,$Value,[Text.UTF8Encoding]::new($false))
}
function Hash([string]$Path){(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()}
function Start-CopyFailureWatcher([string]$StageRoot,[string]$LockedPath){
 $watch=@'
param($StageRoot,$LockedPath)
$deadline=(Get-Date).AddSeconds(45)
do{
 $stage=@(Get-ChildItem -LiteralPath $StageRoot -Directory -Filter '*.stage-*' -ErrorAction SilentlyContinue|Select-Object -First 1)
 if($stage){break}
 Start-Sleep -Milliseconds 5
}while((Get-Date)-lt $deadline)
if(-not $stage){exit 4}
$s=[IO.File]::Open($LockedPath,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::None)
try{Start-Sleep -Seconds 8}finally{$s.Dispose()}
'@
 $watchPath=Join-Path $root 'copy-failure-watcher.ps1'
 [IO.File]::WriteAllText($watchPath,$watch,[Text.UTF8Encoding]::new($true))
 Start-Process powershell.exe -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',$watchPath,'-StageRoot',$StageRoot,'-LockedPath',$LockedPath) -PassThru
}
function Invoke-LauncherCapture([string[]]$Arguments,[string]$OutName){
 $out=Join-Path $root $OutName
 $oldEap=$ErrorActionPreference
 try{
  $ErrorActionPreference='Continue'
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $launcher @Arguments *> $out
  $exit=$LASTEXITCODE
 }finally{$ErrorActionPreference=$oldEap}
 [pscustomobject]@{exit=$exit;text=$(if(Test-Path $out){Get-Content $out -Raw -Encoding Default}else{''});path=$out}
}
function New-DeepRelativeFile([string]$SourceRoot,[int]$DesiredRelativeChars){
 New-Item -ItemType Directory -Force -Path $SourceRoot|Out-Null
 Write-Utf8 (Join-Path $SourceRoot 'Configuration.xml') '<Configuration name="LongPathControl"/>'
 $remaining=[Math]::Max(20,$DesiredRelativeChars-9)
 $parts=New-Object Collections.Generic.List[string]
 while($remaining -gt 45){
  $take=[Math]::Min(45,$remaining-10)
  $parts.Add(('d' * $take))
  $remaining-=($take+1)
 }
 if($remaining -gt 6){$parts.Add(('e' * ($remaining-6)))}
 $dir=$SourceRoot
 foreach($part in $parts){$dir=Join-Path $dir $part}
 New-Item -ItemType Directory -Force -Path $dir|Out-Null
 $file=Join-Path $dir 'x.txt'
 Write-Utf8 $file 'long-path-control'
 $file
}

try{
 New-Item -ItemType Directory -Force -Path $worker,$pd,$source,(Join-Path $pd 'secrets')|Out-Null
 $secretValue='APPLY-FAILURE-SECRET-MUST-NOT-LEAK-79'
 Write-Utf8 (Join-Path $pd 'secrets\helper-secret.txt') $secretValue

 Import-Module $core -Force -DisableNameChecking
 Write-Utf8 (Join-Path $source 'Configuration.xml') '<Configuration name="ApplyFailureV1"/>'
 Write-Utf8 (Join-Path $source 'baseline.txt') 'baseline-v1'
 New-WorkerProject -ProjectId Demo -DisplayName 'Apply Failure Demo' -WorkerRoot $worker|Out-Null
 Add-WorkerParticipant -ProjectId Demo -ParticipantId erp -Platform ONEC -Role ERP -WorkerRoot $worker|Out-Null
 Set-WorkerMain -ProjectId Demo -ParticipantId erp -SourcePath $source -WorkerRoot $worker|Out-Null
 $baseline=Apply-WorkerProject -ProjectId Demo -WorkerRoot $worker
 Rec 'baseline_ready' ($baseline.status -eq 'READY') ($baseline|ConvertTo-Json -Compress)

 $target=Join-Path $worker 'Demo\Participants\erp\Target\Main'
 $manifest=Join-Path $worker 'Demo\ProjectManifest\project.json'
 $targetBefore=(Get-TreeDigest $target).sha256
 $manifestBefore=Hash $manifest
 $detachedSentinel=Join-Path $worker 'Demo\Detached\keep\sentinel.txt'
 Write-Utf8 $detachedSentinel 'detached-evidence-must-survive'
 $detachedSentinelHash=Hash $detachedSentinel

 # Desired state changes, but canonical Target and old manifest must remain intact if copying fails.
 Write-Utf8 (Join-Path $source 'Configuration.xml') '<Configuration name="ApplyFailureV2"/>'
 Write-Utf8 (Join-Path $source 'baseline.txt') 'baseline-v2'
 1..350|ForEach-Object{Write-Utf8 (Join-Path $source ('a{0:D4}.txt' -f $_)) ('x'*2048)}
 $locked=Join-Path $source 'z-locked.txt'
 Write-Utf8 $locked ('z'*4096)
 Set-WorkerMain -ProjectId Demo -ParticipantId erp -SourcePath $source -ReplaceExisting -WorkerRoot $worker|Out-Null
 $sourceBefore=(Get-TreeDigest $source).sha256

 $stageRoot=Get-ApplyStageRoot $worker
 $watch=Start-CopyFailureWatcher -StageRoot $stageRoot -LockedPath $locked
 $failed=Invoke-LauncherCapture @('-Mode','APPLY','-WorkerRoot',$worker,'-ProgramDataRoot',$pd,'-ProjectId','Demo') 'apply-failure.out.txt'
 $watch.WaitForExit()
 Rec 'injected_apply_fails' ($failed.exit -ne 0) $failed.text

 $current=Get-Content (Join-Path $pd 'operations\current-operation.json') -Raw -Encoding UTF8|ConvertFrom-Json
 Rec 'durable_error_class_stable' ($current.error_class -eq 'APPLY_COPY_FAILED') ($current|ConvertTo-Json -Compress)
 Rec 'durable_error_phase_copying' ($current.error_phase -eq 'COPYING') ([string]$current.error_phase)
 Rec 'durable_error_path_bounded' ($current.error_path -eq $target) ([string]$current.error_path)
 Rec 'durable_error_cause_useful' (-not [string]::IsNullOrWhiteSpace([string]$current.error_message) -and ([string]$current.error_message).Length -le 800) ([string]$current.error_message)
 Rec 'durable_cleanup_status' ($current.cleanup_status -in @('CLEANED','CLEANED_LONG_PATH')) ([string]$current.cleanup_status)
 Rec 'stable_class_not_localized_underscores' ([string]$current.error_class -notmatch '^_+$') ([string]$current.error_class)

 $stages=@(Get-ChildItem -LiteralPath $stageRoot -Directory -Filter '*.stage-*' -ErrorAction SilentlyContinue)
 Rec 'failed_stage_cleaned' ($stages.Count -eq 0) ("remaining="+$stages.Count)
 Rec 'canonical_target_unchanged_after_midcopy_failure' ((Get-TreeDigest $target).sha256 -eq $targetBefore) ''
 Rec 'manifest_unchanged_after_midcopy_failure' ((Hash $manifest) -eq $manifestBefore) ''
 Rec 'source_unchanged_by_failed_apply' ((Get-TreeDigest $source).sha256 -eq $sourceBefore) ''

 $afterFail=Verify-WorkerProject -ProjectId Demo -WorkerRoot $worker
 Rec 'failed_apply_never_reports_ready' ($afterFail.status -ne 'READY') ($afterFail|ConvertTo-Json -Compress)

 $events=Get-Content (Join-Path $pd 'operations\events.jsonl') -Raw -Encoding UTF8
 $history=Get-Content (Join-Path $pd 'operations\history.jsonl') -Raw -Encoding UTF8
 $humanLog=Get-Content (Join-Path $pd 'operations\operations.log') -Raw -Encoding UTF8
 Rec 'operation_event_has_safe_cause' ($events -match '"error_class":"APPLY_COPY_FAILED"' -and $events -match '"error_message":') ''
 Rec 'operation_history_has_safe_cause' ($history -match '"error_class":"APPLY_COPY_FAILED"' -and $history -match '"cleanup_status":"CLEANED') ''
 Rec 'human_log_labels_utc' ($humanLog -match '\[UTC\]') ''
 Rec 'secret_not_in_operation_evidence' (($events+$history+$humanLog+$failed.text) -notmatch [regex]::Escape($secretValue)) ''

 # Guided presentation consumes the durable failure receipt but not raw exception/stack details.
 $oldUi=[Threading.Thread]::CurrentThread.CurrentUICulture
 try{
  . $launcher -Mode LIST -WorkerRoot $worker -ProgramDataRoot $pd *> $null
  $ex=New-Object System.InvalidOperationException('APPLY_COPY_FAILED: injected failure for guided presentation')
  [Threading.Thread]::CurrentThread.CurrentUICulture=New-Object Globalization.CultureInfo('ru-RU')
  $ru=(& {Show-GuidedFailure $ex} 6>&1 | Out-String)
  Rec 'guided_ru_failure_localized' ($ru -match 'Не удалось создать управляемую копию проекта\.' -and $ru -match 'Причина:' -and $ru -match 'Этап: копирование файлов' -and $ru -match 'Неполная временная копия очищена\.' -and $ru -match 'Исходная XML-выгрузка не изменена\.' -and $ru -match 'Далее:') $ru
  [Threading.Thread]::CurrentThread.CurrentUICulture=New-Object Globalization.CultureInfo('de-DE')
  $en=(& {Show-GuidedFailure $ex} 6>&1 | Out-String)
  Rec 'guided_english_fallback_actionable' ($en -match 'The managed project copy could not be created\.' -and $en -match 'Reason:' -and $en -match 'Stage: Copying managed files' -and $en -match 'Incomplete temporary copy was cleaned\.' -and $en -match 'Original XML export was not changed\.' -and $en -match 'Next:') $en
 } finally {
  [Threading.Thread]::CurrentThread.CurrentUICulture=$oldUi
 }

 # Legacy residue from the real pre-#79 layout must block READY/APPLY and be recover-first cleaned.
 $legacy=Join-Path (Split-Path -Parent $target) 'Main.stage-legacy-regression'
 New-Item -ItemType Directory -Force -Path $legacy|Out-Null
 Write-Utf8 (Join-Path $legacy 'partial.txt') 'partial'
 $residue=Get-ApplyStageResidue -ProjectId Demo -WorkerRoot $worker
 Rec 'legacy_stage_detected' (@($residue|Where-Object layout -eq 'LEGACY_TARGET_SIBLING').Count -eq 1) ($residue|ConvertTo-Json -Compress)
 $withResidue=Verify-WorkerProject -ProjectId Demo -WorkerRoot $worker
 Rec 'verify_classifies_incomplete_apply_residue' ($withResidue.status -eq 'INCOMPLETE_APPLY_RESIDUE' -and $withResidue.reason -eq 'ORPHAN_STAGE_PRESENT') ($withResidue|ConvertTo-Json -Compress)
 try{Apply-WorkerProject -ProjectId Demo -WorkerRoot $worker|Out-Null;Rec 'apply_refuses_blind_replay' $false 'unexpected success'}catch{Rec 'apply_refuses_blind_replay' ($_.Exception.Message -like 'APPLY_RESIDUE_REPAIR_REQUIRED:*') $_.Exception.Message}

 $repair=Repair-WorkerProject -ProjectId Demo -WorkerRoot $worker
 Rec 'repair_recover_first_reaches_ready' ($repair.status -eq 'READY') ($repair|ConvertTo-Json -Depth 8 -Compress)
 Rec 'repair_reports_residue_cleanup' ($repair.recovery_cleanup.residue_before -eq 1 -and $repair.recovery_cleanup.status -eq 'CLEAN') ($repair.recovery_cleanup|ConvertTo-Json -Compress)
 Rec 'legacy_stage_removed_by_repair' (-not(Test-Path -LiteralPath $legacy)) ''
 Rec 'detached_evidence_not_deleted' ((Hash $detachedSentinel) -eq $detachedSentinelHash) ''
 Rec 'source_unchanged_after_repair' ((Get-TreeDigest $source).sha256 -eq $sourceBefore) ''
 Rec 'post_repair_verify_ready' ((Verify-WorkerProject -ProjectId Demo -WorkerRoot $worker).status -eq 'READY') ''

 # Synthetic path-shape reproduces why target-sibling GUID staging was unsafe while the bounded stage root stays below PS5.1 MAX_PATH.
 $pathSource=Join-Path $root 'path-source'
 $pathProject=Join-Path $worker 'PathDemo'
 $pathTarget=Join-Path $pathProject 'Participants\p\Target\Main'
 $desired=[Math]::Max(90,245-$pathTarget.Length)
 $deepFile=New-DeepRelativeFile -SourceRoot $pathSource -DesiredRelativeChars $desired
 $relative=[IO.Path]::GetFullPath($deepFile).Substring([IO.Path]::GetFullPath($pathSource).TrimEnd('\').Length).TrimStart('\')
 $oldSiblingStage=$pathTarget+'.stage-'+('f'*32)
 $oldProjected=$oldSiblingStage.Length+1+$relative.Length
 $pathCopy=Copy-ArtifactSafely -Source $pathSource -Target $pathTarget -ProjectRoot $pathProject -ArchiveKey 'p\Target\Main'
 Rec 'bounded_stage_root_avoids_guid_suffix_path_inflation' ($oldProjected -ge 260 -and $pathCopy.stage_max_path_chars -lt 260 -and $pathCopy.target_max_path_chars -lt 260) ("old=$oldProjected new_stage=$($pathCopy.stage_max_path_chars) target=$($pathCopy.target_max_path_chars)")
 Rec 'long_path_shape_copy_commits' ((Get-TreeDigest $pathTarget).sha256 -eq (Get-TreeDigest $pathSource).sha256) ''

 Write-Host ("APPLY_FAILURE_REGRESSION_PASS checks={0} evidence_root={1}" -f $results.Count,$root)
} finally {
 $env:LOCALAPPDATA=$oldLocalAppData
 Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
}
