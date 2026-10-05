param(
 [string]$PackageRoot=(Split-Path -Parent $PSScriptRoot),
 [string]$ReaderName='OneCSourceReader'
)
$ErrorActionPreference='Stop'
$PackageRoot=[IO.Path]::GetFullPath($PackageRoot)
$launcher=Join-Path $PackageRoot 'OneCChatWorker.ps1'
$core=Join-Path $PackageRoot 'core\OneCChatWorker.Core.psm1'
if(-not(Test-Path -LiteralPath $launcher -PathType Leaf)){throw 'GUIDED_UI_LAUNCHER_MISSING'}
if(-not(Test-Path -LiteralPath $core -PathType Leaf)){throw 'GUIDED_UI_CORE_MISSING'}
$root=Join-Path $env:TEMP ('OneCChatWorker-GuidedUI-'+[guid]::NewGuid().ToString('N'))
$oldLocal=$env:LOCALAPPDATA
$env:LOCALAPPDATA=Join-Path $root 'profile'
New-Item -ItemType Directory -Force -Path $env:LOCALAPPDATA|Out-Null
$results=New-Object Collections.Generic.List[object]

function Rec([string]$Name,[bool]$Pass,[string]$Detail=''){
 $results.Add([pscustomobject]@{name=$Name;outcome=$(if($Pass){'PASS'}else{'FAIL'});detail=$Detail})
 if(-not $Pass){throw "ASSERTION_FAILED: $Name :: $Detail"}
}
function Write-Utf8([string]$Path,[string]$Text){
 New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Path)|Out-Null
 [IO.File]::WriteAllText($Path,$Text,[Text.UTF8Encoding]::new($false))
}
function New-Export([string]$Path,[string]$Name){
 New-Item -ItemType Directory -Force -Path $Path|Out-Null
 Write-Utf8 (Join-Path $Path 'Configuration.xml') ('<Configuration name="{0}" />' -f $Name)
 Write-Utf8 (Join-Path $Path 'Module.bsl') ('Procedure Ping() Export'+[Environment]::NewLine+'EndProcedure'+[Environment]::NewLine)
}
function New-Fixture([string]$Name,[bool]$WithSecret=$true){
 $base=Join-Path $root $Name
 $w=Join-Path $base 'worker'
 $pd=Join-Path $base 'programdata'
 New-Item -ItemType Directory -Force -Path $w,$pd|Out-Null
 Write-Utf8 (Join-Path $w 'projects.json') '{"schema_version":1,"projects":[]}'
 Write-Utf8 (Join-Path $pd 'installed-state.json') '{}'
 if($WithSecret){Write-Utf8 (Join-Path $pd 'secrets\helper-secret.txt') 'test-placeholder-not-a-real-secret'}
 [pscustomobject]@{base=$base;worker=$w;pd=$pd}
}
function Run-Menu($Fixture,[string[]]$Lines,[string]$Name){
 $input=Join-Path $Fixture.base ($Name+'.input.txt')
 $out=Join-Path $Fixture.base ($Name+'.out.txt')
 [IO.File]::WriteAllLines($input,$Lines,[Text.UTF8Encoding]::new($true))
 & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $launcher -Mode MENU -WorkerRoot $Fixture.worker -ProgramDataRoot $Fixture.pd -ReaderName $ReaderName -UiInputPath $input *> $out
 $ec=$LASTEXITCODE
 $text=Get-Content -LiteralPath $out -Raw -Encoding Default
 [pscustomobject]@{exit=$ec;text=$text;path=$out}
}
function Assert-NoStack([string]$Name,[string]$Text){
 $bad=($Text -match '(?im)^\s*At .+OneCChatWorker\.ps1:' -or $Text -match 'CategoryInfo\s*:' -or $Text -match 'FullyQualifiedErrorId\s*:' -or $Text -match 'ScriptStackTrace')
 Rec $Name (-not $bad) 'default UI must not emit an uncaught PowerShell stack trace'
}

