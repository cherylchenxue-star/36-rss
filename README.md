# 36kr 融资快讯 RSS 服务

持续抓取 [36kr PitchHub 融资快讯](https://pitchhub.36kr.com/financing-flash) 并生成 RSS feed。

## 功能特性

- ⏰ **自动更新**：每 5 分钟自动抓取最新数据
- 📊 **智能解析**：自动提取公司名、轮次、金额
- 💾 **本地存储**：保留最多 100 条历史数据
- 🌐 **Web 界面**：提供可视化预览页面
- 📱 **标准 RSS**：兼容各类 RSS 阅读器

## 快速开始

### Windows
```bash
cd ~/36kr-rss
start.bat
```

### Mac/Linux
```bash
cd ~/36kr-rss
chmod +x start.sh
./start.sh
```

### Docker
```bash
cd ~/36kr-rss
docker-compose up -d
```

## 使用方式

| 功能 | 地址 |
|------|------|
| 首页预览 | http://localhost:5002 |
| **RSS Feed** | **http://localhost:5002/rss** |
| API 接口 | http://localhost:5002/api/items |
| 手动刷新 | http://localhost:5002/refresh |

**注意：** 服务使用端口 5002（如果 5000/5001 被占用）

## 订阅 RSS

将以下地址添加到你的 RSS 阅读器：

```
http://localhost:5002/rss
```

### 公网访问
如果部署到服务器，将 `localhost` 替换为服务器 IP 或域名即可。

## 数据字段

每条融资信息包含：

- **title**: 完整标题
- **company**: 公司名称
- **round**: 融资轮次
- **amount**: 融资金额
- **pub_date**: 发布时间
- **link**: 原文链接
- **description**: 详细描述

## 目录结构

```
36kr-rss/
├── app.py              # 主程序
├── requirements.txt    # Python 依赖
├── start.bat          # Windows 启动脚本
├── start.sh           # Mac/Linux 启动脚本
├── Dockerfile         # Docker 配置
├── docker-compose.yml # Docker Compose 配置
├── history.json       # 数据缓存（自动生成）
└── README.md          # 说明文档
```

## 部署建议

### 使用 PM2 (推荐)
```bash
npm install -g pm2
pm2 start app.py --name 36kr-rss --interpreter python
pm2 save
pm2 startup
```

### 使用 systemd
创建 `/etc/systemd/system/36kr-rss.service`：
```ini
[Unit]
Description=36kr RSS Service
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/36kr-rss
ExecStart=/home/ubuntu/36kr-rss/venv/bin/python app.py
Restart=always

[Install]
WantedBy=multi-user.target
```

启用服务：
```bash
sudo systemctl enable 36kr-rss
sudo systemctl start 36kr-rss
```

## 更新频率

- 默认每 **5 分钟** 自动抓取一次
- 首次启动会立即抓取一次
- 可在 `app.py` 中修改 `update_interval` 调整

## 注意事项

1. 本服务仅供个人学习使用
2. 请遵守 36kr 网站的使用条款
3. 不要频繁抓取，避免对源站造成压力
