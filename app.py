#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
36kr 融资快讯 RSS 服务
提供持续更新的 RSS feed
"""

import requests
from bs4 import BeautifulSoup
from flask import Flask, Response, render_template_string
from datetime import datetime, timedelta
import re
import json
import os
import threading
import time
import hashlib

app = Flask(__name__)

# 配置文件
CONFIG = {
    'source_url': 'https://pitchhub.36kr.com/financing-flash',
    'update_interval': 300,  # 5分钟更新一次
    'max_items': 100,  # 最多保留100条
    'history_file': 'history.json',
}

# 全局数据存储
class DataStore:
    def __init__(self):
        self.items = []
        self.last_update = None
        self.lock = threading.Lock()
        self.load_history()

    def load_history(self):
        """加载历史数据"""
        if os.path.exists(CONFIG['history_file']):
            try:
                with open(CONFIG['history_file'], 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.items = data.get('items', [])
                    self.last_update = datetime.fromisoformat(data.get('last_update', '2000-01-01'))
                print(f"[init] Loaded {len(self.items)} history items")
            except Exception as e:
                print(f"[init] Load history failed: {e}")
                self.items = []
                self.last_update = None

    def save_history(self):
        """保存历史数据"""
        try:
            with open(CONFIG['history_file'], 'w', encoding='utf-8') as f:
                json.dump({
                    'items': self.items,
                    'last_update': self.last_update.isoformat() if self.last_update else None
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[error] Save history failed: {e}")

    def update_items(self, new_items):
        """更新数据，去重"""
        with self.lock:
            existing_guids = {item['guid'] for item in self.items}
            added = 0
            for item in new_items:
                if item['guid'] not in existing_guids:
                    self.items.insert(0, item)  # 新数据放前面
                    added += 1

            # 限制数量
            if len(self.items) > CONFIG['max_items']:
                self.items = self.items[:CONFIG['max_items']]

            self.last_update = datetime.now()
            self.save_history()
            return added

data_store = DataStore()

def parse_title_details(title):
    """从标题解析公司、轮次、金额"""
    company = round_str = amount = ""

    # 清理标题
    clean_title = title.strip().replace('「', '').replace('」', '').replace('"', '').replace('"', '')

    # 匹配公司名称 - 通常在开头
    # 模式1: 引号/书名号包裹的名称
    match = re.search(r'^[""''](.+?)[""'']', title)
    if match:
        company = match.group(1).strip()
    else:
        # 模式2: 在"完成/获/宣布"之前的内容
        match = re.search(r'^(.+?)(?:完成|获|得到|宣布)', title)
        if match:
            company = match.group(1).strip()
        else:
            # 模式3: 提取前2-8个汉字
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
    """抓取融资快讯 - 从页面 __INIT_PROPS__ 中提取"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Referer': 'https://36kr.com/',
    }

    try:
        print(f"[{datetime.now()}] Fetching...")
        response = requests.get(CONFIG['source_url'], headers=headers, timeout=30)
        response.raise_for_status()
        response.encoding = response.apparent_encoding

        # 从 __INIT_PROPS__ 中提取数据
        # 找到 __INIT_PROPS__ 的开始位置
        props_start = response.text.find('window.__INIT_PROPS__ = ')
        if props_start == -1:
            print("[error] __INIT_PROPS__ not found")
            return []

        # 从赋值后开始解析 JSON
        json_start = props_start + len('window.__INIT_PROPS__ = ')

        # 使用括号计数找到 JSON 结束位置
        brace_count = 0
        in_string = False
        escape_next = False
        json_end = json_start

        for i, char in enumerate(response.text[json_start:]):
            if escape_next:
                escape_next = False
                continue
            if char == '\\':
                escape_next = True
                continue
            if char == '"' and not in_string:
                in_string = True
            elif char == '"' and in_string:
                in_string = False
            elif not in_string:
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        json_end = json_start + i + 1
                        break

        json_str = response.text[json_start:json_end]

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"[error] JSON parse error: {e}")
            return []
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
                    link = CONFIG['source_url']
            else:
                link = CONFIG['source_url']

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

            # 生成 GUID
            guid = hashlib.md5(f"{title}{item.get('itemId', '')}".encode()).hexdigest()

            items.append({
                'title': title,
                'link': link,
                'pub_date': pub_date,
                'description': content or title,
                'company': company,
                'round': round_str,
                'amount': amount,
                'guid': guid,
            })

        print(f"[done] Parsed {len(items)} items")
        return items

    except Exception as e:
        print(f"[error] Fetch failed: {e}")
        import traceback
        traceback.print_exc()
        return []

