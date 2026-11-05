@echo off
setlocal
title LittleBrother
set "PYTHONUTF8=1"

if not exist "%~dp0.venv\Scripts\python.exe" (
    echo [!] Ambiente Python ausente.
    echo Execute instalar.ps1 na pasta do projeto e tente novamente.
    pause
    exit /b 1
)

pushd "%~dp0"
if errorlevel 1 (
    echo [!] Nao foi possivel abrir a pasta do projeto.
    pause
    exit /b 1
)

"%~dp0.venv\Scripts\python.exe" -B "%~dp0LittleBrother.py" %*
set "LB_EXIT_CODE=%ERRORLEVEL%"
popd

if not "%LB_EXIT_CODE%"=="0" (
    echo.
    echo [!] O LittleBrother foi encerrado com erro. Confira a mensagem acima.
    pause
)

exit /b %LB_EXIT_CODE%
