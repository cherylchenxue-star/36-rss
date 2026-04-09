#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
36kr 融资快讯 RSS - Railway 部署版本
按需运行，每次请求时实时抓取
"""

import requests
from bs4 import BeautifulSoup
from flask import Flask, Response, render_template_string
from datetime import datetime
import re
import json

app = Flask(__name__)

SOURCE_URL = 'https://pitchhub.36kr.com/financing-flash'


def parse_title_details(title):
    """从标题解析公司、轮次、金额"""
    company = round_str = amount = ""

    # 匹配公司名称
    match = re.search(r'^[""''](.+?)[""'']', title)
    if match:
        company = match.group(1).strip()
    else:
        match = re.search(r'^(.+?)(?:完成|获|得到|宣布)', title)
        if match:
            company = match.group(1).strip()
        else:
            match = re.search(r'^[\u4e00-\u9fa5]{2,8}', title)
            if match:
                company = match.group(0)

    if len(company) > 15:
        company = company[:15]

    # 匹配轮次
    round_patterns = [
        r'(种子轮?)', r'(天使[轮+]?)', r'(Pre[-\s]?A\+?轮?)',
        r'(A\d*\+?轮)', r'(B\d*\+?轮)', r'(C\d*\+?轮)',
        r'(D\d*\+?轮)', r'(E轮)', r'(F轮)',
        r'(IPO)', r'(战略融资)', r'(股权融资)',
        r'(定增)', r'(并购)', r'(收购)',
    ]
    for pattern in round_patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            round_str = match.group(1)
            break

    # 匹配金额
    amount_patterns = [
        r'(\d+[\d\.]*)\s*([万亿]?)\s*([人民币美元元美金融资]+)',
        r'(数千万|数百万|数亿|上千万元|上百万元|几十亿元|几亿元)',
        r'(千万级|百万级|亿级)',
        r'(近\s*\d+[\d\.]*)\s*([万亿]?[元])',
        r'(超\s*\d+[\d\.]*)\s*([万亿]?[元])',
        r'(金额未披露|未披露|undisclosed)',
    ]
    for pattern in amount_patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            if len(match.groups()) >= 3:
                amount = f"{match.group(1)}{match.group(2)}{match.group(3)}"
            else:
                amount = match.group(1)
            break

    return company, round_str, amount


def fetch_financing_news():
    """实时抓取融资快讯"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }

    try:
        response = requests.get(SOURCE_URL, headers=headers, timeout=30)
        response.raise_for_status()
        response.encoding = response.apparent_encoding

        # 从 __INIT_PROPS__ 中提取数据
        props_start = response.text.find('window.__INIT_PROPS__ = ')
        if props_start == -1:
            return []

        json_start = props_start + len('window.__INIT_PROPS__ = ')

        # 使用括号计数找到 JSON 结束位置
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
            project_card = item.get('projectCard', {})

            title = material.get('widgetTitle', '')
            content = material.get('widgetContent', '')
            pub_time_ms = material.get('publishTime', 0)

            if not title:
                continue

            # 转换时间戳
            if pub_time_ms:
                pub_date = datetime.fromtimestamp(pub_time_ms / 1000).isoformat()
            else:
                pub_date = datetime.now().isoformat()

            # 构建链接
            route = item.get('route', '')
            if route.startswith('detail_newsflash'):
                link = f"https://36kr.com/newsflashes/{item.get('itemId')}"
            elif route.startswith('detail_article'):
                item_id = re.search(r'itemId=(\d+)', route)
                if item_id:
                    link = f"https://36kr.com/p/{item_id.group(1)}"
                else:
                    link = SOURCE_URL
            else:
                link = SOURCE_URL

            # 从 projectCard 获取信息
            company = project_card.get('name', '')
            round_info = project_card.get('lastestFinancingRound', {})
            round_str = round_info.get('name', '')

            # 如果 projectCard 没有，从标题解析
            if not company:
                company, parsed_round, amount = parse_title_details(title)
                if not round_str and parsed_round:
                    round_str = parsed_round
            else:
                _, _, amount = parse_title_details(title)

            items.append({
                'title': title,
                'link': link,
                'pub_date': pub_date,
                'description': content or title,
                'company': company,
                'round': round_str,
                'amount': amount,
            })

        # 按时间倒序排列
        items.sort(key=lambda x: x.get('pub_date', ''), reverse=True)
        return items

    except Exception as e:
        print(f"[error] Fetch failed: {e}")
        return []


