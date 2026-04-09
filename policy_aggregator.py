#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
政府政策聚合 RSS 生成器
聚合工信部、科技部、数据局、发改委等多个政策来源
"""

import requests
from datetime import datetime
import json
import os
import re
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

# ============ 数据源配置 ============
SOURCES = {
    'miit_rss': {
        'name': '工信部官方RSS',
        'type': 'rss',
        'url': 'https://wap.miit.gov.cn/RRSdy/index.html',
        'base_url': 'https://wap.miit.gov.cn',
    },
    'miit_txs': {
        'name': '工信部信息通信发展司',
        'type': 'html_list',
        'url': 'https://www.miit.gov.cn/jgsj/txs/wjfb/index.html',
        'base_url': 'https://www.miit.gov.cn',
        'list_selector': '.clist_con li, .gy_list li, .list-content li',
        'title_selector': 'a',
        'date_selector': 'span',
        'link_attr': 'href',
    },
    'miit_kjs': {
        'name': '工信部科技司',
        'type': 'html_list',
        'url': 'https://www.miit.gov.cn/jgsj/kjs/wjfb/index.html',
        'base_url': 'https://www.miit.gov.cn',
        'list_selector': '.clist_con li, .gy_list li, .list-content li',
        'title_selector': 'a',
        'date_selector': 'span',
        'link_attr': 'href',
    },
    'miit_gxjss': {
        'name': '工信部高新技术司',
        'type': 'html_list',
        'url': 'https://www.miit.gov.cn/gyhxxhb/jgsj/gxjss/wjfb/index.html',
        'base_url': 'https://www.miit.gov.cn',
        'list_selector': '.clist_con li, .gy_list li, .list-content li',
        'title_selector': 'a',
        'date_selector': 'span',
        'link_attr': 'href',
    },
    'miit_waj': {
        'name': '工信部网络安全管理局',
        'type': 'html_list',
        'url': 'https://wap.miit.gov.cn/jgsj/waj/wjfb/index.html',
        'base_url': 'https://wap.miit.gov.cn',
        'list_selector': '.clist_con li, .gy_list li, .list-content li',
        'title_selector': 'a',
        'date_selector': 'span',
        'link_attr': 'href',
    },
    'miit_xgj': {
        'name': '工信部信息通信管理局',
        'type': 'html_list',
        'url': 'https://wap.miit.gov.cn/jgsj/xgj/wjfb/index.html',
        'base_url': 'https://wap.miit.gov.cn',
        'list_selector': '.clist_con li, .gy_list li, .list-content li',
        'title_selector': 'a',
        'date_selector': 'span',
        'link_attr': 'href',
    },
    'nda': {
        'name': '国家数据局',
        'type': 'html_list',
        'url': 'https://www.nda.gov.cn/sjj/zwgk/tzgg/list/index_pc_1.html',
        'base_url': 'https://www.nda.gov.cn',
        'list_selector': '.list_con li, .news-list li, .content-list li',
        'title_selector': 'a',
        'date_selector': 'span, .date',
        'link_attr': 'href',
    },
    'most': {
        'name': '科技部科技政策',
        'type': 'html_list',
        'url': 'https://www.most.gov.cn/satp/',
        'base_url': 'https://www.most.gov.cn',
        'list_selector': '.list_con li, .news_list li, .content_list li',
        'title_selector': 'a',
        'date_selector': 'span',
        'link_attr': 'href',
    },
    'miit_policy': {
        'name': '工信部政策文件',
        'type': 'html_list',
        'url': 'https://www.miit.gov.cn/zwgk/index.html',
        'base_url': 'https://www.miit.gov.cn',
        'list_selector': '.clist_con li, .gy_list li',
        'title_selector': 'a',
        'date_selector': 'span',
        'link_attr': 'href',
    },
    'cac': {
        'name': '国家网信办',
        'type': 'html_list',
        'url': 'https://www.cac.gov.cn/wxzw/A0937index_1.htm',
        'base_url': 'https://www.cac.gov.cn',
        'list_selector': '.list_box li, .news_list li, .list_con li',
        'title_selector': 'a',
        'date_selector': 'span, .date',
        'link_attr': 'href',
    },
    'ndrc': {
        'name': '国家发改委',
        'type': 'html_list',
        'url': 'https://www.ndrc.gov.cn/xxgk/',
        'base_url': 'https://www.ndrc.gov.cn',
        'list_selector': '.list_con li, .news_list li, .u-list li',
        'title_selector': 'a',
        'date_selector': 'span, .date',
        'link_attr': 'href',
    },
    'caai': {
        'name': '中国人工智能学会',
        'type': 'html_list',
        'url': 'https://www.caai.cn/site/term/14.html',
        'base_url': 'https://www.caai.cn',
        'list_selector': '.news_list li, .list_con li, .content-list li',
        'title_selector': 'a',
        'date_selector': 'span, .date',
        'link_attr': 'href',
    },
}


# ============ 通用 HTTP 请求 ============
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
}


def fetch_url(url, timeout=30):
    """通用 URL 抓取"""
    try:
        response = requests.get(url, headers=HEADERS, timeout=timeout)
        response.encoding = response.apparent_encoding
        return response.text
    except Exception as e:
        print(f"[ERROR] 抓取失败 {url}: {e}")
        return None


# ============ RSS 解析 ============
def parse_rss(url, source_config):
    """解析 RSS 源"""
    items = []
    try:
        import xml.etree.ElementTree as ET
        html = fetch_url(url)
        if not html:
            return items

        # 尝试解析为 RSS
        root = ET.fromstring(html)

        # 处理 RSS 2.0
        if root.tag == 'rss':
            channel = root.find('channel')
            if channel is None:
                return items

            for item in channel.findall('item'):
                title = item.findtext('title', '')
                link = item.findtext('link', '')
                pub_date = item.findtext('pubDate', '')
                description = item.findtext('description', '')

                if title and link:
                    items.append({
                        'title': clean_text(title),
                        'link': link,
                        'pub_date': parse_date(pub_date),
                        'description': clean_text(description),
                        'source': source_config['name'],
                        'category': ['政策'],
                    })

        # 处理 Atom
        elif 'feed' in root.tag:
            ns = {'atom': 'http://www.w3.org/2005/Atom'}
            for entry in root.findall('atom:entry', ns):
                title = entry.findtext('atom:title', '', ns)
                link_elem = entry.find('atom:link', ns)
                link = link_elem.get('href', '') if link_elem is not None else ''
                pub_date = entry.findtext('atom:updated', '', ns) or entry.findtext('atom:published', '', ns)
                summary = entry.findtext('atom:summary', '', ns) or entry.findtext('atom:content', '', ns)

                if title and link:
                    items.append({
                        'title': clean_text(title),
                        'link': link,
                        'pub_date': parse_date(pub_date),
                        'description': clean_text(summary),
                        'source': source_config['name'],
                        'category': ['政策'],
                    })

    except Exception as e:
        print(f"[ERROR] RSS 解析失败 {url}: {e}")

    return items[:20]  # 限制数量


# ============ HTML 列表解析 ============
def parse_html_list(source_key, source_config):
    """解析 HTML 列表页面"""
    items = []
    url = source_config['url']

    try:
        from bs4 import BeautifulSoup

        html = fetch_url(url)
        if not html:
            return items

        soup = BeautifulSoup(html, 'html.parser')

        # 尝试多种选择器
        selectors = source_config['list_selector'].split(', ')
        list_items = []
        for selector in selectors:
            list_items = soup.select(selector)
            if list_items:
                break

        for li in list_items[:20]:  # 限制数量
            try:
                # 提取标题和链接
                a_tag = li.select_one(source_config['title_selector'])
                if not a_tag:
                    continue

                title = clean_text(a_tag.get_text())
                link = a_tag.get(source_config['link_attr'], '')

                # 处理相对链接
                if link and not link.startswith('http'):
                    link = urljoin(source_config['base_url'], link)

                # 提取日期
                date_text = ''
                date_elem = li.select_one(source_config['date_selector'])
                if date_elem:
                    date_text = clean_text(date_elem.get_text())

                if title and link:
                    items.append({
                        'title': title,
                        'link': link,
                        'pub_date': parse_date(date_text) or datetime.now().isoformat(),
                        'description': f"来源：{source_config['name']}",
                        'source': source_config['name'],
                        'category': ['政策'],
                    })

            except Exception as e:
                continue

    except ImportError:
        print(f"[ERROR] 需要安装 beautifulsoup4: pip install beautifulsoup4")
    except Exception as e:
        print(f"[ERROR] HTML 解析失败 {url}: {e}")

    return items


# ============ 工具函数 ============
def clean_text(text):
    """清理文本"""
    if not text:
        return ''
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    return text


def parse_date(date_str):
    """解析各种日期格式"""
    if not date_str:
        return datetime.now().isoformat()

    formats = [
        '%Y-%m-%d',
        '%Y/%m/%d',
        '%Y年%m月%d日',
        '%a, %d %b %Y %H:%M:%S %z',
        '%a, %d %b %Y %H:%M:%S GMT',
        '%Y-%m-%d %H:%M:%S',
    ]

    date_str = date_str.strip()

    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.isoformat()
        except:
            continue

    # 尝试提取日期数字
    match = re.search(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', date_str)
    if match:
        try:
            dt = datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            return dt.isoformat()
        except:
            pass

    return datetime.now().isoformat()


def generate_item_id(item):
    """生成唯一 ID"""
    content = f"{item['title']}{item['link']}"
    return hash(content) & 0xFFFFFFFF


# ============ RSS 生成 ============
def generate_rss(items, title="政府政策聚合", description="聚合工信部、科技部、数据局等多个政策来源"):
    """生成 RSS XML"""
    items_xml = ''

    for item in items[:100]:  # 最多 100 条
        pub_date = item.get('pub_date', datetime.now().isoformat())
        try:
            dt = datetime.fromisoformat(pub_date.replace('Z', '+00:00'))
            pub_date_str = dt.strftime('%a, %d %b %Y %H:%M:%S +0800')
        except:
            pub_date_str = datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0800')

        guid = generate_item_id(item)
        source_tag = f"<category>{item['source']}</category>"

        items_xml += f"""
        <item>
            <title><![CDATA[{item['title']}]]></title>
            <link>{item['link']}</link>
            <guid isPermaLink="false">{guid}</guid>
            <pubDate>{pub_date_str}</pubDate>
            <description><![CDATA[{item.get('description', item['title'])}]]></description>
            {source_tag}
        </item>
        """

    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
    <channel>
        <title>{title}</title>
        <link>https://github.com/cherylchenxue-star/policy-rss</link>
        <description>{description}</description>
        <language>zh-CN</language>
        <lastBuildDate>{datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0800')}</lastBuildDate>
        <generator>Policy RSS Aggregator</generator>
        {items_xml}
    </channel>
</rss>"""

    return rss


