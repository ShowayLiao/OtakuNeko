#!/bin/bash

echo "[INFO] 正在检查 Docker..."

if ! docker info > /dev/null 2>&1; then
  echo "[ERROR] Docker 未运行，请先启动 Docker Desktop！"
  exit 1
fi

echo "[INFO] 正在构建并启动 OtakuNeko (Cloud Mode)..."

# 启动容器
docker-compose up -d --build

echo "========================================================"
echo "              OtakuNeko Cloud Mode Started"
echo "========================================================"
echo "Frontend: http://localhost:3000"
echo "Backend:  http://localhost:8000/docs"
echo "========================================================"
echo "正在显示日志 (Ctrl+C 退出)..."

docker-compose logs -f