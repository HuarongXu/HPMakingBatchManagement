@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0\.."

:: Activate virtual environment
call .venv\Scripts\activate.bat

:: Navigate to tool directory
cd BatchManagementTool

:: Run with web dashboard
:: Usage: run_dashboard.bat [date]
:: Example: run_dashboard.bat 20260403
if "%~1"=="" (
    echo Usage: run_dashboard.bat YYYYMMDD
    echo Example: run_dashboard.bat 20260403
    set /p DATE="Enter date (YYYYMMDD): "
) else (
    set DATE=%~1
)

echo.
echo Starting HP Batch Management Dashboard...
echo Date: %DATE%
echo.

python src/main.py --date %DATE% --web

pause
