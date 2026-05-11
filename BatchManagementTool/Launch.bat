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

:: ==========================================================
:: Step 1: Detect Python
:: ==========================================================
set "PYTHON_CMD="
set "VENV_DIR=%~dp0..\.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"

:: Check existing venv is valid
if exist "%VENV_PYTHON%" (
    "%VENV_PYTHON%" -c "print()" >nul 2>&1
    if not errorlevel 1 (
        echo   [OK] Python venv found
        set "PYTHON_CMD=%VENV_PYTHON%"
        goto :check_deps
    ) else (
        echo   [!] Existing venv is invalid, will recreate...
        rmdir /s /q "%VENV_DIR%" >nul 2>&1
    )
)

:: Find system Python
where python >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=python"
    goto :setup_venv
)

where py >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=py -3"
    goto :setup_venv
)

echo.
echo   [X] Python not found!
echo   Please install Python 3.8+ and add it to PATH.
echo   Download: https://www.python.org/downloads/
echo.
pause
exit /b 1

:: ==========================================================
:: Step 2: Create venv (only if no valid venv exists)
:: ==========================================================
:setup_venv
echo   [..] Creating Python virtual environment...
"%PYTHON_CMD%" -m venv "%VENV_DIR%"
if errorlevel 1 (
    echo   [!] Venv creation failed, using system Python directly
    goto :check_deps
)
set "PYTHON_CMD=%VENV_PYTHON%"
echo   [OK] Virtual environment created

:: ==========================================================
:: Step 3: Check and install dependencies
:: ==========================================================
:check_deps
"%PYTHON_CMD%" -c "import flask, pandas" >nul 2>&1
if not errorlevel 1 goto :get_date

echo   [..] Installing dependencies (first-time setup)...
echo.
"%PYTHON_CMD%" -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo.
    echo   [X] Dependency install failed.
    echo   Please check network connection and try again.
    echo.
    pause
    exit /b 1
)
echo.
echo   [OK] Dependencies installed successfully
echo.

:: ==========================================================
:: Step 4: Get date parameter
:: ==========================================================
:get_date
echo.
if "%~1"=="" (
    echo   Enter the data date to analyze:
    echo   Format: YYYYMMDD (e.g. 20260403)
    echo   Press Enter directly to auto-load latest data
    echo.
    set /p "TARGET_DATE=  Date: "
) else (
    set "TARGET_DATE=%~1"
)

:: ==========================================================
:: Step 5: Launch Web Dashboard
:: ==========================================================
echo.
echo   Starting Web Dashboard...

if "%TARGET_DATE%"=="" (
    echo   Mode: auto-load latest data
    "%PYTHON_CMD%" src/main.py --web
) else (
    echo   Date: %TARGET_DATE%
    "%PYTHON_CMD%" src/main.py --date %TARGET_DATE% --web
)

echo.
echo   Program exited.
pause
