# Instalação opcional e local. Fonte oficial, versão fixa e SHA-256 conferido.
$ErrorActionPreference = 'Stop'
if (-not $IsWindows -and $PSVersionTable.PSEdition -eq 'Core') {
    throw 'Este instalador atende Windows x64; em outros sistemas use a distribuição oficial no PATH.'
}
if ([System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture -ne 'X64') {
    throw 'Este pacote fixado é para Windows x64.'
}
$version = '2.17.0'
$expectedHash = 'a3fd612928d591fb31c1e59a2e06055e364421ba32251e553073f5673a2d3103'
$releaseUrl = "https://github.com/projectdiscovery/subfinder/releases/download/v$version/subfinder_${version}_windows_amd64.zip"
$workDirectory = Join-Path $PSScriptRoot '.work'
$toolDirectory = Join-Path $PSScriptRoot '.tools\subfinder'
New-Item -ItemType Directory -Path $workDirectory -Force | Out-Null
$archivePath = Join-Path $workDirectory ("subfinder-" + [guid]::NewGuid().ToString('N') + '.zip')
try {
    Invoke-WebRequest -Uri $releaseUrl -OutFile $archivePath -TimeoutSec 60 -UseBasicParsing
    if ((Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedHash) {
        throw 'SHA-256 divergente. O pacote não será extraído ou executado.'
    }
    New-Item -ItemType Directory -Path $toolDirectory -Force | Out-Null
    Expand-Archive -LiteralPath $archivePath -DestinationPath $toolDirectory -Force
    Write-Host "Subfinder $version instalado em $toolDirectory"
    Write-Host 'Não é preciso alterar o PATH. O LittleBrother detecta a instalação local.'
} finally {
    if (Test-Path -LiteralPath $archivePath -PathType Leaf) {
        Remove-Item -LiteralPath $archivePath -Force
    }
}
