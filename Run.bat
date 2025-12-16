@echo off
chcp 65001 >nul
:: 切换到当前脚本所在的目录
cd /d "%~dp0"

:: 打印提示信息
echo 正在启动 OtakuNeko...
echo 请勿关闭此窗口...

:: 直接使用虚拟环境中的 python 运行 streamlit
:: 这样不需要显式执行 activate 命令
.\venv\Scripts\python.exe -m streamlit run app.py

:: 如果程序异常退出，暂停一下以便查看报错信息
pause