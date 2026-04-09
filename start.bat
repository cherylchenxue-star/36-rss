@echo off
chcp 65001 >nul
echo =====================================
echo   36kr 融资快讯 RSS 服务
echo =====================================
echo.

:: 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请安装 Python 3.8+
    pause
    exit /b 1
)

:: 检查虚拟环境
if not exist venv (
    echo [初始化] 创建虚拟环境...
    python -m venv venv
)

:: 激活虚拟环境
echo [启动] 激活虚拟环境...
call venv\Scripts\activate.bat

:: 安装依赖
echo [启动] 检查依赖...
pip install -q -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

:: 启动服务
echo.
echo =====================================
echo  服务启动成功！
echo  访问地址: http://localhost:5000
echo  RSS地址: http://localhost:5000/rss
echo =====================================
echo.
echo 按 Ctrl+C 停止服务
echo.

python app.py

pause
