param([string]$PackageRoot=(Split-Path -Parent $PSScriptRoot))
$ErrorActionPreference='Stop'
$PackageRoot=[IO.Path]::GetFullPath($PackageRoot)
$core=Join-Path $PackageRoot 'core\OneCChatWorker.Core.psm1'
$launcher=Join-Path $PackageRoot 'OneCChatWorker.ps1'
$helper=Join-Path $PackageRoot 'runtime\hosted-helper.mjs'
$testScratchModule=Join-Path $PSScriptRoot 'TestScratch.psm1'
Import-Module $testScratchModule -Force -DisableNameChecking
$scratch=New-OneCTestScratch -Purpose 'SnapshotFast'
$root=$scratch.path
$oldLocal=$env:LOCALAPPDATA
$results=New-Object Collections.Generic.List[object]
function Rec([string]$Name,[bool]$Ok,[string]$Detail=''){ $results.Add([pscustomobject]@{name=$Name;pass=$Ok;detail=$Detail}); if(-not $Ok){throw "ASSERTION_FAILED: $Name :: $Detail"} }
function Write-Utf8([string]$Path,[string]$Value){New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Path)|Out-Null;[IO.File]::WriteAllText($Path,$Value,[Text.UTF8Encoding]::new($false))}
function New-Fixture([string]$Name){
 $base=Join-Path $root $Name;$worker=Join-Path $base 'worker';$pd=Join-Path $base 'pd';$source=Join-Path $base 'source'
 New-Item -ItemType Directory -Force -Path $worker,$pd,$source,(Join-Path $pd 'runtime')|Out-Null
 Write-Utf8 (Join-Path $pd 'runtime\rg.exe') '';Write-Utf8 (Join-Path $source 'Configuration.xml') ('<Configuration name="'+$Name+'"/>');Write-Utf8 (Join-Path $source 'Root.bsl') 'Procedure Root() EndProcedure'
 for($i=1;$i-le 24;$i++){Write-Utf8 (Join-Path $source ("Catalogs\C{0:D2}\Module.bsl" -f $i)) ("Procedure P"+$i+"()"+[Environment]::NewLine+"EndProcedure")}
 New-WorkerProject -ProjectId $Name -DisplayName $Name -WorkerRoot $worker|Out-Null;Add-WorkerParticipant -ProjectId $Name -ParticipantId erp -Platform ONEC -Role ERP -WorkerRoot $worker|Out-Null;Set-WorkerMain -ProjectId $Name -ParticipantId erp -SourcePath $source -WorkerRoot $worker|Out-Null
 [pscustomobject]@{id=$Name;base=$base;worker=$worker;pd=$pd;source=$source}
}
function Invoke-HelperExpect([string]$Name,$Admission,[string]$Expected){
 $layout=Join-Path $root 'helper-layout';$helperDir=Join-Path $layout 'helper';$providerDir=Join-Path $layout 'provider';New-Item -ItemType Directory -Force -Path $helperDir,$providerDir|Out-Null
 $installedHelper=Join-Path $helperDir 'hosted-helper.mjs'
 if(-not(Test-Path $installedHelper)){
  Copy-Item $helper $installedHelper -Force
  Copy-Item (Join-Path (Join-Path $PackageRoot 'runtime') 'source-reader-integration.mjs') (Join-Path $providerDir 'source-reader-integration.mjs') -Force
  Copy-Item (Join-Path (Join-Path $PackageRoot 'runtime') 'local-quality-adapter.mjs') (Join-Path $helperDir 'local-quality-adapter.mjs') -Force
  Copy-Item (Join-Path (Join-Path $PackageRoot 'runtime') 'task-checkpoint-store.mjs') (Join-Path $helperDir 'task-checkpoint-store.mjs') -Force
  $qualityDst=Join-Path $helperDir 'quality\cc-1c-skills';New-Item -ItemType Directory -Force -Path $qualityDst|Out-Null
  foreach($qualityScript in @('meta-info.ps1','form-info.ps1','form-validate.ps1')){Copy-Item (Join-Path $PackageRoot ('runtime\quality\cc-1c-skills\'+$qualityScript)) (Join-Path $qualityDst $qualityScript) -Force}
 }
 $path=Join-Path $root ($Name+'.admission.json');$out=Join-Path $root ($Name+'.out.txt');$err=Join-Path $root ($Name+'.err.txt')
 [IO.File]::WriteAllText($path,($Admission|ConvertTo-Json -Depth 20),[Text.UTF8Encoding]::new($false))
 $old=$env:ONECCHAT_ADMISSION_PATH;$env:ONECCHAT_ADMISSION_PATH=$path
 try{$p=Start-Process node.exe -ArgumentList @($installedHelper) -RedirectStandardOutput $out -RedirectStandardError $err -NoNewWindow -Wait -PassThru}finally{$env:ONECCHAT_ADMISSION_PATH=$old}
 $txt=$(if(Test-Path $err){Get-Content $err -Raw -Encoding UTF8}else{''});Rec $Name ($p.ExitCode -ne 0 -and $txt.Contains($Expected)) ("exit=$($p.ExitCode) stderr=$txt")
}
try{
 New-Item -ItemType Directory -Force -Path $root|Out-Null;$env:LOCALAPPDATA=Join-Path $root 'profile';New-Item -ItemType Directory -Force -Path $env:LOCALAPPDATA|Out-Null
 Import-Module $core -Force -DisableNameChecking
 $f=New-Fixture 'Demo83'
 $progress=New-Object Collections.Generic.List[object]
 $applied=Apply-WorkerProject -ProjectId $f.id -WorkerRoot $f.worker -ProgressCallback {param($x)$progress.Add($x)}
 Rec 'apply_ready_accepted' ($applied.status -eq 'READY' -and $applied.state -eq 'ACCEPTED') ($applied|ConvertTo-Json -Compress)
 $ph=@($progress.phase|Select-Object -Unique);Rec 'apply_progress_phases' ($ph -contains 'SCAN' -and $ph -contains 'COPY_HASH' -and $ph -contains 'PUBLISH') ($ph -join ',')
 $manifestPath=Get-ProjectManifestPath -ProjectId $f.id -WorkerRoot $f.worker;$manifest=Get-Content $manifestPath -Raw -Encoding UTF8|ConvertFrom-Json
 Rec 'manifest_v2_accepted' ($manifest.schema_version -eq 2 -and $manifest.accepted_snapshot.snapshot_contract -eq 'ACCEPTED_SNAPSHOT_V1' -and $manifest.accepted_snapshot.snapshot_state -eq 'ACCEPTED') ''
 Rec 'manifest_fingerprint_present' ($manifest.accepted_snapshot.fingerprint_inventory_state -eq 'PRESENT' -and $manifest.accepted_snapshot.artifacts[0].fingerprint_inventory_state -eq 'PRESENT') ''
 $inv=Join-Path (Split-Path $manifestPath -Parent) $manifest.accepted_snapshot.artifacts[0].fingerprint_inventory_path.Replace('/','\');Rec 'fingerprint_inventory_file_exists' (Test-Path $inv) $inv
 $legacyDigest=Get-TreeDigest $f.source;Rec 'one_pass_digest_equals_legacy' ($manifest.participants[0].target.main.tree_sha256 -eq $legacyDigest.sha256) ("onepass=$($manifest.participants[0].target.main.tree_sha256) legacy=$($legacyDigest.sha256)")
 Rec 'one_pass_counts_equal_legacy' ($manifest.participants[0].target.main.files -eq $legacyDigest.files -and $manifest.participants[0].target.main.bytes -eq $legacyDigest.bytes) ''
 $fp=@{};foreach($sa in @($manifest.accepted_snapshot.artifacts)){$fp[(Get-SnapshotArtifactKey $sa)]=[pscustomobject]@{state=$sa.fingerprint_inventory_state;relative_path=$sa.fingerprint_inventory_path;sha256=$sa.fingerprint_inventory_sha256}}
 $s1=New-AcceptedSnapshot -ManifestParticipants @($manifest.participants) -CatalogSha256 $manifest.catalog_sha256 -ProofBasis $manifest.accepted_snapshot.proof_basis -PublicationGeneration $manifest.accepted_snapshot.publication_generation -PublishedUtc '2026-01-01T00:00:00Z' -FingerprintMap $fp
 $s2=New-AcceptedSnapshot -ManifestParticipants @($manifest.participants) -CatalogSha256 $manifest.catalog_sha256 -ProofBasis $manifest.accepted_snapshot.proof_basis -PublicationGeneration $manifest.accepted_snapshot.publication_generation -PublishedUtc '2026-12-31T23:59:59Z' -FingerprintMap $fp
 Rec 'snapshot_id_excludes_timestamp' ($s1.source_snapshot_id -eq $s2.source_snapshot_id) ''
 $sourceUnavailable=$f.source+'-offline';Move-Item $f.source $sourceUnavailable
 $sw=[Diagnostics.Stopwatch]::StartNew();$fast=Get-FastProjectState -ProjectId $f.id -WorkerRoot $f.worker;$sw.Stop()
 Rec 'fast_accepted_with_external_source_offline' ($fast.state -eq 'ACCEPTED') ($fast|ConvertTo-Json -Compress);Rec 'synthetic_fast_under_2s' ($sw.Elapsed.TotalSeconds -lt 2) ("seconds="+$sw.Elapsed.TotalSeconds)
 $status=Get-WorkerStatus -WorkerRoot $f.worker -ProgramDataRoot $f.pd;Rec 'status_fast_contract' ($status.state_check_contract -eq 'FAST_STATE_CHECK_V1' -and $status.projects[0].fast_state -eq 'ACCEPTED') ''
 $a1=New-Admission -ProjectId $f.id -TaskId task1 -WorkerRoot $f.worker -ProgramDataRoot $f.pd -RelayUrl 'wss://example.invalid/mcp' -AcceptedState $fast -TaskRequestLimit 96 -TaskResultByteLimit 108000 -TaskTtlMinutes 120 -EpochSoftRequestLimit 32 -EpochSoftResultByteLimit 36000
 $a2=New-Admission -ProjectId $f.id -TaskId task2 -WorkerRoot $f.worker -ProgramDataRoot $f.pd -RelayUrl 'wss://example.invalid/mcp' -AcceptedState $fast -TaskRequestLimit 96 -TaskResultByteLimit 108000 -TaskTtlMinutes 120 -EpochSoftRequestLimit 32 -EpochSoftResultByteLimit 36000
 Rec 'second_task_reuses_snapshot' ($a1.source_snapshot_id -eq $a2.source_snapshot_id -and $a1.manifest_sha256 -eq $a2.manifest_sha256) '';Rec 'admission_binds_snapshot' ($a2.snapshot_contract -eq 'ACCEPTED_SNAPSHOT_V1' -and $a2.manifest_sha256 -eq $fast.manifest_sha256) ''
 $target=Join-Path (Join-Path $f.worker $f.id) $manifest.participants[0].target.main.canonical_path.Replace('/','\');$targetOff=$target+'-missing';Move-Item $target $targetOff;$x=Get-FastProjectState -ProjectId $f.id -WorkerRoot $f.worker;Rec 'missing_root_fast_reject' ($x.state -eq 'SNAPSHOT_ROOT_MISSING') ($x|ConvertTo-Json -Compress);Move-Item $targetOff $target
 $cfg=Join-Path $target 'Configuration.xml';$cfgOff=$cfg+'.missing';Move-Item $cfg $cfgOff;$x=Get-FastProjectState -ProjectId $f.id -WorkerRoot $f.worker;Rec 'missing_config_fast_reject' ($x.state -eq 'SNAPSHOT_ROOT_MISSING') ($x|ConvertTo-Json -Compress);Move-Item $cfgOff $cfg
 $catalogPath=Get-CatalogPath $f.worker;$catalogBytes=[IO.File]::ReadAllBytes($catalogPath);Edit-WorkerProject -ProjectId $f.id -DisplayName 'Catalog drift' -WorkerRoot $f.worker|Out-Null;$x=Get-FastProjectState -ProjectId $f.id -WorkerRoot $f.worker;Rec 'catalog_drift_fast_reject' ($x.state -eq 'CATALOG_DRIFT') ($x|ConvertTo-Json -Compress);[IO.File]::WriteAllBytes($catalogPath,$catalogBytes)
 $stage=Join-Path (Get-ApplyStageRoot $f.worker) 'a.stage-test83';New-Item -ItemType Directory -Force -Path $stage|Out-Null;Write-ApplyStageState -StagePath $stage -State COPYING -ProjectRoot (Join-Path $f.worker $f.id) -TargetPath $target -ArchiveKey 'erp\Target\Main';$x=Get-FastProjectState -ProjectId $f.id -WorkerRoot $f.worker;Rec 'residue_fast_recover_first' ($x.state -eq 'INCOMPLETE_APPLY_RESIDUE') ($x|ConvertTo-Json -Compress);$null=Remove-ApplyStageTree $stage;Remove-Item ($stage+'.json') -Force -ErrorAction SilentlyContinue
 $driftFile=Join-Path $target 'Root.bsl';$original=[IO.File]::ReadAllBytes($driftFile);Write-Utf8 $driftFile 'Procedure Drift() EndProcedure';$deep=Verify-WorkerProject -ProjectId $f.id -WorkerRoot $f.worker
 Rec 'deep_verify_detects_seeded_drift' ($deep.status -eq 'FAIL' -and @($deep.errors|Where-Object {$_ -like 'HASH_MISMATCH:*'}).Count -gt 0) ($deep|ConvertTo-Json -Compress);$x=Get-FastProjectState -ProjectId $f.id -WorkerRoot $f.worker;Rec 'deep_failure_invalidates_fast' ($x.state -eq 'DEEP_VERIFY_REQUIRED') ($x|ConvertTo-Json -Compress)
 [IO.File]::WriteAllBytes($driftFile,$original);$deep2=Verify-WorkerProject -ProjectId $f.id -WorkerRoot $f.worker;Rec 'deep_verify_reaccepts_restored' ($deep2.status -eq 'READY' -and (Get-FastProjectState -ProjectId $f.id -WorkerRoot $f.worker).state -eq 'ACCEPTED') ''
 $manifest=Get-Content $manifestPath -Raw -Encoding UTF8|ConvertFrom-Json;$badHash=($a2|ConvertTo-Json -Depth 20|ConvertFrom-Json);$badHash.manifest_sha256=('0'*64);Invoke-HelperExpect 'helper_manifest_hash_mismatch' $badHash 'ADMISSION_MANIFEST_HASH_MISMATCH'
 $badSnap=($a2|ConvertTo-Json -Depth 20|ConvertFrom-Json);$badSnap.manifest_sha256=Get-Sha256File $manifestPath;$badSnap.source_snapshot_id=('f'*64);Invoke-HelperExpect 'helper_snapshot_mismatch' $badSnap 'ADMISSION_SOURCE_SNAPSHOT_MISMATCH'
 $driftSource=Join-Path $root 'source-drift';New-Item -ItemType Directory -Force -Path $driftSource|Out-Null;Write-Utf8 (Join-Path $driftSource 'a.txt') 'abc';$plan=New-SourceCopyPlan $driftSource;(Get-Item (Join-Path $driftSource 'a.txt')).LastWriteTimeUtc=(Get-Date).ToUniversalTime().AddSeconds(2);$stage2=Join-Path $root 'stage-drift';$caught=$null;try{Invoke-OnePassCopyHash -Plan $plan -Stage $stage2|Out-Null}catch{$caught=$_.Exception.Message};Rec 'source_metadata_drift_aborts' ($caught -like 'SOURCE_CHANGED_DURING_SYNC:*') $caught
 $legacyWorker=Join-Path $root 'legacy-worker';Copy-Item $f.worker $legacyWorker -Recurse -Force;$legacyManifest=Get-ProjectManifestPath -ProjectId $f.id -WorkerRoot $legacyWorker;$lm=Get-Content $legacyManifest -Raw -Encoding UTF8|ConvertFrom-Json;$lm.schema_version=1;$lm.PSObject.Properties.Remove('accepted_snapshot');$lm.PSObject.Properties.Remove('acceptance_proof');Write-JsonAtomic $lm $legacyManifest
 $legacyPd=Join-Path $root 'legacy-pd';New-Item -ItemType Directory -Force -Path (Join-Path $legacyPd 'operations')|Out-Null;$proof=[pscustomobject]@{schema_version=1;operation_id='proof83';operation_type='REPAIR';project_id=$f.id;state='RECOVERED';started_utc=(Get-Date).ToUniversalTime().AddMinutes(-2).ToString('o');ended_utc=(Get-Date).ToUniversalTime().ToString('o')};Add-Content -LiteralPath (Join-Path $legacyPd 'operations\history.jsonl') -Value ($proof|ConvertTo-Json -Compress) -Encoding UTF8
 $adopt=Adopt-LegacyAcceptedSnapshot -ProjectId $f.id -WorkerRoot $legacyWorker -ProgramDataRoot $legacyPd;Rec 'legacy_adopts_from_durable_proof' ($adopt.status -eq 'ADOPTED' -and (Get-FastProjectState -ProjectId $f.id -WorkerRoot $legacyWorker).state -eq 'ACCEPTED') ($adopt|ConvertTo-Json -Compress);$am=Get-Content $legacyManifest -Raw -Encoding UTF8|ConvertFrom-Json;Rec 'legacy_inventory_absent' ($am.accepted_snapshot.proof_basis -eq 'LEGACY_DEEP_VERIFIED' -and $am.accepted_snapshot.fingerprint_inventory_state -eq 'ABSENT_LEGACY') ''
 $noProofWorker=Join-Path $root 'legacy-no-proof';Copy-Item $f.worker $noProofWorker -Recurse -Force;$npm=Get-ProjectManifestPath -ProjectId $f.id -WorkerRoot $noProofWorker;$nm=Get-Content $npm -Raw -Encoding UTF8|ConvertFrom-Json;$nm.schema_version=1;$nm.PSObject.Properties.Remove('accepted_snapshot');$nm.PSObject.Properties.Remove('acceptance_proof');Write-JsonAtomic $nm $npm;$npd=Join-Path $root 'no-proof-pd';New-Item -ItemType Directory -Force -Path $npd|Out-Null;$reject=Adopt-LegacyAcceptedSnapshot -ProjectId $f.id -WorkerRoot $noProofWorker -ProgramDataRoot $npd;Rec 'legacy_insufficient_evidence_rejects' ($reject.status -eq 'DEEP_VERIFY_REQUIRED' -and $reject.reason -eq 'LEGACY_DURABLE_READY_PROOF_MISSING') ($reject|ConvertTo-Json -Compress)
 $launcherText=Get-Content $launcher -Raw -Encoding UTF8;$startBlock=$launcherText.Substring($launcherText.IndexOf('function Run-Start {'),$launcherText.IndexOf('function Run-Continue {')-$launcherText.IndexOf('function Run-Start {'));$guidedBlock=$launcherText.Substring($launcherText.IndexOf('function Get-GuidedContext {'),$launcherText.IndexOf('function Get-GuidedStateLabel {')-$launcherText.IndexOf('function Get-GuidedContext {'))
 Rec 'start_exactly_one_fast_no_deep' (([regex]::Matches($startBlock,'Get-FastProjectState')).Count -eq 1 -and $startBlock -notmatch 'Verify-WorkerProject') '';Rec 'guided_no_deep' ($guidedBlock -match 'Get-FastProjectState' -and $guidedBlock -notmatch 'Verify-WorkerProject') ''
 $coreText=Get-Content $core -Raw -Encoding UTF8;$statusBlock=$coreText.Substring($coreText.IndexOf('function Get-WorkerStatus {'),$coreText.IndexOf('function Get-WorkerDiagnostics {')-$coreText.IndexOf('function Get-WorkerStatus {'));$admissionBlock=$coreText.Substring($coreText.IndexOf('function New-Admission {'),$coreText.IndexOf('function Test-IsAdministrator {')-$coreText.IndexOf('function New-Admission {'))
 Rec 'status_no_deep_or_tree_digest' ($statusBlock -match 'Get-FastProjectState' -and $statusBlock -notmatch 'Verify-WorkerProject|Get-TreeDigest') '';Rec 'admission_no_deep_or_tree_digest' ($admissionBlock -match 'Get-FastProjectState' -and $admissionBlock -notmatch 'Verify-WorkerProject|Get-TreeDigest') ''
 $helperText=Get-Content $helper -Raw -Encoding UTF8;$ops=@([regex]::Matches($helperText,"if\(op==='([^']+)'\)")|ForEach-Object{$_.Groups[1].Value}|Select-Object -Unique);Rec 'helper_six_ops_exact' (($ops -join ',') -eq 'context,search,read,proposal_write,proposal_read,task_checkpoint_write') ($ops -join ',');Rec 'helper_no_source_write' ($helperText -notmatch 'source_write') ''
 Write-Host ("SNAPSHOT_FAST_REGRESSION_PASS checks={0}" -f $results.Count)
} finally {$env:LOCALAPPDATA=$oldLocal;Remove-OneCTestScratch -Path $root -RunId $scratch.run_id -Base $scratch.base|Out-Null}
