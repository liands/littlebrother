$ErrorActionPreference = 'Stop'
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw 'Execute instalar.ps1 antes da verificação.'
}
$previousTemp = $env:TEMP
$previousTmp = $env:TMP
Push-Location $PSScriptRoot
try {
    New-Item -ItemType Directory -Path '.work' -Force | Out-Null
    $env:TEMP = (Resolve-Path '.work').Path
    $env:TMP = $env:TEMP
    & $pythonPath -B LittleBrother.py --check
    if ($LASTEXITCODE -ne 0) { throw 'Configuração inválida.' }
    & $pythonPath -B -m unittest discover -s tests
    if ($LASTEXITCODE -ne 0) { throw 'Falha nos testes.' }
    & $pythonPath -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Dependências incompatíveis.' }
    Write-Host 'Verificações concluídas.'
} finally {
    $env:TEMP = $previousTemp
    $env:TMP = $previousTmp
    Pop-Location
}
