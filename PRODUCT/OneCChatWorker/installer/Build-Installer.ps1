param([Parameter(Mandatory)][string]$OutputRoot,[string]$DotnetPath='dotnet',[string]$IsccPath="${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe")
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$packageRoot=Split-Path -Parent $PSScriptRoot
$OutputRoot=[IO.Path]::GetFullPath($OutputRoot)
if(Test-Path -LiteralPath $OutputRoot){throw 'BUILD_OUTPUT_MUST_BE_NEW'}
$payload=Join-Path $OutputRoot 'payload'
New-Item -ItemType Directory -Path $payload|Out-Null
$lock=Get-Content -LiteralPath (Join-Path $packageRoot 'runtime.lock.json') -Raw -Encoding UTF8|ConvertFrom-Json
foreach($component in $lock.components.PSObject.Properties){
    $target=Join-Path $payload $component.Name
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target)|Out-Null
    Copy-Item -LiteralPath (Join-Path $packageRoot $component.Name) -Destination $target
}
$publish=Join-Path $OutputRoot 'gui'
& $DotnetPath publish (Join-Path $packageRoot 'control-center/OneCArchitecture.ControlCenter/OneCArchitecture.ControlCenter.csproj') -c Release -r win-x64 --self-contained true -p:ContinuousIntegrationBuild=true -o $publish --nologo
if($LASTEXITCODE -ne 0){throw 'INSTALLER_GUI_BUILD_FAILED'}
Copy-Item -LiteralPath (Join-Path $publish 'OneCArchitecture.ControlCenter.exe') -Destination (Join-Path $payload 'control-center/publish/OneCArchitecture.ControlCenter.exe') -Force
$deps=Join-Path $payload 'dependencies';New-Item -ItemType Directory -Path $deps|Out-Null
# Only fixed official distribution endpoints and hash-pinned executable payloads.
$nodeVersion=$lock.dependencies.node.version
Invoke-WebRequest -Uri "https://nodejs.org/dist/v$nodeVersion/win-x64/node.exe" -OutFile (Join-Path $deps 'node.exe') -UseBasicParsing
$rgVersion=$lock.dependencies.ripgrep.version
$rgZip=Join-Path $OutputRoot 'ripgrep.zip'
Invoke-WebRequest -Uri "https://github.com/BurntSushi/ripgrep/releases/download/$rgVersion/ripgrep-$rgVersion-x86_64-pc-windows-msvc.zip" -OutFile $rgZip -UseBasicParsing
Expand-Archive -LiteralPath $rgZip -DestinationPath (Join-Path $OutputRoot 'ripgrep')
Copy-Item -LiteralPath (Join-Path $OutputRoot "ripgrep/ripgrep-$rgVersion-x86_64-pc-windows-msvc/rg.exe") -Destination (Join-Path $deps 'rg.exe')
foreach($name in @('node','rg')){
    $spec=if($name -eq 'node'){$lock.dependencies.node}else{$lock.dependencies.ripgrep}
    if((Get-FileHash -LiteralPath (Join-Path $deps ($name+'.exe')) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $spec.reference_sha256){throw ('INSTALLER_DEPENDENCY_HASH_MISMATCH:'+ $name)}
}
foreach($component in $lock.components.PSObject.Properties){$component.Value=(Get-FileHash -LiteralPath (Join-Path $payload $component.Name) -Algorithm SHA256).Hash.ToLowerInvariant()}
$lock|ConvertTo-Json -Depth 30|Set-Content -LiteralPath (Join-Path $payload 'runtime.lock.json') -Encoding UTF8
& $IsccPath ('/DPayload='+$payload) ('/DOutput='+$OutputRoot) (Join-Path $PSScriptRoot 'OneCOrbit.iss')
if($LASTEXITCODE -ne 0){throw 'INSTALLER_COMPILE_FAILED'}
$repo=Resolve-Path (Join-Path $packageRoot '../..')
$head=(& git -C $repo rev-parse HEAD).Trim()
$rows=@(Get-ChildItem -LiteralPath $OutputRoot -File -Filter '*.exe'|ForEach-Object{@{file=$_.Name;sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant();bytes=$_.Length}})
$rows+=,@{file='GUI';sha256=(Get-FileHash -LiteralPath (Join-Path $publish 'OneCArchitecture.ControlCenter.exe') -Algorithm SHA256).Hash.ToLowerInvariant()}
@{schema='ORBIT_BUILD_RECEIPT_V1';source_head=$head;dotnet_sdk=(& $DotnetPath --version).Trim();inno_compiler=(Get-Item -LiteralPath $IsccPath).VersionInfo.ProductVersion;files=$rows;unsigned_internal_pilot=$true}|ConvertTo-Json -Depth 10|Set-Content -LiteralPath (Join-Path $OutputRoot 'build-receipt.json') -Encoding UTF8
