#requires -Version 5.1
$ErrorActionPreference='Stop'
$probe=Join-Path $PSScriptRoot 'Inspect-OrbitMigrationReadOnly.ps1'
$root=Join-Path ([IO.Path]::GetTempPath()) ('orbit-readonly-gate-'+[guid]::NewGuid().ToString('N'))
[void](New-Item -ItemType Directory -Force -Path $root)
$checks=0
$substDrive=$null
$aclDenyPath=$null
$aclOriginal=$null
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
 # Two different lexical Windows roots resolving to the same physical directory.
 # Only bind an unused letter to a disposable TEMP root; remove it in finally.
 $inUse=@([Environment]::GetLogicalDrives()|ForEach-Object{$_.Substring(0,2).ToUpperInvariant()})
 foreach($candidate in @('Z:','Y:','X:','W:','V:','U:')){
    if($inUse -notcontains $candidate){$substDrive=$candidate;break}
 }
 Assert ($null -ne $substDrive) 'free disposable SUBST drive available'
 & subst.exe $substDrive $root | Out-Null
 Assert ($LASTEXITCODE -eq 0) 'SUBST temporary drive created'
 File (Join-Path $legacy 'installed-state.json')
 $viaSubst=$substDrive+'\legacy-worker'
 Assert ((Get-FileHash -LiteralPath (Join-Path $legacy 'projects.json')).Hash -eq
         (Get-FileHash -LiteralPath (Join-Path $viaSubst 'projects.json')).Hash) 'SUBST same physical marker'
 $alias=(& $probe -LegacyWorkerRoot $legacy -LegacyProgramDataRoot $viaSubst -OrbitWorkerRoot $orbit -OrbitProgramDataRoot $orbitData)|ConvertFrom-Json
 Assert ($alias.status -eq 'BLOCKED' -and @($alias.reasons) -contains 'PHYSICAL_ROOT_IDENTITY_UNVERIFIED') 'SUBST directory alias fails closed'
 Assert ($alias.migration_permitted -eq $false -and $alias.mutation_performed -eq $false) 'SUBST no cutover'
 $child=Join-Path $viaSubst 'nested'
 $nested=(& $probe -LegacyWorkerRoot $legacy -LegacyProgramDataRoot $child -OrbitWorkerRoot $orbit -OrbitProgramDataRoot $orbitData)|ConvertFrom-Json
 Assert ($nested.status -eq 'BLOCKED' -and @($nested.reasons) -contains 'PHYSICAL_ROOT_IDENTITY_UNVERIFIED') 'SUBST physical descendant alias fails closed'
 & subst.exe $substDrive /D | Out-Null
 Assert ($LASTEXITCODE -eq 0) 'SUBST cleanup before remaining fixtures'
 $substDrive=$null
 # Reparse/junction is tested separately from DOS device aliases.
 $junction=Join-Path $root 'junction-to-legacy'
 $newLink=New-Item -Path $junction -ItemType Junction -Target $legacy -ErrorAction Stop
 Assert (($newLink.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) 'disposable reparse fixture'
 $reparse=(& $probe -LegacyWorkerRoot $legacy -LegacyProgramDataRoot $data -OrbitWorkerRoot $junction -OrbitProgramDataRoot $orbitData)|ConvertFrom-Json
 Assert ($reparse.status -eq 'BLOCKED' -and @($reparse.reasons) -contains 'REPARSE_ANCESTOR') 'reparse root hard hold'
 [IO.Directory]::Delete($junction,$false)
 $ambiguous=(& $probe -LegacyWorkerRoot '\\?\C:\untrusted-alias' -LegacyProgramDataRoot $data -OrbitWorkerRoot $orbit -OrbitProgramDataRoot $orbitData)|ConvertFrom-Json
 Assert ($ambiguous.status -eq 'BLOCKED' -and @($ambiguous.reasons) -contains 'PHYSICAL_ROOT_IDENTITY_UNVERIFIED') 'unprovable local namespace alias blocked'
 # Disposable ACL denied-access adversary: no alteration of any real install.
 $aclDenyPath=Join-Path $root 'deny-only-test-root'
 File (Join-Path $aclDenyPath 'projects.json')
 $aclOriginal=Get-Acl -LiteralPath $aclDenyPath -ErrorAction Stop
 $denyAcl=Get-Acl -LiteralPath $aclDenyPath -ErrorAction Stop
 $userSid=[Security.Principal.WindowsIdentity]::GetCurrent().User
 $rights=([Security.AccessControl.FileSystemRights]::ListDirectory -bor [Security.AccessControl.FileSystemRights]::ReadAttributes)
 $flags=([Security.AccessControl.InheritanceFlags]::ContainerInherit -bor [Security.AccessControl.InheritanceFlags]::ObjectInherit)
 $denyRule=New-Object Security.AccessControl.FileSystemAccessRule($userSid,$rights,$flags,[Security.AccessControl.PropagationFlags]::None,[Security.AccessControl.AccessControlType]::Deny)
 [void]$denyAcl.AddAccessRule($denyRule)
 Set-Acl -LiteralPath $aclDenyPath -AclObject $denyAcl -ErrorAction Stop
 $denied=(& $probe -LegacyWorkerRoot $aclDenyPath -LegacyProgramDataRoot $data -OrbitWorkerRoot $orbit -OrbitProgramDataRoot $orbitData)|ConvertFrom-Json
 Assert ($denied.status -eq 'BLOCKED' -and @($denied.reasons) -contains 'ACL_READ_DENY_PRESENT' -and $denied.migration_permitted -eq $false) 'ACL explicit read deny detected even under elevated runner'
 Set-Acl -LiteralPath $aclDenyPath -AclObject $aclOriginal -ErrorAction Stop
 $aclOriginal=$null
 $short=(& $probe -LegacyWorkerRoot ($root+'\\CACHE~1\\legacy') -LegacyProgramDataRoot $data -OrbitWorkerRoot $orbit -OrbitProgramDataRoot $orbitData)|ConvertFrom-Json
 Assert ($short.status -eq 'BLOCKED' -and @($short.reasons) -contains 'PHYSICAL_ROOT_IDENTITY_UNVERIFIED') 'NTFS short-name aliases remain untrusted'
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
 if($aclOriginal -and $aclDenyPath){
   try { Set-Acl -LiteralPath $aclDenyPath -AclObject $aclOriginal -ErrorAction Stop } catch { }
 }
 if($substDrive){
   & subst.exe $substDrive /D | Out-Null
 }
 Remove-Item -LiteralPath $root -Force -Recurse -ErrorAction SilentlyContinue
}
