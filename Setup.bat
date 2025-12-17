@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo [1/4] 正在检查 Python 环境...
:: Check if python is available
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo 错误: 未找到 python。请先安装 Python 3.8 或更高版本。
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version') do set PYTHON_VERSION=%%i
echo 找到 %PYTHON_VERSION%

echo [2/4] 正在检查/创建虚拟环境 (venv)...
if not exist "venv" (
    echo 正在创建虚拟环境...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo 错误: 虚拟环境创建失败。
        pause
        exit /b 1
    )
    echo 虚拟环境创建完成。
) else (
    echo 虚拟环境已存在，跳过创建。
)

echo [3/4] 正在安装依赖 (requirements.txt)...
echo 正在安装项目依赖...
.\venv\Scripts\pip.exe install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if %errorlevel% neq 0 (
    echo 警告: 使用国内镜像重新尝试安装...
    .\venv\Scripts\pip.exe install -r requirements.txt 
    if %errorlevel% neq 0 (
        echo 错误: 依赖安装失败。请检查网络连接和 requirements.txt 文件。
        pause
        exit /b 1
    )
)
echo 依赖安装完成。

echo [4/4] 正在验证安装...
:: Verify that key packages are installed
.\venv\Scripts\python.exe -c "import streamlit, openai, pandas" >nul 2>nul
if %errorlevel% neq 0 (
    echo 警告: 部分包可能未正确安装，请手动检查。
) else (
    echo 安装验证通过。
)

echo.
echo 配置完成！
echo.
echo 现在你可以直接双击 "Run.bat" 来运行了。
echo 或者在项目根目录下运行以下命令来启动：
echo venv\Scripts\activate.bat ^&^& streamlit run app.py
pause