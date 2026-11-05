$ErrorActionPreference = 'Stop'
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$temporaryPath = Join-Path $PSScriptRoot '.work'
$previousTemp = $env:TEMP
$previousTmp = $env:TMP
try {
    New-Item -ItemType Directory -Path $temporaryPath -Force | Out-Null
    $env:TEMP = $temporaryPath
    $env:TMP = $temporaryPath
    if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
        python -m venv (Join-Path $PSScriptRoot '.venv')
        if ($LASTEXITCODE -ne 0) { throw 'Não foi possível criar o ambiente virtual.' }
    }
    & $pythonPath -m ensurepip --upgrade
    if ($LASTEXITCODE -ne 0) { throw 'Não foi possível preparar o pip.' }
    & $pythonPath -m pip install --disable-pip-version-check -r (Join-Path $PSScriptRoot 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'A instalação das dependências falhou.' }
    & $pythonPath -B (Join-Path $PSScriptRoot 'LittleBrother.py') --check
    if ($LASTEXITCODE -ne 0) { throw 'A verificação da instalação falhou.' }
    Write-Host 'Instalação concluída. Execute .\iniciar.ps1'
} finally {
    $env:TEMP = $previousTemp
    $env:TMP = $previousTmp
}
