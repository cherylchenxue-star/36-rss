# 部署到 Railway 指南

## 部署步骤

### 1. 创建 GitHub 仓库

1. 登录 GitHub
2. 创建新仓库，如 `36kr-rss`
3. 上传本目录所有文件到仓库

### 2. 注册 Railway

1. 访问 https://railway.app
2. 用 GitHub 账号登录
3. 点击 "New Project"
4. 选择 "Deploy from GitHub repo"
5. 选择你刚创建的仓库

### 3. 部署

1. Railway 会自动检测 `railway.json` 和 `Procfile`
2. 点击 "Deploy"
3. 等待部署完成（约 2-3 分钟）
4. 获得公网 URL（如 `https://your-app-name.railway.app`）

### 4. 验证部署

访问 `https://your-app-name.railway.app/rss`

应该能看到 RSS 内容

---

## 配置 GitHub Action

### 设置 RSS_URL 密钥

1. 进入 GitHub 仓库
2. Settings → Secrets and variables → Actions
3. 添加 `RSS_URL` 密钥：
   - Name: `RSS_URL`
   - Value: `https://your-app-name.railway.app/rss`

### 手动触发测试

1. 进入 Actions 页面
2. 选择 "获取 36kr 融资快讯"
3. 点击 "Run workflow"

---

## 使用方式

### RSS 订阅地址

```
https://your-app-name.railway.app/rss
```

### API 接口

```
https://your-app-name.railway.app/api/items
```

### 首页预览

```
https://your-app-name.railway.app/
```

---

## 费用说明

- **计算时间**: 每次访问约 1-2 分钟
- **每月**: 约 60-120 分钟（按每天 2 次计算）
- **Railway 免费额度**: 500 小时/月
- **结论**: 完全免费！

---

## 分享 RSS

部署成功后，把 URL 分享给其他人：

```
https://your-app-name.railway.app/rss
```

任何人都可以订阅这个 RSS！
