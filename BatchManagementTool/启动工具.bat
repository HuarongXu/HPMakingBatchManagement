@echo off
chcp 65001 >nul
title HP Making Batch Management Tool

echo.
echo  ╔════════════════════════════════════════════════╗
echo  ║   HP Making Batch Management Tool              ║
echo  ║   正在启动...                                   ║
echo  ╚════════════════════════════════════════════════╝
echo.

:: 切换到脚本所在目录
cd /d "%~dp0"

:: ──────────────────────────────────────────────────────
:: 检测 Python 环境
:: ──────────────────────────────────────────────────────
set "VENV_PYTHON=%~dp0..\.venv\Scripts\python.exe"

if exist "%VENV_PYTHON%" (
    set "PYTHON_CMD=%VENV_PYTHON%"
    goto :check_deps
)

where python >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=python"
    goto :check_deps
)

echo   × 未检测到 Python 环境
echo   请先运行 "install.bat" 进行安装
echo.
pause
exit /b 1

:: ──────────────────────────────────────────────────────
:: 检查依赖是否已安装
:: ──────────────────────────────────────────────────────
:check_deps
"%PYTHON_CMD%" -c "import flask, pandas" >nul 2>&1
if errorlevel 1 (
    echo   正在安装缺少的依赖...
    "%PYTHON_CMD%" -m pip install -r "%~dp0requirements.txt" --quiet
    if errorlevel 1 (
        echo   × 依赖安装失败，请先运行 "install.bat"
        pause
        exit /b 1
    )
)

:: ──────────────────────────────────────────────────────
:: 获取日期参数
:: ──────────────────────────────────────────────────────
if "%~1"=="" (
    echo   请输入要分析的数据日期:
    echo   格式: YYYYMMDD (例如: 20260403^)
    echo   直接按回车将自动加载最新数据
    echo.
    set /p "DATE=  日期: "
) else (
    set "DATE=%~1"
)

:: ──────────────────────────────────────────────────────
:: 启动 Web Dashboard
:: ──────────────────────────────────────────────────────
echo.
echo   正在启动 Web Dashboard...

if "%DATE%"=="" (
    echo   模式: 自动加载最新数据
    "%PYTHON_CMD%" src/main.py --web
) else (
    echo   日期: %DATE%
    "%PYTHON_CMD%" src/main.py --date %DATE% --web
)

echo.
echo   程序已退出。
pause