def generate_rss(items):
    """生成 RSS XML"""
    items_xml = ''

    for item in items[:50]:
        pub_date = item.get('pub_date', datetime.now().isoformat())
        if isinstance(pub_date, str):
            try:
                dt = datetime.fromisoformat(pub_date.replace('Z', '+00:00'))
                pub_date = dt.strftime('%a, %d %b %Y %H:%M:%S +0800')
            except:
                pub_date = datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0800')

        # 构建 GUID
        import hashlib
        guid = hashlib.md5(f"{item['title']}{item['link']}".encode()).hexdigest()

        desc_html = f"""
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; line-height: 1.6; color: #333;">
            <p style="margin: 8px 0;"><strong style="color: #1a73e8;">公司:</strong> {item.get('company') or '未知'}</p>
            <p style="margin: 8px 0;"><strong style="color: #1a73e8;">轮次:</strong> {item.get('round') or '未知'}</p>
            <p style="margin: 8px 0;"><strong style="color: #1a73e8;">金额:</strong> {item.get('amount') or '未披露'}</p>
            <hr style="border: none; border-top: 1px solid #e0e0e0; margin: 12px 0;">
            <p style="margin: 8px 0; color: #555;">{item.get('description', item['title'])}</p>
            <p style="margin: 12px 0;"><a href="{item['link']}" target="_blank" style="color: #1a73e8; text-decoration: none;">查看详情</a></p>
        </div>
        """

        items_xml += f"""
        <item>
            <title><![CDATA[{item['title']}]]></title>
            <link>{item['link']}</link>
            <guid isPermaLink="false">{guid}</guid>
            <pubDate>{pub_date}</pubDate>
            <description><![CDATA[{desc_html}]]></description>
        </item>
        """

    last_build = datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0800')

    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
    <channel>
        <title>36kr 融资快讯</title>
        <link>{SOURCE_URL}</link>
        <description>36氪 PitchHub 最新一级市场股权融资动态</description>
        <language>zh-CN</language>
        <lastBuildDate>{last_build}</lastBuildDate>
        <generator>36kr RSS for Railway</generator>
        {items_xml}
    </channel>
</rss>"""

    return rss


@app.route('/')
def index():
    """首页"""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>36kr 融资快讯 RSS</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; max-width: 800px; margin: 40px auto; padding: 20px; background: #f5f7fa; }
            h1 { color: #1a1a1a; margin-bottom: 10px; }
            .info { background: white; padding: 25px; border-radius: 12px; margin: 20px 0; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
            a { color: #1a73e8; text-decoration: none; }
            .rss-link { background: #1a73e8; color: white !important; padding: 10px 20px; border-radius: 6px; display: inline-block; margin: 10px 0; }
            .stats { color: #1a73e8; font-weight: 600; }
        </style>
    </head>
    <body>
        <h1>📰 36kr 融资快讯 RSS</h1>
        <div class="info">
            <p><strong>RSS 地址:</strong> <a href="/rss" class="rss-link">/rss</a></p>
            <p>每次访问实时抓取最新数据</p>
            <p>数据来源于: <a href="https://pitchhub.36kr.com/financing-flash" target="_blank">36kr PitchHub</a></p>
        </div>
    </body>
    </html>
    """
    return render_template_string(html)


@app.route('/rss')
def rss_feed():
    """RSS 接口 - 实时抓取"""
    items = fetch_financing_news()
    rss_xml = generate_rss(items)
    return Response(rss_xml, mimetype='application/rss+xml; charset=utf-8')


@app.route('/api/items')
def api_items():
    """API 接口 - 返回 JSON 格式"""
    items = fetch_financing_news()
    return {
        'items': items,
        'total': len(items),
        'last_update': datetime.now().isoformat()
    }


if __name__ == '__main__':
    # Railway 使用 PORT 环境变量
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