def generate_rss():
    """生成 RSS XML"""
    items_xml = ''

    with data_store.lock:
        items = data_store.items.copy()

    # 按时间倒序排列（最新的在前）
    items.sort(key=lambda x: x.get('pub_date', ''), reverse=True)

    for item in items[:50]:
        pub_date = item.get('pub_date', datetime.now().isoformat())
        if isinstance(pub_date, str):
            try:
                dt = datetime.fromisoformat(pub_date.replace('Z', '+00:00'))
                pub_date = dt.strftime('%a, %d %b %Y %H:%M:%S +0800')
            except:
                pub_date = datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0800')

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
            <guid isPermaLink="false">{item['guid']}</guid>
            <pubDate>{pub_date}</pubDate>
            <description><![CDATA[{desc_html}]]></description>
        </item>
        """

    last_build = datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0800')

    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
    <channel>
        <title>36kr 融资快讯</title>
        <link>{CONFIG['source_url']}</link>
        <description>36氪 PitchHub 最新一级市场股权融资动态 - 持续更新</description>
        <language>zh-CN</language>
        <lastBuildDate>{last_build}</lastBuildDate>
        <generator>36kr RSS Service</generator>
        <atom:link href="http://localhost:5002/rss" rel="self" type="application/rss+xml" />
        {items_xml}
    </channel>
</rss>"""

    return rss

def background_updater():
    """后台更新线程"""
    while True:
        try:
            new_items = fetch_financing_news()
            if new_items:
                added = data_store.update_items(new_items)
                print(f"[update] Added {added} new items")
            else:
                print("[update] No new data")
        except Exception as e:
            print(f"[error] Background update failed: {e}")

        time.sleep(CONFIG['update_interval'])

