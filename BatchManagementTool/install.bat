@echo off
chcp 936 >nul
title HP Making Batch Management Tool - Install

echo.
echo  +================================================+
echo  :   HP Making Batch Management Tool              :
echo  :   Install                                      :
echo  +================================================+
echo.

:: --------------------------------------------------------
:: Switch to script directory
:: --------------------------------------------------------
cd /d "%~dp0"

:: --------------------------------------------------------
:: Step 1: Detect Python
:: --------------------------------------------------------
echo [1/4] Detecting Python environment...
echo.

:: Check for project venv AND verify it actually works
set "VENV_PYTHON=%~dp0..\.venv\Scripts\python.exe"
if exist "%VENV_PYTHON%" (
    "%VENV_PYTHON%" -c "print()" >nul 2>&1
    if not errorlevel 1 (
        echo   [OK] Project venv found and valid
        set "PYTHON_CMD=%VENV_PYTHON%"
        goto :install_deps
    ) else (
        echo   [!] Existing venv is invalid, will recreate...
        rmdir /s /q "%~dp0..\.venv" >nul 2>&1
    )
)

:: Check system Python
where python >nul 2>&1
if not errorlevel 1 (
    python -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>&1
    if not errorlevel 1 (
        echo   [OK] System Python found:
        python --version
        set "PYTHON_CMD=python"
        goto :setup_venv
    )
)

:: Check py launcher
where py >nul 2>&1
if not errorlevel 1 (
    py -3 -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>&1
    if not errorlevel 1 (
        echo   [OK] Python Launcher found:
        py -3 --version
        set "PYTHON_CMD=py -3"
        goto :setup_venv
    )
)

:: Python not found
echo   [X] Python 3.8+ not detected
echo.
echo   Auto-downloading Python...
echo   (This may take a few minutes, please wait)
echo.

set "PYTHON_VERSION=3.11.9"
set "PYTHON_INSTALLER=%TEMP%\python_installer.exe"
set "PYTHON_URL=https://www.python.org/ftp/python/%PYTHON_VERSION%/python-%PYTHON_VERSION%-amd64.exe"

echo   Downloading Python %PYTHON_VERSION%...
powershell -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%PYTHON_URL%' -OutFile '%PYTHON_INSTALLER%' -UseBasicParsing } catch { exit 1 }"
if errorlevel 1 (
    echo.
    echo   +----------------------------------------------+
    echo   :  Download failed! Please install manually:    :
    echo   :                                               :
    echo   :  1. Open browser:                             :
    echo   :     https://www.python.org/downloads/          :
    echo   :                                               :
    echo   :  2. Download Python 3.11 or later             :
    echo   :                                               :
    echo   :  3. MUST check during install:                :
    echo   :     [v] Add Python to PATH                    :
    echo   :                                               :
    echo   :  4. Re-run this installer after done          :
    echo   +----------------------------------------------+
    echo.
    pause
    exit /b 1
)

echo   Installing Python %PYTHON_VERSION% (silent install)...
echo   (Install location: current user directory, no admin required)
"%PYTHON_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_pip=1
if errorlevel 1 (
    echo.
    echo   Silent install failed, trying GUI install...
    echo   Please check "Add Python to PATH" in the installer
    "%PYTHON_INSTALLER%"
)

:: Delete installer
del /f /q "%PYTHON_INSTALLER%" >nul 2>&1

:: Refresh PATH
echo   Refreshing environment variables...
set "PATH=%LOCALAPPDATA%\Programs\Python\Python311\;%LOCALAPPDATA%\Programs\Python\Python311\Scripts\;%PATH%"

:: Re-detect
where python >nul 2>&1
if errorlevel 1 (
    echo.
    echo   [X] Python still not detected after install
    echo   Please close this window and reopen to try again
    pause
    exit /b 1
)

echo   [OK] Python installed successfully!
python --version
set "PYTHON_CMD=python"

:: --------------------------------------------------------
:: Step 2: Create virtual environment
:: --------------------------------------------------------
:setup_venv
echo.
echo [2/4] Creating Python virtual environment...

set "VENV_DIR=%~dp0..\.venv"
if not exist "%VENV_DIR%" (
    "%PYTHON_CMD%" -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo   [X] Venv creation failed
        echo   Trying direct install...
        goto :install_deps_global
    )
    echo   [OK] Venv created
) else (
    echo   [OK] Venv already exists
)

set "PYTHON_CMD=%VENV_DIR%\Scripts\python.exe"

:: --------------------------------------------------------
:: Step 3: Install dependencies
:: --------------------------------------------------------
:install_deps
echo.
echo [3/4] Installing project dependencies...
echo.

if exist "%~dp0..\.venv\Scripts\pip.exe" (
    "%~dp0..\.venv\Scripts\pip.exe" install -r "%~dp0requirements.txt" --quiet
) else (
    "%PYTHON_CMD%" -m pip install -r "%~dp0requirements.txt" --quiet
)
if errorlevel 1 (
    echo   [!] Install failed, retrying...
    "%PYTHON_CMD%" -m pip install -r "%~dp0requirements.txt"
    if errorlevel 1 (
        echo.
        echo   [X] Dependency install failed, check network and retry
        pause
        exit /b 1
    )
)
echo   [OK] All dependencies installed
goto :done

:install_deps_global
echo.
echo [3/4] Installing dependencies (global mode)...
"%PYTHON_CMD%" -m pip install -r "%~dp0requirements.txt" --quiet
if errorlevel 1 (
    echo   [X] Dependency install failed
    pause
    exit /b 1
)
echo   [OK] All dependencies installed

:: --------------------------------------------------------
:: Step 4: Done
:: --------------------------------------------------------
:done
echo.
echo  +================================================+
echo  :          Install successful!                    :
echo  +================================================+
echo  :                                                :
echo  :  How to use:                                   :
echo  :    Double-click "Launch.bat" to run             :
echo  :                                                :
echo  :  Data files go in:                             :
echo  :    1.DataBase folder                           :
echo  :                                                :
echo  +================================================+
echo.
pause
