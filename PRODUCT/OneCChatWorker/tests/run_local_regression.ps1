$ErrorActionPreference='Stop'
$m=Join-Path (Split-Path -Parent $PSScriptRoot) 'core\OneCChatWorker.Core.psm1'
Import-Module $m -Force -DisableNameChecking
$root=Join-Path $env:TEMP ('OneCChatProduct-'+[Guid]::NewGuid().ToString('N'))
$worker=Join-Path $root 'worker'
$pd=Join-Path $root 'programdata'
$src=Join-Path $root 'source'
$main=Join-Path $src 'Main'
$ext=Join-Path $src 'Ext'
New-Item -ItemType Directory -Force -Path (Join-Path $main 'CommonModules\M\Ext'),(Join-Path $ext 'CommonModules\E\Ext'),$worker,$pd|Out-Null
[IO.File]::WriteAllText((Join-Path $main 'Configuration.xml'),'<Configuration id="main-v1"/>')
[IO.File]::WriteAllText((Join-Path $main 'CommonModules\M\Ext\Module.bsl'),('Procedure MainV1()'+[Environment]::NewLine+'EndProcedure'))
[IO.File]::WriteAllText((Join-Path $ext 'Configuration.xml'),'<Configuration id="ext-v1"/>')
[IO.File]::WriteAllText((Join-Path $ext 'CommonModules\E\Ext\Module.bsl'),('Procedure ExtV1()'+[Environment]::NewLine+'EndProcedure'))
$sourceMainV1=Get-TreeDigest $main
$sourceExtV1=Get-TreeDigest $ext
$results=New-Object Collections.Generic.List[object]
function Pass($n,$d=''){$results.Add([pscustomobject]@{name=$n;status='PASS';detail=$d})}
function Fail($n,$d){$results.Add([pscustomobject]@{name=$n;status='FAIL';detail=$d})}
function Assert($name,[bool]$ok,$detail=''){if($ok){Pass $name $detail}else{Fail $name $detail}}

