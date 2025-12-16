@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo [1/3] 正在检查/创建虚拟环境 (venv)...
if not exist "venv" (
    python -m venv venv
    echo 虚拟环境创建完成。
) else (
    echo 虚拟环境已存在，跳过创建。
)

echo [2/3] 正在安装依赖 (requirements.txt)...
:: 使用刚创建的虚拟环境中的 pip
.\venv\Scripts\pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

echo [3/3] 配置完成！
echo.
echo 现在你可以直接双击 "启动程序.bat" 来运行了。
pause