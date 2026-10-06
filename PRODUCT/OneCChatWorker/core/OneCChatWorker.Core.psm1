Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:ProductVersion = '1.0.0-preview1'
$script:DefaultWorkerRoot = 'C:\OneCChatWorker'
$script:DefaultProgramDataRoot = 'C:\ProgramData\OneCChatWorker'
$script:ReaderName = 'OneCSourceReader'
$script:DefaultRelayUrl = 'wss://onec-g1q1-relay.alex-lebad1.workers.dev/helper'
$script:NodeVersion = '26.7.0'
$script:RgVersion = '15.2.0'
$script:OperationLogMaxBytes = 2097152

function Get-RipgrepSemanticVersion {
    param([Parameter(Mandatory)][string]$VersionLine)
    $line=$VersionLine.Trim()
    $match=[regex]::Match($line,'^ripgrep\s+([0-9]+(?:\.[0-9]+){2})(?:\s+\(rev\s+[^)]+\))?$')
    if(-not $match.Success){throw "RG_VERSION_OUTPUT_INVALID: $line"}
    $match.Groups[1].Value
}

function Get-WorkerOperationRoot {
    param([string]$ProgramDataRoot=$script:DefaultProgramDataRoot)
    $preferred=Join-Path $ProgramDataRoot 'operations'
    if(Test-Path -LiteralPath $ProgramDataRoot -PathType Container){
        try {New-Item -ItemType Directory -Force -Path $preferred|Out-Null;return $preferred}catch{}
    }
    $fallback=Join-Path $env:LOCALAPPDATA 'OneCChatWorker\operations'
    New-Item -ItemType Directory -Force -Path $fallback|Out-Null
    return $fallback
}

function Get-WorkerOperationRoots {
    param([string]$ProgramDataRoot=$script:DefaultProgramDataRoot)
    $roots=New-Object Collections.Generic.List[string]
    $preferred=Join-Path $ProgramDataRoot 'operations'
    $fallback=Join-Path $env:LOCALAPPDATA 'OneCChatWorker\operations'
    if(Test-Path -LiteralPath $preferred -PathType Container){$roots.Add($preferred)}
    if((Test-Path -LiteralPath $fallback -PathType Container) -and -not $roots.Contains($fallback)){$roots.Add($fallback)}
    @($roots)
}

function Rotate-WorkerLog {
    param([Parameter(Mandatory)][string]$Path)
    if((Test-Path -LiteralPath $Path -PathType Leaf) -and (Get-Item -LiteralPath $Path).Length -ge $script:OperationLogMaxBytes){
        $previous=$Path+'.1'
        Move-Item -LiteralPath $Path -Destination $previous -Force
    }
}