try{
 New-WorkerProject -ProjectId Demo -DisplayName Demo -WorkerRoot $worker|Out-Null
 Add-WorkerParticipant -ProjectId Demo -ParticipantId ut -Platform ONEC -Role UT -WorkerRoot $worker|Out-Null
 Edit-WorkerProject -ProjectId Demo -DisplayName 'Demo edited' -WorkerRoot $worker|Out-Null
 Edit-WorkerParticipant -ProjectId Demo -ParticipantId ut -Role 'Trade role' -WorkerRoot $worker|Out-Null
 $cat0=Read-WorkerCatalog $worker
 Assert 'edit_project_metadata' ($cat0.projects[0].display_name -eq 'Demo edited')
 Assert 'edit_participant_metadata' ($cat0.projects[0].participants[0].role -eq 'Trade role')

 Set-WorkerMain -ProjectId Demo -ParticipantId ut -SourcePath $main -WorkerRoot $worker|Out-Null
 Add-WorkerExtension -ProjectId Demo -ParticipantId ut -ExtensionId custom -SourcePath $ext -WorkerRoot $worker|Out-Null
 $v=Apply-WorkerProject -ProjectId Demo -WorkerRoot $worker
 Assert 'apply_ready' ($v.status -eq 'READY') ($v|ConvertTo-Json -Compress)
 Assert 'apply_change_summary' (@($v.changes|Where-Object action -eq 'COPIED').Count -eq 2) ($v.changes|ConvertTo-Json -Compress)
 $mainRoot=Join-Path $worker 'Demo\Participants\ut\Target\Main'
 $extRoot=Join-Path $worker 'Demo\Participants\ut\Target\Extensions\custom'
 Assert 'direct_main_root' ((Test-Path (Join-Path $mainRoot 'Configuration.xml')) -and !(Test-Path (Join-Path $mainRoot 'Main')))
 Assert 'direct_extension_root' ((Test-Path (Join-Path $extRoot 'Configuration.xml')) -and !(Test-Path (Join-Path $extRoot 'custom')))

 $marker=Join-Path $worker 'Demo\Output\keep.txt';[IO.File]::WriteAllText($marker,'keep')
 $v2=Apply-WorkerProject -ProjectId Demo -WorkerRoot $worker
 Assert 'idempotent_apply_preserves_output' ($v2.status -eq 'READY' -and (Get-Content $marker -Raw) -eq 'keep')
 Assert 'idempotent_apply_reports_reused' (@($v2.changes|Where-Object action -eq 'REUSED').Count -eq 2)

 $c=Read-WorkerCatalog -WorkerRoot $worker;$c.projects[0].display_name='Drifted';Write-WorkerCatalog $c $worker
 $drift=Verify-WorkerProject -ProjectId Demo -WorkerRoot $worker
 Assert 'catalog_drift_detected' ($drift.status -eq 'DRIFT_APPLY_REQUIRED') $drift.status
 $repair=Repair-WorkerProject -ProjectId Demo -WorkerRoot $worker
 Assert 'bounded_repair' ($repair.status -eq 'READY') $repair.status

 [IO.File]::WriteAllText((Join-Path $main 'CommonModules\M\Ext\Module.bsl'),('Procedure MainV2()'+[Environment]::NewLine+'EndProcedure'))
 $sourceMainOperatorV2=Get-TreeDigest $main
 Set-WorkerMain -ProjectId Demo -ParticipantId ut -SourcePath $main -ReplaceExisting -WorkerRoot $worker|Out-Null
 $replace=Apply-WorkerProject -ProjectId Demo -WorkerRoot $worker
 $detachedMain=@(Get-ChildItem -LiteralPath (Join-Path $worker 'Demo\Detached\ut\Target\Main') -Directory -ErrorAction SilentlyContinue)
 Assert 'safe_replace_detached_old_main' ($replace.status -eq 'READY' -and $detachedMain.Count -ge 1 -and (Get-Content (Join-Path $mainRoot 'CommonModules\M\Ext\Module.bsl') -Raw) -match 'MainV2') "detached=$($detachedMain.Count)"
 Assert 'replace_main_summary' (@($replace.changes|Where-Object {$_.artifact_type -eq 'MAIN' -and $_.action -eq 'REPLACED_DETACHED'}).Count -eq 1)

 [IO.File]::WriteAllText((Join-Path $ext 'CommonModules\E\Ext\Module.bsl'),('Procedure ExtV2()'+[Environment]::NewLine+'EndProcedure'))
 $sourceExtOperatorV2=Get-TreeDigest $ext
 Add-WorkerExtension -ProjectId Demo -ParticipantId ut -ExtensionId custom -SourcePath $ext -ReplaceExisting -WorkerRoot $worker|Out-Null
 $replaceExt=Apply-WorkerProject -ProjectId Demo -WorkerRoot $worker
 $detachedExt=@(Get-ChildItem -LiteralPath (Join-Path $worker 'Demo\Detached\ut\Target\Extensions\custom') -Directory -ErrorAction SilentlyContinue)
 Assert 'safe_replace_detached_old_extension' ($replaceExt.status -eq 'READY' -and $detachedExt.Count -ge 1 -and (Get-Content (Join-Path $extRoot 'CommonModules\E\Ext\Module.bsl') -Raw) -match 'ExtV2') "detached=$($detachedExt.Count)"

 Disable-WorkerCatalogItem -Kind EXTENSION -ProjectId Demo -ParticipantId ut -ExtensionId custom -WorkerRoot $worker
 $deact=Apply-WorkerProject -ProjectId Demo -WorkerRoot $worker
 $deactCopies=@(Get-ChildItem -LiteralPath (Join-Path $worker 'Demo\Detached\Deactivated') -Recurse -Filter Configuration.xml -ErrorAction SilentlyContinue)
 Assert 'deactivate_detaches_extension' ($deact.status -eq 'READY' -and !(Test-Path $extRoot) -and $deactCopies.Count -ge 1) "copies=$($deactCopies.Count)"

 Disable-WorkerCatalogItem -Kind MAIN -ProjectId Demo -ParticipantId ut -WorkerRoot $worker
 $deactMain=Apply-WorkerProject -ProjectId Demo -WorkerRoot $worker
 Assert 'deactivate_main_materializes_but_not_ready' ($deactMain.status -eq 'FAIL' -and @($deactMain.errors|Where-Object {$_ -like 'ONEC_MAIN_REQUIRED:*'}).Count -eq 1 -and !(Test-Path $mainRoot)) ($deactMain|ConvertTo-Json -Compress)
 Set-WorkerMain -ProjectId Demo -ParticipantId ut -SourcePath $main -WorkerRoot $worker|Out-Null
 $restore=Apply-WorkerProject -ProjectId Demo -WorkerRoot $worker
 Assert 'set_main_recovers_ready' ($restore.status -eq 'READY') ($restore|ConvertTo-Json -Compress)

 $externalMainAfter=Get-TreeDigest $main;$externalExtAfter=Get-TreeDigest $ext
 Assert 'external_main_immutable_after_operator_v2' ($externalMainAfter.sha256 -eq $sourceMainOperatorV2.sha256)
 Assert 'external_extension_immutable_after_operator_v2' ($externalExtAfter.sha256 -eq $sourceExtOperatorV2.sha256)
 Assert 'original_external_versions_were_distinct' ($sourceMainV1.sha256 -ne $sourceMainOperatorV2.sha256 -and $sourceExtV1.sha256 -ne $sourceExtOperatorV2.sha256)

 $bad=Join-Path $root 'bad';New-Item -ItemType Directory -Force -Path $bad|Out-Null
 try{Set-WorkerMain -ProjectId Demo -ParticipantId ut -SourcePath $bad -WorkerRoot $worker|Out-Null;Fail 'reject_non_onec_root' 'unexpected success'}catch{Pass 'reject_non_onec_root' $_.Exception.Message}

 $op=Start-WorkerOperation -OperationType TEST -RequestedAction observability -TotalSteps 2 -ProgramDataRoot $pd
 $null=Update-WorkerOperation -Operation $op -Message Working -Step 1 -Total 2 -State RUNNING -ProgramDataRoot $pd -Quiet
 $null=Complete-WorkerOperation -Operation $op -State PASS -Message Done -ProgramDataRoot $pd -Quiet
 $recent=@(Get-RecentWorkerOperations -Limit 5 -ProgramDataRoot $pd)
 $logs=@(Get-WorkerOperationLog -Tail 10 -ProgramDataRoot $pd)
 Assert 'observability_history' ($recent.Count -eq 1 -and $recent[0].state -eq 'PASS')
 Assert 'observability_human_log' (@($logs|Where-Object {$_ -match 'TEST.*PASS'}).Count -ge 1)

 $stale=Start-WorkerOperation -OperationType APPLY -RequestedAction 'simulate interrupted operation' -TotalSteps 3 -ProjectId Demo -ProgramDataRoot $pd
 $classification=Get-OperationRecoveryClassification -ProgramDataRoot $pd
 Assert 'interrupted_operation_requires_recovery' ($classification.classification -eq 'RECOVERY_REQUIRED' -and $classification.operation.operation_id -eq $stale.operation_id)
 $null=Complete-WorkerOperation -Operation $stale -State CANCELLED -Message 'test cleanup' -RecoveryHint test -ProgramDataRoot $pd -Quiet

 $diag=Get-WorkerDiagnostics -WorkerRoot $worker -ProgramDataRoot $pd
 Assert 'diagnostics_redacts_secret_material' (-not $diag.secret_material_included)
 $bundle=Export-WorkerDiagnosticBundle -WorkerRoot $worker -ProgramDataRoot $pd -Destination (Join-Path $root 'diag.zip')
 Assert 'diagnostic_bundle_created' ($bundle.status -eq 'PASS' -and (Test-Path $bundle.bundle) -and -not $bundle.secret_material_included)

 $plan=Get-UninstallPlan -WorkerRoot $worker -ProgramDataRoot $pd
 Assert 'safe_uninstall_retains_project_data' (@($plan.retain|Where-Object {$_ -like '*Participants*'}).Count -eq 1 -and @($plan.retain|Where-Object {$_ -like '*Output*'}).Count -eq 1)
 Assert 'safe_uninstall_has_no_source_purge' (@($plan.explicitly_not_performed|Where-Object {$_ -match 'Source deletion|Output purge'}).Count -ge 2)

 $cat=Read-WorkerCatalog $worker;$cat.projects[0].participants[0].platform='CLEVERENCE';Write-WorkerCatalog $cat $worker
 try{Apply-WorkerProject -ProjectId Demo -WorkerRoot $worker|Out-Null;Fail 'cleverence_fail_closed' 'unexpected success'}catch{if($_.Exception.Message -match 'PLATFORM_NOT_IMPLEMENTED_1C_FIRST'){Pass 'cleverence_fail_closed'}else{Fail 'cleverence_fail_closed' $_.Exception.Message}}
}finally{
 $out=[pscustomobject]@{root=$root;pass=(@($results|Where-Object status -eq 'FAIL').Count -eq 0);results=$results}
 $out|ConvertTo-Json -Depth 12|Set-Content -LiteralPath (Join-Path $env:TEMP 'OneCChatWorker-local-regression-result.json') -Encoding UTF8
}
$out|ConvertTo-Json -Depth 12
if(-not $out.pass){exit 2}
