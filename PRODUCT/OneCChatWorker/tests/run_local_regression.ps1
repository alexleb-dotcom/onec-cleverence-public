$ErrorActionPreference='Stop'
$m='C:\Git\onec-cleverence-public\PRODUCT\OneCChatWorker\core\OneCChatWorker.Core.psm1'
Import-Module $m -Force
$root=Join-Path $env:TEMP ('OneCChatProduct-'+[Guid]::NewGuid().ToString('N'))
$worker=Join-Path $root 'worker';$src=Join-Path $root 'source';$main=Join-Path $src 'Main';$ext=Join-Path $src 'Ext'
New-Item -ItemType Directory -Force -Path (Join-Path $main 'CommonModules\M\Ext'),(Join-Path $ext 'CommonModules\E\Ext'),$worker|Out-Null
[IO.File]::WriteAllText((Join-Path $main 'Configuration.xml'),'<Configuration id="main-v1"/>')
[IO.File]::WriteAllText((Join-Path $main 'CommonModules\M\Ext\Module.bsl'),'Procedure MainV1()`r`nEndProcedure')
[IO.File]::WriteAllText((Join-Path $ext 'Configuration.xml'),'<Configuration id="ext-v1"/>')
[IO.File]::WriteAllText((Join-Path $ext 'CommonModules\E\Ext\Module.bsl'),'Procedure ExtV1()`r`nEndProcedure')
$sourceMainBefore=Get-TreeDigest $main;$sourceExtBefore=Get-TreeDigest $ext
$results=New-Object Collections.Generic.List[object]
function Pass($n,$d=''){$results.Add([pscustomobject]@{name=$n;status='PASS';detail=$d})}
function Fail($n,$d){$results.Add([pscustomobject]@{name=$n;status='FAIL';detail=$d})}
try{
 New-WorkerProject -ProjectId 'Demo' -DisplayName 'Demo' -WorkerRoot $worker|Out-Null
 Add-WorkerParticipant -ProjectId 'Demo' -ParticipantId 'ut' -Platform ONEC -Role 'UT' -WorkerRoot $worker|Out-Null
 Set-WorkerMain -ProjectId 'Demo' -ParticipantId 'ut' -SourcePath $main -WorkerRoot $worker|Out-Null
 Add-WorkerExtension -ProjectId 'Demo' -ParticipantId 'ut' -ExtensionId 'custom' -SourcePath $ext -WorkerRoot $worker|Out-Null
 $v=Apply-WorkerProject -ProjectId Demo -WorkerRoot $worker
 if($v.status -eq 'READY'){Pass 'apply_ready'}else{Fail 'apply_ready' ($v|ConvertTo-Json -Compress)}
 $mainRoot=Join-Path $worker 'Demo\Participants\ut\Target\Main';$extRoot=Join-Path $worker 'Demo\Participants\ut\Target\Extensions\custom'
 if((Test-Path (Join-Path $mainRoot 'Configuration.xml')) -and !(Test-Path (Join-Path $mainRoot 'Main'))){Pass 'direct_main_root'}else{Fail 'direct_main_root' 'wrapper or missing config'}
 if((Test-Path (Join-Path $extRoot 'Configuration.xml')) -and !(Test-Path (Join-Path $extRoot 'custom'))){Pass 'direct_extension_root'}else{Fail 'direct_extension_root' 'wrapper or missing config'}
 $marker=Join-Path $worker 'Demo\Output\keep.txt';[IO.File]::WriteAllText($marker,'keep')
 $v2=Apply-WorkerProject -ProjectId Demo -WorkerRoot $worker
 if($v2.status -eq 'READY' -and (Get-Content $marker -Raw) -eq 'keep'){Pass 'idempotent_apply_preserves_output'}else{Fail 'idempotent_apply_preserves_output' ''}
 $c=Read-WorkerCatalog -WorkerRoot $worker;$c.projects[0].display_name='Changed';Write-WorkerCatalog $c $worker
 $drift=Verify-WorkerProject -ProjectId Demo -WorkerRoot $worker
 if($drift.status -eq 'DRIFT_APPLY_REQUIRED'){Pass 'catalog_drift_detected'}else{Fail 'catalog_drift_detected' $drift.status}
 $repair=Repair-WorkerProject -ProjectId Demo -WorkerRoot $worker
 if($repair.status -eq 'READY'){Pass 'bounded_repair'}else{Fail 'bounded_repair' $repair.status}
 [IO.File]::WriteAllText((Join-Path $main 'CommonModules\M\Ext\Module.bsl'),'Procedure MainV2()`r`nEndProcedure')
 Set-WorkerMain -ProjectId Demo -ParticipantId ut -SourcePath $main -ReplaceExisting -WorkerRoot $worker|Out-Null
 $replace=Apply-WorkerProject -ProjectId Demo -WorkerRoot $worker
 $detached=@(Get-ChildItem -LiteralPath (Join-Path $worker 'Demo\Detached\ut\Target\Main') -Directory -ErrorAction SilentlyContinue)
 if($replace.status -eq 'READY' -and $detached.Count -ge 1 -and (Get-Content (Join-Path $mainRoot 'CommonModules\M\Ext\Module.bsl') -Raw) -match 'MainV2'){Pass 'safe_replace_detached_old'}else{Fail 'safe_replace_detached_old' "detached=$($detached.Count)"}
 Disable-WorkerCatalogItem -Kind EXTENSION -ProjectId Demo -ParticipantId ut -ExtensionId custom -WorkerRoot $worker
 $deact=Apply-WorkerProject -ProjectId Demo -WorkerRoot $worker
 $deactCopies=@(Get-ChildItem -LiteralPath (Join-Path $worker 'Demo\Detached\Deactivated') -Recurse -Filter Configuration.xml -ErrorAction SilentlyContinue)
 if($deact.status -eq 'READY' -and !(Test-Path $extRoot) -and $deactCopies.Count -ge 1){Pass 'deactivate_detaches_extension'}else{Fail 'deactivate_detaches_extension' "copies=$($deactCopies.Count) exists=$(Test-Path $extRoot)"}
 $externalMainAfter=Get-TreeDigest $main;$externalExtAfter=Get-TreeDigest $ext
 if($externalExtAfter.sha256 -eq $sourceExtBefore.sha256){Pass 'external_extension_immutable'}else{Fail 'external_extension_immutable' ''}
 if((Get-Content (Join-Path $main 'CommonModules\M\Ext\Module.bsl') -Raw) -match 'MainV2'){Pass 'external_main_only_operator_change'}else{Fail 'external_main_only_operator_change' ''}
 $bad=Join-Path $root 'bad';New-Item -ItemType Directory -Force -Path $bad|Out-Null
 try{Set-WorkerMain -ProjectId Demo -ParticipantId ut -SourcePath $bad -WorkerRoot $worker|Out-Null;Fail 'reject_non_onec_root' 'unexpected success'}catch{Pass 'reject_non_onec_root' $_.Exception.Message}
 $cat=Read-WorkerCatalog $worker;$cat.projects[0].participants[0].platform='CLEVERENCE';Write-WorkerCatalog $cat $worker
 try{Apply-WorkerProject -ProjectId Demo -WorkerRoot $worker|Out-Null;Fail 'cleverence_fail_closed' 'unexpected success'}catch{if($_.Exception.Message -match 'PLATFORM_NOT_IMPLEMENTED_1C_FIRST'){Pass 'cleverence_fail_closed'}else{Fail 'cleverence_fail_closed' $_.Exception.Message}}
}finally{
 $out=[pscustomobject]@{root=$root;pass=(@($results|Where-Object status -eq 'FAIL').Count -eq 0);results=$results}
 $out|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $env:TEMP 'OneCChatWorker-local-regression-result.json') -Encoding UTF8
}
$out|ConvertTo-Json -Depth 8
if(-not $out.pass){exit 2}