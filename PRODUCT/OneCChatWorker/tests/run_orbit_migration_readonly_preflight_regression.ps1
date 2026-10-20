#requires -Version 5.1
$ErrorActionPreference='Stop'
$probe=Join-Path $PSScriptRoot 'Inspect-OrbitMigrationReadOnly.ps1'
$root=Join-Path ([IO.Path]::GetTempPath()) ('orbit-readonly-gate-'+[guid]::NewGuid().ToString('N'))
[void](New-Item -ItemType Directory -Force -Path $root)
$checks=0
function Assert([bool]$Ok,[string]$Name){
 if(-not $Ok){throw ('ORBIT_PREFLIGHT_REGRESSION_FAILED: '+$Name)}
 $script:checks++
}
function File([string]$Path,[string]$Text='{}'){
 [void](New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Path))
 [IO.File]::WriteAllText($Path,$Text,[Text.UTF8Encoding]::new($false))
}
$legacy=Join-Path $root 'legacy-worker'
$data=Join-Path $root 'legacy-data'
$orbit=Join-Path $root 'orbit-worker'
$orbitData=Join-Path $root 'orbit-data'
function Check([string]$Expect,[string]$Reason){
 $out=(& $probe -LegacyWorkerRoot $legacy -LegacyProgramDataRoot $data -OrbitWorkerRoot $orbit -OrbitProgramDataRoot $orbitData) | ConvertFrom-Json
 Assert ($out.schema -eq 'ORBIT_MIGRATION_READONLY_PREFLIGHT_V1') 'schema'
 Assert ($out.status -eq $Expect) ('status '+$Reason)
 Assert (@($out.reasons) -contains $Reason) ('reason '+$Reason)
 Assert ($out.migration_permitted -eq $false -and $out.mutation_performed -eq $false -and $out.source_main_incoming_content_access -eq $false) 'always nonmutating'
 return $out
}
try {
 $null=Check 'BLOCKED' 'LEGACY_ROOT_MISSING'
 File (Join-Path $legacy 'projects.json')
 $null=Check 'BLOCKED' 'LEGACY_ROOT_MISSING'
 File (Join-Path $data 'installed-state.json')
 $null=Check 'OWNER_ATTESTATION_REQUIRED' 'PROJECT_SOURCE_S4_ATTESTATION_REQUIRED'
 File (Join-Path $data 'runtime\active-admission.json') '{"project_id":"fixture","state":"ACTIVE"}'
 $null=Check 'BLOCKED' 'ADMISSION_MARKER_PRESENT'
 Remove-Item -LiteralPath (Join-Path $data 'runtime\active-admission.json')
 File (Join-Path $data 'runtime\hosted-helper-state.json')
 $null=Check 'BLOCKED' 'HELPER_STATE_UNADJUDICATED'
 Remove-Item -LiteralPath (Join-Path $data 'runtime\hosted-helper-state.json')
 File (Join-Path $data 'operations\current-operation.json')
 $null=Check 'BLOCKED' 'OPERATION_STATE_UNADJUDICATED'
 Remove-Item -LiteralPath (Join-Path $data 'operations\current-operation.json')
 [void](New-Item -ItemType Directory -Force -Path $orbit)
 $null=Check 'BLOCKED' 'ORBIT_DESTINATION_OCCUPIED'
 Remove-Item -LiteralPath $orbit -Force
 $other=(& $probe -LegacyWorkerRoot $legacy -LegacyProgramDataRoot $data -OrbitWorkerRoot $legacy -OrbitProgramDataRoot $orbitData)|ConvertFrom-Json
 Assert ($other.status -eq 'BLOCKED' -and @($other.reasons) -contains 'ROOT_COLLISION') 'collision'
 $live=(& $probe -LegacyWorkerRoot 'C:\OneCChatWorker' -LegacyProgramDataRoot 'C:\ProgramData\OneCChatWorker' -OrbitWorkerRoot 'C:\OneCOrbit' -OrbitProgramDataRoot 'C:\ProgramData\OneCOrbit')|ConvertFrom-Json
 Assert ($live.status -eq 'BLOCKED' -and @($live.reasons) -contains 'PRODUCTION_INSPECTION_NOT_AUTHORIZED') 'live guard without inspection'
 $before=[IO.File]::ReadAllBytes((Join-Path $legacy 'projects.json'))
 $null=Check 'OWNER_ATTESTATION_REQUIRED' 'PROJECT_SOURCE_S4_ATTESTATION_REQUIRED'
 Assert ([Linq.Enumerable]::SequenceEqual([byte[]]$before,[byte[]][IO.File]::ReadAllBytes((Join-Path $legacy 'projects.json')))) 'marker unchanged'
 Remove-Item -LiteralPath (Join-Path $legacy 'projects.json')
 $null=Check 'BLOCKED' 'INCOMPLETE_LEGACY_INSTALL'
 File (Join-Path $legacy 'projects.json')
 Remove-Item -LiteralPath (Join-Path $data 'installed-state.json')
 $null=Check 'BLOCKED' 'INCOMPLETE_LEGACY_INSTALL'
 Write-Host ('ORBIT_MIGRATION_READONLY_PREFLIGHT_PASS checks='+$checks+' production_access=false source_main_access=false')
} finally {
 Remove-Item -LiteralPath $root -Force -Recurse -ErrorAction SilentlyContinue
}
