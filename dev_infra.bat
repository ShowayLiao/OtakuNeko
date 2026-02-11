@echo off
@chcp 65001 >nul
title OtakuNeko Infra Only
echo [INFO] 正在启动开发基础设施 (PostgreSQL & Redis)...

:: 核心命令：只启动指定的两个服务，-d 为后台运行
docker compose up db redis -d

if %errorlevel% neq 0 (
    echo [ERROR] 启动失败，请检查 Docker 是否开启。
    pause
    exit /b
)

echo [SUCCESS] 数据库和缓存已在后台就绪！
echo ----------------------------------------
echo PostgreSQL: localhost:5432
echo Redis:      localhost:6379
echo ----------------------------------------
echo [提示] 现在你可以运行本地的 start_all.bat 了。
echo [提示] 停止服务请运行: docker compose stop
pause