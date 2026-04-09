#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抓取36kr融资快讯并生成静态RSS文件
用于GitHub Actions定时运行
"""

import requests
from datetime import datetime
import re
import json
import os

SOURCE_URL = 'https://pitchhub.36kr.com/financing-flash'


def fetch_financing_news():
    """抓取融资快讯"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9',
    }

    try:
        response = requests.get(SOURCE_URL, headers=headers, timeout=30)
        response.encoding = response.apparent_encoding

        # 从 __INIT_PROPS__ 中提取
        props_start = response.text.find('window.__INIT_PROPS__ = ')
        if props_start == -1:
            print("[ERROR] 未找到数据")
            return []

        json_start = props_start + len('window.__INIT_PROPS__ = ')
        brace_count = 0
        in_string = False
        json_end = json_start

        for i, char in enumerate(response.text[json_start:]):
            if char == '\\' and not in_string:
                continue
            if char == '"':
                in_string = not in_string
            elif not in_string:
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        json_end = json_start + i + 1
                        break

        json_str = response.text[json_start:json_end]
        data = json.loads(json_str)
        item_list = data.get('itemList', [])

        items = []
        for item in item_list:
            material = item.get('templateMaterial', {})
            title = material.get('widgetTitle', '')
            content = material.get('widgetContent', '')
            pub_time_ms = material.get('publishTime', 0)

            if not title:
                continue

            # 只保留含"AI"、"人工智能"、"大模型"的标题（可选过滤）
            # keywords = ['AI', '人工智能', '大模型', '智能', '机器人', '算法']
            # if not any(kw in title for kw in keywords):
            #     continue

            pub_date = datetime.fromtimestamp(pub_time_ms / 1000).isoformat() if pub_time_ms else datetime.now().isoformat()

            route = item.get('route', '')
            if route.startswith('detail_newsflash'):
                link = f"https://36kr.com/newsflashes/{item.get('itemId')}"
            else:
                link = SOURCE_URL

            items.append({
                'title': title,
                'link': link,
                'pub_date': pub_date,
                'description': content or title,
            })

        # 按时间倒序
        items.sort(key=lambda x: x.get('pub_date', ''), reverse=True)
        print(f"[OK] 抓取到 {len(items)} 条数据")
        return items

    except Exception as e:
        print(f"[ERROR] 抓取失败: {e}")
        return []


def generate_rss(items):
    """生成RSS XML"""
    items_xml = ''

    for item in items[:50]:
        pub_date = item.get('pub_date', datetime.now().isoformat())
        try:
            dt = datetime.fromisoformat(pub_date.replace('Z', '+00:00'))
            pub_date_str = dt.strftime('%a, %d %b %Y %H:%M:%S +0800')
        except:
            pub_date_str = datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0800')

        guid = hash(f"{item['title']}{item['link']}")

        items_xml += f"""
        <item>
            <title><![CDATA[{item['title']}]]></title>
            <link>{item['link']}</link>
            <guid isPermaLink="false">{guid}</guid>
            <pubDate>{pub_date_str}</pubDate>
            <description><![CDATA[{item.get('description', item['title'])}]]></description>
        </item>
        """

    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
    <channel>
        <title>36kr 融资快讯</title>
        <link>{SOURCE_URL}</link>
        <description>36氪 PitchHub 最新一级市场股权融资动态</description>
        <language>zh-CN</language>
        <lastBuildDate>{datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0800')}</lastBuildDate>
        <generator>36kr RSS Generator</generator>
        {items_xml}
    </channel>
</rss>"""

    return rss


def main():
    print(f"[{datetime.now()}] 开始抓取...")

    # 抓取数据
    items = fetch_financing_news()

    if not items:
        print("[ERROR] 没有获取到数据")
        return

    # 生成RSS
    rss_content = generate_rss(items)

    # 保存到 public 目录（GitHub Pages用）
    os.makedirs('public', exist_ok=True)

    with open('public/rss.xml', 'w', encoding='utf-8') as f:
        f.write(rss_content)

    # 同时生成一个HTML预览页
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>36kr 融资快讯 RSS</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; background: #f5f7fa; }}
        h1 {{ color: #1a1a1a; }}
        .info {{ background: white; padding: 25px; border-radius: 12px; margin: 20px 0; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
        .rss-link {{ background: #1a73e8; color: white; padding: 10px 20px; border-radius: 6px; display: inline-block; margin: 10px 0; text-decoration: none; }}
        .item {{ background: white; padding: 15px; border-radius: 8px; margin: 10px 0; }}
        .item-title {{ font-weight: bold; color: #1a1a1a; }}
        .item-time {{ color: #666; font-size: 14px; }}
    </style>
</head>
<body>
    <h1>📰 36kr 融资快讯 RSS</h1>
    <div class="info">
        <p>当前数据: <strong>{len(items)}</strong> 条</p>
        <p>最后更新: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        <a href="rss.xml" class="rss-link">📡 RSS 订阅</a>
    </div>
    <h2>最新数据</h2>
"""

    for item in items[:10]:
        pub_time = item['pub_date'][:16] if len(item['pub_date']) > 16 else item['pub_date']
        html += f"""
    <div class="item">
        <div class="item-title">{item['title']}</div>
        <div class="item-time">{pub_time}</div>
    </div>
"""

    html += """
    <p style="text-align: center; color: #999; margin-top: 40px;">
        数据来源于: <a href="https://pitchhub.36kr.com/financing-flash">36kr PitchHub</a>
    </p>
</body>
</html>"""

    with open('public/index.html', 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"[OK] RSS已生成: public/rss.xml")
    print(f"[OK] 共 {len(items)} 条数据")


if __name__ == '__main__':
    main()
