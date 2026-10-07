Set-StrictMode -Version 2.0
$ErrorActionPreference='Stop'

$script:ScratchSchemaVersion=1
$script:ScratchKind='ONEC_TEST_SCRATCH'
$script:ScratchOwner='OneCChatWorker.Tests'
$script:ScratchMarker='.onec-test-scratch.json'
$script:DefaultTtlHours=24

function Get-OneCTestScratchBase {
    [CmdletBinding()]
    param()
    if([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)){throw 'SCRATCH_LOCALAPPDATA_UNAVAILABLE'}
    [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'Temp\OneCWT'))
}

function Get-OneCTestScratchMarkerPath {
    param([Parameter(Mandatory)][string]$Path)
    Join-Path ([IO.Path]::GetFullPath($Path)) $script:ScratchMarker
}

function Test-OneCTestScratchBoundedPath {
    param(
        [Parameter(Mandatory)][string]$Path,
        [string]$Base=(Get-OneCTestScratchBase)
    )
    $full=[IO.Path]::GetFullPath($Path).TrimEnd('\')
    $baseFull=[IO.Path]::GetFullPath($Base).TrimEnd('\')
    if($full.Equals($baseFull,[StringComparison]::OrdinalIgnoreCase)){return $false}
    $prefix=$baseFull+'\'
    $full.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)
}

function Get-OneCTestScratchProcessStartUtc {
    param([int]$ProcessId)
    try{
        $p=Get-Process -Id $ProcessId -ErrorAction Stop
        return $p.StartTime.ToUniversalTime()
    }catch{
        return $null
    }
}

function Read-OneCTestScratchMarker {
    param(
        [Parameter(Mandatory)][string]$Path,
        [string]$Base=(Get-OneCTestScratchBase)
    )
    $full=[IO.Path]::GetFullPath($Path).TrimEnd('\')
    if(-not(Test-OneCTestScratchBoundedPath -Path $full -Base $Base)){return $null}
    $markerPath=Get-OneCTestScratchMarkerPath $full
    if(-not(Test-Path -LiteralPath $markerPath -PathType Leaf)){return $null}
    try{
        $m=Get-Content -LiteralPath $markerPath -Raw -Encoding UTF8|ConvertFrom-Json
        if([int]$m.schema_version -ne $script:ScratchSchemaVersion){return $null}
        if([string]$m.kind -ne $script:ScratchKind -or [string]$m.owner -ne $script:ScratchOwner){return $null}
        if([string]::IsNullOrWhiteSpace([string]$m.run_id)){return $null}
        $marked=[IO.Path]::GetFullPath([string]$m.path).TrimEnd('\')
        if(-not $marked.Equals($full,[StringComparison]::OrdinalIgnoreCase)){return $null}
        [void][datetime]::Parse([string]$m.created_utc,[Globalization.CultureInfo]::InvariantCulture,[Globalization.DateTimeStyles]::RoundtripKind)
        [void][datetime]::Parse([string]$m.expires_utc,[Globalization.CultureInfo]::InvariantCulture,[Globalization.DateTimeStyles]::RoundtripKind)
        $m
    }catch{return $null}
}

function Get-OneCTestScratchClassification {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Path,
        [string]$Base=(Get-OneCTestScratchBase),
        [datetime]$NowUtc=(Get-Date).ToUniversalTime()
    )
    $full=[IO.Path]::GetFullPath($Path).TrimEnd('\')
    $baseFull=[IO.Path]::GetFullPath($Base).TrimEnd('\')
    if(-not(Test-OneCTestScratchBoundedPath -Path $full -Base $baseFull)){
        return [pscustomobject]@{path=$full;classification='OUTSIDE_OWNER_ROOT';owned=$false;stale=$false;active=$false;run_id=$null}
    }
    if(-not(Test-Path -LiteralPath $full)){
        return [pscustomobject]@{path=$full;classification='ABSENT';owned=$false;stale=$false;active=$false;run_id=$null}
    }
    $markerPath=Get-OneCTestScratchMarkerPath $full
    if(-not(Test-Path -LiteralPath $markerPath -PathType Leaf)){
        return [pscustomobject]@{path=$full;classification='MARKER_MISSING';owned=$false;stale=$false;active=$false;run_id=$null}
    }
    $m=Read-OneCTestScratchMarker -Path $full -Base $baseFull
    if($null -eq $m){
        return [pscustomobject]@{path=$full;classification='MARKER_INVALID';owned=$false;stale=$false;active=$false;run_id=$null}
    }
    $active=$false
    $pidValue=0
    if([int]::TryParse([string]$m.creator_pid,[ref]$pidValue) -and $pidValue -gt 0){
        $actualStart=Get-OneCTestScratchProcessStartUtc -ProcessId $pidValue
        if($null -ne $actualStart){
            try{
                $markedStart=[datetime]::Parse([string]$m.creator_process_start_utc,[Globalization.CultureInfo]::InvariantCulture,[Globalization.DateTimeStyles]::RoundtripKind).ToUniversalTime()
                $active=([math]::Abs(($actualStart-$markedStart).TotalSeconds) -lt 2)
            }catch{$active=$true}
        }
    }
    $expires=[datetime]::Parse([string]$m.expires_utc,[Globalization.CultureInfo]::InvariantCulture,[Globalization.DateTimeStyles]::RoundtripKind).ToUniversalTime()
    $stale=(-not $active -and $NowUtc.ToUniversalTime() -ge $expires)
    $classification=$(if($active){'ACTIVE'}elseif($stale){'OWNED_STALE'}else{'OWNED_FRESH'})
    [pscustomobject]@{
        path=$full
        classification=$classification
        owned=$true
        stale=$stale
        active=$active
        run_id=[string]$m.run_id
        purpose=[string]$m.purpose
        created_utc=[string]$m.created_utc
        expires_utc=[string]$m.expires_utc
        creator_pid=$pidValue
    }
}

function Test-OneCTestScratchAdmin {
    try{
        $id=[Security.Principal.WindowsIdentity]::GetCurrent()
        return (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    }catch{return $false}
}

function Remove-OneCTestScratch {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Path,
        [string]$RunId,
        [string]$Base=(Get-OneCTestScratchBase)
    )
    $full=[IO.Path]::GetFullPath($Path).TrimEnd('\')
    if(-not(Test-OneCTestScratchBoundedPath -Path $full -Base $Base)){throw "SCRATCH_PATH_OUTSIDE_OWNER_ROOT: $full"}
    if(-not(Test-Path -LiteralPath $full)){
        return [pscustomobject]@{path=$full;status='ALREADY_ABSENT'}
    }
    $m=Read-OneCTestScratchMarker -Path $full -Base $Base
    if($null -eq $m){throw "SCRATCH_MARKER_INVALID_OR_MISSING: $full"}
    if(-not [string]::IsNullOrWhiteSpace($RunId) -and [string]$m.run_id -ne $RunId){throw "SCRATCH_RUN_ID_MISMATCH: $full"}
    $classification=Get-OneCTestScratchClassification -Path $full -Base $Base
    if($classification.active -and [string]::IsNullOrWhiteSpace($RunId)){
        return [pscustomobject]@{path=$full;status='SKIPPED_ACTIVE';run_id=$classification.run_id}
    }
    try{
        Remove-Item -LiteralPath $full -Recurse -Force -ErrorAction Stop
    }catch{
        $firstError=$_.Exception
        try{
            $extended=$(if($full.StartsWith('\\')){'\\?\UNC\'+$full.Substring(2)}else{'\\?\'+$full})
            $cmd='rmdir /s /q "{0}"' -f $extended.Replace('"','""')
            & $env:ComSpec /d /s /c $cmd | Out-Null
        }catch{}
        if(Test-Path -LiteralPath $full){
            $node=Get-Command node.exe -ErrorAction SilentlyContinue
            if($node){
                try{& $node.Source -e "const fs=require('fs'),p=require('path');fs.rmSync(p.toNamespacedPath(process.argv[1]),{recursive:true,force:true});" $full | Out-Null}catch{}
            }
        }
        if(Test-Path -LiteralPath $full){
            if(-not(Test-OneCTestScratchAdmin)){throw $firstError}
            & takeown.exe /F $full /R /D Y | Out-Null
            & icacls.exe $full /grant '*S-1-5-32-544:F' /T /C | Out-Null
            & icacls.exe $full /grant '*S-1-5-18:F' /T /C | Out-Null
            Remove-Item -LiteralPath $full -Recurse -Force -ErrorAction Stop
        }
    }
    if(Test-Path -LiteralPath $full){throw "SCRATCH_CLEANUP_FAILED: $full"}
    [pscustomobject]@{path=$full;status='REMOVED';run_id=[string]$m.run_id}
}

function Clear-StaleOneCTestScratch {
    [CmdletBinding()]
    param(
        [string]$Base=(Get-OneCTestScratchBase),
        [datetime]$NowUtc=(Get-Date).ToUniversalTime()
    )
    $baseFull=[IO.Path]::GetFullPath($Base).TrimEnd('\')
    if(-not(Test-Path -LiteralPath $baseFull -PathType Container)){return @()}
    $results=New-Object Collections.Generic.List[object]
    foreach($dir in @(Get-ChildItem -LiteralPath $baseFull -Directory -Force -ErrorAction Stop)){
        $c=Get-OneCTestScratchClassification -Path $dir.FullName -Base $baseFull -NowUtc $NowUtc
        if($c.classification -eq 'OWNED_STALE'){
            try{
                $removed=Remove-OneCTestScratch -Path $dir.FullName -RunId $c.run_id -Base $baseFull
                $results.Add([pscustomobject]@{path=$dir.FullName;classification='OWNED_STALE';action=$removed.status;run_id=$c.run_id})
            }catch{
                $results.Add([pscustomobject]@{path=$dir.FullName;classification='OWNED_STALE';action='CLEANUP_FAILED';run_id=$c.run_id;error=$_.Exception.Message})
            }
        }else{
            $results.Add([pscustomobject]@{path=$dir.FullName;classification=$c.classification;action='KEPT';run_id=$c.run_id})
        }
    }
    [object[]]$results.ToArray()
}

function New-OneCTestScratch {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')][string]$Purpose,
        [ValidateRange(1,168)][int]$TtlHours=$script:DefaultTtlHours
    )
    $base=Get-OneCTestScratchBase
    New-Item -ItemType Directory -Force -Path $base|Out-Null
    [void](Clear-StaleOneCTestScratch -Base $base)
    $runId=[guid]::NewGuid().ToString('N')
    $path=Join-Path $base ('run-'+$runId)
    if(Test-Path -LiteralPath $path){throw "SCRATCH_RUN_COLLISION: $path"}
    New-Item -ItemType Directory -Path $path|Out-Null
    $created=(Get-Date).ToUniversalTime()
    $start=(Get-Process -Id $PID).StartTime.ToUniversalTime()
    $marker=[ordered]@{
        schema_version=$script:ScratchSchemaVersion
        kind=$script:ScratchKind
        owner=$script:ScratchOwner
        run_id=$runId
        purpose=$Purpose
        path=[IO.Path]::GetFullPath($path).TrimEnd('\')
        created_utc=$created.ToString('o')
        expires_utc=$created.AddHours($TtlHours).ToString('o')
        creator_pid=$PID
        creator_process_start_utc=$start.ToString('o')
    }
    $markerPath=Get-OneCTestScratchMarkerPath $path
    [IO.File]::WriteAllText($markerPath,($marker|ConvertTo-Json -Depth 5),[Text.UTF8Encoding]::new($false))
    [pscustomobject]@{path=$path;base=$base;run_id=$runId;marker=$markerPath;purpose=$Purpose;expires_utc=$marker.expires_utc}
}

Export-ModuleMember -Function Get-OneCTestScratchBase,Get-OneCTestScratchClassification,New-OneCTestScratch,Remove-OneCTestScratch,Clear-StaleOneCTestScratch
