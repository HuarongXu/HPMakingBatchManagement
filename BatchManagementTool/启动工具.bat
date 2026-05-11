@echo off
chcp 936 >nul
title HP Making Batch Management Tool

echo.
echo  +================================================+
echo  :   HP Making Batch Management Tool              :
echo  :   Starting...                                  :
echo  +================================================+
echo.

:: Switch to script directory
cd /d "%~dp0"

:: ──────────────────────────────────────────────────────
:: Detect Python environment
:: ──────────────────────────────────────────────────────
set "VENV_PYTHON=%~dp0..\.venv\Scripts\python.exe"

:: Check venv exists AND actually works (not stale from another machine)
if exist "%VENV_PYTHON%" (
    "%VENV_PYTHON%" -c "print()" >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON_CMD=%VENV_PYTHON%"
        goto :check_deps
    ) else (
        echo   [!] Venv Python invalid, checking system Python...
    )
)

where python >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=python"
    goto :check_deps
)

where py >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=py -3"
    goto :check_deps
)

echo   [X] Python not found
echo   Please run "install.bat" first
echo.
pause
exit /b 1

:: ──────────────────────────────────────────────────────
:: Check dependencies
:: ──────────────────────────────────────────────────────
:check_deps
"%PYTHON_CMD%" -c "import flask, pandas" >nul 2>&1
if errorlevel 1 (
    echo   Installing missing dependencies...
    "%PYTHON_CMD%" -m pip install -r "%~dp0requirements.txt" --quiet
    if errorlevel 1 (
        echo   [X] Dependency install failed, please run "install.bat" first
        pause
        exit /b 1
    )
)

:: ──────────────────────────────────────────────────────
:: 获取日期参数
:: ──────────────────────────────────────────────────────
if "%~1"=="" (
    echo   Enter the data date to analyze:
    echo   Format: YYYYMMDD (e.g. 20260403^)
    echo   Press Enter directly to auto-load latest data
    echo.
    set /p "DATE=  Date: "
) else (
    set "DATE=%~1"
)

:: ──────────────────────────────────────────────────────
:: Start Web Dashboard
:: ──────────────────────────────────────────────────────
echo.
echo   Starting Web Dashboard...

if "%DATE%"=="" (
    echo   Mode: auto-load latest data
    "%PYTHON_CMD%" src/main.py --web
) else (
    echo   Date: %DATE%
    "%PYTHON_CMD%" src/main.py --date %DATE% --web
)

echo.
echo   程序已退出。
pause
