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
# Query DOS device identity, not a lexical drive-letter spelling.
# A SUBST drive maps to \??\C:\... and is refused conservatively.
# Only a locally attached \Device\HarddiskVolumeN DOS drive is admitted in C0.
# UNC, mapped, virtual, ambiguous or unresolvable devices remain a hard HOLD.
if(-not ('OrbitC0.DosDeviceIdentity' -as [type])){
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Text;
namespace OrbitC0 {
    public static class DosDeviceIdentity {
        [DllImport("kernel32.dll", EntryPoint="QueryDosDeviceW", CharSet=CharSet.Unicode, SetLastError=true)]
        public static extern uint QueryDosDevice(string name, StringBuilder target, int maxChars);
    }
}
'@ -ErrorAction Stop
}
# The pure conversion accepts a Windows mapping target. Only Get-PhysicalRoot
# queries the real OS mapping; regression injects synthetic C:/D: targets.
function Convert-DosDeviceRoot([string]$PathValue,[string]$DeviceTarget) {
    if($PathValue -notmatch '^[A-Za-z]:\\'){ throw 'UNTRUSTED_NON_LOCAL_ROOT' }
    if($PathValue -match '(?i)(^|\\)[^\\]*~[0-9]+(\\|$)'){throw 'UNTRUSTED_SHORT_NAME_ALIAS'}
    if($DeviceTarget -notmatch '^\\Device\\HarddiskVolume[0-9]+$'){
        throw 'NONCANONICAL_DOS_DEVICE_ALIAS'
    }
    return $DeviceTarget+$PathValue.Substring(2).TrimEnd('\')
}
function Get-PhysicalRoot([string]$PathValue) {
    if($PathValue -notmatch '^[A-Za-z]:\\'){ throw 'UNTRUSTED_NON_LOCAL_ROOT' }
    $drive=$PathValue.Substring(0,2).ToUpperInvariant()
    $buf=New-Object System.Text.StringBuilder 4096
    $size=[OrbitC0.DosDeviceIdentity]::QueryDosDevice($drive,$buf,$buf.Capacity)
    if($size -eq 0){throw 'DOS_DEVICE_IDENTITY_UNAVAILABLE'}
    $targets=@($buf.ToString().Split([char]0,[StringSplitOptions]::RemoveEmptyEntries))
    if($targets.Count -ne 1){throw 'NONCANONICAL_DOS_DEVICE_ALIAS'}
    return Convert-DosDeviceRoot -PathValue $PathValue -DeviceTarget $targets[0]
}
# Compare against FIXED PROTECTED defaults as well as against each other.
# This function is pure; the caller obtains device mappings without inspecting
# C:\OneCChatWorker, ProgramData, Source or any other protected folder.
function Test-ProtectedPhysicalRootOverlap {
    param([string[]]$RequestedRoots,[string[]]$ProtectedRoots,[bool]$AllowProductionReadOnly=$false)
    if($AllowProductionReadOnly){return $false}
    foreach($requested in $RequestedRoots){
        foreach($protected in $ProtectedRoots){
            if(Root-Intersects $requested $protected){return $true}
        }
    }
    return $false
}
# Deny ACEs relevant to reading root metadata are a hard hold even if an
# elevated runner happens to bypass them when opening files.
function Has-MetadataReadDenyAcl([string]$PathValue) {
    $mask=([Security.AccessControl.FileSystemRights]::ListDirectory -bor
           [Security.AccessControl.FileSystemRights]::ReadAttributes -bor
           [Security.AccessControl.FileSystemRights]::ReadExtendedAttributes -bor
           [Security.AccessControl.FileSystemRights]::ReadPermissions)
    $cursor=$PathValue
    while (-not [string]::IsNullOrWhiteSpace($cursor)) {
        if (Test-Path -LiteralPath $cursor) {
            $acl=Get-Acl -LiteralPath $cursor -ErrorAction Stop
            foreach($ace in @($acl.Access)) {
                if($ace.AccessControlType -eq [Security.AccessControl.AccessControlType]::Deny -and
                   (($ace.FileSystemRights -band $mask) -ne 0)) {return $true}
            }
        }
        $parent=[IO.Directory]::GetParent($cursor)
        if ($null -eq $parent) {break}
        $cursor=$parent.FullName
    }
    return $false
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
        $resolved=@()
        foreach($r in $roots){
            try { $resolved+=,(Get-PhysicalRoot $r) }
            catch { Add-Hold 'PHYSICAL_ROOT_IDENTITY_UNVERIFIED';break }
        }
        if($reasons.Count -eq 0){
            for($i=0;$i -lt $resolved.Count;$i++){
                for($j=$i+1;$j -lt $resolved.Count;$j++){
                    if(Root-Intersects $resolved[$i] $resolved[$j]){Add-Hold 'ROOT_COLLISION'}
                }
            }
        }
    }
    # An alias of any fixed live product root is protected too. Resolve
    # the defaults with QueryDosDevice ONLY: no Test-Path/ACL or marker read
    # from a protected root occurs before this gate.
    if($reasons.Count -eq 0 -and -not $AllowProductionReadOnly) {
        try {
            $protectedPhysical=@()
            foreach($fixed in @('C:\OneCChatWorker','C:\ProgramData\OneCChatWorker',
                                 'C:\OneCOrbit','C:\ProgramData\OneCOrbit')){
                $protectedPhysical+=,(Get-PhysicalRoot $fixed)
            }
            if(Test-ProtectedPhysicalRootOverlap -RequestedRoots $resolved -ProtectedRoots $protectedPhysical){
                Add-Hold 'PRODUCTION_INSPECTION_NOT_AUTHORIZED'
            }
        } catch {
            Add-Hold 'PHYSICAL_ROOT_IDENTITY_UNVERIFIED'
        }
    }
    if($reasons.Count -eq 0) {
        foreach($r in $roots) {
            if(Has-ReparseAncestor $r) {Add-Hold 'REPARSE_ANCESTOR';break}
        }
    }
    if($reasons.Count -eq 0) {
        foreach($r in $roots){
            if(Has-MetadataReadDenyAcl $r){Add-Hold 'ACL_READ_DENY_PRESENT';break}
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
$hardBlock=@('ROOT_COLLISION','PHYSICAL_ROOT_IDENTITY_UNVERIFIED','ACL_READ_DENY_PRESENT','PRODUCTION_INSPECTION_NOT_AUTHORIZED','REPARSE_ANCESTOR',
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
