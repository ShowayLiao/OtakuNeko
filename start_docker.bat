@echo off
:: 强制切换控制台代码页为 UTF-8，解决乱码问题
@chcp 65001 >nul
setlocal EnableDelayedExpansion
title OtakuNeko Docker Launcher

echo [INFO] 正在检查 Docker 环境...

:: 1. 检查 Docker 是否运行
docker info >nul 2>&1
if !errorlevel! neq 0 (
    echo [ERROR] Docker 未运行！请先启动 Docker Desktop。
    echo.
    echo 请打开 Docker Desktop 等待其启动完毕后，在此窗口按任意键重试...
    pause >nul
    
    :: 二次检查
    docker info >nul 2>&1
    if !errorlevel! neq 0 (
        echo [FATAL] 依然未检测到 Docker 进程。
        echo 请确保 Docker Desktop 正在运行。
        pause
        exit /b 1
    )
)

echo [INFO] Docker 运行正常。
echo [INFO] 正在构建并启动服务 (Cloud Mode)...

:: 2. 启动服务
:: 尝试使用新版命令 docker compose，如果失败则回退到 docker-compose
docker compose up -d --build 2>nul
if !errorlevel! neq 0 (
    echo [INFO] 尝试旧版命令...
    docker-compose up -d --build
    if !errorlevel! neq 0 (
        echo.
        echo [ERROR] 启动失败！请检查上方红色错误信息。
        echo 可能原因：
        echo 1. 端口被占用 (3000, 8000, 5432, 6379)
        echo 2. Dockerfile 构建错误
        echo 3. 网络问题导致依赖下载失败
        pause
        exit /b 1
    )
)

:: 3. 显示成功信息
cls
echo ========================================================
echo               OtakuNeko Cloud Mode 已启动
echo ========================================================
echo.
echo [前端页面] http://localhost:3000
echo [后端文档] http://localhost:8000/docs
echo [数据库]   localhost:5432 (User: otaku / Pass: password)
echo.
echo ========================================================
echo 正在实时显示日志 (按 Ctrl+C 退出日志查看，服务仍在后台运行)...
echo.

:: 4. 自动显示日志
docker compose logs -f 2>nul
if !errorlevel! neq 0 (
    docker-compose logs -f
)

pause