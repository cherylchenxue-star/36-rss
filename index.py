#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
36kr 融资快讯 RSS - Vercel Flask 版本
"""

from flask import Flask, Response, render_template_string
import requests
from datetime import datetime
import re
import json

app = Flask(__name__)

SOURCE_URL = 'https://pitchhub.36kr.com/financing-flash'


def fetch_financing_news():
    """实时抓取融资快讯"""
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

            pub_date = datetime.fromtimestamp(pub_time_ms / 1000).isoformat() if pub_time_ms else datetime.now().isoformat()

            route = item.get('route', '')
            item_id = item.get('itemId', '')

            # 提取 route 主体（去掉 ?itemId=xxx 参数）
            route_base = route.split('?')[0] if '?' in route else route

            if route_base == 'detail_newsflash':
                link = f"https://36kr.com/newsflashes/{item_id}"
            elif route_base == 'detail_article':
                link = f"https://36kr.com/p/{item_id}"
            elif route_base.startswith('detail_'):
                # 其他 detail_ 类型的通用处理
                link = f"https://36kr.com/{route_base.replace('detail_', '')}/{item_id}"
            else:
                link = SOURCE_URL

            # 提取企业信息（如果有 projectCard）
            project_card = item.get('projectCard', {})
            company_info = {}
            if project_card:
                company_info = {
                    'name': project_card.get('name', ''),
                    'brief': project_card.get('briefIntro', ''),
                    'trades': [t.get('name', '') for t in project_card.get('tradeList', [])],
                    'round': project_card.get('lastestFinancingRound', {}).get('name', ''),
                    'city': project_card.get('city', {}).get('name', ''),
                    'establish_time': project_card.get('establishTime', {}).get('name', ''),
                }

            # 构建描述内容
            description = content or title
            if company_info.get('name'):
                company_desc = f"<p><strong>🏢 被投企业：{company_info['name']}</strong></p>"
                if company_info.get('brief'):
                    company_desc += f"<p>📋 企业简介：{company_info['brief']}</p>"
                if company_info.get('trades'):
                    company_desc += f"<p>🏭 行业类型：{'、'.join(company_info['trades'])}</p>"
                if company_info.get('round'):
                    company_desc += f"<p>💰 融资轮次：{company_info['round']}</p>"
                if company_info.get('city'):
                    company_desc += f"<p>📍 所在城市：{company_info['city']}</p>"
                if company_info.get('establish_time'):
                    company_desc += f"<p>📅 成立时间：{company_info['establish_time']}</p>"
                company_desc += "<hr/>"
                description = company_desc + description

            items.append({
                'title': title,
                'link': link,
                'pub_date': pub_date,
                'description': description,
                'company': company_info,
            })

        items.sort(key=lambda x: x.get('pub_date', ''), reverse=True)
        return items

    except Exception as e:
        print(f"[error] {e}")
        return []


def generate_rss(items):
    """生成 RSS"""
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

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
    <channel>
        <title>36kr 融资快讯</title>
        <link>{SOURCE_URL}</link>
        <description>36氪 PitchHub 最新一级市场股权融资动态</description>
        <lastBuildDate>{datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0800')}</lastBuildDate>
        {items_xml}
    </channel>
</rss>"""


@app.route('/')
def index():
    items = fetch_financing_news()
    return f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"><title>36kr RSS</title></head>
    <body style="font-family: Arial; max-width: 600px; margin: 50px auto; padding: 20px;">
        <h1>📰 36kr 融资快讯 RSS</h1>
        <p>当前数据: <strong>{len(items)}</strong> 条</p>
        <p><a href="/rss" style="background: #1a73e8; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">RSS 订阅</a></p>
        <p>数据实时抓取自: <a href="{SOURCE_URL}">36kr PitchHub</a></p>
    </body>
    </html>
    """


@app.route('/rss')
def rss_feed():
    items = fetch_financing_news()
    rss_xml = generate_rss(items)
    return Response(rss_xml, mimetype='application/rss+xml; charset=utf-8')


@app.route('/api/items')
def api_items():
    items = fetch_financing_news()
    return {'items': items, 'total': len(items)}


# Vercel 入口
if __name__ == '__main__':
    app.run(debug=True)