function Write-WorkerOperationEvent {
    param(
        [Parameter(Mandatory)]$Operation,
        [Parameter(Mandatory)][ValidateSet('RUNNING','PASS','FAIL','WAITING_FOR_USER','CANCELLED','RECOVERED')][string]$State,
        [Parameter(Mandatory)][string]$Message,
        [int]$Step=0,[int]$Total=0,
        [string]$ErrorClass,
        [string]$ErrorMessage,
        [string]$ErrorPhase,
        [string]$ErrorPath,
        [string]$CleanupStatus,
        [string]$RecoveryHint,
        [hashtable]$SafeDetails,
        [string]$ProgramDataRoot=$script:DefaultProgramDataRoot,
        [switch]$Quiet
    )
    $root=Get-WorkerOperationRoot $ProgramDataRoot
    $event=[ordered]@{
        schema_version=1
        at_utc=(Get-Date).ToUniversalTime().ToString('o')
        operation_id=[string]$Operation.operation_id
        operation_type=[string]$Operation.operation_type
        state=$State
        step=$Step
        total_steps=$Total
        project_id=$Operation.project_id
        participant_id=$Operation.participant_id
        artifact_id=$Operation.artifact_id
        requested_action=$Operation.requested_action
        message=$Message
        error_class=$ErrorClass
        error_message=$ErrorMessage
        error_phase=$ErrorPhase
        error_path=$ErrorPath
        cleanup_status=$CleanupStatus
        recovery_hint=$RecoveryHint
        details=$(if($SafeDetails){$SafeDetails}else{@{}})
    }
    $events=Join-Path $root 'events.jsonl'
    $human=Join-Path $root 'operations.log'
    Rotate-WorkerLog $events;Rotate-WorkerLog $human
    Add-Content -LiteralPath $events -Value (($event|ConvertTo-Json -Depth 12 -Compress)) -Encoding UTF8
    $prefix=if($Total -gt 0 -and $Step -gt 0){"[$Step/$Total]"}else{'[-/-]'}
    $line="{0} {1} {2} ... {3}" -f $prefix,$Operation.operation_type,$Message,$State
    $diagnostic=$(if($ErrorClass){" error_class=$ErrorClass"}else{''})
    Add-Content -LiteralPath $human -Value ("{0} [UTC] {1}{2}" -f (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ'),$line,$diagnostic) -Encoding UTF8
    foreach($pair in @(
        @('state',$State),@('current_step',$Step),@('total_steps',$Total),@('message',$Message),
        @('error_class',$ErrorClass),@('error_message',$ErrorMessage),@('error_phase',$ErrorPhase),
        @('error_path',$ErrorPath),@('cleanup_status',$CleanupStatus),@('recovery_hint',$RecoveryHint)
    )){$Operation|Add-Member -NotePropertyName $pair[0] -NotePropertyValue $pair[1] -Force}
    Write-JsonAtomic $Operation (Join-Path $root 'current-operation.json')
    if(-not $Quiet){Write-Host $line}
    $event
}

function Start-WorkerOperation {
    param(
        [Parameter(Mandatory)][string]$OperationType,
        [string]$RequestedAction,
        [string]$ProjectId,
        [string]$ParticipantId,
        [string]$ArtifactId,
        [int]$TotalSteps=1,
        [string]$ProgramDataRoot=$script:DefaultProgramDataRoot
    )
    $op=[pscustomobject]@{
        schema_version=1
        operation_id=[Guid]::NewGuid().ToString('N')
        operation_type=$OperationType
        requested_action=$RequestedAction
        project_id=$ProjectId
        participant_id=$ParticipantId
        artifact_id=$ArtifactId
        started_utc=(Get-Date).ToUniversalTime().ToString('o')
        ended_utc=$null
        state='RUNNING'
        current_step=0
        total_steps=$TotalSteps
        message='Starting'
        error_class=$null
        error_message=$null
        error_phase=$null
        error_path=$null
        cleanup_status=$null
        recovery_hint=$null
    }
    $null=Write-WorkerOperationEvent -Operation $op -State RUNNING -Message 'Starting' -Step 0 -Total $TotalSteps -ProgramDataRoot $ProgramDataRoot
    $op
}

function Update-WorkerOperation {
    param(
        [Parameter(Mandatory)]$Operation,
        [Parameter(Mandatory)][string]$Message,
        [Parameter(Mandatory)][int]$Step,
        [Parameter(Mandatory)][int]$Total,
        [ValidateSet('RUNNING','PASS','FAIL','WAITING_FOR_USER','CANCELLED','RECOVERED')][string]$State='RUNNING',
        [hashtable]$SafeDetails,
        [string]$ProgramDataRoot=$script:DefaultProgramDataRoot,
        [switch]$Quiet
    )
    Write-WorkerOperationEvent -Operation $Operation -State $State -Message $Message -Step $Step -Total $Total -SafeDetails $SafeDetails -ProgramDataRoot $ProgramDataRoot -Quiet:$Quiet
}

function Complete-WorkerOperation {
    param(
        [Parameter(Mandatory)]$Operation,
        [ValidateSet('PASS','FAIL','WAITING_FOR_USER','CANCELLED','RECOVERED')][string]$State='PASS',
        [Parameter(Mandatory)][string]$Message,
        [string]$ErrorClass,
        [string]$ErrorMessage,
        [string]$ErrorPhase,
        [string]$ErrorPath,
        [string]$CleanupStatus,
        [string]$RecoveryHint,
        [hashtable]$SafeDetails,
        [string]$ProgramDataRoot=$script:DefaultProgramDataRoot,
        [switch]$Quiet
    )
    $root=Get-WorkerOperationRoot $ProgramDataRoot
    $Operation.ended_utc=(Get-Date).ToUniversalTime().ToString('o')
    $null=Write-WorkerOperationEvent -Operation $Operation -State $State -Message $Message -Step $Operation.total_steps -Total $Operation.total_steps -ErrorClass $ErrorClass -ErrorMessage $ErrorMessage -ErrorPhase $ErrorPhase -ErrorPath $ErrorPath -CleanupStatus $CleanupStatus -RecoveryHint $RecoveryHint -SafeDetails $SafeDetails -ProgramDataRoot $ProgramDataRoot -Quiet:$Quiet
    $history=Join-Path $root 'history.jsonl';Rotate-WorkerLog $history
    Add-Content -LiteralPath $history -Value (($Operation|ConvertTo-Json -Depth 12 -Compress)) -Encoding UTF8
    $Operation
}

function Get-CurrentWorkerOperation {
    param([string]$ProgramDataRoot=$script:DefaultProgramDataRoot)
    foreach($root in Get-WorkerOperationRoots $ProgramDataRoot){
        $p=Join-Path $root 'current-operation.json'
        if(Test-Path -LiteralPath $p -PathType Leaf){
            try{return Get-Content -LiteralPath $p -Raw -Encoding UTF8|ConvertFrom-Json}catch{}
        }
    }
    $null
}

function Get-RecentWorkerOperations {
    param([int]$Limit=10,[string]$ProgramDataRoot=$script:DefaultProgramDataRoot)
    $all=New-Object Collections.Generic.List[object]
    foreach($root in Get-WorkerOperationRoots $ProgramDataRoot){
        $p=Join-Path $root 'history.jsonl'
        if(-not(Test-Path -LiteralPath $p -PathType Leaf)){continue}
        foreach($line in Get-Content -LiteralPath $p -Encoding UTF8){
            if([string]::IsNullOrWhiteSpace($line)){continue}
            try{$all.Add(($line|ConvertFrom-Json))}catch{}
        }
    }
    @($all|Sort-Object started_utc -Descending|Select-Object -First $Limit)
}

function Get-WorkerOperationLog {
    param([int]$Tail=100,[string]$ProgramDataRoot=$script:DefaultProgramDataRoot)
    $lines=New-Object Collections.Generic.List[string]
    foreach($root in Get-WorkerOperationRoots $ProgramDataRoot){
        $p=Join-Path $root 'operations.log'
        if(Test-Path -LiteralPath $p -PathType Leaf){foreach($line in Get-Content -LiteralPath $p -Tail $Tail -Encoding UTF8){$lines.Add($line)}}
    }
    @($lines|Select-Object -Last $Tail)
}

function Get-OperationRecoveryClassification {
    param([string]$ProgramDataRoot=$script:DefaultProgramDataRoot)
    $cur=Get-CurrentWorkerOperation $ProgramDataRoot
    if(!$cur){return [pscustomobject]@{classification='NOT_STARTED';operation=$null}}
    if($cur.state -in @('PASS','FAIL','CANCELLED','RECOVERED','WAITING_FOR_USER')){return [pscustomobject]@{classification='COMMITTED_OR_CLASSIFIED';operation=$cur}}
    [pscustomobject]@{classification='RECOVERY_REQUIRED';operation=$cur}
}

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

function Set-WorkerReaderIdentity {
    param([Parameter(Mandatory)][string]$ReaderName)
    Assert-SafeId $ReaderName 'reader_name'|Out-Null
    $script:ReaderName=$ReaderName
    $script:ReaderName
}

function Read-RuntimeLock {
    param([Parameter(Mandatory)][string]$PackageRoot)
    $path=Join-Path $PackageRoot 'runtime.lock.json'
    if(-not(Test-Path -LiteralPath $path -PathType Leaf)){throw "RUNTIME_LOCK_MISSING: $path"}
    $lock=Get-Content -LiteralPath $path -Raw -Encoding UTF8|ConvertFrom-Json
    if($lock.schema_version -ne 1){throw 'RUNTIME_LOCK_SCHEMA_UNSUPPORTED'}
    if($lock.product_version -ne $script:ProductVersion){throw "RUNTIME_LOCK_PRODUCT_VERSION_MISMATCH: $($lock.product_version)"}
    $lock
}

function Test-ProductPackageIntegrity {
    param([Parameter(Mandatory)][string]$PackageRoot)
    $lock=Read-RuntimeLock $PackageRoot
    $rows=@()
    foreach($prop in $lock.components.PSObject.Properties){
        $rel=[string]$prop.Name;$expected=[string]$prop.Value
        $path=Join-Path $PackageRoot ($rel.Replace('/','\'))
        $actual=if(Test-Path -LiteralPath $path -PathType Leaf){Get-Sha256File $path}else{$null}
        $ok=($actual -eq $expected)
        $rows+=,[pscustomobject]@{path=$rel;expected_sha256=$expected;actual_sha256=$actual;healthy=$ok}
        if(-not $ok){throw "PACKAGE_COMPONENT_HASH_MISMATCH: $rel"}
    }
    [pscustomobject]@{status='PASS';product_version=$lock.product_version;components=$rows;lock_sha256=Get-Sha256File (Join-Path $PackageRoot 'runtime.lock.json')}
}

function Copy-ProductComponent {
    param([Parameter(Mandatory)][string]$Source,[Parameter(Mandatory)][string]$Destination,[Parameter(Mandatory)][string]$ExpectedSha256)
    $sourceHash=Get-Sha256File $Source
    if($sourceHash -ne $ExpectedSha256){throw "PACKAGE_COMPONENT_HASH_MISMATCH: $Source"}
    $action='INSTALLED'
    if(Test-Path -LiteralPath $Destination -PathType Leaf){
        $old=Get-Sha256File $Destination
        $action=if($old -eq $ExpectedSha256){'REUSED'}else{'UPDATED'}
    }
    if($action -ne 'REUSED'){
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination)|Out-Null
        Copy-Item -LiteralPath $Source -Destination $Destination -Force
    }
    $actual=Get-Sha256File $Destination
    if($actual -ne $ExpectedSha256){throw "INSTALLED_COMPONENT_HASH_MISMATCH: $Destination"}
    [pscustomobject]@{action=$action;source=$Source;destination=$Destination;sha256=$actual}
}

function Test-InstalledProductIntegrity {
    param([string]$WorkerRoot=$script:DefaultWorkerRoot,[string]$ProgramDataRoot=$script:DefaultProgramDataRoot)
    $lockPath=Join-Path $ProgramDataRoot 'product\runtime.lock.json'
    if(-not(Test-Path -LiteralPath $lockPath -PathType Leaf)){throw 'INSTALLED_RUNTIME_LOCK_MISSING'}
    $lock=Get-Content -LiteralPath $lockPath -Raw -Encoding UTF8|ConvertFrom-Json
    $map=[ordered]@{
        'runtime/source-reader-integration.mjs'=(Join-Path $ProgramDataRoot 'provider\source-reader-integration.mjs')
        'runtime/hosted-helper.mjs'=(Join-Path $ProgramDataRoot 'helper\hosted-helper.mjs')
        'core/OneCChatWorker.Core.psm1'=(Join-Path $ProgramDataRoot 'product\OneCChatWorker.Core.psm1')
        'OneCChatWorker.ps1'=(Join-Path $WorkerRoot 'OneCChatWorker.ps1')
        'README.md'=(Join-Path $ProgramDataRoot 'product\README.md')
    }
    $rows=@()
    foreach($rel in $map.Keys){
        $expected=[string]$lock.components.$rel
        if([string]::IsNullOrWhiteSpace($expected)){throw "INSTALLED_LOCK_COMPONENT_MISSING: $rel"}
        $actual=if(Test-Path -LiteralPath $map[$rel] -PathType Leaf){Get-Sha256File $map[$rel]}else{$null}
        $ok=($actual -eq $expected)
        $rows+=,[pscustomobject]@{path=$rel;installed_path=$map[$rel];expected_sha256=$expected;actual_sha256=$actual;healthy=$ok}
        if(-not $ok){throw "INSTALLED_COMPONENT_HASH_MISMATCH: $rel"}
    }
    [pscustomobject]@{status='PASS';components=$rows;runtime_lock_sha256=Get-Sha256File $lockPath}
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
    param([Parameter(Mandatory)][string]$Root,[scriptblock]$ProgressCallback)
    if(-not(Test-Path -LiteralPath $Root -PathType Container)){throw "TREE_NOT_FOUND: $Root"}
    $rootFull=[IO.Path]::GetFullPath($Root).TrimEnd('\')
    $all=@(Get-ChildItem -LiteralPath $rootFull -Recurse -Force -ErrorAction Stop)
    $reparse=@($all|Where-Object {($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0})
    if($reparse.Count -gt 0){throw "REPARSE_POINT: $($reparse[0].FullName)"}
    $items=@($all|Where-Object {-not $_.PSIsContainer}|Sort-Object FullName)
    $sum=($items|Measure-Object Length -Sum).Sum;if($null -eq $sum){$sum=0}
    if($ProgressCallback){& $ProgressCallback ([pscustomobject]@{phase='DEEP_VERIFY';files_processed=0;files_total=$items.Count;bytes_processed=[int64]0;bytes_total=[int64]$sum})}
    $sha=[Security.Cryptography.SHA256]::Create();$maxRelativePathChars=0;$maxRelativePath=$null;$processed=0;$processedBytes=[int64]0
    try{
        foreach($f in $items){
            $rel=$f.FullName.Substring($rootFull.Length).TrimStart('\').Replace('\','/')
            if($rel.Length -gt $maxRelativePathChars){$maxRelativePathChars=$rel.Length;$maxRelativePath=$rel}
            $fh=(Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
            $row=[string]::Join([char]9,@($rel,[string]$f.Length,$fh))+[Environment]::NewLine
            $line=[Text.Encoding]::UTF8.GetBytes($row);$null=$sha.TransformBlock($line,0,$line.Length,$line,0)
            $processed++;$processedBytes+=[int64]$f.Length
            if($ProgressCallback -and (($processed % 250) -eq 0 -or $processed -eq $items.Count)){& $ProgressCallback ([pscustomobject]@{phase='DEEP_VERIFY';files_processed=$processed;files_total=$items.Count;bytes_processed=$processedBytes;bytes_total=[int64]$sum})}
        }
        $null=$sha.TransformFinalBlock([byte[]]@(),0,0);$digest=([BitConverter]::ToString($sha.Hash)).Replace('-','').ToLowerInvariant()
    }finally{$sha.Dispose()}
    [pscustomobject]@{sha256=$digest;files=$items.Count;bytes=[int64]$sum;max_relative_path_chars=$maxRelativePathChars;max_relative_path=$maxRelativePath}
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

function Edit-WorkerProject {
    param([Parameter(Mandatory)][string]$ProjectId,[Parameter(Mandatory)][string]$DisplayName,[string]$WorkerRoot=$script:DefaultWorkerRoot)
    $c=Read-WorkerCatalog $WorkerRoot;$p=Find-Project $c $ProjectId;if(!$p){throw 'PROJECT_NOT_FOUND'}
    if([string]::IsNullOrWhiteSpace($DisplayName)){throw 'DISPLAY_NAME_REQUIRED'}
    $p.display_name=$DisplayName
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

function Edit-WorkerParticipant {
    param([Parameter(Mandatory)][string]$ProjectId,[Parameter(Mandatory)][string]$ParticipantId,[string]$Role,[string]$WorkerRoot=$script:DefaultWorkerRoot)
    $c=Read-WorkerCatalog $WorkerRoot;$p=Find-Project $c $ProjectId;if(!$p){throw 'PROJECT_NOT_FOUND'}
    $part=@($p.participants|Where-Object {$_.participant_id -eq $ParticipantId})|Select-Object -First 1;if(!$part){throw 'PARTICIPANT_NOT_FOUND'}
    $part.role=$Role
    Write-WorkerCatalog $c $WorkerRoot
    $part
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
    if($part.platform -eq 'ONEC'){Assert-OneCExportRoot $SourcePath}
    $existing=@($part.target.extensions|Where-Object {$_.extension_id -eq $ExtensionId})|Select-Object -First 1
    if($existing){
        if(-not $ReplaceExisting){throw 'EXTENSION_ALREADY_EXISTS'}
        $existing.active=$true
        $existing.source_path=[IO.Path]::GetFullPath($SourcePath)
        $existing.replace_existing=$true
        Write-WorkerCatalog $c $WorkerRoot
        return $existing
    }
    $e=[pscustomobject]@{extension_id=$ExtensionId;active=$true;source_path=[IO.Path]::GetFullPath($SourcePath);replace_existing=[bool]$ReplaceExisting}
    $part.target.extensions=@($part.target.extensions)+@($e);Write-WorkerCatalog $c $WorkerRoot;$e
}

function Disable-WorkerCatalogItem {
    param([Parameter(Mandatory)][ValidateSet('PROJECT','PARTICIPANT','MAIN','EXTENSION')][string]$Kind,[Parameter(Mandatory)][string]$ProjectId,[string]$ParticipantId,[string]$ExtensionId,[string]$WorkerRoot=$script:DefaultWorkerRoot)
    $c=Read-WorkerCatalog $WorkerRoot;$p=Find-Project $c $ProjectId;if(!$p){throw 'PROJECT_NOT_FOUND'}
    if($Kind -eq 'PROJECT'){$p.active=$false}
    else {
        $part=@($p.participants|Where-Object {$_.participant_id -eq $ParticipantId})|Select-Object -First 1;if(!$part){throw 'PARTICIPANT_NOT_FOUND'}
        if($Kind -eq 'PARTICIPANT'){$part.active=$false}
        elseif($Kind -eq 'MAIN'){
            if(-not $part.target.main){throw 'MAIN_NOT_CONFIGURED'}
            $part.target.main.active=$false
        } else {
            $e=@($part.target.extensions|Where-Object {$_.extension_id -eq $ExtensionId})|Select-Object -First 1;if(!$e){throw 'EXTENSION_NOT_FOUND'};$e.active=$false
        }
    }
    Write-WorkerCatalog $c $WorkerRoot
}

function ConvertTo-BoundedDiagnosticText {
    param([string]$Text,[int]$MaxChars=800)
    if([string]::IsNullOrWhiteSpace($Text)){return $null}
    $v=($Text -replace '[\r\n\t]+',' ').Trim()
    if($v -match '(?i)helper-secret|\\secrets\\'){return 'Sensitive path or value omitted.'}
    if($v.Length -gt $MaxChars){$v=$v.Substring(0,$MaxChars)}
    $v
}

function Get-ApplyStageRoot {
    param([string]$WorkerRoot=$script:DefaultWorkerRoot)
    Join-Path $WorkerRoot '.stage'
}

function Write-ApplyStageState {
    param(
        [Parameter(Mandatory)][string]$StagePath,
        [Parameter(Mandatory)][ValidateSet('CREATED','COPYING','VERIFIED','COMMITTED')][string]$State,
        [Parameter(Mandatory)][string]$ProjectRoot,
        [Parameter(Mandatory)][string]$TargetPath,
        [string]$ArchiveKey
    )
    $doc=[ordered]@{
        schema_version=1
        state=$State
        updated_utc=(Get-Date).ToUniversalTime().ToString('o')
        project_root=$ProjectRoot
        project_id=Split-Path -Leaf $ProjectRoot
        stage_path=$StagePath
        target_path=$TargetPath
        archive_key=$ArchiveKey
    }
    Write-JsonAtomic $doc ($StagePath+'.json')
}

function Get-ApplyStageResidue {
    param([Parameter(Mandatory)][string]$ProjectId,[string]$WorkerRoot=$script:DefaultWorkerRoot)
    Assert-SafeId $ProjectId 'project_id'|Out-Null
    $projectRoot=Join-Path $WorkerRoot $ProjectId
    $rows=New-Object Collections.Generic.List[object]

    $participantsRoot=Join-Path $projectRoot 'Participants'
    if(Test-Path -LiteralPath $participantsRoot -PathType Container){
        foreach($participantDir in @(Get-ChildItem -LiteralPath $participantsRoot -Directory -Force -ErrorAction SilentlyContinue)){
            $targetRoot=Join-Path $participantDir.FullName 'Target'
            foreach($scanRoot in @($targetRoot,(Join-Path $targetRoot 'Extensions'))){
                if(-not(Test-Path -LiteralPath $scanRoot -PathType Container)){continue}
                foreach($dir in @(Get-ChildItem -LiteralPath $scanRoot -Directory -Force -Filter '*.stage-*' -ErrorAction SilentlyContinue)){
                    $idx=$dir.Name.IndexOf('.stage-')
                    if($idx -lt 1){continue}
                    $targetName=$dir.Name.Substring(0,$idx)
                    $rows.Add([pscustomobject]@{
                        layout='LEGACY_TARGET_SIBLING'
                        project_id=$ProjectId
                        state='UNKNOWN_INTERRUPTED'
                        stage_path=$dir.FullName
                        target_path=Join-Path $scanRoot $targetName
                        metadata_path=$null
                    })
                }
            }
        }
    }

    $stageRoot=Get-ApplyStageRoot $WorkerRoot
    if(Test-Path -LiteralPath $stageRoot -PathType Container){
        foreach($dir in @(Get-ChildItem -LiteralPath $stageRoot -Directory -Force -Filter '*.stage-*' -ErrorAction SilentlyContinue)){
            $metaPath=$dir.FullName+'.json';$meta=$null
            if(Test-Path -LiteralPath $metaPath -PathType Leaf){try{$meta=Get-Content -LiteralPath $metaPath -Raw -Encoding UTF8|ConvertFrom-Json}catch{}}
            $metaProject=$(if($meta -and $meta.project_id){[string]$meta.project_id}else{$null})
            if($metaProject -and $metaProject -ne $ProjectId){continue}
            if(-not $metaProject -and $meta -and $meta.project_root -and ([IO.Path]::GetFullPath([string]$meta.project_root).TrimEnd('\') -ne [IO.Path]::GetFullPath($projectRoot).TrimEnd('\'))){continue}
            if(-not $metaProject -and -not $meta){continue}
            $rows.Add([pscustomobject]@{
                layout='BOUNDED_STAGE_ROOT'
                project_id=$ProjectId
                state=$(if($meta -and $meta.state){[string]$meta.state}else{'UNKNOWN_INTERRUPTED'})
                stage_path=$dir.FullName
                target_path=$(if($meta){[string]$meta.target_path}else{$null})
                metadata_path=$(if(Test-Path -LiteralPath $metaPath -PathType Leaf){$metaPath}else{$null})
            })
        }
    }
    @($rows | ForEach-Object {$_})
}

function Remove-ApplyStageTree {
    param([Parameter(Mandatory)][string]$StagePath)
    if(-not(Test-Path -LiteralPath $StagePath -PathType Container)){return [pscustomobject]@{status='ALREADY_ABSENT';path=$StagePath;error=$null}}
    $firstError=$null
    try{Remove-Item -LiteralPath $StagePath -Recurse -Force -ErrorAction Stop}
    catch{$firstError=ConvertTo-BoundedDiagnosticText $_.Exception.Message}
    if(-not(Test-Path -LiteralPath $StagePath -PathType Container)){return [pscustomobject]@{status='CLEANED';path=$StagePath;error=$firstError}}
    try{
        $full=[IO.Path]::GetFullPath($StagePath)
        $extended=$(if($full.StartsWith('\\')){'\\?\UNC\'+$full.Substring(2)}else{'\\?\'+$full})
        $cmd='rmdir /s /q "{0}"' -f $extended.Replace('"','""')
        & $env:ComSpec /d /s /c $cmd | Out-Null
    }catch{}
    if(-not(Test-Path -LiteralPath $StagePath -PathType Container)){return [pscustomobject]@{status='CLEANED_LONG_PATH';path=$StagePath;error=$firstError}}
    [pscustomobject]@{status='CLEANUP_FAILED';path=$StagePath;error=$firstError}
}

function Move-ApplyStageToQuarantine {
    param([Parameter(Mandatory)]$Residue,[Parameter(Mandatory)][string]$ProjectRoot)
    $root=Join-Path $ProjectRoot 'Recovery\ApplyResidue'
    New-Item -ItemType Directory -Force -Path $root|Out-Null
    $stamp=(Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffZ')
    $leaf=Split-Path -Leaf ([string]$Residue.stage_path)
    $destination=Join-Path $root ("$stamp-$leaf")
    try{
        Move-Item -LiteralPath $Residue.stage_path -Destination $destination -ErrorAction Stop
        if($Residue.metadata_path -and (Test-Path -LiteralPath $Residue.metadata_path -PathType Leaf)){
            Move-Item -LiteralPath $Residue.metadata_path -Destination ($destination+'.json') -Force -ErrorAction SilentlyContinue
        }
        return [pscustomobject]@{status='QUARANTINED';original_path=$Residue.stage_path;quarantine_path=$destination;error=$null}
    }catch{
        $record=Join-Path $root ("$stamp-quarantine-record.json")
        $doc=[ordered]@{
            schema_version=1
            state='QUARANTINE_MOVE_FAILED'
            recorded_utc=(Get-Date).ToUniversalTime().ToString('o')
            stage_path=[string]$Residue.stage_path
            target_path=[string]$Residue.target_path
            error=ConvertTo-BoundedDiagnosticText $_.Exception.Message
        }
        Write-JsonAtomic $doc $record
        return [pscustomobject]@{status='QUARANTINE_RECORDED';original_path=$Residue.stage_path;quarantine_path=$record;error=$doc.error}
    }
}

function Resolve-ApplyStageResidue {
    param([Parameter(Mandatory)][string]$ProjectId,[string]$WorkerRoot=$script:DefaultWorkerRoot)
    $projectRoot=Join-Path $WorkerRoot $ProjectId
    $before=@(Get-ApplyStageResidue -ProjectId $ProjectId -WorkerRoot $WorkerRoot)
    $actions=@()
    foreach($residue in $before){
        $cleanup=Remove-ApplyStageTree -StagePath $residue.stage_path
        if($cleanup.status -in @('CLEANED','CLEANED_LONG_PATH','ALREADY_ABSENT')){
            if($residue.metadata_path){Remove-Item -LiteralPath $residue.metadata_path -Force -ErrorAction SilentlyContinue}
            $actions+=,[pscustomobject]@{stage_path=$residue.stage_path;action=$cleanup.status;quarantine_path=$null;error=$cleanup.error}
        }else{
            $q=Move-ApplyStageToQuarantine -Residue $residue -ProjectRoot $projectRoot
            $actions+=,[pscustomobject]@{stage_path=$residue.stage_path;action=$q.status;quarantine_path=$q.quarantine_path;error=$q.error}
        }
    }
    $remaining=@(Get-ApplyStageResidue -ProjectId $ProjectId -WorkerRoot $WorkerRoot)
    [pscustomobject]@{
        project_id=$ProjectId
        status=$(if($remaining.Count){'RESIDUE_REMAINS'}else{'CLEAN'})
        residue_before=$before.Count
        remaining=$remaining.Count
        actions=$actions
        authoritative_source_untouched=$true
        canonical_target_deleted=$false
        detached_deleted=$false
    }
}

function New-ApplyCopyException {
    param(
        [Parameter(Mandatory)][string]$Class,
        [Parameter(Mandatory)][string]$SafeMessage,
        [Parameter(Mandatory)][string]$Phase,
        [string]$Path,
        [string]$CleanupStatus,
        [Exception]$InnerException
    )
    $ex=New-Object System.InvalidOperationException(("${Class}: $SafeMessage"),$InnerException)
    $ex.Data['phase']=$Phase
    if($Path){$ex.Data['path']=$Path}
    if($CleanupStatus){$ex.Data['cleanup_status']=$CleanupStatus}
    if($InnerException){$ex.Data['cause_type']=$InnerException.GetType().FullName;$ex.Data['cause_message']=ConvertTo-BoundedDiagnosticText $InnerException.Message}
    $ex
}


function Get-Sha256Text {
    param([Parameter(Mandatory)][AllowEmptyString()][string]$Text)
    $sha=[Security.Cryptography.SHA256]::Create()
    try{$bytes=[Text.Encoding]::UTF8.GetBytes($Text);$hash=$sha.ComputeHash($bytes);([BitConverter]::ToString($hash)).Replace('-','').ToLowerInvariant()}finally{$sha.Dispose()}
}
function Get-ProjectManifestPath {
    param([Parameter(Mandatory)][string]$ProjectId,[string]$WorkerRoot=$script:DefaultWorkerRoot)
    Join-Path $WorkerRoot "$ProjectId\ProjectManifest\project.json"
}
function Get-ManifestArtifactRows {
    param([Parameter(Mandatory)]$Manifest)
    $rows=@()
    foreach($part in @($Manifest.participants)){
        if($part.active -eq $false){continue}
        if($part.target.main -and $part.target.main.active -ne $false){$a=$part.target.main;$rows+=,[pscustomobject]@{participant_id=[string]$part.participant_id;platform=[string]$part.platform;artifact_type='MAIN';artifact_id='main';canonical_path=[string]$a.canonical_path;tree_sha256=[string]$a.tree_sha256;files=[int64]$a.files;bytes=[int64]$a.bytes;configuration_xml_sha256=[string]$a.configuration_xml_sha256}}
        foreach($a in @($part.target.extensions|Where-Object {$_.active -ne $false})){$rows+=,[pscustomobject]@{participant_id=[string]$part.participant_id;platform=[string]$part.platform;artifact_type='EXTENSION';artifact_id=[string]$(if($a.extension_id){$a.extension_id}else{$a.artifact_id});canonical_path=[string]$a.canonical_path;tree_sha256=[string]$a.tree_sha256;files=[int64]$a.files;bytes=[int64]$a.bytes;configuration_xml_sha256=[string]$a.configuration_xml_sha256}}
    }
    @($rows|Sort-Object participant_id,artifact_type,artifact_id,canonical_path)
}
function Get-SnapshotArtifactKey {
    param([Parameter(Mandatory)]$Artifact)
    "{0}|{1}|{2}" -f ([string]$Artifact.participant_id),([string]$Artifact.artifact_type),([string]$Artifact.artifact_id)
}
function New-AcceptedSnapshot {
    param([Parameter(Mandatory)]$ManifestParticipants,[Parameter(Mandatory)][string]$CatalogSha256,[Parameter(Mandatory)][string]$ProofBasis,[int]$PublicationGeneration=1,[string]$PublishedUtc,[hashtable]$FingerprintMap)
    if([string]::IsNullOrWhiteSpace($PublishedUtc)){$PublishedUtc=(Get-Date).ToUniversalTime().ToString('o')}
    if($null -eq $FingerprintMap){$FingerprintMap=@{}}
    $stub=[pscustomobject]@{participants=@($ManifestParticipants)};$baseRows=@(Get-ManifestArtifactRows $stub);$rows=@();$states=New-Object Collections.Generic.List[string]
    foreach($a in $baseRows){$key=Get-SnapshotArtifactKey $a;$fp=$null;if($FingerprintMap.ContainsKey($key)){$fp=$FingerprintMap[$key]};$state=$(if($fp -and $fp.state){[string]$fp.state}else{'ABSENT_LEGACY'});$states.Add($state);$rows+=,[pscustomobject][ordered]@{participant_id=$a.participant_id;platform=$a.platform;artifact_type=$a.artifact_type;artifact_id=$a.artifact_id;canonical_path=$a.canonical_path;files=[int64]$a.files;bytes=[int64]$a.bytes;tree_sha256=$a.tree_sha256;configuration_xml_sha256=$a.configuration_xml_sha256;fingerprint_inventory_state=$state;fingerprint_inventory_path=$(if($fp){$fp.relative_path}else{$null});fingerprint_inventory_sha256=$(if($fp){$fp.sha256}else{$null})}}
    $present=@($states|Where-Object {$_ -eq 'PRESENT'}).Count;$inventoryState=$(if($present -eq $rows.Count -and $rows.Count -gt 0){'PRESENT'}elseif($present){'MIXED'}else{'ABSENT_LEGACY'})
    $sep=[string][char]9;$nl=[Environment]::NewLine;$identityLines=New-Object Collections.Generic.List[string]
    $identityLines.Add("snapshot_contract"+$sep+"ACCEPTED_SNAPSHOT_V1");$identityLines.Add("catalog_sha256"+$sep+$CatalogSha256);$identityLines.Add("proof_basis"+$sep+$ProofBasis);$identityLines.Add("fingerprint_inventory_state"+$sep+$inventoryState)
    foreach($a in $rows){$identityLines.Add([string]::Join([char]9,@([string]$a.participant_id,[string]$a.platform,[string]$a.artifact_type,[string]$a.artifact_id,[string]$a.canonical_path,[string]$a.files,[string]$a.bytes,[string]$a.tree_sha256,[string]$a.configuration_xml_sha256,[string]$a.fingerprint_inventory_state,[string]$a.fingerprint_inventory_path,[string]$a.fingerprint_inventory_sha256)))}
    $identity=Get-Sha256Text ("OneCChatWorker-accepted-snapshot-v1"+$nl+([string]::Join($nl,$identityLines))+$nl)
    [pscustomobject][ordered]@{snapshot_contract='ACCEPTED_SNAPSHOT_V1';snapshot_state='ACCEPTED';source_snapshot_id=$identity;publication_generation=$PublicationGeneration;published_utc=$PublishedUtc;catalog_sha256=$CatalogSha256;proof_basis=$ProofBasis;fingerprint_inventory_state=$inventoryState;artifacts=@($rows)}
}
function Set-ManifestAcceptedSnapshot {
    param([Parameter(Mandatory)]$Manifest,[Parameter(Mandatory)][string]$ManifestPath,[Parameter(Mandatory)][string]$ProofBasis,[int]$PublicationGeneration=1,[hashtable]$FingerprintMap,$ProofReceipt)
    $snap=New-AcceptedSnapshot -ManifestParticipants @($Manifest.participants) -CatalogSha256 ([string]$Manifest.catalog_sha256) -ProofBasis $ProofBasis -PublicationGeneration $PublicationGeneration -FingerprintMap $FingerprintMap
    $Manifest.schema_version=2
    if($Manifest.PSObject.Properties.Name -contains 'accepted_snapshot'){$Manifest.accepted_snapshot=$snap}else{$Manifest|Add-Member -NotePropertyName accepted_snapshot -NotePropertyValue $snap}
    if($ProofReceipt){$proof=[pscustomobject][ordered]@{operation_id=[string]$ProofReceipt.operation_id;operation_type=[string]$ProofReceipt.operation_type;state=[string]$ProofReceipt.state;ended_utc=[string]$ProofReceipt.ended_utc};if($Manifest.PSObject.Properties.Name -contains 'acceptance_proof'){$Manifest.acceptance_proof=$proof}else{$Manifest|Add-Member -NotePropertyName acceptance_proof -NotePropertyValue $proof}}
    Write-JsonAtomic $Manifest $ManifestPath
    [pscustomobject]@{status='ACCEPTED';source_snapshot_id=$snap.source_snapshot_id;manifest_sha256=Get-Sha256File $ManifestPath;proof_basis=$ProofBasis;publication_generation=$PublicationGeneration}
}
function Get-FastProjectState {
    param([Parameter(Mandatory)][string]$ProjectId,[string]$WorkerRoot=$script:DefaultWorkerRoot)
    $catalog=Read-WorkerCatalog $WorkerRoot;$p=Find-Project $catalog $ProjectId;if(!$p){throw 'PROJECT_NOT_FOUND'}
    if($p.active -eq $false){return [pscustomobject]@{project_id=$ProjectId;state='APPLY_REQUIRED';status='APPLY_REQUIRED';reason='PROJECT_INACTIVE'}}
    $residue=@(Get-ApplyStageResidue -ProjectId $ProjectId -WorkerRoot $WorkerRoot);if($residue.Count){return [pscustomobject]@{project_id=$ProjectId;state='INCOMPLETE_APPLY_RESIDUE';status='INCOMPLETE_APPLY_RESIDUE';reason='ORPHAN_STAGE_PRESENT';residue_count=$residue.Count}}
    $activeParticipants=@($p.participants|Where-Object {$_.active -ne $false})
    if(-not $activeParticipants.Count){return [pscustomobject]@{project_id=$ProjectId;state='APPLY_REQUIRED';status='APPLY_REQUIRED';reason='NO_ACTIVE_PARTICIPANTS'}}
    $missingMain=@($activeParticipants|Where-Object {$_.platform -eq 'ONEC' -and (-not $_.target.main -or $_.target.main.active -eq $false)})
    if($missingMain.Count){return [pscustomobject]@{project_id=$ProjectId;state='APPLY_REQUIRED';status='APPLY_REQUIRED';reason=("ONEC_MAIN_REQUIRED:"+[string]$missingMain[0].participant_id)}}
    $manifestPath=Get-ProjectManifestPath -ProjectId $ProjectId -WorkerRoot $WorkerRoot
    if(-not(Test-Path -LiteralPath $manifestPath -PathType Leaf)){return [pscustomobject]@{project_id=$ProjectId;state='APPLY_REQUIRED';status='APPLY_REQUIRED';reason='MANIFEST_MISSING'}}
    try{$m=Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8|ConvertFrom-Json}catch{return [pscustomobject]@{project_id=$ProjectId;state='SNAPSHOT_MANIFEST_INVALID';status='SNAPSHOT_MANIFEST_INVALID';reason='MANIFEST_PARSE_FAILED'}}
    $catalogHash=Get-CatalogHash $WorkerRoot
    if([string]$m.catalog_sha256 -ne $catalogHash){return [pscustomobject]@{project_id=$ProjectId;state='CATALOG_DRIFT';status='CATALOG_DRIFT';reason='CATALOG_HASH_MISMATCH';catalog_sha256=$catalogHash;manifest_catalog_sha256=[string]$m.catalog_sha256}}
    if([int]$m.schema_version -eq 1){return [pscustomobject]@{project_id=$ProjectId;state='DEEP_VERIFY_REQUIRED';status='DEEP_VERIFY_REQUIRED';reason='LEGACY_MANIFEST_REQUIRES_ADOPTION';catalog_sha256=$catalogHash}}
    if([int]$m.schema_version -ne 2 -or -not $m.accepted_snapshot){return [pscustomobject]@{project_id=$ProjectId;state='SNAPSHOT_MANIFEST_INVALID';status='SNAPSHOT_MANIFEST_INVALID';reason='MANIFEST_SCHEMA_UNSUPPORTED'}}
    $snap=$m.accepted_snapshot
    if([string]$snap.snapshot_contract -ne 'ACCEPTED_SNAPSHOT_V1'){return [pscustomobject]@{project_id=$ProjectId;state='SNAPSHOT_MANIFEST_INVALID';status='SNAPSHOT_MANIFEST_INVALID';reason='SNAPSHOT_CONTRACT_INVALID'}}
    if([string]$snap.snapshot_state -eq 'DEEP_VERIFY_REQUIRED'){return [pscustomobject]@{project_id=$ProjectId;state='DEEP_VERIFY_REQUIRED';status='DEEP_VERIFY_REQUIRED';reason='DEEP_INTEGRITY_VERIFY_FAILED';source_snapshot_id=[string]$snap.source_snapshot_id}}
    if([string]$snap.snapshot_state -ne 'ACCEPTED'){return [pscustomobject]@{project_id=$ProjectId;state='SNAPSHOT_MANIFEST_INVALID';status='SNAPSHOT_MANIFEST_INVALID';reason='SNAPSHOT_STATE_INVALID'}}
    if([string]$snap.catalog_sha256 -ne $catalogHash){return [pscustomobject]@{project_id=$ProjectId;state='CATALOG_DRIFT';status='CATALOG_DRIFT';reason='SNAPSHOT_CATALOG_HASH_MISMATCH'}}
    $projectRoot=Join-Path $WorkerRoot $ProjectId;$manifestRows=@(Get-ManifestArtifactRows $m);$snapRows=@($snap.artifacts)
    if(-not $manifestRows.Count){return [pscustomobject]@{project_id=$ProjectId;state='SNAPSHOT_MANIFEST_INVALID';status='SNAPSHOT_MANIFEST_INVALID';reason='NO_ACTIVE_ARTIFACTS'}}
    if($snapRows.Count -ne $manifestRows.Count){return [pscustomobject]@{project_id=$ProjectId;state='SNAPSHOT_MANIFEST_INVALID';status='SNAPSHOT_MANIFEST_INVALID';reason='SNAPSHOT_ARTIFACT_COUNT_MISMATCH'}}
    $fpMap=@{}
    foreach($a in $manifestRows){
        $key=Get-SnapshotArtifactKey $a;$sa=@($snapRows|Where-Object {(Get-SnapshotArtifactKey $_) -eq $key}|Select-Object -First 1)
        if(-not $sa){return [pscustomobject]@{project_id=$ProjectId;state='SNAPSHOT_MANIFEST_INVALID';status='SNAPSHOT_MANIFEST_INVALID';reason=("SNAPSHOT_ARTIFACT_MISSING:"+$key)}}
        foreach($field in @('canonical_path','tree_sha256','configuration_xml_sha256')){if([string]$sa.$field -ne [string]$a.$field){return [pscustomobject]@{project_id=$ProjectId;state='SNAPSHOT_MANIFEST_INVALID';status='SNAPSHOT_MANIFEST_INVALID';reason=("SNAPSHOT_ARTIFACT_FIELD_MISMATCH:"+$key+":"+$field)}}}
        if([int64]$sa.files -ne [int64]$a.files -or [int64]$sa.bytes -ne [int64]$a.bytes){return [pscustomobject]@{project_id=$ProjectId;state='SNAPSHOT_MANIFEST_INVALID';status='SNAPSHOT_MANIFEST_INVALID';reason=("SNAPSHOT_ARTIFACT_SIZE_MISMATCH:"+$key)}}
        $abs=Join-Path $projectRoot ([string]$a.canonical_path).Replace('/','\')
        if(-not(Test-Path -LiteralPath $abs -PathType Container)){return [pscustomobject]@{project_id=$ProjectId;state='SNAPSHOT_ROOT_MISSING';status='SNAPSHOT_ROOT_MISSING';reason=("CANONICAL_ROOT_MISSING:"+$a.canonical_path)}}
        if($a.platform -eq 'ONEC' -and -not(Test-Path -LiteralPath (Join-Path $abs 'Configuration.xml') -PathType Leaf)){return [pscustomobject]@{project_id=$ProjectId;state='SNAPSHOT_ROOT_MISSING';status='SNAPSHOT_ROOT_MISSING';reason=("ONEC_CONFIGURATION_XML_MISSING:"+$a.canonical_path)}}
        $state=[string]$sa.fingerprint_inventory_state
        if($state -eq 'PRESENT'){if([string]::IsNullOrWhiteSpace([string]$sa.fingerprint_inventory_path) -or [string]::IsNullOrWhiteSpace([string]$sa.fingerprint_inventory_sha256)){return [pscustomobject]@{project_id=$ProjectId;state='SNAPSHOT_MANIFEST_INVALID';status='SNAPSHOT_MANIFEST_INVALID';reason=("FINGERPRINT_IDENTITY_MISSING:"+$key)}};$inv=Join-Path (Split-Path -Parent $manifestPath) ([string]$sa.fingerprint_inventory_path).Replace('/','\');if(-not(Test-Path -LiteralPath $inv -PathType Leaf)){return [pscustomobject]@{project_id=$ProjectId;state='SNAPSHOT_ROOT_MISSING';status='SNAPSHOT_ROOT_MISSING';reason=("FINGERPRINT_INVENTORY_MISSING:"+$key)}}}elseif($state -ne 'ABSENT_LEGACY'){return [pscustomobject]@{project_id=$ProjectId;state='SNAPSHOT_MANIFEST_INVALID';status='SNAPSHOT_MANIFEST_INVALID';reason=("FINGERPRINT_STATE_INVALID:"+$key)}}
        $fpMap[$key]=[pscustomobject]@{state=$state;relative_path=[string]$sa.fingerprint_inventory_path;sha256=[string]$sa.fingerprint_inventory_sha256}
    }
    $expected=New-AcceptedSnapshot -ManifestParticipants @($m.participants) -CatalogSha256 $catalogHash -ProofBasis ([string]$snap.proof_basis) -PublicationGeneration ([int]$snap.publication_generation) -PublishedUtc ([string]$snap.published_utc) -FingerprintMap $fpMap
    if([string]$expected.source_snapshot_id -ne [string]$snap.source_snapshot_id){return [pscustomobject]@{project_id=$ProjectId;state='SNAPSHOT_MANIFEST_INVALID';status='SNAPSHOT_MANIFEST_INVALID';reason='SOURCE_SNAPSHOT_ID_MISMATCH'}}
    if(-not(Test-Path -LiteralPath (Join-Path $projectRoot 'Output') -PathType Container)){return [pscustomobject]@{project_id=$ProjectId;state='SNAPSHOT_ROOT_MISSING';status='SNAPSHOT_ROOT_MISSING';reason='OUTPUT_MISSING'}}
    [pscustomobject]@{project_id=$ProjectId;state='ACCEPTED';status='READY';reason='ACCEPTED_SNAPSHOT';source_snapshot_id=[string]$snap.source_snapshot_id;manifest_sha256=Get-Sha256File $manifestPath;manifest_path=$manifestPath;catalog_sha256=$catalogHash;publication_generation=[int]$snap.publication_generation;proof_basis=[string]$snap.proof_basis;artifact_count=$manifestRows.Count;deep_integrity_checked=$false}
}
function Test-LegacyManifestShape {
    param([Parameter(Mandatory)]$Manifest,[Parameter(Mandatory)][string]$ProjectRoot)
    if([int]$Manifest.schema_version -ne 1){return [pscustomobject]@{ok=$false;reason='NOT_LEGACY_V1'}}
    $rows=@(Get-ManifestArtifactRows $Manifest);if(-not $rows.Count){return [pscustomobject]@{ok=$false;reason='NO_ACTIVE_ARTIFACTS'}}
    foreach($a in $rows){if([string]::IsNullOrWhiteSpace($a.tree_sha256) -or $a.files -lt 1 -or $a.bytes -lt 1){return [pscustomobject]@{ok=$false;reason=("LEGACY_DIGEST_EVIDENCE_MISSING:"+(Get-SnapshotArtifactKey $a))}};$abs=Join-Path $ProjectRoot $a.canonical_path.Replace('/','\');if(-not(Test-Path -LiteralPath $abs -PathType Container)){return [pscustomobject]@{ok=$false;reason=("CANONICAL_ROOT_MISSING:"+$a.canonical_path)}};if($a.platform -eq 'ONEC' -and (-not(Test-Path -LiteralPath (Join-Path $abs 'Configuration.xml') -PathType Leaf) -or [string]::IsNullOrWhiteSpace($a.configuration_xml_sha256))){return [pscustomobject]@{ok=$false;reason=("ONEC_CONFIGURATION_EVIDENCE_MISSING:"+$a.canonical_path)}}}
    [pscustomobject]@{ok=$true;reason='OK';artifacts=$rows}
}
function Adopt-LegacyAcceptedSnapshot {
    param([Parameter(Mandatory)][string]$ProjectId,[string]$WorkerRoot=$script:DefaultWorkerRoot,[string]$ProgramDataRoot=$script:DefaultProgramDataRoot)
    $manifestPath=Get-ProjectManifestPath -ProjectId $ProjectId -WorkerRoot $WorkerRoot
    if(-not(Test-Path -LiteralPath $manifestPath -PathType Leaf)){return [pscustomobject]@{project_id=$ProjectId;status='DEEP_VERIFY_REQUIRED';reason='MANIFEST_MISSING'}}
    try{$m=Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8|ConvertFrom-Json}catch{return [pscustomobject]@{project_id=$ProjectId;status='DEEP_VERIFY_REQUIRED';reason='MANIFEST_PARSE_FAILED'}}
    if([int]$m.schema_version -eq 2){$f=Get-FastProjectState -ProjectId $ProjectId -WorkerRoot $WorkerRoot;return [pscustomobject]@{project_id=$ProjectId;status=$(if($f.state -eq 'ACCEPTED'){'ALREADY_ACCEPTED'}else{'DEEP_VERIFY_REQUIRED'});reason=$f.reason;fast_state=$f}}
    $catalogHash=Get-CatalogHash $WorkerRoot
    if([string]$m.catalog_sha256 -ne $catalogHash){return [pscustomobject]@{project_id=$ProjectId;status='DEEP_VERIFY_REQUIRED';reason='CATALOG_HASH_MISMATCH'}}
    if(@(Get-ApplyStageResidue -ProjectId $ProjectId -WorkerRoot $WorkerRoot).Count){return [pscustomobject]@{project_id=$ProjectId;status='DEEP_VERIFY_REQUIRED';reason='ORPHAN_STAGE_PRESENT'}}
    $shape=Test-LegacyManifestShape -Manifest $m -ProjectRoot (Join-Path $WorkerRoot $ProjectId);if(-not $shape.ok){return [pscustomobject]@{project_id=$ProjectId;status='DEEP_VERIFY_REQUIRED';reason=$shape.reason}}
    try{$applied=[DateTime]::Parse([string]$m.applied_utc).ToUniversalTime()}catch{return [pscustomobject]@{project_id=$ProjectId;status='DEEP_VERIFY_REQUIRED';reason='LEGACY_APPLIED_UTC_INVALID'}}
    $proof=@(Get-RecentWorkerOperations -Limit 10000 -ProgramDataRoot $ProgramDataRoot|Where-Object {$_.project_id -eq $ProjectId -and $_.operation_type -in @('APPLY','VERIFY','REPAIR') -and $_.state -in @('PASS','RECOVERED') -and $_.ended_utc -and ([DateTime]::Parse([string]$_.ended_utc).ToUniversalTime() -ge $applied)}|Sort-Object ended_utc -Descending|Select-Object -First 1)
    if(-not $proof.Count){return [pscustomobject]@{project_id=$ProjectId;status='DEEP_VERIFY_REQUIRED';reason='LEGACY_DURABLE_READY_PROOF_MISSING'}}
    $r=Set-ManifestAcceptedSnapshot -Manifest $m -ManifestPath $manifestPath -ProofBasis 'LEGACY_DEEP_VERIFIED' -PublicationGeneration 1 -ProofReceipt $proof[0]
    [pscustomobject]@{project_id=$ProjectId;status='ADOPTED';reason='LEGACY_DURABLE_READY_PROOF';source_snapshot_id=$r.source_snapshot_id;manifest_sha256=$r.manifest_sha256;proof_operation_id=[string]$proof[0].operation_id}
}
function Convert-DeepVerifiedManifestToAcceptedSnapshot {
    param([Parameter(Mandatory)][string]$ProjectId,[string]$WorkerRoot=$script:DefaultWorkerRoot)
    $manifestPath=Get-ProjectManifestPath -ProjectId $ProjectId -WorkerRoot $WorkerRoot;$m=Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8|ConvertFrom-Json
    if([int]$m.schema_version -eq 2){return Get-FastProjectState -ProjectId $ProjectId -WorkerRoot $WorkerRoot}
    $null=Set-ManifestAcceptedSnapshot -Manifest $m -ManifestPath $manifestPath -ProofBasis 'EXPLICIT_DEEP_VERIFIED' -PublicationGeneration 1
    Get-FastProjectState -ProjectId $ProjectId -WorkerRoot $WorkerRoot
}
function Adopt-AllLegacyAcceptedSnapshots {
    param([string]$WorkerRoot=$script:DefaultWorkerRoot,[string]$ProgramDataRoot=$script:DefaultProgramDataRoot)
    $catalog=Read-WorkerCatalog -WorkerRoot $WorkerRoot -AllowMissing;$rows=@()
    foreach($p in @($catalog.projects|Where-Object {$_.active -ne $false})){$manifestPath=Get-ProjectManifestPath -ProjectId $p.project_id -WorkerRoot $WorkerRoot;if(-not(Test-Path -LiteralPath $manifestPath -PathType Leaf)){continue};try{$m=Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8|ConvertFrom-Json}catch{$rows+=,[pscustomobject]@{project_id=$p.project_id;status='DEEP_VERIFY_REQUIRED';reason='MANIFEST_PARSE_FAILED'};continue};if([int]$m.schema_version -eq 1){$rows+=,(Adopt-LegacyAcceptedSnapshot -ProjectId $p.project_id -WorkerRoot $WorkerRoot -ProgramDataRoot $ProgramDataRoot)}elseif([int]$m.schema_version -eq 2){$f=Get-FastProjectState -ProjectId $p.project_id -WorkerRoot $WorkerRoot;$rows+=,[pscustomobject]@{project_id=$p.project_id;status=$(if($f.state -eq 'ACCEPTED'){'ALREADY_ACCEPTED'}else{'DEEP_VERIFY_REQUIRED'});reason=$f.reason}}}
    @($rows)
}
function New-SourceCopyPlan {
    param([Parameter(Mandatory)][string]$Source)
    if(-not(Test-Path -LiteralPath $Source -PathType Container)){throw "SOURCE_FOLDER_NOT_FOUND: $Source"}
    $root=[IO.Path]::GetFullPath($Source).TrimEnd('\');$rootItem=Get-Item -LiteralPath $root -Force -ErrorAction Stop
    if(($rootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){throw "REPARSE_POINT: $root"}
    $entries=@(Get-ChildItem -LiteralPath $root -Recurse -Force -ErrorAction Stop);$reparse=@($entries|Where-Object {($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0});if($reparse.Count){throw "REPARSE_POINT: $($reparse[0].FullName)"}
    $files=@();$dirs=@();$sum=[int64]0;$maxChars=0;$maxRel=$null
    foreach($e in $entries){$e.Refresh();$rel=$e.FullName.Substring($root.Length).TrimStart('\').Replace('\','/');if($e.PSIsContainer){$dirs+=,[pscustomobject]@{full_path=$e.FullName;relative_path=$rel;last_write_ticks=$e.LastWriteTimeUtc.Ticks}}else{$files+=,[pscustomobject]@{full_path=$e.FullName;relative_path=$rel;length=[int64]$e.Length;last_write_ticks=$e.LastWriteTimeUtc.Ticks};$sum+=[int64]$e.Length;if($rel.Length -gt $maxChars){$maxChars=$rel.Length;$maxRel=$rel}}}
    $rootItem.Refresh()
    [pscustomobject]@{root=$root;root_last_write_ticks=$rootItem.LastWriteTimeUtc.Ticks;files=@($files|Sort-Object full_path);directories=@($dirs|Sort-Object relative_path);file_count=$files.Count;bytes=$sum;max_relative_path_chars=$maxChars;max_relative_path=$maxRel}
}
function Assert-SourceCopyPlanStable {
    param([Parameter(Mandatory)]$Plan)
    try{$rootItem=Get-Item -LiteralPath $Plan.root -Force -ErrorAction Stop;if($rootItem.LastWriteTimeUtc.Ticks -ne [int64]$Plan.root_last_write_ticks){throw 'ROOT_METADATA_CHANGED'};foreach($d in @($Plan.directories)){$x=Get-Item -LiteralPath $d.full_path -Force -ErrorAction Stop;if(-not $x.PSIsContainer -or ($x.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or $x.LastWriteTimeUtc.Ticks -ne [int64]$d.last_write_ticks){throw ("DIRECTORY_METADATA_CHANGED:"+$d.relative_path)}};foreach($f in @($Plan.files)){$x=Get-Item -LiteralPath $f.full_path -Force -ErrorAction Stop;if($x.PSIsContainer -or ($x.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or [int64]$x.Length -ne [int64]$f.length -or $x.LastWriteTimeUtc.Ticks -ne [int64]$f.last_write_ticks){throw ("FILE_METADATA_CHANGED:"+$f.relative_path)}}}catch{throw ("SOURCE_CHANGED_DURING_SYNC: "+$_.Exception.Message)}
}
function Invoke-OnePassCopyHash {
    param([Parameter(Mandatory)]$Plan,[Parameter(Mandatory)][string]$Stage,[scriptblock]$ProgressCallback)
    New-Item -ItemType Directory -Force -Path $Stage|Out-Null
    foreach($d in @($Plan.directories)){if(-not [string]::IsNullOrWhiteSpace([string]$d.relative_path)){New-Item -ItemType Directory -Force -Path (Join-Path $Stage $d.relative_path.Replace('/','\'))|Out-Null}}
    if($ProgressCallback){& $ProgressCallback ([pscustomobject]@{phase='COPY_HASH';files_processed=0;files_total=$Plan.file_count;bytes_processed=[int64]0;bytes_total=[int64]$Plan.bytes})}
    $aggregate=[Security.Cryptography.SHA256]::Create();$rows=New-Object Collections.Generic.List[object];$processed=0;$processedBytes=[int64]0
    try{foreach($f in @($Plan.files)){$dest=Join-Path $Stage $f.relative_path.Replace('/','\');$parent=Split-Path -Parent $dest;if(-not(Test-Path -LiteralPath $parent)){New-Item -ItemType Directory -Force -Path $parent|Out-Null};$fileSha=[Security.Cryptography.SHA256]::Create();$input=$null;$output=$null;try{$input=[IO.File]::Open($f.full_path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read);$output=[IO.File]::Open($dest,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None);$buffer=New-Object byte[] 1048576;$written=[int64]0;while(($n=$input.Read($buffer,0,$buffer.Length)) -gt 0){$output.Write($buffer,0,$n);$null=$fileSha.TransformBlock($buffer,0,$n,$buffer,0);$written+=$n};$null=$fileSha.TransformFinalBlock([byte[]]@(),0,0);$output.Flush();if($written -ne [int64]$f.length){throw ("SOURCE_CHANGED_DURING_SYNC: length changed while copying "+$f.relative_path)}}finally{if($output){$output.Dispose()};if($input){$input.Dispose()}};$fh=([BitConverter]::ToString($fileSha.Hash)).Replace('-','').ToLowerInvariant();$fileSha.Dispose();if([int64](Get-Item -LiteralPath $dest -Force).Length -ne [int64]$f.length){throw ("APPLY_COPY_LENGTH_MISMATCH: "+$f.relative_path)};$row=[string]::Join([char]9,@([string]$f.relative_path,[string]$f.length,$fh))+[Environment]::NewLine;$line=[Text.Encoding]::UTF8.GetBytes($row);$null=$aggregate.TransformBlock($line,0,$line.Length,$line,0);$rows.Add([pscustomobject][ordered]@{path=[string]$f.relative_path;size=[int64]$f.length;sha256=$fh});$processed++;$processedBytes+=[int64]$f.length;if($ProgressCallback -and (($processed % 250) -eq 0 -or $processed -eq $Plan.file_count)){& $ProgressCallback ([pscustomobject]@{phase='COPY_HASH';files_processed=$processed;files_total=$Plan.file_count;bytes_processed=$processedBytes;bytes_total=[int64]$Plan.bytes})}};$null=$aggregate.TransformFinalBlock([byte[]]@(),0,0);$digest=([BitConverter]::ToString($aggregate.Hash)).Replace('-','').ToLowerInvariant()}finally{$aggregate.Dispose()}
    Assert-SourceCopyPlanStable $Plan
    [pscustomobject]@{digest=[pscustomobject]@{sha256=$digest;files=$Plan.file_count;bytes=[int64]$Plan.bytes;max_relative_path_chars=$Plan.max_relative_path_chars;max_relative_path=$Plan.max_relative_path};fingerprints=@($rows|ForEach-Object{$_})}
}
function Write-FingerprintInventory {
    param([Parameter(Mandatory)][string]$ManifestDir,[Parameter(Mandatory)][string]$ParticipantId,[Parameter(Mandatory)][string]$ArtifactType,[Parameter(Mandatory)][string]$ArtifactId,[Parameter(Mandatory)]$Rows)
    $dir=Join-Path $ManifestDir 'Fingerprints';New-Item -ItemType Directory -Force -Path $dir|Out-Null;$name=("{0}.{1}.{2}.jsonl" -f (Assert-SafeId $ParticipantId 'participant_id'),$ArtifactType.ToLowerInvariant(),(Assert-SafeId $ArtifactId 'artifact_id'));$path=Join-Path $dir $name;$tmp=$path+'.tmp-'+[Guid]::NewGuid().ToString('N');$writer=New-Object IO.StreamWriter($tmp,$false,(New-Object Text.UTF8Encoding($false)));try{foreach($r in @($Rows)){$writer.WriteLine(($r|ConvertTo-Json -Compress))}}finally{$writer.Dispose()};Move-Item -LiteralPath $tmp -Destination $path -Force;[pscustomobject]@{state='PRESENT';relative_path=("Fingerprints/$name");sha256=Get-Sha256File $path}
}

function Copy-ArtifactSafely {
    param([Parameter(Mandatory)][string]$Source,[Parameter(Mandatory)][string]$Target,[switch]$ReplaceExisting,[Parameter(Mandatory)][string]$ProjectRoot,[Parameter(Mandatory)][string]$ArchiveKey,[string]$ExpectedTargetDigest,[scriptblock]$ProgressCallback)
    $plan=New-SourceCopyPlan $Source
    if($ProgressCallback){& $ProgressCallback ([pscustomobject]@{phase='SCAN';files_processed=0;files_total=$plan.file_count;bytes_processed=[int64]0;bytes_total=[int64]$plan.bytes})}
    $archive=$null;$targetExisted=Test-Path -LiteralPath $Target -PathType Container;$workerRoot=Split-Path -Parent $ProjectRoot;$stageRoot=Get-ApplyStageRoot $workerRoot
    New-Item -ItemType Directory -Force -Path $stageRoot|Out-Null
    do{$token=[Guid]::NewGuid().ToString('N').Substring(0,8);$stage=Join-Path $stageRoot ("a.stage-$token")}while(Test-Path -LiteralPath $stage)
    $targetMaxChars=$(if($plan.max_relative_path_chars -gt 0){$Target.Length+1+[int]$plan.max_relative_path_chars}else{$Target.Length});$stageMaxChars=$(if($plan.max_relative_path_chars -gt 0){$stage.Length+1+[int]$plan.max_relative_path_chars}else{$stage.Length})
    if($targetMaxChars -ge 260){throw (New-ApplyCopyException -Class 'APPLY_TARGET_PATH_TOO_LONG' -SafeMessage ("Managed target path would reach {0} characters; Windows PowerShell 5.1 safe limit is 259." -f $targetMaxChars) -Phase 'PREFLIGHT' -Path $Target)}
    if($stageMaxChars -ge 260){throw (New-ApplyCopyException -Class 'APPLY_STAGE_PATH_TOO_LONG' -SafeMessage ("Internal staging path would reach {0} characters; safe copy was not started." -f $stageMaxChars) -Phase 'PREFLIGHT' -Path $stage)}
    $stageState='CREATED';$archiveMoved=$false
    try{
        Write-ApplyStageState -StagePath $stage -State CREATED -ProjectRoot $ProjectRoot -TargetPath $Target -ArchiveKey $ArchiveKey
        $stageState='COPYING';Write-ApplyStageState -StagePath $stage -State COPYING -ProjectRoot $ProjectRoot -TargetPath $Target -ArchiveKey $ArchiveKey
        $copied=Invoke-OnePassCopyHash -Plan $plan -Stage $stage -ProgressCallback $ProgressCallback;$srcDigest=$copied.digest
        $stageState='VERIFIED';Write-ApplyStageState -StagePath $stage -State VERIFIED -ProjectRoot $ProjectRoot -TargetPath $Target -ArchiveKey $ArchiveKey
        if($targetExisted){
            $targetHash=$ExpectedTargetDigest;if([string]::IsNullOrWhiteSpace($targetHash)){$targetHash=(Get-TreeDigest $Target).sha256}
            if($targetHash -eq $srcDigest.sha256){$null=Remove-ApplyStageTree -StagePath $stage;Remove-Item -LiteralPath ($stage+'.json') -Force -ErrorAction SilentlyContinue;return [pscustomobject]@{digest=$srcDigest;fingerprints=$copied.fingerprints;changed=$false;archived=$null;stage_lifecycle=@('CREATED','COPYING','VERIFIED','COMMITTED');target_max_path_chars=$targetMaxChars;stage_max_path_chars=$stageMaxChars}}
            if(-not $ReplaceExisting){throw "TARGET_CONFLICT: $Target"}
        }
        if($ProgressCallback){& $ProgressCallback ([pscustomobject]@{phase='PUBLISH';files_processed=$plan.file_count;files_total=$plan.file_count;bytes_processed=[int64]$plan.bytes;bytes_total=[int64]$plan.bytes})}
        if($targetExisted){$stamp=(Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ');$archive=Join-Path $ProjectRoot ("Detached\$ArchiveKey\$stamp");New-Item -ItemType Directory -Force -Path (Split-Path -Parent $archive)|Out-Null;Move-Item -LiteralPath $Target -Destination $archive -ErrorAction Stop;$archiveMoved=$true}else{$parent=Split-Path -Parent $Target;New-Item -ItemType Directory -Force -Path $parent|Out-Null}
        try{Move-Item -LiteralPath $stage -Destination $Target -ErrorAction Stop}catch{if($archiveMoved -and (Test-Path -LiteralPath $archive -PathType Container) -and -not(Test-Path -LiteralPath $Target)){try{Move-Item -LiteralPath $archive -Destination $Target -ErrorAction Stop;$archiveMoved=$false;$archive=$null}catch{}};throw}
        $stageState='COMMITTED';Write-ApplyStageState -StagePath $stage -State COMMITTED -ProjectRoot $ProjectRoot -TargetPath $Target -ArchiveKey $ArchiveKey;Remove-Item -LiteralPath ($stage+'.json') -Force -ErrorAction SilentlyContinue
        [pscustomobject]@{digest=$srcDigest;fingerprints=$copied.fingerprints;changed=$true;archived=$archive;stage_lifecycle=@('CREATED','COPYING','VERIFIED','COMMITTED');target_max_path_chars=$targetMaxChars;stage_max_path_chars=$stageMaxChars}
    }catch{
        $cause=$_.Exception;$residue=[pscustomobject]@{stage_path=$stage;target_path=$Target;metadata_path=($stage+'.json')};$cleanup=Remove-ApplyStageTree -StagePath $stage;$cleanupStatus=$cleanup.status
        if($cleanup.status -eq 'CLEANUP_FAILED'){$q=Move-ApplyStageToQuarantine -Residue $residue -ProjectRoot $ProjectRoot;$cleanupStatus=$q.status}else{Remove-Item -LiteralPath ($stage+'.json') -Force -ErrorAction SilentlyContinue}
        if($archiveMoved -and (Test-Path -LiteralPath $archive -PathType Container) -and -not(Test-Path -LiteralPath $Target)){try{Move-Item -LiteralPath $archive -Destination $Target -ErrorAction Stop;$archiveMoved=$false;$archive=$null}catch{throw (New-ApplyCopyException -Class 'APPLY_COMMIT_ROLLBACK_FAILED' -SafeMessage 'Verified stage commit failed and the previous canonical Target could not be restored automatically.' -Phase 'COMMIT_ROLLBACK' -Path $Target -CleanupStatus $cleanupStatus -InnerException $_.Exception)}}
        if($cause.Message -match '^SOURCE_CHANGED_DURING_SYNC:'){throw (New-ApplyCopyException -Class 'SOURCE_CHANGED_DURING_SYNC' -SafeMessage 'Source metadata changed while the managed snapshot was being copied; publication was aborted.' -Phase 'COPYING' -Path $Source -CleanupStatus $cleanupStatus -InnerException $cause)}
        $class=$(if($stageState -eq 'COPYING'){'APPLY_COPY_FAILED'}elseif($stageState -eq 'VERIFIED'){'APPLY_COMMIT_FAILED'}else{'APPLY_STAGE_FAILED'});$safe=$(if($stageState -eq 'COPYING'){'Copying into the managed staging area failed.'}elseif($stageState -eq 'VERIFIED'){'Verified staging data could not be committed to the canonical Target.'}else{'Managed staging failed before copy could complete.'})
        throw (New-ApplyCopyException -Class $class -SafeMessage $safe -Phase $stageState -Path $Target -CleanupStatus $cleanupStatus -InnerException $cause)
    }
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
    param([Parameter(Mandatory)][string]$ProjectId,[string]$WorkerRoot=$script:DefaultWorkerRoot,[scriptblock]$ProgressCallback)
    $c=Read-WorkerCatalog $WorkerRoot;$p=Find-Project $c $ProjectId;if(!$p){throw 'PROJECT_NOT_FOUND'};if($p.active -eq $false){throw 'PROJECT_INACTIVE'}
    $catalogHash=Get-CatalogHash $WorkerRoot;$projectRoot=Join-Path $WorkerRoot $ProjectId;$residue=@(Get-ApplyStageResidue -ProjectId $ProjectId -WorkerRoot $WorkerRoot)
    if($residue.Count){throw "APPLY_RESIDUE_REPAIR_REQUIRED: $($residue.Count) incomplete staging artifact(s) detected; run REPAIR before APPLY."}
    $manifestDir=Join-Path $projectRoot 'ProjectManifest';New-Item -ItemType Directory -Force -Path $manifestDir,(Join-Path $projectRoot 'Participants'),(Join-Path $projectRoot 'Output')|Out-Null
    $manifestPath=Join-Path $manifestDir 'project.json';$oldManifest=$null;if(Test-Path -LiteralPath $manifestPath -PathType Leaf){try{$oldManifest=Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8|ConvertFrom-Json}catch{}}
    $oldGeneration=$(if($oldManifest -and $oldManifest.accepted_snapshot){[int]$oldManifest.accepted_snapshot.publication_generation}else{0});$manifestParticipants=@();$changes=@();$fingerprintMap=@{}
    $activeParticipants=@($p.participants|Where-Object {$_.active -ne $false})
    $missingRequiredMain=@($activeParticipants|Where-Object {$_.platform -eq 'ONEC' -and (-not $_.target.main -or $_.target.main.active -eq $false)})
    foreach($part in $activeParticipants){
        if($part.platform -ne 'ONEC'){throw "PLATFORM_NOT_IMPLEMENTED_1C_FIRST: $($part.platform)"};$participantKey=Assert-SafeId $part.participant_id 'participant_id';$mPart=[ordered]@{participant_id=$participantKey;platform=$part.platform;role=$part.role;active=$true;target=[ordered]@{main=$null;extensions=@()}}
        if($part.target.main -and $part.target.main.active -ne $false){
            Assert-OneCExportRoot $part.target.main.source_path;$rel="Participants/$participantKey/Target/Main";$target=Join-Path $projectRoot $rel.Replace('/','\');$oldDigest=$null
            if($oldManifest){$oa=@(Get-ManifestArtifactRows $oldManifest|Where-Object {$_.canonical_path -eq $rel}|Select-Object -First 1);if($oa.Count){$oldDigest=$oa[0].tree_sha256}}
            $copy=Copy-ArtifactSafely -Source $part.target.main.source_path -Target $target -ReplaceExisting:([bool]$part.target.main.replace_existing) -ProjectRoot $projectRoot -ArchiveKey "$participantKey\Target\Main" -ExpectedTargetDigest $oldDigest -ProgressCallback $ProgressCallback
            $action=if(-not $copy.changed){'REUSED'}elseif($copy.archived){'REPLACED_DETACHED'}else{'COPIED'};$changes+=,[pscustomobject]@{participant_id=$participantKey;artifact_type='MAIN';artifact_id='main';source_input=$part.target.main.source_path;target_canonical_path=$rel;action=$action;detached_path=$copy.archived}
            $mPart.target.main=[ordered]@{artifact_id='main';active=$true;canonical_path=$rel;source_path=$part.target.main.source_path;tree_sha256=$copy.digest.sha256;files=$copy.digest.files;bytes=$copy.digest.bytes;configuration_xml_sha256=(Get-Sha256File (Join-Path $target 'Configuration.xml'))}
            $fingerprintMap["$participantKey|MAIN|main"]=Write-FingerprintInventory -ManifestDir $manifestDir -ParticipantId $participantKey -ArtifactType MAIN -ArtifactId main -Rows $copy.fingerprints
        }
        foreach($ext in @($part.target.extensions|Where-Object {$_.active -ne $false})){
            $eid=Assert-SafeId $ext.extension_id 'extension_id';Assert-OneCExportRoot $ext.source_path;$rel="Participants/$participantKey/Target/Extensions/$eid";$target=Join-Path $projectRoot $rel.Replace('/','\');$oldDigest=$null
            if($oldManifest){$oa=@(Get-ManifestArtifactRows $oldManifest|Where-Object {$_.canonical_path -eq $rel}|Select-Object -First 1);if($oa.Count){$oldDigest=$oa[0].tree_sha256}}
            $copy=Copy-ArtifactSafely -Source $ext.source_path -Target $target -ReplaceExisting:([bool]$ext.replace_existing) -ProjectRoot $projectRoot -ArchiveKey "$participantKey\Target\Extensions\$eid" -ExpectedTargetDigest $oldDigest -ProgressCallback $ProgressCallback
            $action=if(-not $copy.changed){'REUSED'}elseif($copy.archived){'REPLACED_DETACHED'}else{'COPIED'};$changes+=,[pscustomobject]@{participant_id=$participantKey;artifact_type='EXTENSION';artifact_id=$eid;source_input=$ext.source_path;target_canonical_path=$rel;action=$action;detached_path=$copy.archived}
            $mPart.target.extensions+=,[ordered]@{extension_id=$eid;artifact_id=$eid;active=$true;canonical_path=$rel;source_path=$ext.source_path;tree_sha256=$copy.digest.sha256;files=$copy.digest.files;bytes=$copy.digest.bytes;configuration_xml_sha256=(Get-Sha256File (Join-Path $target 'Configuration.xml'))}
            $fingerprintMap["$participantKey|EXTENSION|$eid"]=Write-FingerprintInventory -ManifestDir $manifestDir -ParticipantId $participantKey -ArtifactType EXTENSION -ArtifactId $eid -Rows $copy.fingerprints
        }
        $manifestParticipants+=,[pscustomobject]$mPart
    }
    $manifest=[pscustomobject][ordered]@{schema_version=2;project_id=$p.project_id;display_name=$p.display_name;active=$true;topology_authority='RP-20261004-026';catalog_sha256=$catalogHash;applied_utc=(Get-Date).ToUniversalTime().ToString('o');project_root=$projectRoot;participants=$manifestParticipants;output_relative='Output';accepted_snapshot=$null}
    if(-not $missingRequiredMain.Count -and $activeParticipants.Count){
        $manifest.accepted_snapshot=New-AcceptedSnapshot -ManifestParticipants @($manifestParticipants) -CatalogSha256 $catalogHash -ProofBasis 'ONE_PASS_COPY_HASH' -PublicationGeneration ($oldGeneration+1) -FingerprintMap $fingerprintMap
    }
    if($oldManifest){
        $desired=New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
        foreach($dp in @($manifest.participants)){
            if($dp.target.main){$null=$desired.Add([string]$dp.target.main.canonical_path)}
            foreach($de in @($dp.target.extensions)){$null=$desired.Add([string]$de.canonical_path)}
        }
        foreach($op in @($oldManifest.participants)){
            $oldArts=@()
            if($op.target.main){$oldArts+=,$op.target.main}
            $oldArts+=@($op.target.extensions)
            foreach($oa in $oldArts){
                $rel=[string]$oa.canonical_path
                if(-not $desired.Contains($rel)){
                    $abs=Join-Path $projectRoot $rel.Replace('/','\')
                    if(Test-Path -LiteralPath $abs){
                        $stamp=(Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
                        $detached=Join-Path $projectRoot ("Detached\Deactivated\$stamp\"+$rel.Replace('/','\'))
                        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $detached)|Out-Null
                        Move-Item -LiteralPath $abs -Destination $detached
                        $changes+=,[pscustomobject]@{
                            participant_id=[string]$op.participant_id
                            artifact_type=$(if($rel -match '/Extensions/'){'EXTENSION'}else{'MAIN'})
                            artifact_id=$(if($rel -match '/Extensions/([^/]+)$'){$Matches[1]}else{'main'})
                            source_input=$null
                            target_canonical_path=$rel
                            action='DEACTIVATED_DETACHED'
                            detached_path=$detached
                        }
                    }
                }
            }
        }
    }
    if($ProgressCallback){& $ProgressCallback ([pscustomobject]@{phase='PUBLISH';files_processed=$null;files_total=$null;bytes_processed=$null;bytes_total=$null})}
    Write-JsonAtomic $manifest $manifestPath;Apply-ProjectAcl -ProjectRoot $projectRoot
    $fast=Get-FastProjectState -ProjectId $ProjectId -WorkerRoot $WorkerRoot
    if($missingRequiredMain.Count){
        return [pscustomobject]@{project_id=$ProjectId;status='FAIL';state=$fast.state;catalog_sha256=$catalogHash;manifest_sha256=(Get-Sha256File $manifestPath);source_snapshot_id=$null;publication_generation=$oldGeneration;changes=$changes;errors=@($missingRequiredMain|ForEach-Object{"ONEC_MAIN_REQUIRED:"+[string]$_.participant_id});fast_state=$fast}
    }
    if(-not $activeParticipants.Count){
        return [pscustomobject]@{project_id=$ProjectId;status='FAIL';state=$fast.state;catalog_sha256=$catalogHash;manifest_sha256=(Get-Sha256File $manifestPath);source_snapshot_id=$null;publication_generation=$oldGeneration;changes=$changes;errors=@('NO_ACTIVE_PARTICIPANTS');fast_state=$fast}
    }
    if($fast.state -ne 'ACCEPTED'){throw ("SNAPSHOT_PUBLICATION_NOT_ACCEPTED: "+$fast.reason)}
    [pscustomobject]@{project_id=$ProjectId;status='READY';state='ACCEPTED';catalog_sha256=$catalogHash;manifest_sha256=$fast.manifest_sha256;source_snapshot_id=$fast.source_snapshot_id;publication_generation=$fast.publication_generation;changes=$changes;fast_state=$fast}
}

function Verify-WorkerProject {
    param([Parameter(Mandatory)][string]$ProjectId,[string]$WorkerRoot=$script:DefaultWorkerRoot,[scriptblock]$ProgressCallback)
    $catalog=Read-WorkerCatalog $WorkerRoot;$p=Find-Project $catalog $ProjectId;if(!$p){throw 'PROJECT_NOT_FOUND'};$projectRoot=Join-Path $WorkerRoot $ProjectId;$manifestPath=Get-ProjectManifestPath -ProjectId $ProjectId -WorkerRoot $WorkerRoot
    $residue=@(Get-ApplyStageResidue -ProjectId $ProjectId -WorkerRoot $WorkerRoot);if($residue.Count){return [pscustomobject]@{project_id=$ProjectId;status='INCOMPLETE_APPLY_RESIDUE';reason='ORPHAN_STAGE_PRESENT';residue_count=$residue.Count;residue=@($residue|Select-Object layout,state,stage_path,target_path);verification_contract='DEEP_INTEGRITY_VERIFY_V1'}}
    if(-not(Test-Path -LiteralPath $manifestPath -PathType Leaf)){return [pscustomobject]@{project_id=$ProjectId;status='APPLY_REQUIRED';reason='MANIFEST_MISSING';verification_contract='DEEP_INTEGRITY_VERIFY_V1'}}
    try{$m=Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8|ConvertFrom-Json}catch{return [pscustomobject]@{project_id=$ProjectId;status='FAIL';reason='MANIFEST_PARSE_FAILED';errors=@('MANIFEST_PARSE_FAILED');verification_contract='DEEP_INTEGRITY_VERIFY_V1'}}
    $catalogHash=Get-CatalogHash $WorkerRoot;if($m.catalog_sha256 -ne $catalogHash){return [pscustomobject]@{project_id=$ProjectId;status='DRIFT_APPLY_REQUIRED';reason='CATALOG_HASH_MISMATCH';manifest_catalog_sha256=$m.catalog_sha256;catalog_sha256=$catalogHash;verification_contract='DEEP_INTEGRITY_VERIFY_V1'}}
    $errors=New-Object System.Collections.Generic.List[string];$artifacts=@(Get-ManifestArtifactRows $m);if(-not $artifacts.Count){$errors.Add('NO_ACTIVE_PARTICIPANTS')};$artifactIndex=0
    foreach($a in $artifacts){$artifactIndex++;$abs=Join-Path $projectRoot $a.canonical_path.Replace('/','\');if(-not(Test-Path -LiteralPath $abs -PathType Container)){$errors.Add("MISSING:$($a.canonical_path)");continue};$cb=$null;if($ProgressCallback){$cb={param($x);& $ProgressCallback ([pscustomobject]@{phase='DEEP_VERIFY';artifact_index=$artifactIndex;artifact_total=$artifacts.Count;artifact_path=$a.canonical_path;files_processed=$x.files_processed;files_total=$x.files_total;bytes_processed=$x.bytes_processed;bytes_total=$x.bytes_total})}.GetNewClosure()};try{$dig=Get-TreeDigest -Root $abs -ProgressCallback $cb;if($dig.sha256 -ne $a.tree_sha256){$errors.Add("HASH_MISMATCH:$($a.canonical_path)")}}catch{$errors.Add("VERIFY_ERROR:$($a.canonical_path):$($_.Exception.Message)")};if($a.platform -eq 'ONEC' -and -not(Test-Path -LiteralPath (Join-Path $abs 'Configuration.xml') -PathType Leaf)){$errors.Add("ONEC_LAYOUT:$($a.canonical_path)")}}
    if(-not(Test-Path -LiteralPath (Join-Path $projectRoot 'Output') -PathType Container)){$errors.Add('OUTPUT_MISSING')}
    if([int]$m.schema_version -eq 2 -and $m.accepted_snapshot){
        if($errors.Count){
            $m.accepted_snapshot.snapshot_state='DEEP_VERIFY_REQUIRED'
            Write-JsonAtomic $m $manifestPath
        }elseif([string]$m.accepted_snapshot.snapshot_state -ne 'ACCEPTED'){
            $fp=@{}
            foreach($sa in @($m.accepted_snapshot.artifacts)){
                $fp[(Get-SnapshotArtifactKey $sa)]=[pscustomobject]@{state=[string]$sa.fingerprint_inventory_state;relative_path=[string]$sa.fingerprint_inventory_path;sha256=[string]$sa.fingerprint_inventory_sha256}
            }
            $null=Set-ManifestAcceptedSnapshot -Manifest $m -ManifestPath $manifestPath -ProofBasis 'EXPLICIT_DEEP_VERIFIED' -PublicationGeneration ([int]$m.accepted_snapshot.publication_generation+1) -FingerprintMap $fp
        }
    }
    [pscustomobject]@{project_id=$ProjectId;status=$(if($errors.Count){'FAIL'}else{'READY'});catalog_sha256=$catalogHash;manifest_sha256=Get-Sha256File $manifestPath;errors=@($errors);verification_contract='DEEP_INTEGRITY_VERIFY_V1';artifact_count=$artifacts.Count}
}

function Get-WorkerDependencyHealth {
    param([string]$ProgramDataRoot=$script:DefaultProgramDataRoot)
    $node=Get-Command node.exe -ErrorAction SilentlyContinue
    $nodeVersion=$(if($node){(& $node.Source --version).Trim()}else{$null})
    $rgPath=Join-Path $ProgramDataRoot 'runtime\rg.exe'
    $rgVersion=$null
    if(Test-Path -LiteralPath $rgPath -PathType Leaf){
        try{$rgVersion=Get-RipgrepSemanticVersion ((& $rgPath --version|Select-Object -First 1))}catch{}
    }
    [pscustomobject]@{
        node=[pscustomobject]@{required=$script:NodeVersion;actual=$nodeVersion;healthy=($nodeVersion -eq "v$($script:NodeVersion)")}
        ripgrep=[pscustomobject]@{required=$script:RgVersion;actual=$rgVersion;healthy=($rgVersion -eq $script:RgVersion);path=$rgPath}
        python_required=$false
        cloudflare_cli_required=$false
    }
}

function Get-HelperConnectionState {
    param([string]$ProgramDataRoot=$script:DefaultProgramDataRoot)
    $helper=Join-Path $ProgramDataRoot 'helper\hosted-helper.mjs'
    $procs=@()
    if(Test-Path -LiteralPath $helper -PathType Leaf){
        $procs=@(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue|Where-Object{$_.Name -eq 'node.exe' -and $_.CommandLine -and $_.CommandLine.Contains($helper)})
    }
    $statePath=Join-Path $ProgramDataRoot 'runtime\hosted-helper-state.json'
    $state=$null
    if(Test-Path -LiteralPath $statePath -PathType Leaf){try{$state=Get-Content -LiteralPath $statePath -Raw -Encoding UTF8|ConvertFrom-Json}catch{}}
    $logPath=Join-Path $ProgramDataRoot 'runtime\hosted-helper-log.jsonl'
    $connected=$null
    if(Test-Path -LiteralPath $logPath -PathType Leaf){
        foreach($line in @(Get-Content -LiteralPath $logPath -Tail 100 -Encoding UTF8)){
            try{$e=$line|ConvertFrom-Json;if($e.event -eq 'CONNECTED'){$connected=$e}}catch{}
        }
    }
    $notExpired=$false
    if($state -and $state.expires_utc){try{$notExpired=(Get-Date).ToUniversalTime() -lt ([DateTime]::Parse($state.expires_utc).ToUniversalTime())}catch{}}
    $status=if($procs.Count -eq 0){'OFFLINE'}elseif($connected -and $notExpired){'CONNECTED'}else{'RUNNING_NO_CONNECT_EVIDENCE'}
    [pscustomobject]@{
        status=$status
        process_count=$procs.Count
        process_ids=@($procs|Select-Object -ExpandProperty ProcessId)
        session_id=$(if($state){$state.session_id}else{$null})
        expires_utc=$(if($state){$state.expires_utc}else{$null})
        project_id=$(if($state){$state.project_id}else{$null})
        task_id=$(if($state){$state.task_id}else{$null})
        last_connected_utc=$(if($connected){$connected.at_utc}else{$null})
        helper_path=$helper
    }
}

function Get-OutputProposalSummary {
    param([string]$WorkerRoot=$script:DefaultWorkerRoot)
    $catalog=Read-WorkerCatalog -WorkerRoot $WorkerRoot -AllowMissing
    $rows=@()
    foreach($p in @($catalog.projects)){
        $outRoot=Join-Path (Join-Path $WorkerRoot $p.project_id) 'Output'
        $tasks=@()
        if(Test-Path -LiteralPath $outRoot -PathType Container){
            foreach($dir in @(Get-ChildItem -LiteralPath $outRoot -Directory -ErrorAction SilentlyContinue)){
                $prov=Join-Path $dir.FullName '_proposal_provenance.json'
                $status=$null;$files=$null;$bytes=$null
                if(Test-Path -LiteralPath $prov -PathType Leaf){
                    try{$doc=Get-Content -LiteralPath $prov -Raw -Encoding UTF8|ConvertFrom-Json;$status=$doc.status;$files=$doc.total_files;$bytes=$doc.total_bytes}catch{$status='INVALID_PROVENANCE'}
                }
                $tasks+=,[pscustomobject]@{task_id=$dir.Name;status=$status;proposal_files=$files;proposal_bytes=$bytes;last_write_utc=$dir.LastWriteTimeUtc.ToString('o')}
            }
        }
        $rows+=,[pscustomobject]@{project_id=$p.project_id;task_count=$tasks.Count;tasks=@($tasks|Sort-Object last_write_utc -Descending|Select-Object -First 20)}
    }
    $rows
}

function Get-WorkerStatus {
    param([string]$WorkerRoot=$script:DefaultWorkerRoot,[string]$ProgramDataRoot=$script:DefaultProgramDataRoot)
    $catalog=Read-WorkerCatalog -WorkerRoot $WorkerRoot -AllowMissing;$runtimeState=Join-Path $ProgramDataRoot 'runtime\active-admission.json';$active=$null;if(Test-Path -LiteralPath $runtimeState){try{$active=Get-Content $runtimeState -Raw|ConvertFrom-Json}catch{}}
    $rows=@();foreach($p in @($catalog.projects)){$v=try{Get-FastProjectState -ProjectId $p.project_id -WorkerRoot $WorkerRoot}catch{[pscustomobject]@{state='SNAPSHOT_MANIFEST_INVALID';status='SNAPSHOT_MANIFEST_INVALID';reason=$_.Exception.Message}};$rows+=,[pscustomobject]@{project_id=$p.project_id;display_name=$p.display_name;active=($p.active -ne $false);verification=$(if($v.state -eq 'ACCEPTED'){'READY'}else{$v.state});fast_state=$v.state;fast_reason=$v.reason;source_snapshot_id=$v.source_snapshot_id;participant_count=@($p.participants|Where-Object{$_.active -ne $false}).Count}}
    $recent=@(Get-RecentWorkerOperations -Limit 20 -ProgramDataRoot $ProgramDataRoot);$lastVerify=@($recent|Where-Object{$_.operation_type -eq 'VERIFY'}|Select-Object -First 1);$installedPath=Join-Path $ProgramDataRoot 'installed-state.json';$installed=$null;if(Test-Path -LiteralPath $installedPath -PathType Leaf){try{$installed=Get-Content -LiteralPath $installedPath -Raw -Encoding UTF8|ConvertFrom-Json}catch{}}
    $integrity=$null;if($installed){try{$integrity=Test-InstalledProductIntegrity -WorkerRoot $WorkerRoot -ProgramDataRoot $ProgramDataRoot}catch{$integrity=[pscustomobject]@{status='FAIL';error_class=(($_.Exception.Message -split ':',2)[0]);message=$_.Exception.Message}}}else{$integrity=[pscustomobject]@{status='NOT_INSTALLED'}}
    [pscustomobject]@{product_version=$script:ProductVersion;installed=($null -ne $installed);installed_state=$installed;installed_integrity=$integrity;worker_root=$WorkerRoot;catalog_path=Get-CatalogPath $WorkerRoot;dependencies=Get-WorkerDependencyHealth $ProgramDataRoot;projects=$rows;active_admission=$active;helper=Get-HelperConnectionState $ProgramDataRoot;current_operation=Get-CurrentWorkerOperation $ProgramDataRoot;last_operation=$(if($recent.Count){$recent[0]}else{$null});operation_recovery=Get-OperationRecoveryClassification $ProgramDataRoot;last_verify=$(if($lastVerify.Count){$lastVerify[0]}else{$null});output=Get-OutputProposalSummary $WorkerRoot;state_check_contract='FAST_STATE_CHECK_V1'}
}

function Get-WorkerDiagnostics {
    param([string]$WorkerRoot=$script:DefaultWorkerRoot,[string]$ProgramDataRoot=$script:DefaultProgramDataRoot,[int]$Recent=20)
    [pscustomobject]@{
        generated_utc=(Get-Date).ToUniversalTime().ToString('o')
        status=Get-WorkerStatus -WorkerRoot $WorkerRoot -ProgramDataRoot $ProgramDataRoot
        recent_operations=@(Get-RecentWorkerOperations -Limit $Recent -ProgramDataRoot $ProgramDataRoot)
        operation_log=@(Get-WorkerOperationLog -Tail 100 -ProgramDataRoot $ProgramDataRoot)
        secret_material_included=$false
    }
}

function Export-WorkerDiagnosticBundle {
    param([string]$WorkerRoot=$script:DefaultWorkerRoot,[string]$ProgramDataRoot=$script:DefaultProgramDataRoot,[string]$Destination)
    if([string]::IsNullOrWhiteSpace($Destination)){
        $dir=Join-Path $env:USERPROFILE 'Desktop'
        if(-not(Test-Path -LiteralPath $dir -PathType Container)){$dir=$env:TEMP}
        $Destination=Join-Path $dir ("OneCChatWorker-Diagnostics-{0}.zip" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
    }
    $stage=Join-Path $env:TEMP ('OneCChatWorker-Diag-'+[Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force -Path $stage|Out-Null
    try{
        $diag=Get-WorkerDiagnostics -WorkerRoot $WorkerRoot -ProgramDataRoot $ProgramDataRoot
        [IO.File]::WriteAllText((Join-Path $stage 'diagnostics.json'),($diag|ConvertTo-Json -Depth 30),(New-Object Text.UTF8Encoding($false)))
        [IO.File]::WriteAllLines((Join-Path $stage 'operations.log'),@($diag.operation_log),(New-Object Text.UTF8Encoding($false)))
        $helperLog=Join-Path $ProgramDataRoot 'runtime\hosted-helper-log.jsonl'
        if(Test-Path -LiteralPath $helperLog -PathType Leaf){
            Get-Content -LiteralPath $helperLog -Tail 200 -Encoding UTF8|Set-Content -LiteralPath (Join-Path $stage 'helper-log-tail.jsonl') -Encoding UTF8
        }
        Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $Destination -Force
    }finally{Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue}
    [pscustomobject]@{status='PASS';bundle=$Destination;secret_material_included=$false}
}

function Write-ProviderConfig {
    param([Parameter(Mandatory)][string]$ProjectId,[string]$WorkerRoot=$script:DefaultWorkerRoot,[string]$ProgramDataRoot=$script:DefaultProgramDataRoot)
    $rg=Join-Path $ProgramDataRoot 'runtime\rg.exe'
    if(-not(Test-Path -LiteralPath $rg -PathType Leaf)){throw 'RG_NOT_INSTALLED'}
    $cfg=[ordered]@{schema_version=1;contract_id='onecchatworker';contract_version='1.0';provider_version='1.0.0';worker_root=$WorkerRoot;admitted_projects=@($ProjectId);rg_path=$rg;audit_path=(Join-Path $ProgramDataRoot 'audit\reader-audit.jsonl');limits=[ordered]@{max_list_depth=4;max_list_entries=2000;default_read_lines=120;max_read_lines=400;max_context_lines=20;max_pattern_chars=512;default_search_matches=20;max_search_matches=100;search_timeout_ms=30000;max_rg_output_bytes=33554432;max_source_file_bytes=16777216;max_artifact_read_bytes=4194304;max_artifact_file_bytes=4194304;max_encoded_content_chars=6000000;max_batch_files=16;max_batch_total_bytes=12582912}}
    Write-JsonAtomic $cfg (Join-Path $ProgramDataRoot 'provider\provider-config.json')
}

function New-Admission {
    param([Parameter(Mandatory)][string]$ProjectId,[Parameter(Mandatory)][string]$TaskId,[string]$WorkerRoot=$script:DefaultWorkerRoot,[string]$ProgramDataRoot=$script:DefaultProgramDataRoot,[string]$RelayUrl=$script:DefaultRelayUrl,$AcceptedState)
    Assert-SafeId $TaskId 'task_id'|Out-Null;$v=$AcceptedState;if(-not $v){$v=Get-FastProjectState -ProjectId $ProjectId -WorkerRoot $WorkerRoot};if($v.project_id -ne $ProjectId -or $v.state -ne 'ACCEPTED'){throw "PROJECT_NOT_READY: $($v.state)"}
    $manifest=Get-ProjectManifestPath -ProjectId $ProjectId -WorkerRoot $WorkerRoot;$manifestDoc=Get-Content -LiteralPath $manifest -Raw -Encoding UTF8|ConvertFrom-Json;if([int]$manifestDoc.schema_version -ne 2 -or -not $manifestDoc.accepted_snapshot){throw 'SNAPSHOT_MANIFEST_INVALID'};if(@($manifestDoc.participants|Where-Object {$_.platform -ne 'ONEC'}).Count){throw 'PLATFORM_NOT_IMPLEMENTED_1C_FIRST'}
    $manifestSha=Get-Sha256File $manifest;if([string]$v.manifest_sha256 -and $manifestSha -ne [string]$v.manifest_sha256){throw 'SNAPSHOT_CHANGED_DURING_ADMISSION'};if([string]$manifestDoc.accepted_snapshot.source_snapshot_id -ne [string]$v.source_snapshot_id){throw 'SOURCE_SNAPSHOT_ID_MISMATCH'}
    Write-ProviderConfig -ProjectId $ProjectId -WorkerRoot $WorkerRoot -ProgramDataRoot $ProgramDataRoot
    $a=[ordered]@{schema_version=2;project_id=$ProjectId;task_id=$TaskId;created_utc=(Get-Date).ToUniversalTime().ToString('o');manifest_path=$manifest;manifest_sha256=$manifestSha;source_snapshot_id=[string]$v.source_snapshot_id;snapshot_contract='ACCEPTED_SNAPSHOT_V1';provider_config_path=(Join-Path $ProgramDataRoot 'provider\provider-config.json');relay_url=$RelayUrl;helper_secret_path=(Join-Path $ProgramDataRoot 'secrets\helper-secret.txt');runtime_dir=(Join-Path $ProgramDataRoot 'runtime');caps=[ordered]@{ttl_minutes=360;max_requests=32;max_cumulative_result_bytes=36000;max_result_bytes=3000;max_search_matches=8;max_read_lines=20;max_write_file_bytes=32768;max_task_bytes=131072;max_task_files=8;max_read_chunk_bytes=1800}}
    Write-JsonAtomic $a (Join-Path $ProgramDataRoot 'runtime\active-admission.json');[pscustomobject]$a
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
    [pscustomobject]@{powershell=$PSVersionTable.PSVersion.ToString();administrator=(Test-IsAdministrator);winget=[bool]$winget;node=$(if($node){(& $node.Source --version).Trim()}else{$null});node_required=$script:NodeVersion;rg=$(if($rg){Get-RipgrepSemanticVersion ((& $rg.Source --version|Select-Object -First 1))}else{$null});rg_required=$script:RgVersion}
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
    param(
        [Parameter(Mandatory)][string]$PackageRoot,
        [string]$ProgramDataRoot=$script:DefaultProgramDataRoot,
        [switch]$NoInstall
    )
    if(-not(Test-IsAdministrator)){throw 'ADMIN_REQUIRED'}
    $lock=Read-RuntimeLock $PackageRoot
    $nodeSpec=$lock.dependencies.node
    $rgSpec=$lock.dependencies.ripgrep

    $node=Get-Command node.exe -ErrorAction SilentlyContinue
    if(-not $node -and (Test-Path -LiteralPath 'C:\Program Files\nodejs\node.exe' -PathType Leaf)){$node=Get-Item 'C:\Program Files\nodejs\node.exe'}
    $nodePath=$(if($node){if($node.PSObject.Properties.Name -contains 'Source' -and $node.Source){[string]$node.Source}else{[string]$node.FullName}}else{$null})
    $nodeAction='REUSED'
    $nodeVersion=$(if($nodePath){(& $nodePath --version).Trim()}else{$null})
    if(-not $node -or $nodeVersion -ne "v$($nodeSpec.version)"){
        if($NoInstall){throw "NODE_REQUIRED_PIN_MISSING: $($nodeSpec.version)"}
        if(-not(Get-Command winget.exe -ErrorAction SilentlyContinue)){throw 'WAITING_FOR_NODE: winget unavailable'}
        $nodeAction=if($node){'UPDATED'}else{'INSTALLED'}
        & winget.exe install --id $nodeSpec.winget_id --version $nodeSpec.version --exact --silent --accept-package-agreements --accept-source-agreements
        if($LASTEXITCODE -ne 0){throw 'NODE_INSTALL_FAILED'}
        $nodePath='C:\Program Files\nodejs\node.exe'
        if(-not(Test-Path -LiteralPath $nodePath -PathType Leaf)){throw 'NODE_NOT_FOUND_AFTER_INSTALL'}
        $node=Get-Item $nodePath;$nodeVersion=(& $nodePath --version).Trim()
    }
    if($nodeVersion -ne "v$($nodeSpec.version)"){throw "NODE_VERSION_MISMATCH: $nodeVersion"}
    $nodeHash=Get-Sha256File $nodePath
    if($nodeHash -ne [string]$nodeSpec.reference_sha256){throw "NODE_HASH_MISMATCH: $nodeHash"}

    $rgPath=Find-RipgrepExecutable
    $rgVersion=$null
    if($rgPath){$rgVersion=Get-RipgrepSemanticVersion ((& $rgPath --version|Select-Object -First 1))}
    $rgAction='REUSED'
    if(-not $rgPath -or $rgVersion -ne [string]$rgSpec.version){
        if($NoInstall){throw "RG_REQUIRED_PIN_MISSING: $($rgSpec.version)"}
        if(-not(Get-Command winget.exe -ErrorAction SilentlyContinue)){throw 'WAITING_FOR_RG: winget unavailable'}
        $rgAction=if($rgPath){'UPDATED'}else{'INSTALLED'}
        & winget.exe install --id $rgSpec.winget_id --version $rgSpec.version --exact --silent --accept-package-agreements --accept-source-agreements
        if($LASTEXITCODE -ne 0){throw 'RG_INSTALL_FAILED'}
        $rgPath=Find-RipgrepExecutable
    }
    if(-not $rgPath){throw 'RG_NOT_FOUND_AFTER_INSTALL'}
    $actualRg=Get-RipgrepSemanticVersion ((& $rgPath --version|Select-Object -First 1))
    if($actualRg -ne [string]$rgSpec.version){throw "RG_VERSION_MISMATCH: $actualRg"}
    $rgHash=Get-Sha256File $rgPath
    if($rgHash -ne [string]$rgSpec.reference_sha256){throw "RG_HASH_MISMATCH: $rgHash"}
    $runtime=Join-Path $ProgramDataRoot 'runtime';New-Item -ItemType Directory -Force -Path $runtime|Out-Null
    $rgInstalled=Join-Path $runtime 'rg.exe'
    $rgCopyAction='INSTALLED'
    if(Test-Path -LiteralPath $rgInstalled -PathType Leaf){$rgCopyAction=if((Get-Sha256File $rgInstalled) -eq $rgHash){'REUSED'}else{'UPDATED'}}
    if($rgCopyAction -ne 'REUSED'){Copy-Item -LiteralPath $rgPath -Destination $rgInstalled -Force}
    if((Get-Sha256File $rgInstalled) -ne $rgHash){throw 'RG_INSTALLED_COPY_HASH_MISMATCH'}
    [pscustomobject]@{
        node=[pscustomobject]@{action=$nodeAction;version=$nodeVersion;sha256=$nodeHash;path=$nodePath}
        ripgrep=[pscustomobject]@{action=$rgAction;runtime_copy_action=$rgCopyAction;version=$actualRg;sha256=$rgHash;source_path=$rgPath;runtime_path=$rgInstalled}
        python=[pscustomobject]@{action='SKIPPED_NOT_REQUIRED'}
        cloudflare_cli=[pscustomobject]@{action='SKIPPED_NOT_REQUIRED'}
    }
}

function Resolve-WorkerOperatorIdentity {
    param([string]$OperatorIdentity)
    if([string]::IsNullOrWhiteSpace($OperatorIdentity)){$OperatorIdentity=[Security.Principal.WindowsIdentity]::GetCurrent().Name}
    try{
        $account=New-Object Security.Principal.NTAccount($OperatorIdentity)
        $sid=$account.Translate([Security.Principal.SecurityIdentifier])
    }catch{throw "OPERATOR_IDENTITY_INVALID: $OperatorIdentity"}
    $readerAccount=New-Object Security.Principal.NTAccount("$env:COMPUTERNAME\$($script:ReaderName)")
    try{$readerSid=$readerAccount.Translate([Security.Principal.SecurityIdentifier])}catch{throw "READER_IDENTITY_INVALID: $($script:ReaderName)"}
    if($sid.Value -eq $readerSid.Value){throw 'OPERATOR_IDENTITY_MUST_DIFFER_FROM_READER'}
    [pscustomobject]@{account=$account.Value;sid=$sid.Value;icacls_identity=('*'+$sid.Value);reader_sid=$readerSid.Value;reader_icacls_identity=('*'+$readerSid.Value)}
}

function Invoke-IcaclsChecked {
    param([Parameter(Mandatory)][string]$Path,[Parameter(Mandatory)][string[]]$Arguments)
    & icacls.exe $Path @Arguments | Out-Null
    if($LASTEXITCODE -ne 0){throw "ACL_REPAIR_FAILED: $Path"}
}

function Protect-WorkerRuntimeFile {
    param([Parameter(Mandatory)][string]$Path,[Parameter(Mandatory)]$Identity,[switch]$Secret)
    if(-not(Test-Path -LiteralPath $Path -PathType Leaf)){return}
    $grants=@('*S-1-5-18:F','*S-1-5-32-544:F')
    if($Secret){$grants+=($Identity.reader_icacls_identity+':R')}
    else{
        $grants+=($Identity.icacls_identity+':RX')
        $grants+=($Identity.reader_icacls_identity+':RX')
    }
    Invoke-IcaclsChecked -Path $Path -Arguments @('/reset')
    Invoke-IcaclsChecked -Path $Path -Arguments @('/inheritance:r')
    Invoke-IcaclsChecked -Path $Path -Arguments (@('/grant:r')+$grants)
}

function Set-WorkerOperatorAcl {
    param([string]$WorkerRoot=$script:DefaultWorkerRoot,[string]$ProgramDataRoot=$script:DefaultProgramDataRoot,[string]$OperatorIdentity)
    if(-not(Test-IsAdministrator)){throw 'ADMIN_REQUIRED'}
    $identity=Resolve-WorkerOperatorIdentity $OperatorIdentity
    $required=@($WorkerRoot,$ProgramDataRoot,(Join-Path $ProgramDataRoot 'provider'),(Join-Path $ProgramDataRoot 'helper'),(Join-Path $ProgramDataRoot 'runtime'),(Join-Path $ProgramDataRoot 'audit'),(Join-Path $ProgramDataRoot 'secrets'),(Join-Path $ProgramDataRoot 'product'))
    foreach($path in $required){if(-not(Test-Path -LiteralPath $path -PathType Container)){throw "ACL_REPAIR_ROOT_MISSING: $path"}}
    $operations=Join-Path $ProgramDataRoot 'operations'
    New-Item -ItemType Directory -Force -Path $operations|Out-Null

    $system='*S-1-5-18:(OI)(CI)F'
    $admins='*S-1-5-32-544:(OI)(CI)F'
    $operatorM=$identity.icacls_identity+':(OI)(CI)M'
    $operatorRx=$identity.icacls_identity+':(OI)(CI)RX'
    $readerRx=$identity.reader_icacls_identity+':(OI)(CI)RX'
    $readerM=$identity.reader_icacls_identity+':(OI)(CI)M'

    Invoke-IcaclsChecked -Path $ProgramDataRoot -Arguments @('/inheritance:r','/grant:r',$system,$admins,($identity.icacls_identity+':(OI)(CI)RX'),($identity.reader_icacls_identity+':(OI)(CI)RX'))
    Invoke-IcaclsChecked -Path $WorkerRoot -Arguments @('/inheritance:r','/grant:r',$system,$admins,$operatorM,$readerRx)
    Invoke-IcaclsChecked -Path $operations -Arguments @('/grant:r',$operatorM,$readerRx)
    Invoke-IcaclsChecked -Path (Join-Path $ProgramDataRoot 'provider') -Arguments @('/grant:r',$operatorM,$readerRx)
    Invoke-IcaclsChecked -Path (Join-Path $ProgramDataRoot 'runtime') -Arguments @('/grant:r',$operatorM,$readerM)
    Invoke-IcaclsChecked -Path (Join-Path $ProgramDataRoot 'audit') -Arguments @('/inheritance:r','/grant:r',$system,$admins,$operatorRx,$readerM)
    Invoke-IcaclsChecked -Path (Join-Path $ProgramDataRoot 'helper') -Arguments @('/inheritance:r','/grant:r',$system,$admins,$operatorRx,$readerRx)
    Invoke-IcaclsChecked -Path (Join-Path $ProgramDataRoot 'product') -Arguments @('/inheritance:r','/grant:r',$system,$admins,$operatorRx,$readerRx)
    Invoke-IcaclsChecked -Path (Join-Path $ProgramDataRoot 'secrets') -Arguments @('/inheritance:r','/grant:r','*S-1-5-18:F','*S-1-5-32-544:F',($identity.icacls_identity+':RX'),($identity.reader_icacls_identity+':RX'))

    Protect-WorkerRuntimeFile -Path (Join-Path $WorkerRoot 'OneCChatWorker.ps1') -Identity $identity
    Protect-WorkerRuntimeFile -Path (Join-Path $ProgramDataRoot 'provider\source-reader-integration.mjs') -Identity $identity
    Protect-WorkerRuntimeFile -Path (Join-Path $ProgramDataRoot 'runtime\rg.exe') -Identity $identity
    Protect-WorkerRuntimeFile -Path (Join-Path $ProgramDataRoot 'helper\hosted-helper.mjs') -Identity $identity
    Protect-WorkerRuntimeFile -Path (Join-Path $ProgramDataRoot 'product\OneCChatWorker.Core.psm1') -Identity $identity
    Protect-WorkerRuntimeFile -Path (Join-Path $ProgramDataRoot 'product\README.md') -Identity $identity
    Protect-WorkerRuntimeFile -Path (Join-Path $ProgramDataRoot 'product\runtime.lock.json') -Identity $identity
    Protect-WorkerRuntimeFile -Path (Join-Path $ProgramDataRoot 'secrets\helper-secret.txt') -Identity $identity -Secret

    [pscustomobject]@{
        status='PASS'
        operator_identity=$identity.account
        operator_sid=$identity.sid
        mutable=@($WorkerRoot,$operations,(Join-Path $ProgramDataRoot 'provider'),(Join-Path $ProgramDataRoot 'runtime'))
        read_only=@((Join-Path $ProgramDataRoot 'audit'),(Join-Path $ProgramDataRoot 'helper'),(Join-Path $ProgramDataRoot 'product'))
        secret=(Join-Path $ProgramDataRoot 'secrets\helper-secret.txt')
        protected_binaries=@((Join-Path $WorkerRoot 'OneCChatWorker.ps1'),(Join-Path $ProgramDataRoot 'provider\source-reader-integration.mjs'),(Join-Path $ProgramDataRoot 'runtime\rg.exe'))
    }
}

function Install-OneCChatWorker {
    param([Parameter(Mandatory)][string]$PackageRoot,[string]$WorkerRoot=$script:DefaultWorkerRoot,[string]$ProgramDataRoot=$script:DefaultProgramDataRoot,[string]$OperatorIdentity,[switch]$SkipDependencies)
    if(-not(Test-IsAdministrator)){throw 'ADMIN_REQUIRED'}
    $packageCheck=Test-ProductPackageIntegrity $PackageRoot
    $deps=Ensure-PinnedDependencies -PackageRoot $PackageRoot -ProgramDataRoot $ProgramDataRoot -NoInstall:$SkipDependencies
    foreach($p in @($WorkerRoot,$ProgramDataRoot,(Join-Path $ProgramDataRoot 'runtime'),(Join-Path $ProgramDataRoot 'provider'),(Join-Path $ProgramDataRoot 'helper'),(Join-Path $ProgramDataRoot 'audit'),(Join-Path $ProgramDataRoot 'secrets'),(Join-Path $ProgramDataRoot 'product'))){New-Item -ItemType Directory -Force -Path $p|Out-Null}

    $readerAction='REUSED'
    if(-not(Get-LocalUser -Name $script:ReaderName -ErrorAction SilentlyContinue)){
        $readerAction='CREATED'
        $pw=Read-Host -Prompt "Set local password for $($script:ReaderName)" -AsSecureString
        New-LocalUser -Name $script:ReaderName -Password $pw -Description 'OneCChatWorker non-admin bounded source/output identity'|Out-Null
    }
    $reader="$env:COMPUTERNAME\$($script:ReaderName)"
    $lock=Read-RuntimeLock $PackageRoot
    $componentResults=@()
    $componentResults+=, (Copy-ProductComponent -Source (Join-Path $PackageRoot 'runtime\source-reader-integration.mjs') -Destination (Join-Path $ProgramDataRoot 'provider\source-reader-integration.mjs') -ExpectedSha256 ([string]$lock.components.'runtime/source-reader-integration.mjs'))
    $componentResults+=, (Copy-ProductComponent -Source (Join-Path $PackageRoot 'runtime\hosted-helper.mjs') -Destination (Join-Path $ProgramDataRoot 'helper\hosted-helper.mjs') -ExpectedSha256 ([string]$lock.components.'runtime/hosted-helper.mjs'))
    $componentResults+=, (Copy-ProductComponent -Source (Join-Path $PackageRoot 'core\OneCChatWorker.Core.psm1') -Destination (Join-Path $ProgramDataRoot 'product\OneCChatWorker.Core.psm1') -ExpectedSha256 ([string]$lock.components.'core/OneCChatWorker.Core.psm1'))
    $componentResults+=, (Copy-ProductComponent -Source (Join-Path $PackageRoot 'OneCChatWorker.ps1') -Destination (Join-Path $WorkerRoot 'OneCChatWorker.ps1') -ExpectedSha256 ([string]$lock.components.'OneCChatWorker.ps1'))
    $componentResults+=, (Copy-ProductComponent -Source (Join-Path $PackageRoot 'README.md') -Destination (Join-Path $ProgramDataRoot 'product\README.md') -ExpectedSha256 ([string]$lock.components.'README.md'))
    Copy-Item -LiteralPath (Join-Path $PackageRoot 'runtime.lock.json') -Destination (Join-Path $ProgramDataRoot 'product\runtime.lock.json') -Force

    $catalogAction='REUSED'
    if(-not(Test-Path -LiteralPath (Get-CatalogPath $WorkerRoot))){
        $catalogAction='CREATED'
        Write-WorkerCatalog ([pscustomobject]@{schema_version=1;projects=@()}) $WorkerRoot
    }

    $snapshotAdoption=@(Adopt-AllLegacyAcceptedSnapshots -WorkerRoot $WorkerRoot -ProgramDataRoot $ProgramDataRoot)
    $operatorAcl=Set-WorkerOperatorAcl -WorkerRoot $WorkerRoot -ProgramDataRoot $ProgramDataRoot -OperatorIdentity $OperatorIdentity

    $installedIntegrity=Test-InstalledProductIntegrity -WorkerRoot $WorkerRoot -ProgramDataRoot $ProgramDataRoot
    $secretReady=Test-Path -LiteralPath (Join-Path $ProgramDataRoot 'secrets\helper-secret.txt') -PathType Leaf
    $state=[ordered]@{
        schema_version=1
        product_version=$script:ProductVersion
        installed_utc=(Get-Date).ToUniversalTime().ToString('o')
        worker_root=$WorkerRoot
        program_data_root=$ProgramDataRoot
        reader_identity=$reader
        reader_action=$readerAction
        operator_identity=$operatorAcl.operator_identity
        operator_acl_status=$operatorAcl.status
        catalog_action=$catalogAction
        package_lock_sha256=$packageCheck.lock_sha256
        node_version=$deps.node.version
        node_sha256=$deps.node.sha256
        rg_version=$deps.ripgrep.version
        rg_sha256=$deps.ripgrep.sha256
        component_integrity='PASS'
        remote_auth_ready=$secretReady
    }
    Write-JsonAtomic $state (Join-Path $ProgramDataRoot 'installed-state.json')
    [pscustomobject]@{
        status=$(if($secretReady){'INSTALLED'}else{'INSTALLED_WAITING_FOR_REMOTE_AUTH'})
        installed_state=(Join-Path $ProgramDataRoot 'installed-state.json')
        package=$packageCheck
        dependencies=$deps
        reader=[pscustomobject]@{identity=$reader;action=$readerAction}
        operator_acl=$operatorAcl
        catalog=[pscustomobject]@{path=(Get-CatalogPath $WorkerRoot);action=$catalogAction}
        snapshot_adoption=$snapshotAdoption
        components=$componentResults
        installed_integrity=$installedIntegrity
        next=$(if($secretReady){'ADD/APPLY/VERIFY project then START'}else{'Complete ChatGPT app authorization and SETTINGS helper enrollment, then ADD/APPLY/VERIFY/START'})
    }
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

function New-HelperRunAsCommand {
    param([Parameter(Mandatory)][string]$HelperPath,[Parameter(Mandatory)][string]$ProgramDataRoot)
    $admissionPath=Join-Path $ProgramDataRoot 'runtime\active-admission.json'
    $programDataLiteral=$ProgramDataRoot.Replace("'","''")
    $admissionLiteral=$admissionPath.Replace("'","''")
    $helperLiteral=$HelperPath.Replace("'","''")
    $launchScript="`$env:ONECCHAT_PROGRAM_DATA='$programDataLiteral'; `$env:ONECCHAT_ADMISSION_PATH='$admissionLiteral'; & 'C:\Program Files\nodejs\node.exe' '$helperLiteral'"
    $encoded=[Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($launchScript))
    "powershell.exe -NoProfile -EncodedCommand $encoded"
}

function Start-WorkerAdmission {
    param([Parameter(Mandatory)][string]$ProjectId,[Parameter(Mandatory)][string]$TaskId,[string]$WorkerRoot=$script:DefaultWorkerRoot,[string]$ProgramDataRoot=$script:DefaultProgramDataRoot,[string]$RelayUrl=$script:DefaultRelayUrl,$AcceptedState)
    if(-not(Test-Path -LiteralPath (Join-Path $ProgramDataRoot 'secrets\helper-secret.txt'))){throw 'REMOTE_AUTH_REQUIRED'}
    New-Admission -ProjectId $ProjectId -TaskId $TaskId -WorkerRoot $WorkerRoot -ProgramDataRoot $ProgramDataRoot -RelayUrl $RelayUrl -AcceptedState $AcceptedState|Out-Null
    $helper=Join-Path $ProgramDataRoot 'helper\hosted-helper.mjs';$existing=@(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue|Where-Object{$_.Name -eq 'node.exe' -and $_.CommandLine -and $_.CommandLine.Contains($helper)});if($existing.Count){throw 'ADMISSION_ALREADY_RUNNING'}
    $runAs="$env:SystemRoot\System32\runas.exe";$program=New-HelperRunAsCommand -HelperPath $helper -ProgramDataRoot $ProgramDataRoot;& $runAs "/profile" "/user:$env:COMPUTERNAME\$($script:ReaderName)" $program;if($LASTEXITCODE -ne 0){throw "RUNAS_FAILED_OR_CANCELLED: $LASTEXITCODE"}
    [pscustomobject]@{status='START_REQUESTED';project_id=$ProjectId;task_id=$TaskId;source_snapshot_id=[string]$AcceptedState.source_snapshot_id}
}

function Stop-WorkerAdmission {
    param([string]$ProgramDataRoot=$script:DefaultProgramDataRoot)
    if(-not(Test-IsAdministrator)){throw 'ADMIN_REQUIRED'}
    $helper=Join-Path $ProgramDataRoot 'helper\hosted-helper.mjs'
    $procs=@(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue|Where-Object{$_.Name -eq 'node.exe' -and $_.CommandLine -and $_.CommandLine.Contains($helper)})
    foreach($p in $procs){Stop-Process -Id $p.ProcessId -Force}
    Remove-Item -LiteralPath (Join-Path $ProgramDataRoot 'runtime\active-admission.json') -Force -ErrorAction SilentlyContinue
    [pscustomobject]@{status='OFF';stopped=$procs.Count}
}

function Repair-WorkerProject {
    param([Parameter(Mandatory)][string]$ProjectId,[string]$WorkerRoot=$script:DefaultWorkerRoot,[string]$ProgramDataRoot=$script:DefaultProgramDataRoot,[scriptblock]$ProgressCallback)
    $cleanup=$null;$state=Get-FastProjectState -ProjectId $ProjectId -WorkerRoot $WorkerRoot
    if($state.state -eq 'INCOMPLETE_APPLY_RESIDUE'){$cleanup=Resolve-ApplyStageResidue -ProjectId $ProjectId -WorkerRoot $WorkerRoot;if($cleanup.status -ne 'CLEAN'){throw "APPLY_RESIDUE_CLEANUP_FAILED: $($cleanup|ConvertTo-Json -Depth 8 -Compress)"};$state=Get-FastProjectState -ProjectId $ProjectId -WorkerRoot $WorkerRoot}
    if($state.state -eq 'ACCEPTED'){$r=[pscustomobject]@{project_id=$ProjectId;status='READY';state='ACCEPTED';source_snapshot_id=$state.source_snapshot_id;repair_action='FAST_ACCEPTED_NO_DEEP_VERIFY'};if($cleanup){$r|Add-Member -NotePropertyName recovery_cleanup -NotePropertyValue $cleanup -Force};return $r}
    if($state.state -eq 'DEEP_VERIFY_REQUIRED'){
        $adopt=Adopt-LegacyAcceptedSnapshot -ProjectId $ProjectId -WorkerRoot $WorkerRoot -ProgramDataRoot $ProgramDataRoot
        if($adopt.status -in @('ADOPTED','ALREADY_ACCEPTED')){$f=Get-FastProjectState -ProjectId $ProjectId -WorkerRoot $WorkerRoot;return [pscustomobject]@{project_id=$ProjectId;status='READY';state='ACCEPTED';source_snapshot_id=$f.source_snapshot_id;repair_action='LEGACY_ADOPTED_NO_DEEP_VERIFY';adoption=$adopt}}
        $deep=Verify-WorkerProject -ProjectId $ProjectId -WorkerRoot $WorkerRoot -ProgressCallback $ProgressCallback
        if($deep.status -eq 'READY'){$f=Convert-DeepVerifiedManifestToAcceptedSnapshot -ProjectId $ProjectId -WorkerRoot $WorkerRoot;return [pscustomobject]@{project_id=$ProjectId;status='READY';state='ACCEPTED';source_snapshot_id=$f.source_snapshot_id;repair_action='DEEP_VERIFY_THEN_ACCEPT';deep_verification=$deep}}
        throw "REPAIR_DEEP_VERIFY_FAILED: $($deep|ConvertTo-Json -Compress)"
    }
    if($state.state -in @('APPLY_REQUIRED','CATALOG_DRIFT','SNAPSHOT_ROOT_MISSING')){$x=Apply-WorkerProject -ProjectId $ProjectId -WorkerRoot $WorkerRoot -ProgressCallback $ProgressCallback;if($cleanup){$x|Add-Member -NotePropertyName recovery_cleanup -NotePropertyValue $cleanup -Force};return $x}
    throw "REPAIR_REFUSED_DESTRUCTIVE_OR_UNKNOWN: $($state|ConvertTo-Json -Compress)"
}

function Get-UninstallPlan {
    param([string]$WorkerRoot=$script:DefaultWorkerRoot,[string]$ProgramDataRoot=$script:DefaultProgramDataRoot)
    [pscustomobject]@{
        action='SAFE_UNINSTALL_PLAN'
        requires_explicit_confirmation=$true
        remove=@(
            (Join-Path $ProgramDataRoot 'provider'),
            (Join-Path $ProgramDataRoot 'helper'),
            (Join-Path $ProgramDataRoot 'runtime'),
            (Join-Path $ProgramDataRoot 'secrets'),
            (Join-Path $ProgramDataRoot 'product'),
            (Join-Path $ProgramDataRoot 'installed-state.json'),
            (Join-Path $WorkerRoot 'OneCChatWorker.ps1')
        )
        retain=@(
            (Get-CatalogPath $WorkerRoot),
            (Join-Path $WorkerRoot '<project>\Participants'),
            (Join-Path $WorkerRoot '<project>\Output'),
            (Join-Path $WorkerRoot '<project>\Detached'),
            (Join-Path $ProgramDataRoot 'audit'),
            (Join-Path $ProgramDataRoot 'operations'),
            "$env:COMPUTERNAME\$($script:ReaderName) local account"
        )
        explicitly_not_performed=@('recursive project deletion','external business Source deletion','Output purge','Detached purge','reader account deletion')
        runtime_root=$ProgramDataRoot
        worker_root=$WorkerRoot
    }
}

function Invoke-SafeUninstall {
    param([string]$WorkerRoot=$script:DefaultWorkerRoot,[string]$ProgramDataRoot=$script:DefaultProgramDataRoot,[switch]$ConfirmRuntimeRemoval)
    if(-not(Test-IsAdministrator)){throw 'ADMIN_REQUIRED'}
    $plan=Get-UninstallPlan -WorkerRoot $WorkerRoot -ProgramDataRoot $ProgramDataRoot
    if(-not $ConfirmRuntimeRemoval){return [pscustomobject]@{status='WAITING_FOR_USER';plan=$plan}}
    $stop=$null
    try{$stop=Stop-WorkerAdmission -ProgramDataRoot $ProgramDataRoot}catch{
        if($_.Exception.Message -notmatch 'ADMIN_REQUIRED'){throw}
    }
    $removed=@();$alreadyAbsent=@()
    foreach($target in @($plan.remove)){
        if(Test-Path -LiteralPath $target){
            Remove-Item -LiteralPath $target -Recurse -Force
            $removed+=,$target
        }else{$alreadyAbsent+=,$target}
    }
    [pscustomobject]@{
        status='PASS'
        stopped=$stop
        removed=$removed
        already_absent=$alreadyAbsent
        retained=$plan.retain
        reader_identity_retained=$true
        authoritative_external_source_untouched=$true
    }
}

Export-ModuleMember -Function *