@app.route('/')
def index():
    """首页"""
    last_update = data_store.last_update.strftime('%Y-%m-%d %H:%M:%S') if data_store.last_update else 'never'

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>36kr 融资快讯 RSS</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; max-width: 900px; margin: 40px auto; padding: 20px; background: #f5f7fa; }}
            h1 {{ color: #1a1a1a; margin-bottom: 10px; }}
            .subtitle {{ color: #666; margin-bottom: 30px; }}
            .info {{ background: white; padding: 25px; border-radius: 12px; margin: 20px 0; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
            .info p {{ margin: 12px 0; font-size: 15px; }}
            .info strong {{ color: #333; display: inline-block; width: 100px; }}
            a {{ color: #1a73e8; text-decoration: none; }}
            a:hover {{ text-decoration: underline; }}
            .stats {{ color: #1a73e8; font-weight: 600; }}
            .rss-link {{ background: #1a73e8; color: white !important; padding: 8px 16px; border-radius: 6px; display: inline-block; margin-top: 10px; }}
            .rss-link:hover {{ background: #1557b0; text-decoration: none; }}
            .item {{ background: white; padding: 20px; border-radius: 10px; margin: 15px 0; box-shadow: 0 1px 4px rgba(0,0,0,0.06); transition: transform 0.2s; }}
            .item:hover {{ transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.1); }}
            .item-title {{ font-size: 16px; font-weight: 600; color: #1a1a1a; line-height: 1.5; }}
            .item-title a {{ color: inherit; }}
            .item-title a:hover {{ color: #1a73e8; }}
            .item-meta {{ color: #666; font-size: 13px; margin-top: 10px; display: flex; gap: 20px; flex-wrap: wrap; }}
            .item-meta span {{ display: flex; align-items: center; gap: 5px; }}
            .badge {{ background: #e8f0fe; color: #1a73e8; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 500; }}
            h2 {{ color: #333; margin-top: 40px; border-bottom: 2px solid #e0e0e0; padding-bottom: 10px; }}
        </style>
    </head>
    <body>
        <h1>36kr 融资快讯 RSS</h1>
        <p class="subtitle">持续追踪一级市场股权融资动态</p>

        <div class="info">
            <p><strong>RSS:</strong> <a href="/rss" class="rss-link">/rss</a></p>
            <p><strong>Updated:</strong> {last_update}</p>
            <p><strong>Items:</strong> <span class="stats">{len(data_store.items)}</span></p>
            <p><strong>Interval:</strong> <span class="stats">{CONFIG['update_interval'] // 60} min</span></p>
        </div>

        <h2>Latest</h2>
        <div>
            {generate_preview()}
        </div>

        <div style="text-align: center; margin-top: 40px; color: #999; font-size: 13px;">
            <p>Data source: 36kr PitchHub</p>
        </div>
    </body>
    </html>
    """
    return render_template_string(html)

def generate_preview():
    """生成预览 HTML"""
    # 按时间倒序排列（最新的在前）
    sorted_items = sorted(data_store.items, key=lambda x: x.get('pub_date', ''), reverse=True)
    items = sorted_items[:10]
    if not items:
        return '<p style="text-align: center; color: #999; padding: 40px;">No data yet, please wait...</p>'

    html = ''
    for item in items:
        company = item.get('company') or 'Unknown'
        round_str = item.get('round') or 'Unknown'
        amount = item.get('amount') or 'Undisclosed'

        html += f"""
        <div class="item">
            <div class="item-title"><a href="{item['link']}" target="_blank">{item['title']}</a></div>
            <div class="item-meta">
                <span>{company}</span>
                <span><span class="badge">{round_str}</span></span>
                <span>{amount}</span>
            </div>
        </div>
        """
    return html

@app.route('/rss')
def rss_feed():
    """RSS 接口"""
    rss_xml = generate_rss()
    return Response(rss_xml, mimetype='application/rss+xml; charset=utf-8')

@app.route('/api/items')
def api_items():
    """API 接口"""
    with data_store.lock:
        items = data_store.items.copy()
    return {
        'items': items,
        'total': len(items),
        'last_update': data_store.last_update.isoformat() if data_store.last_update else None
    }

@app.route('/refresh')
def manual_refresh():
    """手动刷新"""
    def do_refresh():
        new_items = fetch_financing_news()
        if new_items:
            added = data_store.update_items(new_items)
            print(f"[refresh] Added {added} items")

    thread = threading.Thread(target=do_refresh)
    thread.start()
    return {'status': 'refreshing', 'message': 'Background refreshing...'}

if __name__ == '__main__':
    # 启动后台更新线程
    updater_thread = threading.Thread(target=background_updater, daemon=True)
    updater_thread.start()

    # 立即执行一次抓取
    print("[startup] First fetch...")
    initial_items = fetch_financing_news()
    if initial_items:
        data_store.update_items(initial_items)
        print(f"[startup] Loaded {len(initial_items)} items")

    print("=" * 50)
    print("36kr RSS Service Started")
    print("=" * 50)
    print("Home : http://localhost:5002")
    print("RSS  : http://localhost:5002/rss")
    print("API  : http://localhost:5002/api/items")
    print("=" * 50)

    # 启动 Flask 服务
    app.run(host='0.0.0.0', port=5002, debug=False, threaded=True)
