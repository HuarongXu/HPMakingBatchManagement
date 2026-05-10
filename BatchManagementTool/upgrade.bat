@echo off
chcp 65001 >nul
title HP Making Batch Management Tool - 升级

echo.
echo  ╔════════════════════════════════════════════════╗
echo  ║   HP Making Batch Management Tool              ║
echo  ║   升级程序                                      ║
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
    goto :check_git
)

where python >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=python"
    goto :check_git
)

echo   × 未检测到 Python 环境，请先运行 "install.bat"
pause
exit /b 1

:: ──────────────────────────────────────────────────────
:: 检查 Git
:: ──────────────────────────────────────────────────────
:check_git
set "USE_GIT=0"
set "PROJECT_ROOT=%~dp0.."

if exist "%PROJECT_ROOT%\.git" (
    where git >nul 2>&1
    if not errorlevel 1 (
        set "USE_GIT=1"
    )
)

if "%USE_GIT%"=="1" (
    goto :upgrade_git
) else (
    goto :upgrade_download
)

:: ──────────────────────────────────────────────────────
:: 方式1: 使用 Git 拉取更新
:: ──────────────────────────────────────────────────────
:upgrade_git
echo   检测到 Git 仓库，使用 Git 拉取最新版本...
echo.

cd /d "%PROJECT_ROOT%"

echo [1/3] 正在拉取最新代码...
git pull origin main
if errorlevel 1 (
    echo.
    echo   Git 拉取失败，尝试下载方式...
    goto :upgrade_download
)
echo   √ 代码已更新到最新版本

echo.
echo [2/3] 正在更新依赖...
cd /d "%~dp0"
"%PYTHON_CMD%" -m pip install -r requirements.txt --quiet
echo   √ 依赖已更新

echo.
echo [3/3] 升级完成!
goto :done

:: ──────────────────────────────────────────────────────
:: 方式2: 下载 ZIP 更新
:: ──────────────────────────────────────────────────────
:upgrade_download
echo   使用下载方式更新...
echo.

set "REPO_URL=https://github.com/HuarongXu/HPMakingBatchManagement/archive/refs/heads/main.zip"
set "DOWNLOAD_FILE=%TEMP%\hp_batch_update.zip"
set "EXTRACT_DIR=%TEMP%\hp_batch_update"

echo [1/5] 正在下载最新版本...

:: 尝试使用 token (如果存在配置文件)
set "TOKEN_FILE=%~dp0..\.github_token"
set "GITHUB_TOKEN="
if exist "%TOKEN_FILE%" (
    set /p GITHUB_TOKEN=<"%TOKEN_FILE%"
)

if defined GITHUB_TOKEN (
    powershell -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $h = @{'Authorization'='token %GITHUB_TOKEN%'}; Invoke-WebRequest -Uri '%REPO_URL%' -Headers $h -OutFile '%DOWNLOAD_FILE%' -UseBasicParsing } catch { exit 1 }"
) else (
    powershell -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%REPO_URL%' -OutFile '%DOWNLOAD_FILE%' -UseBasicParsing } catch { exit 1 }"
)
if errorlevel 1 (
    echo.
    echo   × 下载失败！
    echo.
    echo   可能的原因:
    echo     1. 没有网络连接
    echo     2. 仓库是私有的，需要配置 GitHub Token
    echo.
    echo   配置 Token 方法:
    echo     在项目根目录创建 .github_token 文件
    echo     文件内容为你的 GitHub Personal Access Token
    echo.
    pause
    exit /b 1
)

echo [2/5] 正在解压更新文件...
if exist "%EXTRACT_DIR%" rmdir /s /q "%EXTRACT_DIR%"
powershell -Command "Expand-Archive -Path '%DOWNLOAD_FILE%' -DestinationPath '%EXTRACT_DIR%' -Force"

echo [3/5] 正在备份用户数据...
set "BACKUP_DIR=%~dp0..\_backup_%date:~0,4%%date:~5,2%%date:~8,2%"

:: 备份数据文件
if exist "%~dp0data" (
    if not exist "%BACKUP_DIR%\data" mkdir "%BACKUP_DIR%\data"
    xcopy "%~dp0data\*.*" "%BACKUP_DIR%\data\" /s /q /y >nul 2>&1
)
:: 备份数据库文件
if exist "%PROJECT_ROOT%\1.DataBase" (
    if not exist "%BACKUP_DIR%\1.DataBase" mkdir "%BACKUP_DIR%\1.DataBase"
    xcopy "%PROJECT_ROOT%\1.DataBase\*.*" "%BACKUP_DIR%\1.DataBase\" /s /q /y >nul 2>&1
)
echo   √ 用户数据已备份到 _backup 文件夹

echo [4/5] 正在更新程序文件...
:: 找到解压后的目录（通常是 HPMakingBatchManagement-main）
setlocal enabledelayedexpansion
set "UPDATE_SOURCE="
for /d %%D in ("%EXTRACT_DIR%\*") do (
    set "UPDATE_SOURCE=%%D"
)

if "!UPDATE_SOURCE!"=="" (
    echo   × 解压后未找到文件
    endlocal
    pause
    exit /b 1
)

:: 更新 BatchManagementTool 下的源代码文件（保留用户数据）
if exist "!UPDATE_SOURCE!\BatchManagementTool\src" (
    xcopy "!UPDATE_SOURCE!\BatchManagementTool\src\*.*" "%~dp0src\" /s /q /y >nul 2>&1
)
if exist "!UPDATE_SOURCE!\BatchManagementTool\static" (
    xcopy "!UPDATE_SOURCE!\BatchManagementTool\static\*.*" "%~dp0static\" /s /q /y >nul 2>&1
)
if exist "!UPDATE_SOURCE!\BatchManagementTool\templates" (
    xcopy "!UPDATE_SOURCE!\BatchManagementTool\templates\*.*" "%~dp0templates\" /s /q /y >nul 2>&1
)
if exist "!UPDATE_SOURCE!\BatchManagementTool\requirements.txt" (
    copy /y "!UPDATE_SOURCE!\BatchManagementTool\requirements.txt" "%~dp0requirements.txt" >nul 2>&1
)

:: 更新脚本文件
for %%F in ("!UPDATE_SOURCE!\BatchManagementTool\*.bat") do (
    copy /y "%%F" "%~dp0" >nul 2>&1
)

:: 更新根目录文件
if exist "!UPDATE_SOURCE!\scripts" (
    if not exist "%PROJECT_ROOT%\scripts" mkdir "%PROJECT_ROOT%\scripts"
    xcopy "!UPDATE_SOURCE!\scripts\*.*" "%PROJECT_ROOT%\scripts\" /s /q /y >nul 2>&1
)
endlocal

echo   √ 程序文件已更新

echo [5/5] 正在更新依赖...
"%PYTHON_CMD%" -m pip install -r "%~dp0requirements.txt" --quiet
echo   √ 依赖已更新

:: 清理临时文件
del /f /q "%DOWNLOAD_FILE%" >nul 2>&1
rmdir /s /q "%EXTRACT_DIR%" >nul 2>&1

:: ──────────────────────────────────────────────────────
:: 完成
:: ──────────────────────────────────────────────────────
:done
echo.
echo  ╔════════════════════════════════════════════════╗
echo  ║             升级成功！                          ║
echo  ╠════════════════════════════════════════════════╣
echo  ║                                                ║
echo  ║  您的数据文件已自动备份                        ║
echo  ║  请双击 "启动工具.bat" 使用新版本              ║
echo  ║                                                ║
echo  ╚════════════════════════════════════════════════╝
echo.
pause
