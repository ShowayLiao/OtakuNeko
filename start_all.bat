@echo off
:: 强制 UTF-8 编码，防止中文乱码
@chcp 65001 >nul
setlocal enabledelayedexpansion
title OtakuNeko 一键启动终端 (Pro)

:: --- 全局路径配置 ---
set "OTK_ROOT=%~dp0"
set "OTK_BACKEND=%OTK_ROOT%backend"
set "OTK_FRONTEND=%OTK_ROOT%frontend"

echo ========================================================
echo               OtakuNeko 开发环境一键启动
echo ========================================================
echo.

:: ============================================================
:: Step 0: 检测前置工具 (uv / Node.js / pnpm)
:: ============================================================
echo [0/4] 检测前置工具...

:: --- uv ---
where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] 未检测到 uv，正在安装...
    powershell -Command "irm https://astral.sh/uv/install.ps1 | iex"
    :: 安装后刷新 PATH（cargo bin 目录）
    for /f "tokens=*" %%i in ('powershell -Command "echo $env:USERPROFILE"') do set "USERPROFILE_PATH=%%i"
    set "PATH=%USERPROFILE_PATH%\.cargo\bin;%PATH%"
) else (
    echo   [OK] uv
)

:: --- Node.js ---
where node >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] 未检测到 Node.js 20+，请先安装:
    echo          https://nodejs.org/
    pause
    exit /b 1
)
echo   [OK] Node.js

:: --- pnpm ---
where pnpm >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] 未检测到 pnpm，正在通过 corepack 安装...
    call corepack enable
    call corepack prepare pnpm@10.15.1 --activate
    where pnpm >nul 2>&1
    if %errorlevel% neq 0 (
        echo [ERROR] pnpm 安装失败，请检查 Node.js 安装或手动执行 corepack enable
        pause
        exit /b 1
    )
)
echo   [OK] pnpm

echo.
:: ============================================================
:: Step 1: 同步后端依赖
:: ============================================================
echo [1/4] 同步后端依赖 (uv sync)...
if exist "%OTK_BACKEND%\pyproject.toml" (
    cd /d "%OTK_BACKEND%"
    call uv sync
    echo   [OK] 后端依赖已就绪

    :: 自动初始化 .env 配置（新机器首次运行必备）
    if not exist "%OTK_BACKEND%\.env" (
        if exist "%OTK_BACKEND%\.env.example" (
            echo   [INFO] 未检测到 .env 配置，正在从 .env.example 创建...
            copy "%OTK_BACKEND%\.env.example" "%OTK_BACKEND%\.env" >nul
            echo   [OK] 已创建 .env（默认开发配置，含 JWT_SECRET_KEY）
        ) else (
            echo   [WARN] 未找到 .env.example，请手动创建 %OTK_BACKEND%\.env
            echo          JWT_SECRET_KEY 缺失会导致后端启动失败
        )
    ) else (
        echo   [OK] .env 配置文件已存在
    )
) else (
    echo   [WARN] 未找到 backend 目录，跳过
)

echo.
:: ============================================================
:: Step 2: 同步前端依赖
:: ============================================================
echo [2/4] 同步前端依赖 (pnpm install)...
if exist "%OTK_FRONTEND%\package.json" (
    cd /d "%OTK_FRONTEND%"

    :: 自动创建 .npmrc（修复旧淘宝镜像 CERT_HAS_EXPIRED 问题）
    if not exist "%OTK_FRONTEND%\.npmrc" (
        echo   [INFO] 未检测到 .npmrc，正在写入新镜像源...
        echo registry=https://registry.npmmirror.com/> "%OTK_FRONTEND%\.npmrc"
        echo   [OK] 已配置 npmmirror 镜像源
    )

    call pnpm install
    if %errorlevel% neq 0 (
        echo   [ERROR] 前端依赖安装失败，请检查网络或手动运行 pnpm install
        pause
        exit /b 1
    )
    echo   [OK] 前端依赖已就绪
) else (
    echo   [WARN] 未找到 frontend 目录，跳过
)

echo.
:: ============================================================
:: Step 3: 启动后端 (新窗口)
:: ============================================================
echo [3/4] 启动后端服务 http://localhost:8000 ...
if exist "%OTK_BACKEND%" (
    start "OtakuNeko Backend" /D "%OTK_BACKEND%" cmd /k "uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
    echo   [OK] 后端已在独立窗口中启动
) else (
    echo   [WARN] 未找到 backend 目录
)

echo.
:: ============================================================
:: Step 4: 启动前端 (当前窗口)
:: ============================================================
echo [4/4] 启动前端服务 http://localhost:3000 ...
echo --------------------------------------------------------
echo   后端 API 文档 : http://localhost:8000/docs
echo   前端页面      : http://localhost:3000
echo --------------------------------------------------------
echo.

if exist "%OTK_FRONTEND%\package.json" (
    cd /d "%OTK_FRONTEND%"
    call pnpm dev
) else (
    echo [ERROR] 未找到前端目录: %OTK_FRONTEND%
    pause
)

pause
