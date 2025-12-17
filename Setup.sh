#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
# This prevents the script from continuing if a step like pip install fails.
set -e

# Change to the script's directory
cd "$(dirname "$0")"

echo "[1/4] 正在检查 Python 环境..."
# Check if python3 is available
if ! command -v python3 &> /dev/null; then
    echo "错误: 未找到 python3。请先安装 Python 3.8 或更高版本。"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
echo "找到 Python 版本: $PYTHON_VERSION"

echo "[2/4] 正在检查/创建虚拟环境 (venv)..."
if [ ! -d "venv" ]; then
    # Ensure python3 is used for compatibility
    echo "正在创建虚拟环境..."
    python3 -m venv venv
    echo "虚拟环境创建完成。"
else
    echo "虚拟环境已存在，跳过创建。"
fi

echo "[3/4] 正在安装依赖 (requirements.txt)..."
# Use the pip from the newly created virtual environment
echo "正在升级 pip..."
./venv/bin/pip install --upgrade pip

echo "正在安装项目依赖..."
# Install requirements with error handling
if ./venv/bin/pip install -r requirements.txt; then
    echo "依赖安装完成。"
else
    echo "警告: 使用国内镜像重新尝试安装..."
    if ./venv/bin/pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple; then
        echo "依赖安装完成。"
    else
        echo "错误: 依赖安装失败。请检查网络连接和 requirements.txt 文件。"
        exit 1
    fi
fi

echo "[4/4] 正在验证安装..."
# Verify that key packages are installed
if ./venv/bin/python -c "import streamlit, openai, pandas" &> /dev/null; then
    echo "安装验证通过。"
else
    echo "警告: 部分包可能未正确安装，请手动检查。"
fi

echo ""
echo "配置完成！"
echo ""
echo "现在你可以直接运行 \"./Run.sh\" 来启动了。"
echo "或者在项目根目录下运行以下命令来启动："
echo "source venv/bin/activate && streamlit run app.py"