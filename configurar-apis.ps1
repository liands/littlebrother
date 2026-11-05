param([switch]$SomenteCriar)
$ErrorActionPreference = 'Stop'
if ($env:LITTLEBROTHER_CONFIG) {
    $configurationPath = [System.IO.Path]::GetFullPath($env:LITTLEBROTHER_CONFIG)
} else {
    $configurationPath = Join-Path $PSScriptRoot 'config.ini'
}
$configurationDirectory = Split-Path -Parent $configurationPath
New-Item -ItemType Directory -Path $configurationDirectory -Force | Out-Null
if (-not (Test-Path -LiteralPath $configurationPath)) {
    # Copy without overwrite: an existing file always retains its credentials.
    [System.IO.File]::Copy((Join-Path $PSScriptRoot 'configuracao.exemplo.ini'), $configurationPath, $false)
}
Write-Host "Configuracao: $configurationPath"
if (-not $SomenteCriar) {
    & (Join-Path $env:SystemRoot 'System32\notepad.exe') $configurationPath
}
