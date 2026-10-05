param(
 [string]$PackageRoot=(Split-Path -Parent $PSScriptRoot)
)
$ErrorActionPreference='Stop'
$PackageRoot=[IO.Path]::GetFullPath($PackageRoot)
$core=Join-Path $PackageRoot 'core\OneCChatWorker.Core.psm1'
$root=Join-Path $env:TEMP ('OneCChatWorker-ApplyQuarantine-'+[Guid]::NewGuid().ToString('N'))
$worker=Join-Path $root 'worker'
$projectRoot=Join-Path $worker 'Demo'
$source=Join-Path $root 'source'
$results=New-Object Collections.Generic.List[object]

function Rec([string]$Name,[bool]$Ok,[string]$Detail=''){
 $results.Add([pscustomobject]@{name=$Name;pass=$Ok;detail=$Detail})
 if(-not $Ok){throw "ASSERTION_FAILED: $Name :: $Detail"}
}
function Write-Utf8([string]$Path,[string]$Value){
 New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Path)|Out-Null
 [IO.File]::WriteAllText($Path,$Value,[Text.UTF8Encoding]::new($false))
}
function Hash([string]$Path){(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()}

try{
 New-Item -ItemType Directory -Force -Path $worker,$projectRoot,$source|Out-Null
 Import-Module $core -Force -DisableNameChecking

 $sourceSentinel=Join-Path $source 'source.txt'
 $target=Join-Path $projectRoot 'Participants\erp\Target\Main'
 $targetSentinel=Join-Path $target 'canonical.txt'
 $detachedSentinel=Join-Path $projectRoot 'Detached\keep\evidence.txt'
 Write-Utf8 $sourceSentinel 'authoritative-source'
 Write-Utf8 $targetSentinel 'committed-target'
 Write-Utf8 $detachedSentinel 'detached-evidence'
 $sourceHash=Hash $sourceSentinel
 $targetHash=Hash $targetSentinel
 $detachedHash=Hash $detachedSentinel

 $stageRoot=Get-ApplyStageRoot $worker
 New-Item -ItemType Directory -Force -Path $stageRoot|Out-Null
 $stage=Join-Path $stageRoot 'a.stage-quarantine'
 New-Item -ItemType Directory -Force -Path $stage|Out-Null
 Write-Utf8 (Join-Path $stage 'partial.txt') 'partial-unverified'
 Write-ApplyStageState -StagePath $stage -State COPYING -ProjectRoot $projectRoot -TargetPath $target -ArchiveKey 'erp\Target\Main'
 $meta=$stage+'.json'
 Rec 'stage_metadata_exists' (Test-Path -LiteralPath $meta -PathType Leaf) $meta

 $residueBefore=@(Get-ApplyStageResidue -ProjectId Demo -WorkerRoot $worker)
 Rec 'bounded_stage_residue_detected' ($residueBefore.Count -eq 1 -and $residueBefore[0].state -eq 'COPYING') ($residueBefore|ConvertTo-Json -Compress)

 # The product route from CLEANUP_FAILED to this function is asserted statically in the product contract.
 # Here exercise the real quarantine move itself, including metadata and preservation boundaries.
 $qresult=Move-ApplyStageToQuarantine -Residue $residueBefore[0] -ProjectRoot $projectRoot
 Rec 'quarantine_move_reports_quarantined' ($qresult.status -eq 'QUARANTINED') ($qresult|ConvertTo-Json -Compress)
 $q=[string]$qresult.quarantine_path
 Rec 'quarantine_under_project_recovery' (-not [string]::IsNullOrWhiteSpace($q) -and $q.StartsWith((Join-Path $projectRoot 'Recovery\ApplyResidue'),[StringComparison]::OrdinalIgnoreCase)) $q
 Rec 'original_stage_moved' (-not(Test-Path -LiteralPath $stage)) $stage
 Rec 'quarantined_stage_present' (Test-Path -LiteralPath $q -PathType Container) $q
 Rec 'quarantined_metadata_present' (Test-Path -LiteralPath ($q+'.json') -PathType Leaf) ($q+'.json')
 Rec 'residue_no_longer_blocks_canonical_stage_scan' (@(Get-ApplyStageResidue -ProjectId Demo -WorkerRoot $worker).Count -eq 0) ''
 Rec 'canonical_target_preserved' ((Hash $targetSentinel) -eq $targetHash) ''
 Rec 'detached_evidence_preserved' ((Hash $detachedSentinel) -eq $detachedHash) ''
 Rec 'authoritative_source_preserved' ((Hash $sourceSentinel) -eq $sourceHash) ''

 Write-Host ("APPLY_QUARANTINE_REGRESSION_PASS checks={0}" -f $results.Count)
} finally {
 Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
}
