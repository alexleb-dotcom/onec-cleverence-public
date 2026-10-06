param(
 [string]$PackageRoot=(Split-Path -Parent $PSScriptRoot),
 [string]$ReaderName='OneCSourceReader'
)
$ErrorActionPreference='Stop'
$PackageRoot=[IO.Path]::GetFullPath($PackageRoot)
$launcher=Join-Path $PackageRoot 'OneCChatWorker.ps1'
$core=Join-Path $PackageRoot 'core\OneCChatWorker.Core.psm1'
if(-not(Test-Path -LiteralPath $launcher -PathType Leaf)){throw 'GUIDED_PROGRESS_LAUNCHER_MISSING'}
if(-not(Test-Path -LiteralPath $core -PathType Leaf)){throw 'GUIDED_PROGRESS_CORE_MISSING'}

$root=Join-Path $env:TEMP ('OneCChatWorker-GuidedProgress-'+[guid]::NewGuid().ToString('N'))
$oldLocal=$env:LOCALAPPDATA
$oldUi=[Threading.Thread]::CurrentThread.CurrentUICulture
$results=New-Object Collections.Generic.List[object]

function Rec([string]$Name,[bool]$Pass,[string]$Detail=''){
 $results.Add([pscustomobject]@{name=$Name;outcome=$(if($Pass){'PASS'}else{'FAIL'});detail=$Detail})
 if(-not $Pass){throw "ASSERTION_FAILED: $Name :: $Detail"}
}
function Write-Utf8([string]$Path,[string]$Text){
 New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Path)|Out-Null
 [IO.File]::WriteAllText($Path,$Text,[Text.UTF8Encoding]::new($false))
}
function New-ProgressFixture([string]$Name,[int]$FileCount=900){
 $base=Join-Path $root $Name
 $worker=Join-Path $base 'worker'
 $pd=Join-Path $base 'programdata'
 $source=Join-Path $base 'source-main'
 New-Item -ItemType Directory -Force -Path $worker,$pd,$source|Out-Null
 Write-Utf8 (Join-Path $source 'Configuration.xml') ('<Configuration name="'+$Name+'" />')
 for($i=1;$i-le $FileCount;$i++){
  $bucket=Join-Path $source ('Catalogs\Bucket{0:D2}' -f ($i%12))
  Write-Utf8 (Join-Path $bucket ('Object{0:D4}.xml' -f $i)) ('<Object id="'+$i+'"/>')
 }
 New-WorkerProject -ProjectId $Name -DisplayName $Name -WorkerRoot $worker|Out-Null
 Add-WorkerParticipant -ProjectId $Name -ParticipantId erp -Platform ONEC -Role ERP -WorkerRoot $worker|Out-Null
 Set-WorkerMain -ProjectId $Name -ParticipantId erp -SourcePath $source -WorkerRoot $worker|Out-Null
 [pscustomobject]@{id=$Name;base=$base;worker=$worker;pd=$pd;source=$source}
}
function Assert-OrderedStages([string]$Name,[string]$Text,[string[]]$Labels){
 $last=-1
 for($i=0;$i-lt 5;$i++){
  $needle='[{0}/5] {1}' -f ($i+1),$Labels[$i]
  $idx=$Text.IndexOf($needle,[StringComparison]::Ordinal)
  if($idx -lt 0){Rec ($Name+'_stage_'+($i+1)) $false $needle}
  Rec ($Name+'_stage_'+($i+1)) ($idx -gt $last) $needle
  $last=$idx
 }
}
function Assert-Heartbeat([string]$Name,[string]$Text,[string]$Template){
 $prefix=$Template.Replace('{0}','')
 $m=[regex]::Match($Text,[regex]::Escape($prefix)+'\d{2}:\d{2}(?::\d{2})?')
 Rec $Name $m.Success $Text
}
function Invoke-ProgressFixture($Fixture,[string]$CultureName){
 $script:WorkerRoot=$Fixture.worker
 $script:ProgramDataRoot=$Fixture.pd
 $script:ProjectId=$Fixture.id
 $script:GuidedProjectId=$Fixture.id
 $script:ReaderName=$ReaderName
 $script:OperatorIdentity=[Security.Principal.WindowsIdentity]::GetCurrent().Name
 $script:InGuidedMenu=$true
 $script:InAdvancedMenu=$false
 $script:GuidedProgressHeartbeatSeconds=0.5
 $script:GuidedProgressPollMilliseconds=25
 [Threading.Thread]::CurrentThread.CurrentUICulture=New-Object Globalization.CultureInfo($CultureName)
 $script:GuidedProgressFixtureOk=$null
 $captured=(& {
  $script:GuidedProgressFixtureOk=Complete-GuidedProject -ProjectKey $Fixture.id
 } 6>&1 | Out-String)
 if(-not $script:GuidedProgressFixtureOk){
  $op=$null
  try{$op=Get-CurrentWorkerOperation -ProgramDataRoot $Fixture.pd}catch{}
  throw ("GUIDED_PROGRESS_COMPLETE_RETURNED_FALSE: transcript={0} operation={1}" -f $captured,$($op|ConvertTo-Json -Depth 8 -Compress))
 }
 [pscustomobject]@{text=$captured;culture=$CultureName}
}

