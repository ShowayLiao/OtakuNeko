@echo off
:: 1. 环境初始化：强制 UTF-8 编码，防止乱码报错
@chcp 65001 >nul
setlocal enabledelayedexpansion
title OtakuNeko 一键启动终端 (Pro)

:: --- 全局配置 ---
set "ROOT_DIR=%~dp0"
set "RUNTIME_DIR=%ROOT_DIR%.runtime"
set "BACKEND_DIR=%ROOT_DIR%backend"
set "FRONTEND_DIR=%ROOT_DIR%frontend"
set "NODE_VERSION=v20.11.1"

:: --- 2. 注入运行环境环境变量 ---
:: 确保本地下载的 Node, npm, pnpm 和 uv 优先被系统找到
set "NODE_PATH=%RUNTIME_DIR%\node-%NODE_VERSION%-win-x64"
set "PATH=%NODE_PATH%;%NODE_PATH%\node_modules\.bin;%RUNTIME_DIR%;%PATH%"

echo ========================================================
echo               OtakuNeko 开发环境一键启动
echo ========================================================

:: --- 3. 检查并同步后端依赖 ---
echo [1/4] 正在检查后端依赖 (uv sync)...
if exist "%BACKEND_DIR%\pyproject.toml" (
    cd /d "%BACKEND_DIR%"
    :: 使用 call 调用以防脚本提前退出
    call uv sync
) else (
    echo [警告] 未发现 backend 目录，跳过后端同步。
)

:: --- 4. 检查并同步前端依赖 ---
echo [2/4] 正在检查前端依赖 (pnpm install)...
if exist "%FRONTEND_DIR%\package.json" (
    cd /d "%FRONTEND_DIR%"
    call npm install -g pnpm
    call pnpm install
) else (
    echo [警告] 未发现 frontend 目录，跳过前端同步。
)

:: --- 5. 启动后端服务 (新窗口) ---
echo [3/4] 正在启动后端服务 (新窗口)...
if exist "%BACKEND_DIR%" (
    :: 使用 /D 指定目录，直接使用 uv 命令
    start "OtakuNeko Backend (FastAPI)" /D "%BACKEND_DIR%" cmd /k "uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
)
:: --- 6. 启动前端服务 (当前窗口) ---
echo [4/4] 正在启动前端服务 (Next.js)...
echo --------------------------------------------------------
echo 后端预览: http://localhost:8000/docs
echo 前端预览: http://localhost:3000
echo --------------------------------------------------------

if exist "%FRONTEND_DIR%" (
    cd /d "%FRONTEND_DIR%"
    :: 再次校验防止误操作
    if exist "package.json" (
        call pnpm dev
    ) else (
        echo [错误] 无法在前端目录找到 package.json！
        pause
    )
) else (
    echo [错误] 找不到前端目录: %FRONTEND_DIR%
    pause
)

:: 防止窗口意外关闭
pause