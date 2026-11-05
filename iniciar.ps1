[CmdletBinding(PositionalBinding = $false)]
param(
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$AppArgs,
    [Parameter(ValueFromPipeline = $true)][string]$InputLine
)
begin {
    $ErrorActionPreference = 'Stop'
    $inputLines = [System.Collections.Generic.List[string]]::new()
}
process {
    if ($PSBoundParameters.ContainsKey('InputLine')) { $inputLines.Add($InputLine) }
}
end {
    $pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
        throw 'Ambiente virtual ausente. Execute instalar.ps1 primeiro.'
    }
    $env:PYTHONUTF8 = '1'
    if ($inputLines.Count -gt 0) {
        $inputLines | & $pythonPath -B (Join-Path $PSScriptRoot 'LittleBrother.py') @AppArgs
    } else {
        & $pythonPath -B (Join-Path $PSScriptRoot 'LittleBrother.py') @AppArgs
    }
    exit $LASTEXITCODE
}
