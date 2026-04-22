@echo off
chcp 65001 >nul
echo ============================================
echo   HP Making Batch Management Tool Installer
echo ============================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.8+ from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

echo [1/3] Python found:
python --version
echo.

:: Install dependencies
echo [2/3] Installing dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)
echo.

echo [3/3] Starting the tool...
echo.
python src/main.py
echo.
echo ============================================
echo   Done! Check the output folder for results.
echo ============================================
pause
