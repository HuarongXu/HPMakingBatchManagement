@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title HP Making Batch Management Tool - 一键安装

echo.
echo  ╔════════════════════════════════════════════════╗
echo  ║   HP Making Batch Management Tool              ║
echo  ║   一键安装程序                                  ║
echo  ╚════════════════════════════════════════════════╝
echo.

:: ──────────────────────────────────────────────────────
:: 切换到脚本所在目录
:: ──────────────────────────────────────────────────────
cd /d "%~dp0"

:: ──────────────────────────────────────────────────────
:: 第1步: 检测 Python 环境
:: ──────────────────────────────────────────────────────
echo [1/4] 正在检测 Python 环境...
echo.

:: 先检查项目自带的 venv
set "VENV_PYTHON=%~dp0..\.venv\Scripts\python.exe"
if exist "!VENV_PYTHON!" (
    echo   √ 已检测到项目虚拟环境
    set "PYTHON_CMD=!VENV_PYTHON!"
    goto :install_deps
)

:: 检查系统 Python
where python >nul 2>&1
if not errorlevel 1 (
    :: 验证是否是 Python 3
    python -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>&1
    if not errorlevel 1 (
        echo   √ 已检测到系统 Python:
        python --version
        set "PYTHON_CMD=python"
        goto :setup_venv
    )
)

:: 检查 py launcher
where py >nul 2>&1
if not errorlevel 1 (
    py -3 -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>&1
    if not errorlevel 1 (
        echo   √ 已检测到 Python Launcher:
        py -3 --version
        set "PYTHON_CMD=py -3"
        goto :setup_venv
    )
)

:: Python 未安装，自动下载安装
echo   × 未检测到 Python 3.8+
echo.
echo   正在自动下载并安装 Python...
echo   （这可能需要几分钟，请耐心等待）
echo.

set "PYTHON_VERSION=3.11.9"
set "PYTHON_INSTALLER=%TEMP%\python_installer.exe"
set "PYTHON_URL=https://www.python.org/ftp/python/%PYTHON_VERSION%/python-%PYTHON_VERSION%-amd64.exe"

echo   正在下载 Python %PYTHON_VERSION%...
powershell -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%PYTHON_URL%' -OutFile '%PYTHON_INSTALLER%' -UseBasicParsing } catch { exit 1 }"
if errorlevel 1 (
    echo.
    echo   ╔══════════════════════════════════════════════╗
    echo   ║  自动下载失败！请手动安装 Python:              ║
    echo   ║                                               ║
    echo   ║  1. 打开浏览器访问:                           ║
    echo   ║     https://www.python.org/downloads/          ║
    echo   ║                                               ║
    echo   ║  2. 下载并安装 Python 3.11 或更高版本         ║
    echo   ║                                               ║
    echo   ║  3. 安装时务必勾选:                           ║
    echo   ║     [√] Add Python to PATH                    ║
    echo   ║                                               ║
    echo   ║  4. 安装完成后重新运行本安装程序              ║
    echo   ╚══════════════════════════════════════════════╝
    echo.
    pause
    exit /b 1
)

echo   正在安装 Python %PYTHON_VERSION%（静默安装）...
echo   （安装位置: 当前用户目录，不需要管理员权限）
"%PYTHON_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_pip=1
if errorlevel 1 (
    echo.
    echo   静默安装失败，正在尝试图形界面安装...
    echo   请在安装界面中勾选 "Add Python to PATH"
    "%PYTHON_INSTALLER%"
)

:: 删除安装文件
del /f /q "%PYTHON_INSTALLER%" >nul 2>&1

:: 刷新环境变量
echo   正在刷新环境变量...
set "PATH=%LOCALAPPDATA%\Programs\Python\Python311\;%LOCALAPPDATA%\Programs\Python\Python311\Scripts\;%PATH%"

:: 重新检测
where python >nul 2>&1
if errorlevel 1 (
    echo.
    echo   × 安装后仍未检测到 Python
    echo   请关闭此窗口，重新打开后再运行安装程序
    pause
    exit /b 1
)

echo   √ Python 安装成功!
python --version
set "PYTHON_CMD=python"

:: ──────────────────────────────────────────────────────
:: 第2步: 创建虚拟环境
:: ──────────────────────────────────────────────────────
:setup_venv
echo.
echo [2/4] 正在创建 Python 虚拟环境...

set "VENV_DIR=%~dp0..\.venv"
if not exist "!VENV_DIR!" (
    !PYTHON_CMD! -m venv "!VENV_DIR!"
    if errorlevel 1 (
        echo   × 虚拟环境创建失败
        echo   尝试直接安装依赖...
        goto :install_deps_global
    )
    echo   √ 虚拟环境已创建
) else (
    echo   √ 虚拟环境已存在
)

set "PYTHON_CMD=!VENV_DIR!\Scripts\python.exe"
set "PIP_CMD=!VENV_DIR!\Scripts\pip.exe"

:: ──────────────────────────────────────────────────────
:: 第3步: 安装依赖
:: ──────────────────────────────────────────────────────
:install_deps
echo.
echo [3/4] 正在安装项目依赖...
echo.

if exist "%~dp0..\.venv\Scripts\pip.exe" (
    "%~dp0..\.venv\Scripts\pip.exe" install -r "%~dp0requirements.txt" --quiet
) else (
    !PYTHON_CMD! -m pip install -r "%~dp0requirements.txt" --quiet
)
if errorlevel 1 (
    echo   × 依赖安装失败，正在重试...
    !PYTHON_CMD! -m pip install -r "%~dp0requirements.txt"
    if errorlevel 1 (
        echo.
        echo   × 依赖安装失败，请检查网络连接后重试
        pause
        exit /b 1
    )
)
echo   √ 所有依赖已安装完成
goto :done

:install_deps_global
echo.
echo [3/4] 正在安装项目依赖（全局模式）...
!PYTHON_CMD! -m pip install -r "%~dp0requirements.txt" --quiet
if errorlevel 1 (
    echo   × 依赖安装失败
    pause
    exit /b 1
)
echo   √ 所有依赖已安装完成

:: ──────────────────────────────────────────────────────
:: 第4步: 完成
:: ──────────────────────────────────────────────────────
:done
echo.
echo  ╔════════════════════════════════════════════════╗
echo  ║             安装成功！                          ║
echo  ╠════════════════════════════════════════════════╣
echo  ║                                                ║
echo  ║  使用方法:                                     ║
echo  ║    双击 "启动工具.bat" 即可运行                 ║
echo  ║                                                ║
echo  ║  数据文件请放在:                               ║
echo  ║    1.DataBase 文件夹                           ║
echo  ║                                                ║
echo  ╚════════════════════════════════════════════════╝
echo.
pause
