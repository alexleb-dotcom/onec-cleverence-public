param(
 [ValidateSet('RUN','ADMIN_PREPARE','ADMIN_TEST')][string]$Mode='RUN',
 [string]$PackageRoot=(Split-Path -Parent $PSScriptRoot),
 [string]$ScratchRoot,[string]$ScratchRunId,[string]$ScratchBase,
 [string]$OperatorIdentity,[string]$ReportPath
)
$ErrorActionPreference='Stop'
$PackageRoot=[IO.Path]::GetFullPath($PackageRoot)
Import-Module (Join-Path $PSScriptRoot 'TestScratch.psm1') -Force -DisableNameChecking
if([string]::IsNullOrWhiteSpace($OperatorIdentity)){$OperatorIdentity=[Security.Principal.WindowsIdentity]::GetCurrent().Name}
function Is-Admin {$id=[Security.Principal.WindowsIdentity]::GetCurrent();(New-Object Security.Principal.WindowsPrincipal($id)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)}
function W([string]$Path,[string]$Text){New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Path)|Out-Null;[IO.File]::WriteAllText($Path,$Text,[Text.UTF8Encoding]::new($false))}
function A([string]$Name,[bool]$Ok,$Detail=''){if(-not $Ok){if($Mode-eq'ADMIN_TEST'){try{$diag=Join-Path $env:LOCALAPPDATA 'OneCArchitecture\q95-admin-test-failure.txt';[IO.File]::WriteAllText($diag,("ASSERTION_FAILED:{0}::{1}" -f $Name,$Detail),[Text.UTF8Encoding]::new($false))}catch{}};throw ("ASSERTION_FAILED:{0}::{1}" -f $Name,$Detail)};Write-Host ("PASS "+$Name)}
function Get-M([string]$Worker,[string]$Project){Get-Content (Join-Path $Worker ($Project+'\ProjectManifest\project.json')) -Raw -Encoding UTF8|ConvertFrom-Json}
function Art([object]$M,[string]$Key){@((Get-ManifestArtifactRows $M)|Where-Object{(Get-SnapshotArtifactKey $_)-eq$Key}|Select-Object -First 1)[0]}
function Fp([object]$M,[string]$Key){@($M.accepted_snapshot.artifacts|Where-Object{(Get-SnapshotArtifactKey $_)-eq$Key}|Select-Object -First 1)[0]}
function New-Fx([string]$Name,[int]$Extensions=1){
 $base=Join-Path $ScratchRoot ('cases\'+$Name);$worker=Join-Path $base 'worker';$pd=Join-Path $base 'pd';$src=Join-Path $base 'external'
 New-Item -ItemType Directory -Force -Path $worker,(Join-Path $pd 'runtime')|Out-Null
 $main=Join-Path $src 'Main';W (Join-Path $main 'Configuration.xml') '<Configuration name="Main"/>';W (Join-Path $main 'CommonModules\Main\Module.bsl') ("Procedure Main(){0}EndProcedure{0}" -f [Environment]::NewLine)
 $blob=New-Object byte[] (1024*1024);[IO.File]::WriteAllBytes((Join-Path $main 'main.bin'),$blob)
 New-WorkerProject -ProjectId $Name -DisplayName $Name -WorkerRoot $worker|Out-Null
 Add-WorkerParticipant -ProjectId $Name -ParticipantId p -Platform ONEC -Role Test -WorkerRoot $worker|Out-Null
 Set-WorkerMain -ProjectId $Name -ParticipantId p -SourcePath $main -WorkerRoot $worker|Out-Null
 for($i=1;$i-le$Extensions;$i++){
  $eid='e'+$i;$er=Join-Path $src $eid;W (Join-Path $er 'Configuration.xml') ('<Configuration name="{0}"/>' -f $eid);W (Join-Path $er ('CommonModules\'+$eid+'\Module.bsl')) ("Procedure {0}(){1}EndProcedure{1}" -f $eid,[Environment]::NewLine);W (Join-Path $er 'ConfigDumpInfo.xml') ('<ConfigDumpInfo id="{0}"/>' -f $i)
  Add-WorkerExtension -ProjectId $Name -ParticipantId p -ExtensionId $eid -SourcePath $er -WorkerRoot $worker|Out-Null
 }
 $ap=Apply-WorkerProject -ProjectId $Name -WorkerRoot $worker;A ($Name+'.initial_ready') ($ap.status-eq'READY') ($ap|ConvertTo-Json -Compress)
 [pscustomobject]@{name=$Name;worker=$worker;pd=$pd;external=$src}
}
function Fill([string]$Slot,[string]$Label,[int]$Revision=2){
 W (Join-Path $Slot 'Configuration.xml') ('<Configuration name="{0}-r{1}"/>' -f $Label,$Revision)
 W (Join-Path $Slot ('CommonModules\'+$Label+'\Module.bsl')) ("Procedure {0}R{1}(){2}EndProcedure{2}" -f $Label,$Revision,[Environment]::NewLine)
 W (Join-Path $Slot 'ConfigDumpInfo.xml') ('<ConfigDumpInfo revision="{0}"/>' -f $Revision)
}
function FillFrom([string]$Slot,[string]$Canonical){Get-ChildItem -LiteralPath $Canonical -Force|ForEach-Object{Copy-Item -LiteralPath $_.FullName -Destination $Slot -Recurse -Force}}
function NoWrite([string]$Path,[string]$Identity){
 $sid=(New-Object Security.Principal.NTAccount($Identity)).Translate([Security.Principal.SecurityIdentifier]).Value
 $rules=@((Get-Acl -LiteralPath $Path).Access|Where-Object{$_.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value-eq$sid -and $_.AccessControlType-eq'Allow'})
 $write=[Security.AccessControl.FileSystemRights]::WriteData -bor [Security.AccessControl.FileSystemRights]::AppendData -bor [Security.AccessControl.FileSystemRights]::WriteAttributes -bor [Security.AccessControl.FileSystemRights]::WriteExtendedAttributes -bor [Security.AccessControl.FileSystemRights]::Delete -bor [Security.AccessControl.FileSystemRights]::DeleteSubdirectoriesAndFiles -bor [Security.AccessControl.FileSystemRights]::ChangePermissions -bor [Security.AccessControl.FileSystemRights]::TakeOwnership
 -not @($rules|Where-Object{([int64]$_.FileSystemRights-band[int64]$write)-ne0}).Count
}
if($Mode-eq'ADMIN_TEST'){
 trap {
  try{
   $diag=Join-Path $env:LOCALAPPDATA 'OneCArchitecture\q95-admin-test-failure.txt'
   [IO.File]::WriteAllText($diag,($_|Out-String),[Text.UTF8Encoding]::new($false))
  }catch{}
  break
 }
}

if($Mode-eq'RUN'){
 if(Is-Admin){throw 'RUN_EXPECTS_NON_ADMIN'}
 $s=New-OneCTestScratch -Purpose 'SourceZeroCopy';$ScratchRoot=$s.path;$ScratchRunId=$s.run_id;$ScratchBase=$s.base
 $ReportPath=Join-Path $env:LOCALAPPDATA ('OneCArchitecture\source-zero-copy-'+[Guid]::NewGuid().ToString('N')+'.json')
 try{
  $tail=@('-PackageRoot',$PackageRoot,'-ScratchRoot',$ScratchRoot,'-ScratchRunId',$ScratchRunId,'-ScratchBase',$ScratchBase,'-OperatorIdentity',$OperatorIdentity,'-ReportPath',$ReportPath)
  $p=Start-Process powershell.exe -Verb RunAs -ArgumentList (@('-NoProfile','-ExecutionPolicy','Bypass','-File',$PSCommandPath,'-Mode','ADMIN_PREPARE')+$tail) -Wait -PassThru;if($p.ExitCode-ne0){throw ("ADMIN_PREPARE_FAILED:"+$p.ExitCode)}
  $prep=Get-Content (Join-Path $ScratchRoot 'operator-prepared.json') -Raw -Encoding UTF8|ConvertFrom-Json
  W (Join-Path ([string]$prep.slot_path) 'Configuration.xml') '<Configuration name="OperatorWrite"/>'
  W (Join-Path ([string]$prep.slot_path) 'CommonModules\Operator\Module.bsl') ("Procedure OperatorWrite(){0}EndProcedure{0}" -f [Environment]::NewLine)
  W (Join-Path ([string]$prep.slot_path) 'ConfigDumpInfo.xml') '<ConfigDumpInfo operator="true"/>'
  Write-Host 'PASS actual_nonadmin_write_prepared_slot'
  $readerIdentity="$env:COMPUTERNAME\OneCSourceReader";A 'accepted_source_reader_acl_no_write' (NoWrite ([string]$prep.canonical_file) $readerIdentity)
  $adminLog=Join-Path $env:LOCALAPPDATA 'OneCArchitecture\q95-admin-test-output.txt';Remove-Item $adminLog -Force -ErrorAction SilentlyContinue
  $cmdPath=Join-Path $ScratchRoot 'admin-test.cmd'
  $cmdLine='@echo off'+[Environment]::NewLine+'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "'+$PSCommandPath+'" -Mode ADMIN_TEST -PackageRoot "'+$PackageRoot+'" -ScratchRoot "'+$ScratchRoot+'" -ScratchRunId "'+$ScratchRunId+'" -ScratchBase "'+$ScratchBase+'" -OperatorIdentity "'+$OperatorIdentity+'" -ReportPath "'+$ReportPath+'" > "'+$adminLog+'" 2>&1'+[Environment]::NewLine+'exit /b %ERRORLEVEL%'+[Environment]::NewLine
  [IO.File]::WriteAllText($cmdPath,$cmdLine,[Text.ASCIIEncoding]::new())
  $p2=Start-Process $cmdPath -Verb RunAs -Wait -PassThru;if($p2.ExitCode-ne0){$detail=$(if(Test-Path $adminLog){Get-Content $adminLog -Raw -Encoding Default}else{''});throw ("ADMIN_TEST_FAILED:"+$p2.ExitCode+":"+$detail)}
  $r=Get-Content $ReportPath -Raw -Encoding UTF8|ConvertFrom-Json;if($r.result-ne'PASS'){throw 'SOURCE_ZERO_COPY_REPORT_NOT_PASS'}
  Write-Host ("SOURCE_ZERO_COPY_WINDOWS_PS51_PASS checks={0} fault_cases={1}" -f $r.checks,$r.fault_cases)
 }finally{
  if(Test-Path -LiteralPath $ScratchRoot){$testScratchModule=Join-Path $PSScriptRoot 'TestScratch.psm1';$cleanCommand="Import-Module '"+$testScratchModule+"' -Force -DisableNameChecking;Remove-OneCTestScratch -Path '"+$ScratchRoot+"' -RunId '"+$ScratchRunId+"' -Base '"+$ScratchBase+"'|Out-Null";$cl=Start-Process powershell.exe -Verb RunAs -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-Command',$cleanCommand) -Wait -PassThru;if($cl.ExitCode-ne0){Write-Warning ("cleanup exit="+$cl.ExitCode)}}
  Remove-Item -LiteralPath $ReportPath -Force -ErrorAction SilentlyContinue
 }
 exit 0
}
if(-not(Is-Admin)){throw 'ADMIN_PHASE_REQUIRED'}
Import-Module (Join-Path $PackageRoot 'core\OneCChatWorker.Core.psm1') -Force -DisableNameChecking
Set-WorkerReaderIdentity -ReaderName OneCSourceReader|Out-Null
if($Mode-eq'ADMIN_PREPARE'){
 $f=New-Fx 'OperatorWrite';$m=Get-M $f.worker $f.name;$main=Art $m 'p|MAIN|main'
 $prep=Prepare-SourceUpdate -ProjectId $f.name -Selections @('p|EXTENSION|e1') -WorkerRoot $f.worker -ProgramDataRoot $f.pd -OperatorIdentity $OperatorIdentity
 $slot=[string]$prep.slots[0].slot_path;$sid=(New-Object Security.Principal.NTAccount($OperatorIdentity)).Translate([Security.Principal.SecurityIdentifier]).Value
 $rules=@((Get-Acl -LiteralPath $slot).Access|Where-Object{$_.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value-eq$sid -and $_.AccessControlType-eq'Allow'})
 A 'prepared_slot_operator_modify' (@($rules|Where-Object{$_.FileSystemRights.ToString()-match'Modify'}).Count-gt0)
 $canonical=Join-Path (Join-Path $f.worker $f.name) ([string]$main.canonical_path).Replace('/','\')
 $info=[ordered]@{slot_path=$slot;canonical_file=(Join-Path $canonical 'Configuration.xml')};[IO.File]::WriteAllText((Join-Path $ScratchRoot 'operator-prepared.json'),($info|ConvertTo-Json),[Text.UTF8Encoding]::new($false));exit 0
}
$script:checks=0;function T([string]$n,[bool]$ok,$d=''){A $n $ok $d;$script:checks++}
# Complete actual operator-write fixture, first proving active-admission block and sealed ACL.
$base=Join-Path $ScratchRoot 'cases\OperatorWrite';$f=[pscustomobject]@{name='OperatorWrite';worker=(Join-Path $base 'worker');pd=(Join-Path $base 'pd')}
$before=Get-M $f.worker $f.name;$beforeSha=Get-Sha256File (Get-ProjectManifestPath -ProjectId $f.name -WorkerRoot $f.worker);$mainBefore=Art $before 'p|MAIN|main';$mainFpBefore=Fp $before 'p|MAIN|main'
Write-JsonAtomic ([ordered]@{schema_version=3;project_id=$f.name;task_id='live'}) (Join-Path $f.pd 'runtime\active-admission.json')
$blocked=Accept-SourceUpdate -ProjectId $f.name -WorkerRoot $f.worker -ProgramDataRoot $f.pd -OperatorIdentity $OperatorIdentity
T 'active_admission_sealed_validated' ($blocked.status-eq'SEALED_VALIDATED' -and $blocked.reason-eq'PROJECT_ADMISSION_ACTIVE' -and -not $blocked.publication_performed)
$state=Read-SourceUpdateState -ProjectId $f.name -WorkerRoot $f.worker;$slotAcl=(Get-Acl -LiteralPath ([string]$state.selected[0].slot_path)).Access|Select-Object IdentityReference,FileSystemRights,AccessControlType,IsInherited;T 'seal_removes_operator_write' (NoWrite ([string]$state.selected[0].slot_path) $OperatorIdentity) ($slotAcl|ConvertTo-Json -Compress);T 'active_admission_no_manifest_change' ((Get-Sha256File (Get-ProjectManifestPath -ProjectId $f.name -WorkerRoot $f.worker))-eq$beforeSha)
Remove-Item (Join-Path $f.pd 'runtime\active-admission.json') -Force
$ok=Accept-SourceUpdate -ProjectId $f.name -WorkerRoot $f.worker -ProgramDataRoot $f.pd -OperatorIdentity $OperatorIdentity
T 'extension_only_ready' ($ok.status-eq'READY' -and $ok.zero_copy -and $ok.copied_content_bytes-eq0 -and $ok.stage_content_rehash-eq0)
T 'extension_only_main_zero_io' ($ok.main_content_bytes_read-eq0 -and $ok.main_hashed_bytes-eq0 -and $ok.main_copied_bytes-eq0)
$after=Get-M $f.worker $f.name;$mainAfter=Art $after 'p|MAIN|main';$mainFpAfter=Fp $after 'p|MAIN|main'
T 'main_row_reused_exactly' ($mainBefore.tree_sha256-eq$mainAfter.tree_sha256 -and $mainBefore.files-eq$mainAfter.files -and $mainBefore.bytes-eq$mainAfter.bytes -and $mainFpBefore.fingerprint_inventory_sha256-eq$mainFpAfter.fingerprint_inventory_sha256)
T 'snapshot_generation_increment_once' ([int]$after.accepted_snapshot.publication_generation-eq([int]$before.accepted_snapshot.publication_generation+1) -and $after.accepted_snapshot.source_snapshot_id-ne$before.accepted_snapshot.source_snapshot_id)
$oldFp=Fp $before 'p|EXTENSION|e1';$newFp=Fp $after 'p|EXTENSION|e1';T 'versioned_fingerprint_old_retained' ((Test-Path (Join-Path (Split-Path (Get-ProjectManifestPath -ProjectId $f.name -WorkerRoot $f.worker) -Parent) ([string]$oldFp.fingerprint_inventory_path).Replace('/','\'))) -and $oldFp.fingerprint_inventory_path-ne$newFp.fingerprint_inventory_path)
# NO_CHANGE
$n=New-Fx 'NoChange';$bm=Get-M $n.worker $n.name;$bs=Get-Sha256File (Get-ProjectManifestPath -ProjectId $n.name -WorkerRoot $n.worker);$prep=Prepare-SourceUpdate -ProjectId $n.name -Selections @('p|EXTENSION|e1') -WorkerRoot $n.worker -ProgramDataRoot $n.pd -OperatorIdentity $OperatorIdentity
FillFrom ([string]$prep.slots[0].slot_path) (Join-Path (Join-Path $n.worker $n.name) 'Participants\p\Target\Extensions\e1')
$no=Accept-SourceUpdate -ProjectId $n.name -WorkerRoot $n.worker -ProgramDataRoot $n.pd -OperatorIdentity $OperatorIdentity;T 'no_change_preserves_identity' ($no.status-eq'NO_CHANGE' -and $no.source_snapshot_id-eq$bm.accepted_snapshot.source_snapshot_id -and $no.publication_generation-eq$bm.accepted_snapshot.publication_generation -and (Get-Sha256File (Get-ProjectManifestPath -ProjectId $n.name -WorkerRoot $n.worker))-eq$bs)
# multi-artifact
$mu=New-Fx 'Multi' 2;$mb=Get-M $mu.worker $mu.name;$prep=Prepare-SourceUpdate -ProjectId $mu.name -Selections @('p|EXTENSION|e1','p|EXTENSION|e2') -WorkerRoot $mu.worker -ProgramDataRoot $mu.pd -OperatorIdentity $OperatorIdentity;Fill ([string]$prep.slots[0].slot_path) e1 3;Fill ([string]$prep.slots[1].slot_path) e2 4
$mr=Accept-SourceUpdate -ProjectId $mu.name -WorkerRoot $mu.worker -ProgramDataRoot $mu.pd -OperatorIdentity $OperatorIdentity;$ma=Get-M $mu.worker $mu.name;T 'multi_artifact_one_manifest_generation' ($mr.status-eq'READY' -and [int]$ma.accepted_snapshot.publication_generation-eq([int]$mb.accepted_snapshot.publication_generation+1) -and @($mr.selected|Where-Object{$_.change_state-eq'CHANGED'}).Count-eq2)
# stale manifest
$st=New-Fx 'StaleBase';$prep=Prepare-SourceUpdate -ProjectId $st.name -Selections @('p|EXTENSION|e1') -WorkerRoot $st.worker -ProgramDataRoot $st.pd -OperatorIdentity $OperatorIdentity;Fill ([string]$prep.slots[0].slot_path) e1 5;$mp=Get-ProjectManifestPath -ProjectId $st.name -WorkerRoot $st.worker;$md=Get-Content $mp -Raw -Encoding UTF8|ConvertFrom-Json;$md.applied_utc=(Get-Date).AddSeconds(1).ToUniversalTime().ToString('o');Write-JsonAtomic $md $mp;$got='';try{Accept-SourceUpdate -ProjectId $st.name -WorkerRoot $st.worker -ProgramDataRoot $st.pd -OperatorIdentity $OperatorIdentity|Out-Null}catch{$got=$_.Exception.Message};T 'stale_manifest_blocks_before_mutation' ($got-eq'SOURCE_UPDATE_STALE_BASE')
# stale catalog
$sc=New-Fx 'StaleCatalog';$prep=Prepare-SourceUpdate -ProjectId $sc.name -Selections @('p|EXTENSION|e1') -WorkerRoot $sc.worker -ProgramDataRoot $sc.pd -OperatorIdentity $OperatorIdentity;Fill ([string]$prep.slots[0].slot_path) e1 5;$cat=Read-WorkerCatalog $sc.worker;$cat.projects[0].display_name='changed';Write-WorkerCatalog $cat $sc.worker;$got='';try{Accept-SourceUpdate -ProjectId $sc.name -WorkerRoot $sc.worker -ProgramDataRoot $sc.pd -OperatorIdentity $OperatorIdentity|Out-Null}catch{$got=$_.Exception.Message};T 'stale_catalog_blocks_before_mutation' ($got-eq'SOURCE_UPDATE_STALE_CATALOG')
# drift after seal
$dr=New-Fx 'SealDrift';$prep=Prepare-SourceUpdate -ProjectId $dr.name -Selections @('p|EXTENSION|e1') -WorkerRoot $dr.worker -ProgramDataRoot $dr.pd -OperatorIdentity $OperatorIdentity;Fill ([string]$prep.slots[0].slot_path) e1 6;try{Accept-SourceUpdate -ProjectId $dr.name -WorkerRoot $dr.worker -ProgramDataRoot $dr.pd -OperatorIdentity $OperatorIdentity -FaultInjection AFTER_VALIDATION|Out-Null}catch{};$state=Read-SourceUpdateState -ProjectId $dr.name -WorkerRoot $dr.worker;Add-Content -LiteralPath (Join-Path ([string]$state.selected[0].slot_path) 'Configuration.xml') -Value '<!--drift-->' -Encoding UTF8;$got='';try{Accept-SourceUpdate -ProjectId $dr.name -WorkerRoot $dr.worker -ProgramDataRoot $dr.pd -OperatorIdentity $OperatorIdentity|Out-Null}catch{$got=$_.Exception.Message};T 'sealed_drift_blocks_before_promotion' ($got-like'SEALED_SOURCE_DRIFT:*' -and -not(Test-Path (Get-SourceUpdatePaths -ProjectId $dr.name -WorkerRoot $dr.worker).promotion_path))
# cancel
$ca=New-Fx 'CancelCase';$cbs=Get-FastProjectState -ProjectId $ca.name -WorkerRoot $ca.worker;$prep=Prepare-SourceUpdate -ProjectId $ca.name -Selections @('p|EXTENSION|e1') -WorkerRoot $ca.worker -ProgramDataRoot $ca.pd -OperatorIdentity $OperatorIdentity;$cr=Cancel-SourceUpdate -ProjectId $ca.name -WorkerRoot $ca.worker -OperatorIdentity $OperatorIdentity;$cas=Get-FastProjectState -ProjectId $ca.name -WorkerRoot $ca.worker;T 'cancel_unaccepted_only' ($cr.status-eq'CANCELLED' -and $cas.source_snapshot_id-eq$cbs.source_snapshot_id -and (Get-SourceUpdateSummary -ProjectId $ca.name -WorkerRoot $ca.worker).status-eq'NONE')
# direct selected fallback owner
$fb=New-Fx 'Fallback';$fbm=Get-M $fb.worker $fb.name;$mainFb=Art $fbm 'p|MAIN|main';$prep=Prepare-SourceUpdate -ProjectId $fb.name -Selections @('p|EXTENSION|e1') -WorkerRoot $fb.worker -ProgramDataRoot $fb.pd -OperatorIdentity $OperatorIdentity;Fill ([string]$prep.slots[0].slot_path) e1 7;try{Accept-SourceUpdate -ProjectId $fb.name -WorkerRoot $fb.worker -ProgramDataRoot $fb.pd -OperatorIdentity $OperatorIdentity -FaultInjection AFTER_VALIDATION|Out-Null}catch{};$state=Read-SourceUpdateState -ProjectId $fb.name -WorkerRoot $fb.worker;$baseM=Get-Content ([string]$state.base_manifest_path) -Raw -Encoding UTF8|ConvertFrom-Json;$changed=@($state.selected|Where-Object{$_.change_state-eq'CHANGED'});$fr=Invoke-SelectedArtifactFullSafeImportFallback -ProjectId $fb.name -State $state -BaseManifest $baseM -Changed $changed -WorkerRoot $fb.worker -OperatorIdentity $OperatorIdentity;$fbAfter=Get-M $fb.worker $fb.name;$mainFb2=Art $fbAfter 'p|MAIN|main';T 'explicit_selected_full_safe_import_fallback' ($fr.status-eq'READY' -and -not $fr.zero_copy -and $fr.fallback-eq'SELECTED_ARTIFACT_FULL_SAFE_IMPORT' -and $fr.copied_content_bytes-gt0 -and $mainFb.tree_sha256-eq$mainFb2.tree_sha256)
# fault windows
$faults=@('AFTER_MARKER','AFTER_FIRST_DETACH','AFTER_FIRST_PROMOTE','AFTER_ALL_PROMOTED','AFTER_MANIFEST_COMMIT','AFTER_MARKER_REMOVAL');$faultCount=0
foreach($fault in $faults){$name='F'+($faultCount+1);$fx=New-Fx $name;$baseFast=Get-FastProjectState -ProjectId $fx.name -WorkerRoot $fx.worker;$prep=Prepare-SourceUpdate -ProjectId $fx.name -Selections @('p|EXTENSION|e1') -WorkerRoot $fx.worker -ProgramDataRoot $fx.pd -OperatorIdentity $OperatorIdentity;Fill ([string]$prep.slots[0].slot_path) e1 (20+$faultCount);$got='';try{Accept-SourceUpdate -ProjectId $fx.name -WorkerRoot $fx.worker -ProgramDataRoot $fx.pd -OperatorIdentity $OperatorIdentity -FaultInjection $fault|Out-Null}catch{$got=$_.Exception.Message};T ('fault_raised_'+$fault) ($got-like'SOURCE_UPDATE_TEST_FAULT_*') $got;$repair=Repair-WorkerProject -ProjectId $fx.name -WorkerRoot $fx.worker -ProgramDataRoot $fx.pd -OperatorIdentity $OperatorIdentity;$final=Get-FastProjectState -ProjectId $fx.name -WorkerRoot $fx.worker;T ('fault_recovered_'+$fault) ($repair.status-eq'READY' -and $final.state-eq'ACCEPTED' -and (Get-SourceUpdateSummary -ProjectId $fx.name -WorkerRoot $fx.worker).status-eq'NONE');if($fault -in @('AFTER_MARKER','AFTER_FIRST_DETACH','AFTER_FIRST_PROMOTE','AFTER_ALL_PROMOTED')){T ('fault_rollback_base_'+$fault) ($final.source_snapshot_id-eq$baseFast.source_snapshot_id)}else{T ('fault_finalize_new_'+$fault) ($final.source_snapshot_id-ne$baseFast.source_snapshot_id)};$faultCount++}
# contradictory recovery
$co=New-Fx 'Contradict';$prep=Prepare-SourceUpdate -ProjectId $co.name -Selections @('p|EXTENSION|e1') -WorkerRoot $co.worker -ProgramDataRoot $co.pd -OperatorIdentity $OperatorIdentity;Fill ([string]$prep.slots[0].slot_path) e1 99;try{Accept-SourceUpdate -ProjectId $co.name -WorkerRoot $co.worker -ProgramDataRoot $co.pd -OperatorIdentity $OperatorIdentity -FaultInjection AFTER_FIRST_PROMOTE|Out-Null}catch{};$state=Read-SourceUpdateState -ProjectId $co.name -WorkerRoot $co.worker;$mp=Get-ProjectManifestPath -ProjectId $co.name -WorkerRoot $co.worker;$m=Get-Content $mp -Raw -Encoding UTF8|ConvertFrom-Json;$m.applied_utc=(Get-Date).AddMinutes(1).ToUniversalTime().ToString('o');Write-JsonAtomic $m $mp;$got='';try{Recover-SourceUpdatePromotion -ProjectId $co.name -WorkerRoot $co.worker -ProgramDataRoot $co.pd -OperatorIdentity $OperatorIdentity|Out-Null}catch{$got=$_.Exception.Message};T 'contradictory_residue_fails_closed' ($got-eq'SOURCE_UPDATE_RECOVERY_CONTRADICTORY_STATE');Copy-Item ([string]$state.base_manifest_path) $mp -Force;$null=Recover-SourceUpdatePromotion -ProjectId $co.name -WorkerRoot $co.worker -ProgramDataRoot $co.pd -OperatorIdentity $OperatorIdentity
$result=[ordered]@{result='PASS';checks=$script:checks;fault_cases=$faultCount;production_mutation=$false};New-Item -ItemType Directory -Force -Path (Split-Path -Parent $ReportPath)|Out-Null;[IO.File]::WriteAllText($ReportPath,($result|ConvertTo-Json -Depth 8),[Text.UTF8Encoding]::new($false));Write-Host ("ADMIN_SOURCE_ZERO_COPY_PASS checks={0} fault_cases={1}" -f $script:checks,$faultCount)
