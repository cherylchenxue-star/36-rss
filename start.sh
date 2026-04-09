#!/bin/bash

echo "====================================="
echo "  36kr 融资快讯 RSS 服务"
echo "====================================="
echo

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "[错误] 未找到 Python3"
    exit 1
fi

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "[初始化] 创建虚拟环境..."
    python3 -m venv venv
fi

# 激活虚拟环境
echo "[启动] 激活虚拟环境..."
source venv/bin/activate

# 安装依赖
echo "[启动] 检查依赖..."
pip install -q -r requirements.txt

# 启动服务
echo
echo "====================================="
echo "  服务启动成功！"
echo "  访问地址: http://localhost:5000"
echo "  RSS地址: http://localhost:5000/rss"
echo "====================================="
echo
echo "按 Ctrl+C 停止服务"
echo

python app.py
