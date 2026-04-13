# 36kr 融资快讯 RSS

持续抓取 [36kr PitchHub 融资快讯](https://pitchhub.36kr.com/financing-flash) 并生成 RSS feed，部署在 Vercel，无需本地运行。

## 访问地址

| 功能 | 地址 |
|------|------|
| 网页预览 | https://36-rss.vercel.app |
| **RSS 订阅** | **https://36-rss.vercel.app/rss** |
| API 接口 | https://36-rss.vercel.app/api/items |
| 手动刷新 | https://36-rss.vercel.app/refresh |

## 订阅方式

将以下地址添加到 RSS 阅读器（Reeder、NetNewsWire、Feedly 等）：

```
https://36-rss.vercel.app/rss
```

## 功能特性

- 自动更新：每天 2 次（UTC 06:00 / 18:00）
- 智能解析：自动提取公司名、轮次、金额
- 标准 RSS 2.0 格式，兼容各类阅读器
- 保留最多 100 条历史数据

## 数据字段

每条融资信息包含：

- **title**: 完整标题
- **company**: 公司名称
- **round**: 融资轮次
- **amount**: 融资金额
- **pub_date**: 发布时间
- **link**: 原文链接
- **description**: 详细描述

## 数据来源

[36kr PitchHub 融资快讯](https://pitchhub.36kr.com/financing-flash)

## 注意事项

1. 本服务仅供个人学习使用
2. 请遵守 36kr 网站的使用条款