try{
 New-Item -ItemType Directory -Force -Path $root|Out-Null
 $env:LOCALAPPDATA=Join-Path $root 'profile'
 New-Item -ItemType Directory -Force -Path $env:LOCALAPPDATA|Out-Null

 # Load the real launcher functions once without entering MENU.
 $bootstrapWorker=Join-Path $root 'bootstrap-worker'
 $bootstrapPd=Join-Path $root 'bootstrap-programdata'
 New-Item -ItemType Directory -Force -Path $bootstrapWorker,$bootstrapPd|Out-Null
 Write-Utf8 (Join-Path $bootstrapWorker 'projects.json') '{"schema_version":1,"projects":[]}'
 . $launcher -Mode LIST -WorkerRoot $bootstrapWorker -ProgramDataRoot $bootstrapPd -ReaderName $ReaderName 6>$null

 $ruFixture=New-ProgressFixture 'progress-ru'
 $ru=Invoke-ProgressFixture $ruFixture 'ru-RU'
 $ruLabels=@(
  (T 'Checking project structure and current state...'),
  (T 'Building the managed project copy...'),
  (T 'Confirming the managed copy result...'),
  (T 'Checking accepted snapshot state...'),
  (T 'Done.')
 )
 Assert-OrderedStages 'ru_order' $ru.text $ruLabels
 Rec 'ru_stage_labels_are_localized' (($ruLabels|Where-Object{$_ -in @('Checking project structure and current state...','Building the managed project copy...','Confirming the managed copy result...','Checking accepted snapshot state...','Done.')}).Count -eq 0) ($ruLabels -join ' | ')
 Assert-Heartbeat 'ru_liveness_heartbeat' $ru.text (T 'Work continues... elapsed {0}')
 Rec 'ru_large_config_hint_localized' ($ru.text.Contains((T 'This may take some time for large configurations.')) -and -not $ru.text.Contains('This may take some time for large configurations.')) ''
 Rec 'ru_progress_has_no_fake_percent' ($ru.text -notmatch '\b\d{1,3}%\b') ''
 Rec 'ru_progress_hides_technical_lifecycle_spam' ($ru.text -notmatch 'Inspecting catalog/manifest|Applying catalog:|Post-apply verification|Hashing canonical artifacts|Verification result =|APPLY result|VERIFY:') $ru.text
 Rec 'ru_project_ready_after_progress' ((Get-FastProjectState -ProjectId $ruFixture.id -WorkerRoot $ruFixture.worker).state -eq 'ACCEPTED') ''
 $ruHistory=@(Get-Content (Join-Path $ruFixture.pd 'operations\history.jsonl') -Encoding UTF8|ForEach-Object{$_|ConvertFrom-Json})
 $ruApply=@($ruHistory|Where-Object operation_type -eq 'APPLY')[-1]
 $ruVerify=@($ruHistory|Where-Object operation_type -eq 'VERIFY')
 Rec 'durable_apply_semantics_unchanged' ($ruApply.total_steps -eq 3 -and $ruApply.state -eq 'PASS') ($ruApply|ConvertTo-Json -Compress)
 Rec 'guided_does_not_run_deep_verify' ($ruVerify.Count -eq 0) ($ruVerify|ConvertTo-Json -Compress)

 $enFixture=New-ProgressFixture 'progress-en'
 $en=Invoke-ProgressFixture $enFixture 'de-DE'
 $enLabels=@(
  'Checking project structure and current state...',
  'Building the managed project copy...',
  'Confirming the managed copy result...',
  'Checking accepted snapshot state...',
  'Done.'
 )
 Assert-OrderedStages 'en_order' $en.text $enLabels
 Assert-Heartbeat 'en_liveness_heartbeat' $en.text 'Work continues... elapsed {0}'
 Rec 'english_fallback_large_config_hint' ($en.text.Contains('This may take some time for large configurations.')) ''
 Rec 'english_fallback_does_not_use_ru_stage1' (-not $en.text.Contains($ruLabels[0])) ''
 Rec 'en_progress_has_no_fake_percent' ($en.text -notmatch '\b\d{1,3}%\b') ''
 Rec 'en_progress_hides_technical_lifecycle_spam' ($en.text -notmatch 'Inspecting catalog/manifest|Applying catalog:|Post-apply verification|Hashing canonical artifacts|Verification result =|APPLY result|VERIFY:') $en.text
 Rec 'en_project_ready_after_progress' ((Get-FastProjectState -ProjectId $enFixture.id -WorkerRoot $enFixture.worker).state -eq 'ACCEPTED') ''

 $launcherText=Get-Content -LiteralPath $launcher -Raw -Encoding UTF8
 $progressStart=$launcherText.IndexOf('function Start-GuidedLifecycleProcess')
 $progressEnd=$launcherText.IndexOf('function Complete-GuidedProject')
 $progressBlock=$launcherText.Substring($progressStart,$progressEnd-$progressStart)
 Rec 'progress_polls_receipt_not_source_tree' ($progressBlock -match 'Get-CurrentWorkerOperation' -and $progressBlock -notmatch 'Get-TreeDigest|Get-ChildItem.+-Recurse|Measure-Object.+Length') 'presentation may poll only durable operation receipt/process state'
 Rec 'progress_reuses_cli_apply_then_fast_state' ($progressBlock -match "ValidateSet\('APPLY','VERIFY'\)" -and $progressBlock -match '-Mode ' -and $progressBlock -match '-ProjectId ' -and $progressBlock -match 'Get-FastProjectState' -and $progressBlock -notmatch 'Verify-WorkerProject') ''
 Rec 'progress_failure_uses_guided_failure_boundary' ($launcherText -match 'Invoke-GuidedAction -ShowOutput \{Invoke-GuidedManagedProjectProgress' -and $launcherText -match 'Show-GuidedFailure') ''
 Rec 'accepted_apply_failure_contract_retained' ($launcherText -match 'FAIL: \{0\}' -and $launcherText -match 'Reason: \{0\}' -and $launcherText -match 'Stage: \{0\}' -and $launcherText -match 'Cleanup: \{0\}' -and $launcherText -match 'Details: operation \{0\}; Advanced > Diagnostics') ''

 Write-Output ("GUIDED_PROGRESS_REGRESSION_PASS checks={0} evidence_root={1}" -f $results.Count,$root)
} finally {
 [Threading.Thread]::CurrentThread.CurrentUICulture=$oldUi
 $env:LOCALAPPDATA=$oldLocal
 Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
}
