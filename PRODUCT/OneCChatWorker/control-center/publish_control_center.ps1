param(
  [string]$PackageRoot=(Split-Path -Parent $PSScriptRoot),
  [string]$DotnetPath,
  [string]$OutputDir=(Join-Path $PSScriptRoot 'publish')
)
$ErrorActionPreference='Stop'
if([string]::IsNullOrWhiteSpace($DotnetPath)){
  $candidate=Join-Path $env:LOCALAPPDATA 'OneCArchitecture\dotnet-10.0.401\dotnet.exe'
  if(Test-Path -LiteralPath $candidate -PathType Leaf){$DotnetPath=$candidate}else{$DotnetPath='dotnet.exe'}
}
$project=Join-Path $PSScriptRoot 'OneCArchitecture.ControlCenter\OneCArchitecture.ControlCenter.csproj'
if(-not(Test-Path -LiteralPath $project -PathType Leaf)){throw 'CONTROL_CENTER_PROJECT_NOT_FOUND'}
$env:DOTNET_CLI_TELEMETRY_OPTOUT='1'
$env:DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1'
$env:DOTNET_NOLOGO='1'
New-Item -ItemType Directory -Force -Path $OutputDir|Out-Null
Get-ChildItem -LiteralPath $OutputDir -Force -ErrorAction SilentlyContinue|Remove-Item -Force -Recurse
& $DotnetPath publish $project -c Release -r win-x64 --self-contained true --nologo -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -p:EnableCompressionInSingleFile=true -p:PublishReadyToRun=false -p:DebugType=embedded -p:ContinuousIntegrationBuild=true -o $OutputDir
if($LASTEXITCODE-ne0){throw "CONTROL_CENTER_PUBLISH_FAILED: $LASTEXITCODE"}
$exe=Join-Path $OutputDir 'OneCArchitecture.ControlCenter.exe'
if(-not(Test-Path -LiteralPath $exe -PathType Leaf)){throw 'CONTROL_CENTER_EXE_MISSING'}
$extra=@(Get-ChildItem -LiteralPath $OutputDir -File|Where-Object{$_.Name -ne 'OneCArchitecture.ControlCenter.exe'})
if($extra.Count){throw ('CONTROL_CENTER_SINGLE_FILE_VIOLATION: '+(($extra|ForEach-Object{$_.Name}) -join ','))}
$sig=Get-AuthenticodeSignature -LiteralPath $exe
[pscustomobject]@{
  schema='CONTROL_CENTER_PACKAGE_V1'
  status='PASS'
  framework='net10.0-windows'
  runtime='win-x64'
  self_contained=$true
  single_file=$true
  executable=$exe
  bytes=(Get-Item -LiteralPath $exe).Length
  sha256=(Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant()
  signing_status=$(if($sig.Status -eq 'Valid'){'AUTHENTICODE_VALID'}else{'UNSIGNED_INTERNAL_PILOT'})
  powershell7_required=$false
  webview2_required=$false
  loopback_listener=$false
  service=$false
}|ConvertTo-Json -Depth 5
