#!/bin/bash

# 获取脚本所在目录
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$BASE_DIR/backend"
FRONTEND_DIR="$BASE_DIR/frontend"

echo "=== OtakuNeko 启动助手 (macOS/Linux) ==="

# --- 1. 检查后端工具 (uv) ---
if ! command -v uv &> /dev/null; then
    echo "[INFO] 未检测到 uv，正在安装..."
    curl -lsSf https://astral.sh/uv/install.sh | sh
    source $HOME/.cargo/env
else
    echo "[CHECK] uv 已安装"
fi

# --- 2. 检查前端工具 (Node.js & pnpm) ---
# 推荐使用 fnm，如果没有 node，尝试安装 fnm
if ! command -v node &> /dev/null; then
    echo "[INFO] 未检测到 Node.js，正在安装 fnm (Node管理器)..."
    curl -fsSL https://fnm.vercel.app/install | bash
    # 激活 fnm
    export PATH="$HOME/.local/share/fnm:$PATH"
    eval "`fnm env`"
    
    echo "[INFO] 安装 Node.js 20..."
    fnm install 20
    fnm use 20
    fnm default 20
else
    echo "[CHECK] Node.js 已安装: $(node -v)"
fi

if ! command -v pnpm &> /dev/null; then
    echo "[INFO] 安装 pnpm..."
    npm install -g pnpm
fi

# --- 3. 安装依赖 ---
echo "[INFO] 同步后端依赖..."
cd "$BACKEND_DIR"
uv sync

echo "[INFO] 同步前端依赖..."
cd "$FRONTEND_DIR"
pnpm install
pnpm approve-builds

# --- 4. 并行启动 ---
echo "[SUCCESS] 服务启动中..."
echo "后端: http://localhost:8000"
echo "前端: http://localhost:3000"

# 使用 trap 在脚本退出时杀掉所有子进程
trap 'kill $(jobs -p)' EXIT

# 启动后端 (后台运行)
cd "$BACKEND_DIR"
uv run uvicorn app.main:app --reload &

# 启动前端 (前台运行)
cd "$FRONTEND_DIR"
pnpm dev