def generate_html(items):
    """生成 HTML 预览页"""
    html_items = ''
    for item in items[:50]:
        pub_time = item['pub_date'][:10] if len(item['pub_date']) > 10 else item['pub_date']
        source_badge = f'<span class="source">{item["source"]}</span>'
        html_items += f"""
        <div class="item">
            <a href="{item['link']}" target="_blank" class="item-title">{item['title']}</a>
            <div class="item-meta">{source_badge} · {pub_time}</div>
        </div>
        """

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>政府政策聚合 RSS</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; max-width: 900px; margin: 40px auto; padding: 20px; background: #f5f7fa; }}
        h1 {{ color: #1a1a1a; text-align: center; }}
        .info {{ background: white; padding: 25px; border-radius: 12px; margin: 20px 0; box-shadow: 0 2px 8px rgba(0,0,0,0.08); text-align: center; }}
        .rss-link {{ background: #1a73e8; color: white; padding: 12px 24px; border-radius: 6px; display: inline-block; margin: 10px; text-decoration: none; font-weight: bold; }}
        .stats {{ display: flex; justify-content: center; gap: 30px; margin: 20px 0; flex-wrap: wrap; }}
        .stat {{ text-align: center; }}
        .stat-number {{ font-size: 24px; font-weight: bold; color: #1a73e8; }}
        .stat-label {{ color: #666; font-size: 14px; }}
        .item {{ background: white; padding: 16px 20px; border-radius: 8px; margin: 12px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }}
        .item-title {{ font-size: 16px; color: #1a1a1a; text-decoration: none; display: block; margin-bottom: 8px; font-weight: 500; }}
        .item-title:hover {{ color: #1a73e8; }}
        .item-meta {{ color: #888; font-size: 13px; display: flex; gap: 10px; align-items: center; }}
        .source {{ background: #e8f0fe; color: #1a73e8; padding: 2px 8px; border-radius: 4px; font-size: 12px; }}
        .footer {{ text-align: center; color: #999; margin-top: 40px; padding: 20px; }}
    </style>
</head>
<body>
    <h1>📋 政府政策聚合 RSS</h1>
    <div class="info">
        <p>聚合工信部、科技部、数据局、发改委等多个政策来源</p>
        <a href="policy.xml" class="rss-link">📡 RSS 订阅</a>
        <div class="stats">
            <div class="stat">
                <div class="stat-number">{len(items)}</div>
                <div class="stat-label">当前政策数</div>
            </div>
            <div class="stat">
                <div class="stat-number">{len(set(i['source'] for i in items))}</div>
                <div class="stat-label">来源数量</div>
            </div>
        </div>
        <p style="color: #888; font-size: 14px;">最后更新: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>
    <h2>最新政策</h2>
    {html_items}
    <div class="footer">
        数据来源: 工信部、科技部、国家数据局、发改委等
    </div>
</body>
</html>"""


# ============ 主程序 ============
def fetch_source(source_key, source_config):
    """抓取单个数据源"""
    print(f"[INFO] 正在抓取: {source_config['name']}")

    if source_config['type'] == 'rss':
        items = parse_rss(source_config['url'], source_config)
    elif source_config['type'] == 'html_list':
        items = parse_html_list(source_key, source_config)
    else:
        items = []

    print(f"[OK] {source_config['name']}: 获取 {len(items)} 条")
    return items


def main():
    print(f"[{datetime.now()}] 开始抓取政策数据...")

    all_items = []

    # 并行抓取多个源
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_source = {
            executor.submit(fetch_source, key, config): key
            for key, config in SOURCES.items()
        }

        for future in as_completed(future_to_source):
            source_key = future_to_source[future]
            try:
                items = future.result()
                all_items.extend(items)
            except Exception as e:
                print(f"[ERROR] {source_key} 抓取失败: {e}")

    # 去重（基于链接）
    seen_links = set()
    unique_items = []
    for item in all_items:
        if item['link'] not in seen_links:
            seen_links.add(item['link'])
            unique_items.append(item)

    # 按时间排序
    unique_items.sort(key=lambda x: x.get('pub_date', ''), reverse=True)

    print(f"[INFO] 去重后共 {len(unique_items)} 条")

    # 生成 RSS
    rss_content = generate_rss(unique_items)

    # 生成 HTML
    html_content = generate_html(unique_items)

    # 保存到 public 目录
    os.makedirs('public', exist_ok=True)

    with open('public/policy.xml', 'w', encoding='utf-8') as f:
        f.write(rss_content)

    with open('public/policy.html', 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"[OK] RSS 已生成: public/policy.xml")
    print(f"[OK] HTML 已生成: public/policy.html")
    print(f"[OK] 共 {len(unique_items)} 条政策")


if __name__ == '__main__':
    main()
