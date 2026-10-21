#requires -Version 5.1
<#
  Q115 S2: off-production diagnostic for native WPF image users.
  Intentionally NEVER approves, starts, closes or performs UPDATE.
  DO NOT use this as an installation coordinator or a release attestation.
#>
[CmdletBinding()]
param(
 [Parameter(Mandatory=$true)][string]$ImagePath,
 [Parameter(Mandatory=$true)][string]$FixtureRoot
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$reasons=New-Object 'System.Collections.Generic.List[string]'
$observed=New-Object 'System.Collections.Generic.List[int]'
$inventoryAttempted=$false
function Hold([string]$Why) {
 if(-not $reasons.Contains($Why)){[void]$reasons.Add($Why)}
}
function Canonical([string]$InputPath) {
 if([string]::IsNullOrWhiteSpace($InputPath)){throw 'EMPTY_PATH'}
 $full=[IO.Path]::GetFullPath($InputPath)
 if($full -notmatch '^[A-Za-z]:\\'){throw 'NONLOCAL_PATH'}
 return $full.TrimEnd('\')
}
function Intersects([string]$A,[string]$B){
 $cmp=[StringComparison]::OrdinalIgnoreCase
 return $A.Equals($B,$cmp) -or $A.StartsWith($B+'\',$cmp) -or $B.StartsWith($A+'\',$cmp)
}
function ReparseAncestor([string]$Value) {
 $cur=$Value
 while($cur){
   if(Test-Path -LiteralPath $cur){
     $item=Get-Item -LiteralPath $cur -Force -ErrorAction Stop
     if(($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){return $true}
   }
   $parent=[IO.Directory]::GetParent($cur)
   if($null -eq $parent){break}
   $cur=$parent.FullName
 }
 return $false
}
try {
 $root=Canonical $FixtureRoot
 $image=Canonical $ImagePath
 $tempBase=Canonical ([IO.Path]::GetTempPath())
 if(-not $root.StartsWith($tempBase+'\',[StringComparison]::OrdinalIgnoreCase) -or
    (Split-Path -Leaf $root) -notlike 'orbit-updater-lease-*'){
   Hold 'ISOLATED_TEMP_FIXTURE_REQUIRED'
 }
 # Fixture must not be within standard product roots, nor share a parent
 # scope that could permit inspecting installed production executables.
 foreach($protected in @('C:\OneCOrbit','C:\OneCChatWorker','C:\ProgramData\OneCOrbit',
                         'C:\ProgramData\OneCChatWorker')){
   if(Intersects $root $protected -or Intersects $image $protected){
     Hold 'PRODUCTION_ROOT_FORBIDDEN'
   }
 }
 if(-not $image.StartsWith($root+'\',[StringComparison]::OrdinalIgnoreCase)){
   Hold 'IMAGE_OUTSIDE_FIXTURE'
 }
 if((Split-Path -Leaf $image) -notin @('OneCArchitecture.ControlCenter.exe','OneCOrbit.exe')){
   Hold 'UNEXPECTED_IMAGE_BASENAME'
 }
 if($reasons.Count -eq 0){
   if ((ReparseAncestor $root) -or (ReparseAncestor $image)) { Hold 'REPARSE_PATH_FORBIDDEN' }
 }
 if($reasons.Count -eq 0 -and -not (Test-Path -LiteralPath $image -PathType Leaf)){
   Hold 'IMAGE_MISSING'
 }
 if($reasons.Count -eq 0){
   # Win32_Process includes tray-minimized and otherwise invisible WPF EXEs;
   # WM_CLOSE/visible windows are NOT a process shutdown attestation.
   $name=[IO.Path]::GetFileName($image).Replace("'","''")
   $inventoryAttempted=$true
   $all=@(Get-CimInstance -ClassName Win32_Process -Filter ("Name='"+$name+"'") -ErrorAction Stop)
   foreach($process in $all){
     if([string]::IsNullOrWhiteSpace([string]$process.ExecutablePath)){
       Hold 'PROCESS_PATH_UNVERIFIED'
       continue
     }
     $candidate=Canonical ([string]$process.ExecutablePath)
     if($candidate.Equals($image,[StringComparison]::OrdinalIgnoreCase)){
       [void]$observed.Add([int]$process.ProcessId)
     }
   }
   if($observed.Count -gt 0){Hold 'IMAGE_IN_USE'}
 }
} catch {
 Hold 'INVENTORY_OR_PATH_INSPECTION_FAILED'
}
if($reasons.Count -eq 0){Hold 'DETACHED_HANDOFF_NOT_IMPLEMENTED'}
$sorted=@($observed.ToArray()|Sort-Object -Unique)
[pscustomobject][ordered]@{
 schema='ORBIT_UPDATER_IMAGE_LEASE_PREFLIGHT_V1'
 status='BLOCKED'
 updater_ready=$false
 installed_image_write_permitted=$false
 update_invoked=$false
 process_terminated=$false
 worker_or_s4_touched=$false
 process_inventory_attempted=$inventoryAttempted
 observed_instance_count=$sorted.Count
 observed_instance_pids=$sorted
 reasons=@($reasons.ToArray())
} | ConvertTo-Json -Compress -Depth 5
