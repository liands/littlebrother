@echo off
setlocal
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0configurar-apis.ps1"
if errorlevel 1 (
    echo [!] Nao foi possivel abrir a configuracao do projeto.
    pause
    exit /b 1
)
