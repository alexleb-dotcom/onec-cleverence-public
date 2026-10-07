param([string]$PackageRoot=(Split-Path -Parent $PSScriptRoot))
$ErrorActionPreference='Stop'
$PackageRoot=[IO.Path]::GetFullPath($PackageRoot)
Import-Module (Join-Path $PSScriptRoot 'TestScratch.psm1') -Force -DisableNameChecking
$scratch=New-OneCTestScratch -Purpose 'SourceAcquisition'
$root=$scratch.path
try{
 $node=Get-Command node.exe -ErrorAction Stop
 if((& $node.Source --version).Trim() -ne 'v26.7.0'){throw 'PINNED_NODE_VERSION_MISMATCH'}
 $out=Join-Path $root 'node-out.json';$err=Join-Path $root 'node-err.txt'
 $env:ONEC_TEST_CULTURE=[Globalization.CultureInfo]::CurrentCulture.Name
 $p=Start-Process -FilePath $node.Source -ArgumentList @((Join-Path $PSScriptRoot 'source-acquisition-regression.mjs'),$root) -RedirectStandardOutput $out -RedirectStandardError $err -NoNewWindow -Wait -PassThru
 if($p.ExitCode -ne 0){throw ('NODE_SOURCE_ACQUISITION_REGRESSION_FAILED: '+$(if(Test-Path $err){Get-Content $err -Raw -Encoding UTF8}else{''}))}
 $r=Get-Content $out -Raw -Encoding UTF8|ConvertFrom-Json
 if($r.result -ne 'PASS'){throw 'NODE_SOURCE_ACQUISITION_RESULT_NOT_PASS'}

 # FULL_SAFE_IMPORT parity through the canonical #79 publication owner.
 Import-Module (Join-Path $PackageRoot 'core\OneCChatWorker.Core.psm1') -Force -DisableNameChecking
 $legacySource=Join-Path $root 'legacy-parity-source';New-Item -ItemType Directory -Force -Path $legacySource|Out-Null
 [IO.File]::WriteAllText((Join-Path $legacySource 'Configuration.xml'),'<Configuration name="LegacyParity"/>',[Text.UTF8Encoding]::new($false))
 [IO.File]::WriteAllText((Join-Path $legacySource 'a.txt'),'alpha',[Text.UTF8Encoding]::new($false))
 $legacyDir=Join-Path $legacySource 'Catalogs\Товары';New-Item -ItemType Directory -Force -Path $legacyDir|Out-Null
 [IO.File]::WriteAllText((Join-Path $legacyDir 'Object.xml'),'<Object/>',[Text.UTF8Encoding]::new($false))
 $legacyDigest=Get-TreeDigest $legacySource
 $legacyStageParent=Join-Path $root 'legacy-parity-stage';New-Item -ItemType Directory -Force -Path $legacyStageParent|Out-Null
 $legacyStage=Join-Path $legacyStageParent 'a.stage-12121212'
 $legacyNode=Invoke-SourceAcquisition -Source $legacySource -Stage $legacyStage -StageParent $legacyStageParent
 if([string]$legacyNode.digest.sha256 -ne [string]$legacyDigest.sha256 -or [int]$legacyNode.digest.files -ne [int]$legacyDigest.files -or [int64]$legacyNode.digest.bytes -ne [int64]$legacyDigest.bytes){throw ('FULL_SAFE_IMPORT_LEGACY_DIGEST_PARITY_MISMATCH node='+($legacyNode.digest|ConvertTo-Json -Compress)+' legacy='+($legacyDigest|ConvertTo-Json -Compress))}
 $null=Remove-ApplyStageTree -StagePath $legacyStage
 Remove-Item -LiteralPath ([string]$legacyNode.fingerprint_file.path) -Force -ErrorAction SilentlyContinue

 $worker=Join-Path $root 'worker-parity'
 $source=[string]$r.source_root
 New-Item -ItemType Directory -Force -Path $worker|Out-Null
 New-WorkerProject -ProjectId S821Parity -DisplayName 'S82.1 parity' -WorkerRoot $worker|Out-Null
 Add-WorkerParticipant -ProjectId S821Parity -ParticipantId erp -Platform ONEC -Role ERP -WorkerRoot $worker|Out-Null
 Set-WorkerMain -ProjectId S821Parity -ParticipantId erp -SourcePath $source -WorkerRoot $worker|Out-Null
 $applied=Apply-WorkerProject -ProjectId S821Parity -WorkerRoot $worker
 if($applied.status -ne 'READY' -or $applied.state -ne 'ACCEPTED'){throw ('FULL_SAFE_IMPORT_NOT_ACCEPTED: '+($applied|ConvertTo-Json -Compress))}
 $manifestPath=Get-ProjectManifestPath -ProjectId S821Parity -WorkerRoot $worker
 $manifest=Get-Content $manifestPath -Raw -Encoding UTF8|ConvertFrom-Json
 $main=$manifest.participants[0].target.main
 if([string]$main.tree_sha256 -ne [string]$r.tree_sha256){throw 'FULL_SAFE_IMPORT_TREE_IDENTITY_MISMATCH'}
 if([string]$main.configuration_xml_sha256 -ne [string]$r.configuration_xml_sha256){throw 'FULL_SAFE_IMPORT_CONFIGURATION_SHA_MISMATCH'}
 $fingerprint=Join-Path (Split-Path -Parent $manifestPath) ([string]$manifest.accepted_snapshot.artifacts[0].fingerprint_inventory_path).Replace('/','\')
 if(-not(Test-Path -LiteralPath $fingerprint -PathType Leaf)){throw 'FULL_SAFE_IMPORT_FINGERPRINT_MISSING'}
 if((Get-FileHash -LiteralPath $fingerprint -Algorithm SHA256).Hash.ToLowerInvariant() -ne [string]$manifest.accepted_snapshot.artifacts[0].fingerprint_inventory_sha256){throw 'FULL_SAFE_IMPORT_FINGERPRINT_SHA_MISMATCH'}
 $fast=Get-FastProjectState -ProjectId S821Parity -WorkerRoot $worker
 if($fast.state -ne 'ACCEPTED'){throw ('FULL_SAFE_IMPORT_FAST_STATE_REJECTED: '+($fast|ConvertTo-Json -Compress))}
 $metrics=$applied.changes[0].acquisition_metrics
 if([int]$metrics.max_source_path_chars -le 260 -or [int]$metrics.max_stage_path_chars -le 260){throw 'FULL_SAFE_IMPORT_LONGPATH_METRICS_MISSING'}
 if([int]$metrics.recursive_passes.source_content -ne 1 -or [int]$metrics.recursive_passes.stage_content_rehash -ne 0){throw 'FULL_SAFE_IMPORT_ONE_PASS_CONTRACT_MISMATCH'}

 # Deterministic source-drift fail-closed gate driven by the shallow progress receipt.
 $driftSource=Join-Path $root 'drift-source';New-Item -ItemType Directory -Force -Path $driftSource|Out-Null
 $driftConfig=Join-Path $driftSource 'Configuration.xml';[IO.File]::WriteAllText($driftConfig,'<Configuration name="Drift"/>',[Text.UTF8Encoding]::new($false))
 $big=Join-Path $driftSource 'big.bin';$fs=[IO.File]::Open($big,[IO.FileMode]::Create,[IO.FileAccess]::Write,[IO.FileShare]::Read);try{$fs.SetLength(268435456)}finally{$fs.Dispose()}
 $driftStageParent=Join-Path $root 'drift-stage';New-Item -ItemType Directory -Force -Path $driftStageParent|Out-Null
 $driftStage=Join-Path $driftStageParent 'a.stage-99999999';$driftReq=$driftStage+'.request.json';$driftProgress=$driftStage+'.progress.json';$driftFp=$driftStage+'.fingerprints.jsonl'
 $driftDoc=[ordered]@{verb='EXTERNAL_FULL_SAFE_IMPORT';source_root=$driftSource;stage_parent=$driftStageParent;stage_root=$driftStage;fingerprint_path=$driftFp;progress_path=$driftProgress;culture=[Globalization.CultureInfo]::CurrentCulture.Name;max_files=100;max_bytes=[int64]1073741824;timeout_ms=120000}
 Write-JsonAtomic $driftDoc $driftReq
 $driftOut=Join-Path $root 'drift-out.json';$driftErr=Join-Path $root 'drift-err.json';$oldReq=$env:ONEC_ACQ_REQUEST;$env:ONEC_ACQ_REQUEST=$driftReq
 try{$driftProc=Start-Process -FilePath $node.Source -ArgumentList @((Join-Path $PackageRoot 'runtime\source-acquisition.mjs')) -RedirectStandardOutput $driftOut -RedirectStandardError $driftErr -NoNewWindow -PassThru}finally{$env:ONEC_ACQ_REQUEST=$oldReq}
 $sawCopy=$false;$deadline=(Get-Date).AddSeconds(30)
 while(-not $driftProc.HasExited -and (Get-Date)-lt $deadline){if(Test-Path -LiteralPath $driftProgress -PathType Leaf){try{$pg=Get-Content $driftProgress -Raw -Encoding UTF8|ConvertFrom-Json;if($pg.phase -eq 'COPY_HASH'){$sawCopy=$true;break}}catch{}};Start-Sleep -Milliseconds 2}
 if(-not $sawCopy){$wasExited=$driftProc.HasExited;if(-not $wasExited){try{$driftProc.Kill()}catch{};$driftProc.WaitForExit()};$diagErr=$(if(Test-Path $driftErr){Get-Content $driftErr -Raw -Encoding UTF8}else{''});$diagOut=$(if(Test-Path $driftOut){Get-Content $driftOut -Raw -Encoding UTF8}else{''});$diagProgress=$(if(Test-Path $driftProgress){Get-Content $driftProgress -Raw -Encoding UTF8}else{''});throw ('SOURCE_DRIFT_COPY_PHASE_NOT_OBSERVED exited='+$wasExited+' exit='+$driftProc.ExitCode+' err='+$diagErr+' out='+$diagOut+' progress='+$diagProgress)}
 (Get-Item -LiteralPath $driftConfig).LastWriteTimeUtc=(Get-Date).ToUniversalTime().AddSeconds(5)
 $driftProc.WaitForExit();if($driftProc.ExitCode -eq 0){throw 'SOURCE_DRIFT_WAS_NOT_REJECTED'}
 $driftError=Get-Content $driftErr -Raw -Encoding UTF8|ConvertFrom-Json
 if($driftError.code -ne 'SOURCE_CHANGED_DURING_SYNC'){throw ('SOURCE_DRIFT_WRONG_CLASS: '+($driftError|ConvertTo-Json -Compress))}
 if(Test-Path -LiteralPath $driftStage){$null=Remove-ApplyStageTree -StagePath $driftStage}
 foreach($p in @($driftReq,$driftProgress,$driftProgress+'.tmp',$driftFp)){Remove-Item -LiteralPath $p -Force -ErrorAction SilentlyContinue}

 $reg=(Get-ItemProperty -LiteralPath 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' -Name LongPathsEnabled -ErrorAction Stop).LongPathsEnabled
 if($reg -ne 0){throw ('LONG_PATH_REGRESSION_EXPECTED_DISABLED_REGISTRY_ON_QUALIFICATION_HOST actual='+$reg)}
 $core=Get-Content (Join-Path $PackageRoot 'core\OneCChatWorker.Core.psm1') -Raw -Encoding UTF8
 $acq=$core.Substring($core.IndexOf('function Invoke-SourceAcquisition {'),$core.IndexOf('function Write-FingerprintInventory {')-$core.IndexOf('function Invoke-SourceAcquisition {'))
 if($acq -match '\[IO\.File\]::Open|Get-ChildItem\s+.+-Recurse|Get-FileHash'){throw 'PS51_CONTROL_PLANE_DEEP_FILE_IO_PRESENT'}
 if($acq -notmatch '\$psi\.UseShellExecute=\$false'){throw 'SOURCE_ACQUISITION_SHELL_FALSE_MISSING'}
 $launcher=Get-Content (Join-Path $PackageRoot 'OneCChatWorker.ps1') -Raw -Encoding UTF8
 $start=$launcher.Substring($launcher.IndexOf('function Run-Start {'),$launcher.IndexOf('function Run-Continue {')-$launcher.IndexOf('function Run-Start {'))
 $guided=$launcher.Substring($launcher.IndexOf('function Get-GuidedContext {'),$launcher.IndexOf('function Get-GuidedStateLabel {')-$launcher.IndexOf('function Get-GuidedContext {'))
 $fastState=$core.Substring($core.IndexOf('function Get-FastProjectState {'),$core.IndexOf('function Test-LegacyManifestShape {')-$core.IndexOf('function Get-FastProjectState {'))
 $status=$core.Substring($core.IndexOf('function Get-WorkerStatus {'),$core.IndexOf('function Get-WorkerDiagnostics {')-$core.IndexOf('function Get-WorkerStatus {'))
 $admission=$core.Substring($core.IndexOf('function New-Admission {'),$core.IndexOf('function Test-IsAdministrator {')-$core.IndexOf('function New-Admission {'))
 foreach($pair in @(@('START',$start),@('GUIDED',$guided),@('FAST_STATE',$fastState),@('STATUS',$status),@('ADMISSION',$admission))){if([string]$pair[1] -match 'Invoke-SourceAcquisition|source-acquisition'){throw ('WARM_PATH_ACQUISITION_CALL:'+ $pair[0])}}
 $helper=Get-Content (Join-Path $PackageRoot 'runtime\hosted-helper.mjs') -Raw -Encoding UTF8
 if($helper -match 'source-acquisition|Invoke-SourceAcquisition'){throw 'HOSTED_SOURCE_PATH_ACQUISITION_CALL'}
 $install=$core.Substring($core.IndexOf('function Install-OneCChatWorker {'),$core.IndexOf('function Start-WorkerAdmission {')-$core.IndexOf('function Install-OneCChatWorker {'))
 if($install -match 'Invoke-SourceAcquisition|Copy-ArtifactSafely|Apply-WorkerProject|Verify-WorkerProject|Get-TreeDigest'){throw 'INSTALL_MUST_NOT_MIGRATE_ACCEPTED_SNAPSHOTS'}
 if(([regex]::Matches($install,'source-acquisition\.mjs')).Count -ne 3){throw 'INSTALL_SOURCE_ACQUISITION_WIRING_NOT_EXACT'}
 Write-Host 'REFRESH_NOT_CALLED_BY_STATUS_OR_START PASS'
 Write-Host 'EXISTING_SNAPSHOT_NO_MIGRATION_STATIC PASS'
 $nodeMetrics=$r.PSObject.Properties['local_metrics'].Value
 Write-Host ('SOURCE_ACQUISITION_WINDOWS_PS51_PASS node_checks={0} long_paths_enabled={1} max_source={2} max_stage={3}' -f $r.checks,$reg,$nodeMetrics.max_source_path_chars,$nodeMetrics.max_stage_path_chars)
} finally {Remove-OneCTestScratch -Path $root -RunId $scratch.run_id -Base $scratch.base|Out-Null}
