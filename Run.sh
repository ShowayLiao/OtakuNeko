#!/bin/bash

# Change to the script's directory
cd "$(dirname "$0")"

# Print startup messages
echo "正在启动 OtakuNeko..."
echo "请勿关闭此窗口..."

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "错误: 未找到虚拟环境。请先运行 Setup.sh 创建虚拟环境。"
    echo "按 Enter 键关闭窗口。"
    read
    exit 1
fi

# Activate virtual environment and run the streamlit app
source venv/bin/activate
python -m streamlit run app.py

# If the program exits, pause to see any error messages
echo "程序已退出。按 Enter 键关闭窗口。"
read