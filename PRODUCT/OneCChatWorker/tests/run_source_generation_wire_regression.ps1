param([string]$PackageRoot,[Parameter(Mandatory)][string]$ReportPath)
$ErrorActionPreference='Stop'
if([string]::IsNullOrWhiteSpace($PackageRoot)){$PackageRoot=Split-Path -Parent $PSScriptRoot}
$tokens=$null;$errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile((Join-Path $PackageRoot 'OneCChatWorker.ps1'),[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'LAUNCHER_PARSE_FAILED'}
$checks=@()
function Check($Ok,$Name){if(-not $Ok){throw ('ASSERTION_FAILED: '+$Name)};$script:checks+=,$Name;Write-Host ('PASS '+$Name)}
function FunctionText($Name){
 $f=$ast.FindAll({param($x)$x -is [Management.Automation.Language.FunctionDefinitionAst]},$true)|Where-Object Name -eq $Name
 if(@($f).Count -ne 1){throw ('FUNCTION_NOT_UNIQUE: '+$Name)}
 $f.Extent.Text
}
Check (@($ast.ParamBlock.Parameters|Where-Object {$_.Name.VariablePath.UserPath -eq 'ExpectedGenerationId'}).Count -eq 1) 'launcher explicit generation parameter'
Check (@($ast.ParamBlock.Parameters|Where-Object {$_.Name.VariablePath.UserPath -eq 'ExpectedArtifactKey'}).Count -eq 1) 'launcher explicit artifact parameter'
# Execute the real elevation serializer, capturing Start-Process instead of UAC.
$elevation=[scriptblock]::Create((FunctionText 'Require-AdminOrRelaunch'))
& {
 param($Definition)
 . $Definition
 function Is-Admin {$false}
 function Start-Process {
  param($FilePath,$Verb,$ArgumentList,[switch]$Wait,[switch]$PassThru)
  $script:captured=[pscustomobject]@{file=$FilePath;verb=$Verb;arguments=@($ArgumentList)}
  throw 'FIXTURE_CAPTURED_NO_UAC'
 }
 $WorkerRoot='C:\isolated worker';$ProgramDataRoot='C:\isolated data';$ReaderName='fixture';$OperatorIdentity='fixture';$RelayUrl='fixture'
 $ProjectId='RetailGroup';$TaskId=$null;$TaskGoal=$null;$ArtifactSelection=$null
 $ExpectedGenerationId='update-1111111111111111';$ExpectedArtifactKey='un|EXTENSION|bit'
 $SelectedArtifactFullSafeImport=$false;$SkipDependencies=$false;$ConfirmUninstall=$false;$Json=$true
 foreach($mode in @('ACCEPT_SOURCE_UPDATE','CANCEL_SOURCE_UPDATE')){
  $got='';try{Require-AdminOrRelaunch $mode}catch{$got=$_.Exception.Message}
  Check ($got -eq 'FIXTURE_CAPTURED_NO_UAC' -and $script:captured.verb -eq 'RunAs') ($mode+' real elevation serializer, UAC intercepted')
  $a=$script:captured.arguments
  Check ($a[[Array]::IndexOf($a,'-ExpectedGenerationId')+1] -ceq $ExpectedGenerationId) ($mode+' expected G1 survives elevation unchanged')
  Check ($a[[Array]::IndexOf($a,'-ExpectedArtifactKey')+1] -ceq $ExpectedArtifactKey) ($mode+' exact key survives elevation unchanged')
 }
} $elevation
# Execute real launcher handlers. The observer and OS boundary are test doubles;
# backend capture proves parameter forwarding without reading a current generation.
& {
 param($Accept,$Cancel,$Need)
 . ([scriptblock]::Create($Accept));. ([scriptblock]::Create($Cancel));. ([scriptblock]::Create($Need))
 function Require-AdminOrRelaunch {$false}
 function Update-WorkerOperation {}
 function Invoke-ObservedAction {param($OperationType,$RequestedAction,$TotalSteps,$Project,$Body,$FinalStateResolver)& $Body ([pscustomobject]@{})}
 function Show-Value {param($Value)$Value}
 function Accept-SourceUpdate {
  param($ProjectId,$ExpectedGenerationId,$ExpectedArtifactKey,$WorkerRoot,$ProgramDataRoot,$OperatorIdentity,[switch]$UseFullSafeImportFallback)
  [pscustomobject]@{status='NO_CHANGE';generation_id=$ExpectedGenerationId;key=@($ExpectedArtifactKey);project=$ProjectId;source_snapshot_id='fixture';publication_generation=1}
 }
 function Cancel-SourceUpdate {
  param($ProjectId,$ExpectedGenerationId,$ExpectedArtifactKey,$WorkerRoot,$OperatorIdentity)
  [pscustomobject]@{status='CANCELLED';generation_id=$ExpectedGenerationId;key=@($ExpectedArtifactKey);project=$ProjectId}
 }
 $WorkerRoot='fixture';$ProgramDataRoot='fixture';$OperatorIdentity='fixture';$ProjectId='RetailGroup'
 $ExpectedGenerationId='update-1111111111111111';$ExpectedArtifactKey='un|EXTENSION|bit';$SelectedArtifactFullSafeImport=$false
 foreach($fn in @('Run-AcceptSourceUpdate','Run-CancelSourceUpdate')){
  $r=& $fn
  Check ($r.generation_id -ceq $ExpectedGenerationId -and $r.key.Count -eq 1 -and $r.key[0] -ceq $ExpectedArtifactKey -and $r.project -ceq $ProjectId) ($fn+' exact request forwarded to existing Core')
 }
 $ExpectedGenerationId=$null
 foreach($fn in @('Run-AcceptSourceUpdate','Run-CancelSourceUpdate')){
  $got='';try{& $fn|Out-Null}catch{$got=$_.Exception.Message}
  Check ($got -eq 'ARG_REQUIRED: ExpectedGenerationId') ($fn+' legacy ProjectId-only rejected before elevation/observer')
 }
} (FunctionText 'Run-AcceptSourceUpdate') (FunctionText 'Run-CancelSourceUpdate') (FunctionText 'Need')
[IO.File]::WriteAllText($ReportPath,([ordered]@{result='PASS';checks=$checks.Count;cases=$checks;actual_uac_executed=$false}|ConvertTo-Json -Depth 6),[Text.UTF8Encoding]::new($false))
Write-Host ('SOURCE_GENERATION_WIRE_PASS checks='+$checks.Count)
