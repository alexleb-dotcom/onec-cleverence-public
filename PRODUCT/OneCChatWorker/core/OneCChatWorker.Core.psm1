Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:ProductVersion = '1.0.0-preview1'
$script:DefaultWorkerRoot = 'C:\OneCChatWorker'
$script:DefaultProgramDataRoot = 'C:\ProgramData\OneCChatWorker'
$script:ReaderName = 'OneCSourceReader'
$script:DefaultRelayUrl = 'wss://onec-g1q1-relay.alex-lebad1.workers.dev/helper'
$script:NodeVersion = '26.7.0'
$script:RgVersion = '15.2.0'

function Assert-SafeId {
    param([Parameter(Mandatory)][string]$Value,[string]$Name='id')
    if ($Value -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$') { throw "INVALID_$($Name.ToUpperInvariant()): $Value" }
    return $Value
}

function Get-Sha256File {
    param([Parameter(Mandatory)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "FILE_NOT_FOUND: $Path" }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-CatalogPath {
    param([string]$WorkerRoot=$script:DefaultWorkerRoot)
    Join-Path $WorkerRoot 'projects.json'
}

function Read-WorkerCatalog {
    param([string]$WorkerRoot=$script:DefaultWorkerRoot,[switch]$AllowMissing)
    $p=Get-CatalogPath $WorkerRoot
    if(-not(Test-Path -LiteralPath $p -PathType Leaf)){
        if($AllowMissing){ return [pscustomobject]@{schema_version=1;projects=@()} }
        throw "CATALOG_NOT_FOUND: $p"
    }
    $doc=Get-Content -LiteralPath $p -Raw -Encoding UTF8 | ConvertFrom-Json
    if($doc.schema_version -ne 1){ throw 'CATALOG_SCHEMA_UNSUPPORTED' }
    if($null -eq $doc.projects){ throw 'CATALOG_PROJECTS_REQUIRED' }
    return $doc
}

function Write-JsonAtomic {
    param([Parameter(Mandatory)]$Value,[Parameter(Mandatory)][string]$Path)
    $parent=Split-Path -Parent $Path
    if(-not(Test-Path -LiteralPath $parent)){New-Item -ItemType Directory -Force -Path $parent|Out-Null}
    $tmp=$Path+'.tmp-'+[Guid]::NewGuid().ToString('N')
    $json=$Value|ConvertTo-Json -Depth 30
    [IO.File]::WriteAllText($tmp,$json+[Environment]::NewLine,(New-Object Text.UTF8Encoding($false)))
    Move-Item -LiteralPath $tmp -Destination $Path -Force
}

function Write-WorkerCatalog {
    param([Parameter(Mandatory)]$Catalog,[string]$WorkerRoot=$script:DefaultWorkerRoot)
    Write-JsonAtomic $Catalog (Get-CatalogPath $WorkerRoot)
}

function Get-CatalogHash {
    param([string]$WorkerRoot=$script:DefaultWorkerRoot)
    Get-Sha256File (Get-CatalogPath $WorkerRoot)
}

function Get-TreeDigest {
    param([Parameter(Mandatory)][string]$Root)
    if(-not(Test-Path -LiteralPath $Root -PathType Container)){throw "TREE_NOT_FOUND: $Root"}
    $rootFull=[IO.Path]::GetFullPath($Root).TrimEnd('\')
    $items=@(Get-ChildItem -LiteralPath $rootFull -Recurse -Force -File | Sort-Object FullName)
    $reparse=@(Get-ChildItem -LiteralPath $rootFull -Recurse -Force | Where-Object {($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0})
    if($reparse.Count -gt 0){throw "REPARSE_POINT: $($reparse[0].FullName)"}
    $sha=[Security.Cryptography.SHA256]::Create()
    try{
        foreach($f in $items){
            $rel=$f.FullName.Substring($rootFull.Length).TrimStart('\').Replace('\','/')
            $fh=(Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
            $row=[string]::Join([char]9,@($rel,[string]$f.Length,$fh))+[Environment]::NewLine
            $line=[Text.Encoding]::UTF8.GetBytes($row)
            $null=$sha.TransformBlock($line,0,$line.Length,$line,0)
        }
        $null=$sha.TransformFinalBlock([byte[]]@(),0,0)
        $digest=([BitConverter]::ToString($sha.Hash)).Replace('-','').ToLowerInvariant()
    } finally {$sha.Dispose()}
    $sum=($items|Measure-Object Length -Sum).Sum
    if($null -eq $sum){$sum=0}
    [pscustomobject]@{sha256=$digest;files=$items.Count;bytes=[int64]$sum}
}

function Assert-OneCExportRoot {
    param([Parameter(Mandatory)][string]$Path)
    if(-not(Test-Path -LiteralPath $Path -PathType Container)){throw "SOURCE_FOLDER_NOT_FOUND: $Path"}
    $cfg=Join-Path $Path 'Configuration.xml'
    if(-not(Test-Path -LiteralPath $cfg -PathType Leaf)){throw "ONEC_CONFIGURATION_XML_MISSING: $Path"}
    if((Get-Item -LiteralPath $Path).Attributes -band [IO.FileAttributes]::ReparsePoint){throw "REPARSE_POINT: $Path"}
}

function Find-Project {
    param([Parameter(Mandatory)]$Catalog,[Parameter(Mandatory)][string]$ProjectId)
    @($Catalog.projects|Where-Object {$_.project_id -eq $ProjectId})|Select-Object -First 1
}

function New-WorkerProject {
    param([Parameter(Mandatory)][string]$ProjectId,[string]$DisplayName,[string]$WorkerRoot=$script:DefaultWorkerRoot)
    Assert-SafeId $ProjectId 'project_id'|Out-Null
    $c=Read-WorkerCatalog -WorkerRoot $WorkerRoot -AllowMissing
    if(Find-Project $c $ProjectId){throw 'PROJECT_ALREADY_EXISTS'}
    $p=[pscustomobject]@{project_id=$ProjectId;display_name=$(if($DisplayName){$DisplayName}else{$ProjectId});active=$true;participants=@()}
    $c.projects=@($c.projects)+@($p)
    Write-WorkerCatalog $c $WorkerRoot
    $p
}

function Add-WorkerParticipant {
    param([Parameter(Mandatory)][string]$ProjectId,[Parameter(Mandatory)][string]$ParticipantId,[ValidateSet('ONEC','CLEVERENCE')][string]$Platform='ONEC',[string]$Role,[string]$WorkerRoot=$script:DefaultWorkerRoot)
    Assert-SafeId $ParticipantId 'participant_id'|Out-Null
    $c=Read-WorkerCatalog $WorkerRoot;$p=Find-Project $c $ProjectId;if(!$p){throw 'PROJECT_NOT_FOUND'}
    if(@($p.participants|Where-Object {$_.participant_id -eq $ParticipantId}).Count){throw 'PARTICIPANT_ALREADY_EXISTS'}
    $n=[pscustomobject]@{participant_id=$ParticipantId;platform=$Platform;role=$Role;active=$true;target=[pscustomobject]@{main=$null;extensions=@()};reference=$null}
    $p.participants=@($p.participants)+@($n);Write-WorkerCatalog $c $WorkerRoot;$n
}

function Set-WorkerMain {
    param([Parameter(Mandatory)][string]$ProjectId,[Parameter(Mandatory)][string]$ParticipantId,[Parameter(Mandatory)][string]$SourcePath,[switch]$ReplaceExisting,[string]$WorkerRoot=$script:DefaultWorkerRoot)
    $c=Read-WorkerCatalog $WorkerRoot;$p=Find-Project $c $ProjectId;if(!$p){throw 'PROJECT_NOT_FOUND'}
    $part=@($p.participants|Where-Object {$_.participant_id -eq $ParticipantId})|Select-Object -First 1;if(!$part){throw 'PARTICIPANT_NOT_FOUND'}
    if($part.platform -eq 'ONEC'){Assert-OneCExportRoot $SourcePath}
    $part.target.main=[pscustomobject]@{active=$true;source_path=[IO.Path]::GetFullPath($SourcePath);replace_existing=[bool]$ReplaceExisting}
    Write-WorkerCatalog $c $WorkerRoot;$part.target.main
}

function Add-WorkerExtension {
    param([Parameter(Mandatory)][string]$ProjectId,[Parameter(Mandatory)][string]$ParticipantId,[Parameter(Mandatory)][string]$ExtensionId,[Parameter(Mandatory)][string]$SourcePath,[switch]$ReplaceExisting,[string]$WorkerRoot=$script:DefaultWorkerRoot)
    Assert-SafeId $ExtensionId 'extension_id'|Out-Null
    $c=Read-WorkerCatalog $WorkerRoot;$p=Find-Project $c $ProjectId;if(!$p){throw 'PROJECT_NOT_FOUND'}
    $part=@($p.participants|Where-Object {$_.participant_id -eq $ParticipantId})|Select-Object -First 1;if(!$part){throw 'PARTICIPANT_NOT_FOUND'}
    if(@($part.target.extensions|Where-Object {$_.extension_id -eq $ExtensionId -and $_.active -ne $false}).Count){throw 'EXTENSION_ALREADY_EXISTS'}
    if($part.platform -eq 'ONEC'){Assert-OneCExportRoot $SourcePath}
    $e=[pscustomobject]@{extension_id=$ExtensionId;active=$true;source_path=[IO.Path]::GetFullPath($SourcePath);replace_existing=[bool]$ReplaceExisting}
    $part.target.extensions=@($part.target.extensions)+@($e);Write-WorkerCatalog $c $WorkerRoot;$e
}

function Disable-WorkerCatalogItem {
    param([Parameter(Mandatory)][ValidateSet('PROJECT','PARTICIPANT','EXTENSION')][string]$Kind,[Parameter(Mandatory)][string]$ProjectId,[string]$ParticipantId,[string]$ExtensionId,[string]$WorkerRoot=$script:DefaultWorkerRoot)
    $c=Read-WorkerCatalog $WorkerRoot;$p=Find-Project $c $ProjectId;if(!$p){throw 'PROJECT_NOT_FOUND'}
    if($Kind -eq 'PROJECT'){$p.active=$false}
    else {
        $part=@($p.participants|Where-Object {$_.participant_id -eq $ParticipantId})|Select-Object -First 1;if(!$part){throw 'PARTICIPANT_NOT_FOUND'}
        if($Kind -eq 'PARTICIPANT'){$part.active=$false}
        else {$e=@($part.target.extensions|Where-Object {$_.extension_id -eq $ExtensionId})|Select-Object -First 1;if(!$e){throw 'EXTENSION_NOT_FOUND'};$e.active=$false}
    }
    Write-WorkerCatalog $c $WorkerRoot
}

function Copy-ArtifactSafely {
    param([Parameter(Mandatory)][string]$Source,[Parameter(Mandatory)][string]$Target,[switch]$ReplaceExisting,[Parameter(Mandatory)][string]$ProjectRoot,[Parameter(Mandatory)][string]$ArchiveKey)
    $srcDigest=Get-TreeDigest $Source
    $archive=$null
    if(Test-Path -LiteralPath $Target){
        $targetDigest=Get-TreeDigest $Target
        if($targetDigest.sha256 -eq $srcDigest.sha256){return [pscustomobject]@{digest=$srcDigest;changed=$false;archived=$null}}
        if(-not $ReplaceExisting){throw "TARGET_CONFLICT: $Target"}
        $stamp=(Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
        $archive=Join-Path $ProjectRoot ("Detached\$ArchiveKey\$stamp")
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $archive)|Out-Null
        Move-Item -LiteralPath $Target -Destination $archive
    }
    $parent=Split-Path -Parent $Target;New-Item -ItemType Directory -Force -Path $parent|Out-Null
    $stage=$Target+'.stage-'+[Guid]::NewGuid().ToString('N')
    Copy-Item -LiteralPath $Source -Destination $stage -Recurse
    $stageDigest=Get-TreeDigest $stage
    if($stageDigest.sha256 -ne $srcDigest.sha256){Remove-Item -LiteralPath $stage -Recurse -Force;throw 'COPY_VERIFY_FAILED'}
    Move-Item -LiteralPath $stage -Destination $Target
    [pscustomobject]@{digest=$srcDigest;changed=$true;archived=$archive}
}

function Apply-ProjectAcl {
    param([Parameter(Mandatory)][string]$ProjectRoot)
    $reader="$env:COMPUTERNAME\$($script:ReaderName)"
    if(-not(Get-LocalUser -Name $script:ReaderName -ErrorAction SilentlyContinue)){return}
    & icacls.exe $ProjectRoot /grant:r ($reader+':(RX)') | Out-Null
    $participants=Join-Path $ProjectRoot 'Participants'
    $output=Join-Path $ProjectRoot 'Output'
    if(Test-Path -LiteralPath $participants){& icacls.exe $participants /grant:r ($reader+':(OI)(CI)(RX)') /T | Out-Null}
    if(Test-Path -LiteralPath $output){& icacls.exe $output /grant:r ($reader+':(OI)(CI)(M)') /T | Out-Null}
}

function Apply-WorkerProject {
    param([Parameter(Mandatory)][string]$ProjectId,[string]$WorkerRoot=$script:DefaultWorkerRoot)
    $c=Read-WorkerCatalog $WorkerRoot;$p=Find-Project $c $ProjectId;if(!$p){throw 'PROJECT_NOT_FOUND'};if($p.active -eq $false){throw 'PROJECT_INACTIVE'}
    $catalogHash=Get-CatalogHash $WorkerRoot
    $projectRoot=Join-Path $WorkerRoot $ProjectId
    $manifestDir=Join-Path $projectRoot 'ProjectManifest'
    New-Item -ItemType Directory -Force -Path $manifestDir,(Join-Path $projectRoot 'Participants'),(Join-Path $projectRoot 'Output')|Out-Null
    $manifestParticipants=@()
    foreach($part in @($p.participants|Where-Object {$_.active -ne $false})){
        if($part.platform -ne 'ONEC'){throw "PLATFORM_NOT_IMPLEMENTED_1C_FIRST: $($part.platform)"}
        $pid=Assert-SafeId $part.participant_id 'participant_id'
        $mPart=[ordered]@{participant_id=$pid;platform=$part.platform;role=$part.role;active=$true;target=[ordered]@{main=$null;extensions=@()}}
        if($part.target.main -and $part.target.main.active -ne $false){
            if($part.platform -eq 'ONEC'){Assert-OneCExportRoot $part.target.main.source_path}
            $rel="Participants/$pid/Target/Main";$target=Join-Path $projectRoot ($rel.Replace('/','\'))
            $copy=Copy-ArtifactSafely -Source $part.target.main.source_path -Target $target -ReplaceExisting:([bool]$part.target.main.replace_existing) -ProjectRoot $projectRoot -ArchiveKey "$pid\Target\Main"
            $mPart.target.main=[ordered]@{artifact_id='main';active=$true;canonical_path=$rel;source_path=$part.target.main.source_path;tree_sha256=$copy.digest.sha256;files=$copy.digest.files;bytes=$copy.digest.bytes;configuration_xml_sha256=$(if($part.platform -eq 'ONEC'){Get-Sha256File (Join-Path $target 'Configuration.xml')}else{$null})}
        }
        foreach($ext in @($part.target.extensions|Where-Object {$_.active -ne $false})){
            $eid=Assert-SafeId $ext.extension_id 'extension_id'
            if($part.platform -eq 'ONEC'){Assert-OneCExportRoot $ext.source_path}
            $rel="Participants/$pid/Target/Extensions/$eid";$target=Join-Path $projectRoot ($rel.Replace('/','\'))
            $copy=Copy-ArtifactSafely -Source $ext.source_path -Target $target -ReplaceExisting:([bool]$ext.replace_existing) -ProjectRoot $projectRoot -ArchiveKey "$pid\Target\Extensions\$eid"
            $mPart.target.extensions+=,[ordered]@{extension_id=$eid;artifact_id=$eid;active=$true;canonical_path=$rel;source_path=$ext.source_path;tree_sha256=$copy.digest.sha256;files=$copy.digest.files;bytes=$copy.digest.bytes;configuration_xml_sha256=$(if($part.platform -eq 'ONEC'){Get-Sha256File (Join-Path $target 'Configuration.xml')}else{$null})}
        }
        $manifestParticipants+=,[pscustomobject]$mPart
    }
    if($manifestParticipants.Count -eq 0){throw 'PROJECT_HAS_NO_ACTIVE_PARTICIPANTS'}
    $manifest=[ordered]@{schema_version=1;project_id=$p.project_id;display_name=$p.display_name;active=$true;topology_authority='RP-20261004-026';catalog_sha256=$catalogHash;applied_utc=(Get-Date).ToUniversalTime().ToString('o');project_root=$projectRoot;participants=$manifestParticipants;output_relative='Output'}
    $manifestPath=Join-Path $manifestDir 'project.json'
    if(Test-Path -LiteralPath $manifestPath -PathType Leaf){
        $oldManifest=Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $desired=New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
        foreach($dp in @($manifest.participants)){
            if($dp.target.main){$null=$desired.Add([string]$dp.target.main.canonical_path)}
            foreach($de in @($dp.target.extensions)){$null=$desired.Add([string]$de.canonical_path)}
        }
        foreach($op in @($oldManifest.participants)){
            $oldArts=@();if($op.target.main){$oldArts+=,$op.target.main};$oldArts+=@($op.target.extensions)
            foreach($oa in $oldArts){
                $rel=[string]$oa.canonical_path
                if(-not $desired.Contains($rel)){
                    $abs=Join-Path $projectRoot ($rel.Replace('/','\'))
                    if(Test-Path -LiteralPath $abs){
                        $stamp=(Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
                        $detached=Join-Path $projectRoot ("Detached\Deactivated\$stamp\"+$rel.Replace('/','\'))
                        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $detached)|Out-Null
                        Move-Item -LiteralPath $abs -Destination $detached
                    }
                }
            }
        }
    }
    Write-JsonAtomic $manifest $manifestPath
    Apply-ProjectAcl -ProjectRoot $projectRoot
    Verify-WorkerProject -ProjectId $ProjectId -WorkerRoot $WorkerRoot
}

function Verify-WorkerProject {
    param([Parameter(Mandatory)][string]$ProjectId,[string]$WorkerRoot=$script:DefaultWorkerRoot)
    $catalog=Read-WorkerCatalog $WorkerRoot;$p=Find-Project $catalog $ProjectId;if(!$p){throw 'PROJECT_NOT_FOUND'}
    $projectRoot=Join-Path $WorkerRoot $ProjectId;$manifestPath=Join-Path $projectRoot 'ProjectManifest\project.json'
    if(-not(Test-Path -LiteralPath $manifestPath -PathType Leaf)){return [pscustomobject]@{project_id=$ProjectId;status='APPLY_REQUIRED';reason='MANIFEST_MISSING'}}
    $m=Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8|ConvertFrom-Json
    $catalogHash=Get-CatalogHash $WorkerRoot
    if($m.catalog_sha256 -ne $catalogHash){return [pscustomobject]@{project_id=$ProjectId;status='DRIFT_APPLY_REQUIRED';reason='CATALOG_HASH_MISMATCH';manifest_catalog_sha256=$m.catalog_sha256;catalog_sha256=$catalogHash}}
    $errors=New-Object System.Collections.Generic.List[string]
    foreach($part in @($m.participants)){
        $artifacts=@();if($part.target.main){$artifacts+=,$part.target.main};$artifacts+=@($part.target.extensions)
        foreach($a in $artifacts){
            $abs=Join-Path $projectRoot ($a.canonical_path.Replace('/','\'))
            if(-not(Test-Path -LiteralPath $abs -PathType Container)){$errors.Add("MISSING:$($a.canonical_path)");continue}
            try{$dig=Get-TreeDigest $abs;if($dig.sha256 -ne $a.tree_sha256){$errors.Add("HASH_MISMATCH:$($a.canonical_path)")}}catch{$errors.Add("VERIFY_ERROR:$($a.canonical_path):$($_.Exception.Message)")}
            if($part.platform -eq 'ONEC' -and -not(Test-Path -LiteralPath (Join-Path $abs 'Configuration.xml') -PathType Leaf)){$errors.Add("ONEC_LAYOUT:$($a.canonical_path)")}
        }
    }
    if(-not(Test-Path -LiteralPath (Join-Path $projectRoot 'Output') -PathType Container)){$errors.Add('OUTPUT_MISSING')}
    [pscustomobject]@{project_id=$ProjectId;status=$(if($errors.Count){'FAIL'}else{'READY'});catalog_sha256=$catalogHash;manifest_sha256=Get-Sha256File $manifestPath;errors=@($errors)}
}

function Get-WorkerStatus {
    param([string]$WorkerRoot=$script:DefaultWorkerRoot,[string]$ProgramDataRoot=$script:DefaultProgramDataRoot)
    $catalog=Read-WorkerCatalog -WorkerRoot $WorkerRoot -AllowMissing
    $runtimeState=Join-Path $ProgramDataRoot 'runtime\active-admission.json'
    $active=$null;if(Test-Path -LiteralPath $runtimeState){try{$active=Get-Content $runtimeState -Raw|ConvertFrom-Json}catch{}}
    $rows=@()
    foreach($p in @($catalog.projects)){
        $v=try{Verify-WorkerProject -ProjectId $p.project_id -WorkerRoot $WorkerRoot}catch{[pscustomobject]@{status='FAIL';reason=$_.Exception.Message}}
        $rows+=,[pscustomobject]@{project_id=$p.project_id;display_name=$p.display_name;active=($p.active -ne $false);verification=$v.status}
    }
    [pscustomobject]@{product_version=$script:ProductVersion;worker_root=$WorkerRoot;catalog_path=Get-CatalogPath $WorkerRoot;projects=$rows;active_admission=$active}
}

function Write-ProviderConfig {
    param([Parameter(Mandatory)][string]$ProjectId,[string]$WorkerRoot=$script:DefaultWorkerRoot,[string]$ProgramDataRoot=$script:DefaultProgramDataRoot)
    $rg=Join-Path $ProgramDataRoot 'runtime\rg.exe'
    if(-not(Test-Path -LiteralPath $rg -PathType Leaf)){throw 'RG_NOT_INSTALLED'}
    $cfg=[ordered]@{schema_version=1;contract_id='onecchatworker';contract_version='1.0';provider_version='1.0.0';worker_root=$WorkerRoot;admitted_projects=@($ProjectId);rg_path=$rg;audit_path=(Join-Path $ProgramDataRoot 'audit\reader-audit.jsonl');limits=[ordered]@{max_list_depth=4;max_list_entries=2000;default_read_lines=120;max_read_lines=400;max_context_lines=20;max_pattern_chars=512;default_search_matches=20;max_search_matches=100;search_timeout_ms=30000;max_rg_output_bytes=33554432;max_source_file_bytes=16777216;max_artifact_read_bytes=4194304;max_artifact_file_bytes=4194304;max_encoded_content_chars=6000000;max_batch_files=16;max_batch_total_bytes=12582912}}
    Write-JsonAtomic $cfg (Join-Path $ProgramDataRoot 'provider\provider-config.json')
}

function New-Admission {
    param([Parameter(Mandatory)][string]$ProjectId,[Parameter(Mandatory)][string]$TaskId,[string]$WorkerRoot=$script:DefaultWorkerRoot,[string]$ProgramDataRoot=$script:DefaultProgramDataRoot,[string]$RelayUrl=$script:DefaultRelayUrl)
    Assert-SafeId $TaskId 'task_id'|Out-Null
    $v=Verify-WorkerProject -ProjectId $ProjectId -WorkerRoot $WorkerRoot
    if($v.status -ne 'READY'){throw "PROJECT_NOT_READY: $($v.status)"}
    $manifestDoc=Get-Content -LiteralPath (Join-Path $WorkerRoot "$ProjectId\ProjectManifest\project.json") -Raw -Encoding UTF8 | ConvertFrom-Json
    if(@($manifestDoc.participants|Where-Object {$_.platform -ne 'ONEC'}).Count){throw 'PLATFORM_NOT_IMPLEMENTED_1C_FIRST'}
    Write-ProviderConfig -ProjectId $ProjectId -WorkerRoot $WorkerRoot -ProgramDataRoot $ProgramDataRoot
    $manifest=Join-Path $WorkerRoot "$ProjectId\ProjectManifest\project.json"
    $a=[ordered]@{schema_version=1;project_id=$ProjectId;task_id=$TaskId;created_utc=(Get-Date).ToUniversalTime().ToString('o');manifest_path=$manifest;provider_config_path=(Join-Path $ProgramDataRoot 'provider\provider-config.json');relay_url=$RelayUrl;helper_secret_path=(Join-Path $ProgramDataRoot 'secrets\helper-secret.txt');runtime_dir=(Join-Path $ProgramDataRoot 'runtime');caps=[ordered]@{ttl_minutes=360;max_requests=32;max_cumulative_result_bytes=36000;max_result_bytes=3000;max_search_matches=8;max_read_lines=20;max_write_file_bytes=32768;max_task_bytes=131072;max_task_files=8;max_read_chunk_bytes=1800}}
    Write-JsonAtomic $a (Join-Path $ProgramDataRoot 'runtime\active-admission.json')
    $a
}

function Test-IsAdministrator {
    $id=[Security.Principal.WindowsIdentity]::GetCurrent();$p=New-Object Security.Principal.WindowsPrincipal($id)
    $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Invoke-Precheck {
    param()
    $node=Get-Command node.exe -ErrorAction SilentlyContinue
    $winget=Get-Command winget.exe -ErrorAction SilentlyContinue
    $rg=Get-Command rg.exe -ErrorAction SilentlyContinue
    [pscustomobject]@{powershell=$PSVersionTable.PSVersion.ToString();administrator=(Test-IsAdministrator);winget=[bool]$winget;node=$(if($node){(& $node.Source --version).Trim()}else{$null});node_required=$script:NodeVersion;rg=$(if($rg){((& $rg.Source --version|Select-Object -First 1)-replace '^ripgrep\s+','').Trim()}else{$null});rg_required=$script:RgVersion}
}

function Find-RipgrepExecutable {
    $cmd=Get-Command rg.exe -ErrorAction SilentlyContinue
    if($cmd){return $cmd.Source}
    $candidates=@(
        (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links\rg.exe'),
        (Join-Path $env:ProgramFiles 'WinGet\Links\rg.exe')
    )
    foreach($p in $candidates){if($p -and (Test-Path -LiteralPath $p -PathType Leaf)){return $p}}
    foreach($root in @((Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages'),(Join-Path $env:ProgramFiles 'WinGet\Packages'))){
        if(-not $root -or -not(Test-Path -LiteralPath $root -PathType Container)){continue}
        $hit=Get-ChildItem -LiteralPath $root -Filter rg.exe -File -Recurse -ErrorAction SilentlyContinue |
            Where-Object {$_.FullName -match 'BurntSushi\.ripgrep\.MSVC'} | Select-Object -First 1
        if($hit){return $hit.FullName}
    }
    return $null
}

function Ensure-PinnedDependencies {
    param([string]$ProgramDataRoot=$script:DefaultProgramDataRoot)
    if(-not(Test-IsAdministrator)){throw 'ADMIN_REQUIRED'}
    $node=Get-Command node.exe -ErrorAction SilentlyContinue
    if(-not $node -or ((& $node.Source --version).Trim() -ne "v$($script:NodeVersion)")){
        if(-not(Get-Command winget.exe -ErrorAction SilentlyContinue)){throw 'WAITING_FOR_NODE: winget unavailable'}
        & winget.exe install --id OpenJS.NodeJS --version $script:NodeVersion --exact --silent --accept-package-agreements --accept-source-agreements
        if($LASTEXITCODE -ne 0){throw 'NODE_INSTALL_FAILED'}
    }
    $rgPath=Find-RipgrepExecutable
    $rgVersion=$null
    if($rgPath){$rgVersion=(((& $rgPath --version|Select-Object -First 1)-replace '^ripgrep\s+','').Trim())}
    if(-not $rgPath -or $rgVersion -ne $script:RgVersion){
        if(-not(Get-Command winget.exe -ErrorAction SilentlyContinue)){throw 'WAITING_FOR_RG: winget unavailable'}
        & winget.exe install --id BurntSushi.ripgrep.MSVC --version $script:RgVersion --exact --silent --accept-package-agreements --accept-source-agreements
        if($LASTEXITCODE -ne 0){throw 'RG_INSTALL_FAILED'}
        $rgPath=Find-RipgrepExecutable
    }
    if(-not $rgPath){throw 'RG_NOT_FOUND_AFTER_INSTALL'}
    $actualRg=(((& $rgPath --version|Select-Object -First 1)-replace '^ripgrep\s+','').Trim())
    if($actualRg -ne $script:RgVersion){throw "RG_VERSION_MISMATCH: $actualRg"}
    $runtime=Join-Path $ProgramDataRoot 'runtime';New-Item -ItemType Directory -Force -Path $runtime|Out-Null
    Copy-Item -LiteralPath $rgPath -Destination (Join-Path $runtime 'rg.exe') -Force
}

function Install-OneCChatWorker {
    param([Parameter(Mandatory)][string]$PackageRoot,[string]$WorkerRoot=$script:DefaultWorkerRoot,[string]$ProgramDataRoot=$script:DefaultProgramDataRoot,[switch]$SkipDependencies)
    if(-not(Test-IsAdministrator)){throw 'ADMIN_REQUIRED'}
    if(-not $SkipDependencies){Ensure-PinnedDependencies -ProgramDataRoot $ProgramDataRoot}
    foreach($p in @($WorkerRoot,$ProgramDataRoot,(Join-Path $ProgramDataRoot 'runtime'),(Join-Path $ProgramDataRoot 'provider'),(Join-Path $ProgramDataRoot 'helper'),(Join-Path $ProgramDataRoot 'audit'),(Join-Path $ProgramDataRoot 'secrets'),(Join-Path $ProgramDataRoot 'product'))){New-Item -ItemType Directory -Force -Path $p|Out-Null}
    if(-not(Get-LocalUser -Name $script:ReaderName -ErrorAction SilentlyContinue)){
        $pw=Read-Host -Prompt "Set local password for $($script:ReaderName)" -AsSecureString
        New-LocalUser -Name $script:ReaderName -Password $pw -Description 'OneCChatWorker non-admin bounded source/output identity'|Out-Null
    }
    $reader="$env:COMPUTERNAME\$($script:ReaderName)"
    Copy-Item -LiteralPath (Join-Path $PackageRoot 'runtime\source-reader-integration.mjs') -Destination (Join-Path $ProgramDataRoot 'provider\source-reader-integration.mjs') -Force
    Copy-Item -LiteralPath (Join-Path $PackageRoot 'runtime\hosted-helper.mjs') -Destination (Join-Path $ProgramDataRoot 'helper\hosted-helper.mjs') -Force
    Copy-Item -LiteralPath (Join-Path $PackageRoot 'core\OneCChatWorker.Core.psm1') -Destination (Join-Path $ProgramDataRoot 'product\OneCChatWorker.Core.psm1') -Force
    Copy-Item -LiteralPath (Join-Path $PackageRoot 'runtime.lock.json') -Destination (Join-Path $ProgramDataRoot 'product\runtime.lock.json') -Force
    Copy-Item -LiteralPath (Join-Path $PackageRoot 'README.md') -Destination (Join-Path $ProgramDataRoot 'product\README.md') -Force
    Copy-Item -LiteralPath (Join-Path $PackageRoot 'OneCChatWorker.ps1') -Destination (Join-Path $WorkerRoot 'OneCChatWorker.ps1') -Force
    if(-not(Test-Path -LiteralPath (Get-CatalogPath $WorkerRoot))){Write-WorkerCatalog ([pscustomobject]@{schema_version=1;projects=@()}) $WorkerRoot}
    & icacls.exe $WorkerRoot /grant:r ($reader+':(RX)') | Out-Null
    & icacls.exe $ProgramDataRoot /grant:r ($reader+':(RX)') | Out-Null
    & icacls.exe (Join-Path $ProgramDataRoot 'runtime') /grant:r ($reader+':(OI)(CI)M') | Out-Null
    & icacls.exe (Join-Path $ProgramDataRoot 'audit') /grant:r ($reader+':(OI)(CI)M') | Out-Null
    $state=[ordered]@{schema_version=1;product_version=$script:ProductVersion;installed_utc=(Get-Date).ToUniversalTime().ToString('o');worker_root=$WorkerRoot;program_data_root=$ProgramDataRoot;reader_identity=$reader;node_version=$script:NodeVersion;rg_version=$script:RgVersion}
    Write-JsonAtomic $state (Join-Path $ProgramDataRoot 'installed-state.json')
    [pscustomobject]@{status='INSTALLED_WAITING_FOR_REMOTE_AUTH';installed_state=(Join-Path $ProgramDataRoot 'installed-state.json');next='SETTINGS: configure helper enrollment secret, then APPLY/VERIFY/START'}
}

function Set-HelperEnrollmentSecret {
    param([string]$ProgramDataRoot=$script:DefaultProgramDataRoot)
    if(-not(Test-IsAdministrator)){throw 'ADMIN_REQUIRED'}
    $secure=Read-Host -Prompt 'Paste helper enrollment secret' -AsSecureString
    $b=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try{
        $plain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($b);if($plain.Length -lt 20){throw 'HELPER_SECRET_TOO_SHORT'}
        $secretPath=Join-Path $ProgramDataRoot 'secrets\helper-secret.txt'
        [IO.File]::WriteAllText($secretPath,$plain,(New-Object Text.UTF8Encoding($false)))
        $reader="$env:COMPUTERNAME\$($script:ReaderName)"
        & icacls.exe $secretPath /inheritance:r /grant:r '*S-1-5-18:F' '*S-1-5-32-544:F' ($reader+':R') | Out-Null
    }finally{if($b -ne [IntPtr]::Zero){[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b)};$plain=$null}
}

function Start-WorkerAdmission {
    param([Parameter(Mandatory)][string]$ProjectId,[Parameter(Mandatory)][string]$TaskId,[string]$WorkerRoot=$script:DefaultWorkerRoot,[string]$ProgramDataRoot=$script:DefaultProgramDataRoot)
    if(-not(Test-Path -LiteralPath (Join-Path $ProgramDataRoot 'secrets\helper-secret.txt'))){throw 'REMOTE_AUTH_REQUIRED'}
    New-Admission -ProjectId $ProjectId -TaskId $TaskId -WorkerRoot $WorkerRoot -ProgramDataRoot $ProgramDataRoot|Out-Null
    $helper=Join-Path $ProgramDataRoot 'runtime\hosted-helper.mjs'
    $existing=@(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue|Where-Object{$_.Name -eq 'node.exe' -and $_.CommandLine -and $_.CommandLine.Contains($helper)})
    if($existing.Count){throw 'ADMISSION_ALREADY_RUNNING'}
    $runAs="$env:SystemRoot\System32\runas.exe"
    $program='powershell.exe -NoProfile -Command "& ''C:\Program Files\nodejs\node.exe'' '''+$helper+''' "'
    & $runAs "/profile" "/user:$env:COMPUTERNAME\$($script:ReaderName)" $program
    if($LASTEXITCODE -ne 0){throw "RUNAS_FAILED_OR_CANCELLED: $LASTEXITCODE"}
    [pscustomobject]@{status='START_REQUESTED';project_id=$ProjectId;task_id=$TaskId}
}

function Stop-WorkerAdmission {
    param([string]$ProgramDataRoot=$script:DefaultProgramDataRoot)
    if(-not(Test-IsAdministrator)){throw 'ADMIN_REQUIRED'}
    $helper=Join-Path $ProgramDataRoot 'runtime\hosted-helper.mjs'
    $procs=@(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue|Where-Object{$_.Name -eq 'node.exe' -and $_.CommandLine -and $_.CommandLine.Contains($helper)})
    foreach($p in $procs){Stop-Process -Id $p.ProcessId -Force}
    Remove-Item -LiteralPath (Join-Path $ProgramDataRoot 'runtime\active-admission.json') -Force -ErrorAction SilentlyContinue
    [pscustomobject]@{status='OFF';stopped=$procs.Count}
}

function Repair-WorkerProject {
    param([Parameter(Mandatory)][string]$ProjectId,[string]$WorkerRoot=$script:DefaultWorkerRoot)
    $v=Verify-WorkerProject -ProjectId $ProjectId -WorkerRoot $WorkerRoot
    if($v.status -eq 'READY'){return $v}
    if($v.status -eq 'DRIFT_APPLY_REQUIRED' -or $v.status -eq 'APPLY_REQUIRED'){return Apply-WorkerProject -ProjectId $ProjectId -WorkerRoot $WorkerRoot}
    throw "REPAIR_REFUSED_DESTRUCTIVE_OR_UNKNOWN: $($v|ConvertTo-Json -Compress)"
}

function Get-UninstallPlan {
    param([string]$WorkerRoot=$script:DefaultWorkerRoot,[string]$ProgramDataRoot=$script:DefaultProgramDataRoot)
    [pscustomobject]@{action='UNINSTALL_GUIDANCE';safe_default=@('STOP admission','remove installed runtime/launchers only','retain projects.json','retain all project Participants Source copies','retain Output proposals/evidence','retain Detached archives');explicitly_not_performed=@('recursive project deletion','external business Source deletion','Output purge');runtime_root=$ProgramDataRoot;worker_root=$WorkerRoot}
}

Export-ModuleMember -Function *
