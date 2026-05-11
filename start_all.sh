#!/bin/bash
set -e

# --- 全局路径配置 ---
OTK_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OTK_BACKEND="$OTK_ROOT/backend"
OTK_FRONTEND="$OTK_ROOT/frontend"

echo "========================================================"
echo "            OtakuNeko 开发环境一键启动"
echo "========================================================"
echo

# ============================================================
# Step 0: 检测前置工具 (uv / Node.js / pnpm)
# ============================================================
echo "[0/4] 检测前置工具..."

# --- uv ---
if ! command -v uv &> /dev/null; then
    echo "  [INFO] 未检测到 uv，正在安装..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    source "$HOME/.cargo/env"
else
    echo "  [OK] uv"
fi

# --- Node.js ---
if ! command -v node &> /dev/null; then
    echo "  [INFO] 未检测到 Node.js，正在安装 fnm 与 Node.js 20..."
    curl -fsSL https://fnm.vercel.app/install | bash
    export PATH="$HOME/.local/share/fnm:$PATH"
    eval "$(fnm env)"
    fnm install 20
    fnm use 20
    fnm default 20
else
    echo "  [OK] Node.js $(node -v)"
fi

# --- pnpm ---
if ! command -v pnpm &> /dev/null; then
    echo "  [INFO] 未检测到 pnpm，正在安装..."
    npm install -g pnpm
fi
echo "  [OK] pnpm"

echo
# ============================================================
# Step 1: 同步后端依赖
# ============================================================
echo "[1/4] 同步后端依赖 (uv sync)..."
cd "$OTK_BACKEND"
uv sync
echo "  [OK] 后端依赖已就绪"

echo
# ============================================================
# Step 2: 同步前端依赖
# ============================================================
echo "[2/4] 同步前端依赖 (pnpm install)..."
cd "$OTK_FRONTEND"
pnpm install
pnpm approve-builds
echo "  [OK] 前端依赖已就绪"

echo
# ============================================================
# Step 3: 启动后端 (后台运行)
# ============================================================
echo "[3/4] 启动后端服务 http://localhost:8000 ..."
cd "$OTK_BACKEND"
uv run uvicorn app.main:app --reload &
echo "  [OK] 后端已在后台启动"

echo
# ============================================================
# Step 4: 启动前端 (前台运行)
# ============================================================
echo "[4/4] 启动前端服务 http://localhost:3000 ..."
echo "--------------------------------------------------------"
echo "  后端 API 文档 : http://localhost:8000/docs"
echo "  前端页面      : http://localhost:3000"
echo "--------------------------------------------------------"
echo

trap 'kill $(jobs -p) 2>/dev/null' EXIT

cd "$OTK_FRONTEND"
pnpm dev
