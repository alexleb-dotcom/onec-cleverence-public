#requires -Version 5.1
<#
.SYNOPSIS
  Read-only conservative preflight for future OneCChatWorker -> OneCOrbit migration.
.DESCRIPTION
  This is NOT an installer, migrator or a green-light for cutover.
  Only checks bounded root-level metadata and known runtime marker existence.
  Source/Main/Incoming contents and S4/relay are not read, hashed, copied or mutated.
  Any unknown project/source state requires separate owner attestation.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$LegacyWorkerRoot,
    [Parameter(Mandatory=$true)][string]$LegacyProgramDataRoot,
    [Parameter(Mandatory=$true)][string]$OrbitWorkerRoot,
    [Parameter(Mandatory=$true)][string]$OrbitProgramDataRoot,
    [switch]$AllowProductionReadOnly
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$reasons = New-Object 'System.Collections.Generic.List[string]'
function Add-Hold([string]$Reason) {
    if (-not $reasons.Contains($Reason)) { [void]$reasons.Add($Reason) }
}
function Full-Root([string]$PathValue) {
    if ([string]::IsNullOrWhiteSpace($PathValue)) { throw 'EMPTY_ROOT' }
    [IO.Path]::GetFullPath($PathValue).TrimEnd('\')
}
function Root-Intersects([string]$A,[string]$B) {
    return $A.Equals($B,[StringComparison]::OrdinalIgnoreCase) -or
        $A.StartsWith($B+'\',[StringComparison]::OrdinalIgnoreCase) -or
        $B.StartsWith($A+'\',[StringComparison]::OrdinalIgnoreCase)
}
function Has-ReparseAncestor([string]$PathValue) {
    $cursor=$PathValue
    while (-not [string]::IsNullOrWhiteSpace($cursor)) {
        if (Test-Path -LiteralPath $cursor) {
            $item=Get-Item -LiteralPath $cursor -Force
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {return $true}
        }
        $parent=[IO.Directory]::GetParent($cursor)
        if ($null -eq $parent) {break}
        $cursor=$parent.FullName
    }
    return $false
}
try {
    $legacyWorker=Full-Root $LegacyWorkerRoot
    $legacyData=Full-Root $LegacyProgramDataRoot
    $orbitWorker=Full-Root $OrbitWorkerRoot
    $orbitData=Full-Root $OrbitProgramDataRoot
    $roots=@($legacyWorker,$legacyData,$orbitWorker,$orbitData)
    for($i=0;$i -lt $roots.Count;$i++){
        for($j=$i+1;$j -lt $roots.Count;$j++){
            if(Root-Intersects $roots[$i] $roots[$j]){Add-Hold 'ROOT_COLLISION'}
        }
    }
    # No implicit live-machine inspection. Explicit switch is read-only, not migration authority.
    if(-not $AllowProductionReadOnly -and (
      ($legacyWorker -ieq 'C:\OneCChatWorker') -or
      ($legacyData -ieq 'C:\ProgramData\OneCChatWorker') -or
      ($orbitWorker -ieq 'C:\OneCOrbit') -or
      ($orbitData -ieq 'C:\ProgramData\OneCOrbit'))){
        Add-Hold 'PRODUCTION_INSPECTION_NOT_AUTHORIZED'
    }
    if($reasons.Count -eq 0) {
        foreach($r in $roots) {
            if(Has-ReparseAncestor $r) {Add-Hold 'REPARSE_ANCESTOR';break}
        }
    }
    if($reasons.Count -eq 0) {
        if(-not (Test-Path -LiteralPath $legacyWorker -PathType Container) -or
           -not (Test-Path -LiteralPath $legacyData -PathType Container)) {
            Add-Hold 'LEGACY_ROOT_MISSING'
        } else {
            if(-not (Test-Path -LiteralPath (Join-Path $legacyWorker 'projects.json') -PathType Leaf) -or
               -not (Test-Path -LiteralPath (Join-Path $legacyData 'installed-state.json') -PathType Leaf)){
                Add-Hold 'INCOMPLETE_LEGACY_INSTALL'
            }
            if(Test-Path -LiteralPath $orbitWorker){Add-Hold 'ORBIT_DESTINATION_OCCUPIED'}
            if(Test-Path -LiteralPath $orbitData){Add-Hold 'ORBIT_DESTINATION_OCCUPIED'}
            $admission=Join-Path $legacyData 'runtime\active-admission.json'
            if(Test-Path -LiteralPath $admission){Add-Hold 'ADMISSION_MARKER_PRESENT'}
            $helper=Join-Path $legacyData 'runtime\hosted-helper-state.json'
            if(Test-Path -LiteralPath $helper){Add-Hold 'HELPER_STATE_UNADJUDICATED'}
            $operation=Join-Path $legacyData 'operations\current-operation.json'
            if(Test-Path -LiteralPath $operation){Add-Hold 'OPERATION_STATE_UNADJUDICATED'}
        }
    }
} catch {
    Add-Hold 'METADATA_INSPECTION_FAILED'
}
if($reasons.Count -eq 0){
    # The absence of simple markers cannot prove that projects/Source/S4 are quiescent.
    Add-Hold 'PROJECT_SOURCE_S4_ATTESTATION_REQUIRED'
}
$hardBlock=@('ROOT_COLLISION','PRODUCTION_INSPECTION_NOT_AUTHORIZED','REPARSE_ANCESTOR',
    'LEGACY_ROOT_MISSING','INCOMPLETE_LEGACY_INSTALL','ORBIT_DESTINATION_OCCUPIED',
    'ADMISSION_MARKER_PRESENT','HELPER_STATE_UNADJUDICATED',
    'OPERATION_STATE_UNADJUDICATED','METADATA_INSPECTION_FAILED')
$blocked=$false
foreach($r in $reasons){if($hardBlock -contains $r){$blocked=$true}}
[pscustomobject][ordered]@{
    schema='ORBIT_MIGRATION_READONLY_PREFLIGHT_V1'
    status=$(if($blocked){'BLOCKED'}else{'OWNER_ATTESTATION_REQUIRED'})
    migration_permitted=$false
    mutation_performed=$false
    source_main_incoming_content_access=$false
    reasons=@($reasons.ToArray())
} | ConvertTo-Json -Depth 5 -Compress
