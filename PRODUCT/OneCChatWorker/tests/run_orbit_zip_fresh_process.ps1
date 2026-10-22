param([Parameter(Mandatory)][string]$Archive,[Parameter(Mandatory)][string]$Destination,[string]$PackageRoot=(Split-Path -Parent $PSScriptRoot))
$ErrorActionPreference='Stop'
# Intentionally no ZipFile fixture construction or compression assembly imports.
Import-Module (Join-Path $PackageRoot 'core/OneCChatWorker.Core.psm1') -Force -DisableNameChecking
Expand-OrbitXmlArchive -Archive $Archive -Destination $Destination
if(-not(Test-Path -LiteralPath (Join-Path $Destination 'Configuration.xml'))){throw 'FRESH_ZIP_READBACK_FAILED'}
