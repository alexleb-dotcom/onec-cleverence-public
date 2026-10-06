$ErrorActionPreference='Stop'
if($PSVersionTable.PSVersion.Major -ne 5){throw "WINDOWS_PS51_REQUIRED: $($PSVersionTable.PSVersion)"}
$module=Join-Path $PSScriptRoot 'TestScratch.psm1'
Import-Module $module -Force -DisableNameChecking

$results=New-Object Collections.Generic.List[object]
$created=New-Object Collections.Generic.List[object]
$foreign=@()
function Rec([string]$Name,[bool]$Ok,$Detail=''){
    $results.Add([pscustomobject]@{name=$Name;pass=$Ok;detail=$Detail})
    if(-not $Ok){throw "ASSERTION_FAILED: $Name :: $Detail"}
}
function Hash-OrNull([string]$Path){if(Test-Path -LiteralPath $Path -PathType Leaf){(Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()}else{$null}}
function Dir-Names([string]$Path,[string]$Prefix){
    if(-not(Test-Path -LiteralPath $Path -PathType Container)){return @()}
    @((Get-ChildItem -LiteralPath $Path -Directory -Force -ErrorAction Stop|Where-Object{$_.Name.StartsWith($Prefix,[StringComparison]::OrdinalIgnoreCase)}|Select-Object -ExpandProperty FullName|Sort-Object))
}
function New-Tracked([string]$Purpose){
    $s=New-OneCTestScratch -Purpose $Purpose
    $created.Add($s)
    $s
}
function Cleanup-Tracked($Scratch){
    if($null -ne $Scratch -and (Test-Path -LiteralPath $Scratch.path)){
        Remove-OneCTestScratch -Path $Scratch.path -RunId $Scratch.run_id -Base $Scratch.base|Out-Null
    }
}

$prodWorker='C:\OneCChatWorker'
$prodPd='C:\ProgramData\OneCChatWorker'
$helper=Join-Path $prodPd 'helper\hosted-helper.mjs'
$admission=Join-Path $prodPd 'runtime\active-admission.json'
$projects=Join-Path $prodWorker 'projects.json'
$installedState=Join-Path $prodPd 'installed-state.json'
$before=[ordered]@{
    bare_c=Dir-Names 'C:\' 'OneCChatWorker-'
    programdata=Dir-Names 'C:\ProgramData' 'OneCChatWorker-'
    helper_sha=Hash-OrNull $helper
    admission_sha=Hash-OrNull $admission
    projects_sha=Hash-OrNull $projects
    installed_state_sha=Hash-OrNull $installedState
    helper_pid=$null
    helper_start=$null
}
if(Test-Path -LiteralPath $helper -PathType Leaf){
    $hp=@(Get-CimInstance Win32_Process|Where-Object{$_.Name-eq'node.exe' -and $_.CommandLine -and $_.CommandLine.Contains($helper)}|Select-Object -First 1)
    if($hp){
        $before.helper_pid=[int]$hp.ProcessId
        try{$before.helper_start=(Get-Process -Id $hp.ProcessId).StartTime.ToUniversalTime().ToString('o')}catch{$before.helper_start=$null}
    }
}

try{
    $base=Get-OneCTestScratchBase
    Rec 'canonical_base_user_local' ($base.StartsWith(([IO.Path]::GetFullPath($env:LOCALAPPDATA).TrimEnd('\')+'\'),[StringComparison]::OrdinalIgnoreCase)) $base
    Rec 'task_checkpoints_outside_scratch_owner' ((Get-OneCTestScratchClassification -Path (Join-Path $env:LOCALAPPDATA 'OneCArchitecture\TaskCheckpoints')).classification -eq 'OUTSIDE_OWNER_ROOT') $base

    $a=New-Tracked 'Unique'
    $b=New-Tracked 'Unique'
    Rec 'unique_per_run_dirs' ($a.path -ne $b.path -and $a.run_id -ne $b.run_id) @($a.path,$b.path)
    Rec 'owned_marker_classifies_active' ((Get-OneCTestScratchClassification -Path $a.path).classification -eq 'ACTIVE') $a.path
    Cleanup-Tracked $a
    Cleanup-Tracked $b
    Rec 'pass_cleanup_leaves_no_created_scratch' (-not(Test-Path -LiteralPath $a.path) -and -not(Test-Path -LiteralPath $b.path)) ''

    $fail=New-Tracked 'InjectedFail'
    $caught=$false
    try{throw 'INJECTED_TEST_FAILURE'}catch{if($_.Exception.Message -eq 'INJECTED_TEST_FAILURE'){$caught=$true}else{throw}}finally{Cleanup-Tracked $fail}
    Rec 'injected_fail_cleanup' ($caught -and -not(Test-Path -LiteralPath $fail.path)) $fail.path

    $stale=New-Tracked 'Interrupted'
    $m=Get-Content -LiteralPath $stale.marker -Raw -Encoding UTF8|ConvertFrom-Json
    $m.creator_pid=2147483646
    $m.creator_process_start_utc='2000-01-01T00:00:00.0000000Z'
    $m.expires_utc=(Get-Date).ToUniversalTime().AddHours(-1).ToString('o')
    [IO.File]::WriteAllText($stale.marker,($m|ConvertTo-Json -Depth 5),[Text.UTF8Encoding]::new($false))
    Rec 'interrupted_stale_classified' ((Get-OneCTestScratchClassification -Path $stale.path).classification -eq 'OWNED_STALE') $stale.path
    $staleSweep=@(Clear-StaleOneCTestScratch)
    Rec 'interrupted_stale_ttl_cleaned' (-not(Test-Path -LiteralPath $stale.path) -and @($staleSweep|Where-Object{$_.path-eq$stale.path -and $_.action-eq'REMOVED'}).Count -eq 1) $staleSweep

    $active=New-Tracked 'Active'
    $am=Get-Content -LiteralPath $active.marker -Raw -Encoding UTF8|ConvertFrom-Json
    $am.expires_utc=(Get-Date).ToUniversalTime().AddHours(-1).ToString('o')
    [IO.File]::WriteAllText($active.marker,($am|ConvertTo-Json -Depth 5),[Text.UTF8Encoding]::new($false))
    $activeSweep=@(Clear-StaleOneCTestScratch)
    Rec 'active_scratch_not_ttl_deleted' ((Test-Path -LiteralPath $active.path) -and @($activeSweep|Where-Object{$_.path-eq$active.path -and $_.action-eq'KEPT'}).Count -eq 1) $activeSweep
    Cleanup-Tracked $active

    New-Item -ItemType Directory -Force -Path $base|Out-Null
    $foreignPath=Join-Path $base ('OneCChatWorker-Foreign-'+[guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $foreignPath|Out-Null
    $foreign+=$foreignPath
    $invalidPath=Join-Path $base ('OneCChatWorker-InvalidMarker-'+[guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $invalidPath|Out-Null
    [IO.File]::WriteAllText((Join-Path $invalidPath '.onec-test-scratch.json'),'{"owner":"not-ours"}',[Text.UTF8Encoding]::new($false))
    $foreign+=$invalidPath
    $foreignSweep=@(Clear-StaleOneCTestScratch -NowUtc (Get-Date).ToUniversalTime().AddDays(30))
    Rec 'similar_foreign_directory_not_deleted' ((Test-Path -LiteralPath $foreignPath) -and @($foreignSweep|Where-Object{$_.path-eq$foreignPath -and $_.classification-eq'MARKER_MISSING' -and $_.action-eq'KEPT'}).Count -eq 1) $foreignSweep
    Rec 'invalid_marker_directory_not_deleted' ((Test-Path -LiteralPath $invalidPath) -and @($foreignSweep|Where-Object{$_.path-eq$invalidPath -and $_.classification-eq'MARKER_INVALID' -and $_.action-eq'KEPT'}).Count -eq 1) $foreignSweep

    $outsideWorkerRejected=$false
    try{Remove-OneCTestScratch -Path $prodWorker|Out-Null}catch{$outsideWorkerRejected=$_.Exception.Message -like 'SCRATCH_PATH_OUTSIDE_OWNER_ROOT:*'}
    Rec 'production_worker_delete_rejected' $outsideWorkerRejected $prodWorker
    $outsidePdRejected=$false
    try{Remove-OneCTestScratch -Path $prodPd|Out-Null}catch{$outsidePdRejected=$_.Exception.Message -like 'SCRATCH_PATH_OUTSIDE_OWNER_ROOT:*'}
    Rec 'production_programdata_delete_rejected' $outsidePdRejected $prodPd

    foreach($p in $foreign){if(Test-Path -LiteralPath $p){Remove-Item -LiteralPath $p -Recurse -Force -ErrorAction Stop}}
    $foreign=@()

    $afterBare=Dir-Names 'C:\' 'OneCChatWorker-'
    $afterPd=Dir-Names 'C:\ProgramData' 'OneCChatWorker-'
    Rec 'no_new_bare_c_test_roots' (($before.bare_c -join '|') -eq ($afterBare -join '|')) @{before=$before.bare_c;after=$afterBare}
    Rec 'no_new_persistent_programdata_test_roots' (($before.programdata -join '|') -eq ($afterPd -join '|')) @{before=$before.programdata;after=$afterPd}
    Rec 'production_projects_untouched' ($before.projects_sha -eq (Hash-OrNull $projects)) $projects
    Rec 'production_installed_state_untouched' ($before.installed_state_sha -eq (Hash-OrNull $installedState)) $installedState
    Rec 'production_helper_file_untouched' ($before.helper_sha -eq (Hash-OrNull $helper)) $helper
    Rec 'production_active_admission_untouched' ($before.admission_sha -eq (Hash-OrNull $admission)) $admission
    if($null -ne $before.helper_pid){
        $hp2=@(Get-CimInstance Win32_Process|Where-Object{$_.ProcessId-eq$before.helper_pid -and $_.Name-eq'node.exe' -and $_.CommandLine -and $_.CommandLine.Contains($helper)}|Select-Object -First 1)
        $same=$false
        if($hp2){
            try{$same=((Get-Process -Id $before.helper_pid).StartTime.ToUniversalTime().ToString('o') -eq $before.helper_start)}catch{$same=$false}
        }
        Rec 'active_helper_process_untouched' $same @{pid=$before.helper_pid;start=$before.helper_start}
    }else{
        Rec 'active_helper_process_untouched' $true 'production helper not present in this environment'
    }

    foreach($s in $created){Rec ('created_scratch_removed_'+$s.run_id) (-not(Test-Path -LiteralPath $s.path)) $s.path}
    Write-Host ("TEST_SCRATCH_HYGIENE_REGRESSION_PASS checks={0}" -f $results.Count)
}finally{
    foreach($p in $foreign){if(Test-Path -LiteralPath $p){Remove-Item -LiteralPath $p -Recurse -Force -ErrorAction SilentlyContinue}}
    foreach($s in $created){
        if(Test-Path -LiteralPath $s.path){
            try{Remove-OneCTestScratch -Path $s.path -RunId $s.run_id -Base $s.base|Out-Null}catch{Write-Warning $_.Exception.Message}
        }
    }
}