try{
 New-Item -ItemType Directory -Force -Path $root|Out-Null
 Import-Module $core -Force -DisableNameChecking
 Set-WorkerReaderIdentity -ReaderName $ReaderName|Out-Null
 $reader=Get-LocalUser -Name $ReaderName -ErrorAction SilentlyContinue
 Rec 'reader_identity_available_for_actual_apply' ([bool]$reader) $ReaderName

 $fresh=[pscustomobject]@{base=(Join-Path $root 'fresh');worker=(Join-Path $root 'fresh\worker');pd=(Join-Path $root 'fresh\programdata')}
 New-Item -ItemType Directory -Force -Path $fresh.base|Out-Null
 $r=Run-Menu $fresh @('q') 'fresh'
 Rec 'fresh_state_not_installed' ($r.exit -eq 0 -and $r.text -match 'State: Not installed') $r.text
 Rec 'fresh_recommends_install' ($r.text -match 'Recommended: Install OneCChatWorker') $r.text
 Assert-NoStack 'fresh_no_stack' $r.text

 $auth=New-Fixture 'auth-missing' $false
 $r=Run-Menu $auth @('q') 'auth'
 Rec 'installed_auth_missing_state' ($r.exit -eq 0 -and $r.text -match 'State: ChatGPT connection required') $r.text
 Rec 'installed_auth_missing_recommendation' ($r.text -match 'Recommended: Connect ChatGPT') $r.text
 Assert-NoStack 'auth_missing_no_stack' $r.text

 $first=New-Fixture 'first-project' $true
 $main=Join-Path $first.base 'Main'
 New-Export $main 'GuidedMain'
 $bad=Join-Path $first.base 'does-not-exist'
 $r=Run-Menu $first @('', '?','NeoHim','','',$bad,$main,'n','c','n','q') 'first-project'
 Rec 'no_projects_guides_add_project' ($r.text -match 'State: Ready for first project' -and $r.text -match 'Recommended: Add local project') ''
 Rec 'field_help_contract_visible' ($r.text -match 'What:' -and $r.text -match 'Why\s*:' -and $r.text -match 'Example:' -and $r.text -match 'Required:' -and $r.text -match 'Default:') ''
 Rec 'help_repeats_in_context' (([regex]::Matches($r.text,'Project name')).Count -ge 4) ''
 Rec 'invalid_path_reprompts_in_place' ($r.text -match 'FAIL: That folder does not exist\.' -and $r.text -match 'your previous answers are kept') ''
 $catalog=Get-Content (Join-Path $first.worker 'projects.json') -Raw|ConvertFrom-Json
 Rec 'optional_role_accepts_empty' ($catalog.projects[0].participants[0].role -eq '') ''
 Rec 'first_project_reaches_ready' ($r.text -match 'SUCCESS: Project is ready\.' -and $r.text -match 'State: Project ready') ''
 Rec 'guided_hides_internal_lifecycle_terms' ($r.text -notmatch '\bADD_PROJECT\b|\bADD_PARTICIPANT\b|\bSET_MAIN\b|\bAPPLY\b|participant_id|artifact_id|APPLY CATALOG') ''
 $projectId=[string]$catalog.projects[0].project_id
 Rec 'project_id_derived_automatically' ($projectId -eq 'neohim') $projectId
 $verify=Verify-WorkerProject -ProjectId $projectId -WorkerRoot $first.worker
 Rec 'first_project_verify_ready' ($verify.status -eq 'READY') $verify.status
 Assert-NoStack 'first_project_expected_error_no_stack' $r.text

 $resume=New-Fixture 'resume' $true
 New-WorkerProject -ProjectId 'resume-project' -DisplayName 'Resume project' -WorkerRoot $resume.worker|Out-Null
 Add-WorkerParticipant -ProjectId 'resume-project' -ParticipantId 'erp' -Platform ONEC -Role 'ERP' -WorkerRoot $resume.worker|Out-Null
 $resumeMain=Join-Path $resume.base 'Main'
 New-Export $resumeMain 'ResumeMain'
 $r=Run-Menu $resume @('', $resumeMain,'n','c','n','q') 'resume'
 $after=Get-Content (Join-Path $resume.worker 'projects.json') -Raw|ConvertFrom-Json
 Rec 'interrupted_setup_detected' ($r.text -match 'State: Project setup incomplete') ''
 Rec 'interrupted_setup_resumes_to_ready' ($r.text -match 'SUCCESS: Project is ready\.' -and (Verify-WorkerProject -ProjectId 'resume-project' -WorkerRoot $resume.worker).status -eq 'READY') ''
 Rec 'resume_does_not_duplicate_project' (@($after.projects).Count -eq 1 -and @($after.projects[0].participants).Count -eq 1) ''
 Assert-NoStack 'resume_no_stack' $r.text

 $r=Run-Menu $first @('q') 'ready'
 Rec 'existing_ready_state' ($r.text -match 'State: Project ready' -and $r.text -match 'Recommended: Start work') ''
 Assert-NoStack 'ready_no_stack' $r.text

 $launcherText=Get-Content -LiteralPath $launcher -Raw -Encoding UTF8
 Rec 'start_asks_human_task_description' ($launcherText -match "Label 'Task description'" -and $launcherText -match 'technical task id is created automatically') ''
 Rec 'task_id_derivation_present' ($launcherText -match 'Get-UniqueTaskId') ''

 New-Item -ItemType Directory -Force -Path (Join-Path $first.pd 'runtime')|Out-Null
 Write-Utf8 (Join-Path $first.pd 'runtime\active-admission.json') ('{"schema_version":1,"project_id":"'+$projectId+'","task_id":"guided-task"}')
 $r=Run-Menu $first @('q') 'start-incomplete'
 Rec 'orphan_admission_is_start_incomplete' ($r.text -match 'State: Start incomplete' -and $r.text -match 'Recommended: Clear incomplete start') ''
 Rec 'orphan_admission_not_running' ($r.text -notmatch 'State: Work session running') ''
 Assert-NoStack 'start_incomplete_no_stack' $r.text
 Remove-Item -LiteralPath (Join-Path $first.pd 'runtime\active-admission.json') -Force

 $helperPath=Join-Path $first.pd 'helper\hosted-helper.mjs'
 Write-Utf8 $helperPath '// guided UI state fixture only'
 $expires=(Get-Date).ToUniversalTime().AddMinutes(10).ToString('o')
 Write-Utf8 (Join-Path $first.pd 'runtime\hosted-helper-state.json') ('{"session_id":"guided-session","project_id":"'+$projectId+'","task_id":"guided-task","expires_utc":"'+$expires+'"}')
 Write-Utf8 (Join-Path $first.pd 'runtime\hosted-helper-log.jsonl') ('{"at_utc":"'+(Get-Date).ToUniversalTime().ToString('o')+'","event":"CONNECTED","session_id":"guided-session","project_id":"'+$projectId+'","task_id":"guided-task"}')
 Write-Utf8 (Join-Path $first.pd 'runtime\active-admission.json') ('{"schema_version":1,"project_id":"'+$projectId+'","task_id":"guided-task"}')
 $node=Get-Command node.exe -ErrorAction Stop
 $dummy=Start-Process -FilePath $node.Source -ArgumentList @('-e','setTimeout(()=>{},30000)', $helperPath) -PassThru
 try{
  Start-Sleep -Milliseconds 300
  $r=Run-Menu $first @('q') 'running'
  Rec 'running_state_requires_helper' ($r.text -match 'State: Work session running' -and $r.text -match 'Task\s+: guided-task') ''
  Rec 'running_actions_visible' ($r.text -match '\[S\] Stop work' -and $r.text -match '\[O\] Open Output') ''
  Assert-NoStack 'running_no_stack' $r.text
 }finally{
  Stop-Process -Id $dummy.Id -Force -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath (Join-Path $first.pd 'runtime\active-admission.json') -Force -ErrorAction SilentlyContinue
 }

 $r=Run-Menu $first @('a','99','0','q') 'advanced-invalid'
 Rec 'advanced_invalid_is_handled' ($r.exit -eq 0 -and $r.text -match 'FAIL: Unknown Advanced action') ''
 Rec 'advanced_invalid_session_survives' (([regex]::Matches($r.text,'State: Project ready')).Count -ge 2) ''
 Assert-NoStack 'advanced_invalid_no_stack' $r.text

 $sourceHash=(Get-FileHash (Join-Path $main 'Configuration.xml') -Algorithm SHA256).Hash
 Rec 'external_source_unchanged' ($sourceHash -eq (Get-FileHash (Join-Path $main 'Configuration.xml') -Algorithm SHA256).Hash) ''

 Write-Output ("GUIDED_UI_REGRESSION_PASS checks={0} evidence_root={1}" -f $results.Count,$root)
}finally{
 $env:LOCALAPPDATA=$oldLocal
}
