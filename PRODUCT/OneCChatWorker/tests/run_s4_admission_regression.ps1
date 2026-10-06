$ErrorActionPreference='Stop'
if($PSVersionTable.PSVersion.Major -ne 5){throw "WINDOWS_PS51_REQUIRED: $($PSVersionTable.PSVersion)"}
$tests=$PSScriptRoot
$package=Split-Path -Parent $tests
Import-Module (Join-Path $tests 'TestScratch.psm1') -Force -DisableNameChecking
Import-Module (Join-Path $package 'core\OneCChatWorker.Core.psm1') -Force -DisableNameChecking
$s=New-OneCTestScratch -Purpose 'S4Admission'
$worker=Join-Path $s.path 'worker'
$pd=Join-Path $s.path 'pd'
$project='S4Fixture'
$manifestDir=Join-Path $worker ($project+'\ProjectManifest')
$manifest=Join-Path $manifestDir 'project.json'
$artifact=Join-Path $worker ($project+'\Participants\ut\Target\Main')
$results=New-Object Collections.Generic.List[object]
function A([string]$n,[bool]$ok,$d=''){if(-not $ok){throw "ASSERTION_FAILED: $n :: $d"};$results.Add([pscustomobject]@{name=$n;pass=$true})}
try{
 New-Item -ItemType Directory -Force -Path $manifestDir,$artifact,(Join-Path $pd 'runtime')|Out-Null
 [IO.File]::WriteAllText((Join-Path $artifact 'Configuration.xml'),'<Configuration/>',[Text.UTF8Encoding]::new($false))
 New-Item -ItemType File -Force -Path (Join-Path $pd 'runtime\rg.exe')|Out-Null
 $doc=[ordered]@{
  schema_version=2;project_id=$project;project_root=(Join-Path $worker $project);
  participants=@([ordered]@{participant_id='ut';platform='ONEC';role='UT';active=$true;target=[ordered]@{main=[ordered]@{active=$true;canonical_path='Participants/ut/Target/Main'};extensions=@()};reference=$null});
  accepted_snapshot=[ordered]@{snapshot_contract='ACCEPTED_SNAPSHOT_V1';source_snapshot_id=('f'*64);publication_generation=1}
 }
 [IO.File]::WriteAllText($manifest,($doc|ConvertTo-Json -Depth 12),[Text.UTF8Encoding]::new($false))
 $mh=(Get-FileHash -Algorithm SHA256 $manifest).Hash.ToLowerInvariant()
 $accepted=[pscustomobject]@{project_id=$project;state='ACCEPTED';manifest_sha256=$mh;source_snapshot_id=('f'*64)}
 $a=New-Admission -ProjectId $project -TaskId 'task-s4' -TaskGoal 'bounded S4 fixture' -WorkerRoot $worker -ProgramDataRoot $pd -RelayUrl 'wss://example.invalid/helper' -AcceptedState $accepted -TaskRequestLimit 96 -TaskResultByteLimit 108000 -TaskTtlMinutes 120 -EpochSoftRequestLimit 32 -EpochSoftResultByteLimit 36000
 A 'schema_v3' ($a.schema_version -eq 3)
 A 'accounting_contract' ($a.accounting_contract -eq 'S4_DURABLE_TASK_ACCOUNTING_V1')
 A 'opaque_task_admission_id' ([string]$a.task_admission_id -match '^[a-f0-9]{32}$')
 A 'stable_session_id_opaque' ([string]$a.session_id -match '^[a-f0-9]{32}$')
 A 'ids_distinct' ($a.task_admission_id -ne $a.session_id)
 A 'snapshot_bound' ($a.source_snapshot_id -eq ('f'*64) -and $a.manifest_sha256 -eq $mh)
 A 'output_task_bound' ($a.output_task_root -eq 'Output/task-s4')
 A 'task_goal_bound' ($a.task_goal_sha256 -eq (Get-Sha256Text 'bounded S4 fixture'))
 A 'task_expiry_fixed' ([datetime]::Parse($a.task_expires_utc).ToUniversalTime() -gt [datetime]::Parse($a.task_created_utc).ToUniversalTime())
 A 'durable_caps' ($a.caps.task_request_limit -eq 96 -and $a.caps.task_result_byte_limit -eq 108000)
 A 'epoch_soft_caps' ($a.caps.epoch_soft_request_limit -eq 32 -and $a.caps.epoch_soft_result_byte_limit -eq 36000 -and $a.caps.max_result_bytes -eq 3000)
 $saved=Get-Content (Join-Path $pd 'runtime\active-admission.json') -Raw -Encoding UTF8|ConvertFrom-Json
 A 'saved_exact_identity' ($saved.task_admission_id -eq $a.task_admission_id -and $saved.session_id -eq $a.session_id)
 $blocked=$false
 try{New-Admission -ProjectId $project -TaskId 'pending-default' -WorkerRoot $worker -ProgramDataRoot $pd -AcceptedState $accepted|Out-Null}catch{$blocked=$_.Exception.Message -eq 'S4_CAP_QUALIFICATION_REQUIRED'}
 A 'unqualified_default_fails_closed' $blocked
 $core=Get-Content (Join-Path $package 'core\OneCChatWorker.Core.psm1') -Raw -Encoding UTF8
 $block=$core.Substring($core.IndexOf('function New-Admission {'),$core.IndexOf('function Test-IsAdministrator {')-$core.IndexOf('function New-Admission {'))
 A 'no_deep_verify_in_admission' (-not($block.Contains('Verify-WorkerProject')) -and -not($block.Contains('Get-TreeDigest')))
 Write-Host ("S4_ADMISSION_PS51_REGRESSION_PASS checks={0}" -f $results.Count)
}finally{
 Remove-OneCTestScratch -Path $s.path -RunId $s.run_id -Base $s.base|Out-Null
}
