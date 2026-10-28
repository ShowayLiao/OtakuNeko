@echo off
setlocal enabledelayedexpansion
title OtakuNeko Dev Launcher

:: --- Global path config ---
set "OTK_ROOT=%~dp0"
set "OTK_BACKEND=%OTK_ROOT%backend"
set "OTK_FRONTEND=%OTK_ROOT%frontend"

echo ========================================================
echo          OtakuNeko Dev Environment Launcher
echo ========================================================
echo.

:: ============================================================
:: Step 0: Check prerequisites (uv / Node.js / pnpm)
:: ============================================================
echo [0/4] Checking prerequisites...

:: --- uv ---
where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] uv not found, installing...
    powershell -Command "irm https://astral.sh/uv/install.ps1 | iex"
    :: Refresh PATH (cargo bin directory)
    for /f "tokens=*" %%i in ('powershell -Command "echo $env:USERPROFILE"') do set "USERPROFILE_PATH=%%i"
    set "PATH=%USERPROFILE_PATH%\.cargo\bin;%PATH%"
) else (
    echo   [OK] uv
)

:: --- Node.js ---
where node >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js 20+ not found. Please install:
    echo          https://nodejs.org/
    pause
    exit /b 1
)
echo   [OK] Node.js

:: --- pnpm ---
where pnpm >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] pnpm not found, installing via corepack...
    call corepack enable
    call corepack prepare pnpm@10.15.1 --activate
    where pnpm >nul 2>&1
    if %errorlevel% neq 0 (
        echo [ERROR] pnpm install failed. Check Node.js or run: corepack enable
        pause
        exit /b 1
    )
)
echo   [OK] pnpm

echo.
:: ============================================================
:: Step 1: Sync backend dependencies
:: ============================================================
echo [1/4] Checking backend deps...
if exist "%OTK_BACKEND%\pyproject.toml" (
    if exist "%OTK_BACKEND%\.venv" if not defined OTK_SYNC_DEPS (
        echo   [OK] Backend deps already present (set OTK_SYNC_DEPS=1 to sync)
    ) else (
        cd /d "%OTK_BACKEND%"
        call uv sync
        if !errorlevel! neq 0 (
            echo   [ERROR] Backend deps install failed. Check network or run: cd backend ^&^& uv sync
            pause
            exit /b 1
        )
        echo   [OK] Backend deps ready
    )

    :: Auto-init .env config (required for first run)
    if not exist "%OTK_BACKEND%\.env" (
        if exist "%OTK_BACKEND%\.env.example" (
            echo   [INFO] .env not found, creating from .env.example...
            copy "%OTK_BACKEND%\.env.example" "%OTK_BACKEND%\.env" >nul
            echo   [OK] .env created (default dev config with JWT_SECRET_KEY)
        ) else (
            echo   [WARN] .env.example not found, please create %OTK_BACKEND%\.env manually
            echo          Missing JWT_SECRET_KEY will prevent backend startup
        )
    ) else (
        echo   [OK] .env config exists
    )
) else (
    echo   [WARN] backend directory not found, skipping
)

echo.
:: ============================================================
:: Step 2: Sync frontend dependencies
:: ============================================================
echo [2/4] Checking frontend deps...
if exist "%OTK_FRONTEND%\package.json" (
    :: Auto-create .npmrc (fix legacy Taobao registry CERT_HAS_EXPIRED issue)
    if not exist "%OTK_FRONTEND%\.npmrc" (
        echo   [INFO] .npmrc not found, writing new registry mirror...
        echo registry=https://registry.npmmirror.com/> "%OTK_FRONTEND%\.npmrc"
        echo   [OK] npmmirror registry configured
    )

    if exist "%OTK_FRONTEND%\node_modules" if not defined OTK_SYNC_DEPS (
        echo   [OK] Frontend deps already present (set OTK_SYNC_DEPS=1 to sync)
    ) else (
        call pnpm --dir "%OTK_FRONTEND%" install
        if !errorlevel! neq 0 (
            echo   [ERROR] Frontend deps install failed. Check network or run: pnpm install
            pause
            exit /b 1
        )
        echo   [OK] Frontend deps ready
    )
) else (
    echo   [WARN] frontend directory not found, skipping
)

echo.
:: ============================================================
:: Step 3: Start backend (new window)
:: ============================================================
echo [3/4] Starting backend: http://localhost:8000 ...
if exist "%OTK_BACKEND%" (
    start "OtakuNeko Backend" /D "%OTK_BACKEND%" cmd /k "uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
    echo   [OK] Backend started in new window
) else (
    echo   [WARN] backend directory not found
)

echo.
:: ============================================================
:: Step 4: Start frontend (current window)
:: ============================================================
echo [4/4] Starting frontend: http://localhost:3000 ...
echo --------------------------------------------------------
echo   Backend API Docs : http://localhost:8000/docs
echo   Frontend App     : http://localhost:3000
echo --------------------------------------------------------
echo.

if exist "%OTK_FRONTEND%\package.json" (
    pushd "%OTK_FRONTEND%"
    if /I not "!CD!"=="%OTK_FRONTEND%" (
        echo [ERROR] Failed to enter frontend directory: %OTK_FRONTEND%
        popd
        pause
        exit /b 1
    )
    echo   [INFO] Frontend working directory: !CD!
    call pnpm --dir "%OTK_FRONTEND%" dev
    set "FRONTEND_EXIT=!errorlevel!"
    popd
    exit /b !FRONTEND_EXIT!
) else (
    echo [ERROR] Frontend directory not found: %OTK_FRONTEND%
    pause
)

pause
