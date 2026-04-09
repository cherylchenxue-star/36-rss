#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
政府政策聚合 RSS 生成器 - 增强版（带反爬对策）
聚合工信部、科技部、数据局、发改委等多个政策来源
"""

import requests
from datetime import datetime
import json
import os
import re
import time
import random
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ============ 反爬配置 ============
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
]

# 政府网站域名对应的 referer
REFERER_MAP = {
    'miit.gov.cn': 'https://www.miit.gov.cn/',
    'nda.gov.cn': 'https://www.nda.gov.cn/',
    'most.gov.cn': 'https://www.most.gov.cn/',
    'cac.gov.cn': 'https://www.cac.gov.cn/',
    'ndrc.gov.cn': 'https://www.ndrc.gov.cn/',
    'caai.cn': 'https://www.caai.cn/',
}


def create_session():
    """创建带重试机制的 session"""
    session = requests.Session()

    # 配置重试策略：失败后重试 3 次，间隔递增
    retry = Retry(
        total=3,
        backoff_factor=3,  # 间隔 3s, 6s, 12s
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"]
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    session.mount('http://', adapter)
    session.mount('https://', adapter)

    return session


def get_headers(url):
    """根据 URL 生成合适的请求头"""
    domain = urlparse(url).netloc

    # 找匹配的 referer
    referer = 'https://www.baidu.com/s?wd='  # 默认模拟从百度搜索进入
    for key, ref in REFERER_MAP.items():
        if key in domain:
            referer = ref
            break

    headers = {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
        'Accept-Encoding': 'gzip, deflate, br',
        'Referer': referer,
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'cross-site',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0',
        'DNT': '1',
    }
    return headers


def smart_delay(base_delay=2.0):
    """智能延时：基础延时 + 随机扰动"""
    delay = base_delay + random.uniform(0.5, 2.0)
    time.sleep(delay)


# ============ 数据源配置 ============
SOURCES = {
    'miit_txs': {
        'name': '工信部信息通信发展司',
        'type': 'html_list',
        'url': 'https://www.miit.gov.cn/jgsj/txs/wjfb/index.html',
        'base_url': 'https://www.miit.gov.cn',
        'list_selectors': ['.lmy_main_l3 li', '.lmy_main_tj li', '.clist_con li', '.gy_list li', '.list-content li', '.infor-list li', '.list li'],
        'title_selector': 'a',
        'date_selector': 'span',
        'link_attr': 'href',
        'encoding': 'utf-8',
    },
    'miit_kjs': {
        'name': '工信部科技司',
        'type': 'html_list',
        'url': 'https://www.miit.gov.cn/jgsj/kjs/wjfb/index.html',
        'base_url': 'https://www.miit.gov.cn',
        'list_selectors': ['.clist_con li', '.gy_list li', '.list-content li'],
        'title_selector': 'a',
        'date_selector': 'span',
        'link_attr': 'href',
        'encoding': 'utf-8',
    },
    'miit_gxjss': {
        'name': '工信部高新技术司',
        'type': 'html_list',
        'url': 'https://www.miit.gov.cn/gyhxxhb/jgsj/gxjss/wjfb/index.html',
        'base_url': 'https://www.miit.gov.cn',
        'list_selectors': ['.clist_con li', '.gy_list li', '.list-content li'],
        'title_selector': 'a',
        'date_selector': 'span',
        'link_attr': 'href',
        'encoding': 'utf-8',
    },
    'miit_waj': {
        'name': '工信部网络安全管理局',
        'type': 'html_list',
        'url': 'https://www.miit.gov.cn/jgsj/waj/wjfb/index.html',
        'base_url': 'https://www.miit.gov.cn',
        'list_selectors': ['.clist_con li', '.gy_list li', '.list-content li'],
        'title_selector': 'a',
        'date_selector': 'span',
        'link_attr': 'href',
        'encoding': 'utf-8',
    },
    'miit_xgj': {
        'name': '工信部信息通信管理局',
        'type': 'html_list',
        'url': 'https://www.miit.gov.cn/jgsj/xgj/wjfb/index.html',
        'base_url': 'https://www.miit.gov.cn',
        'list_selectors': ['.clist_con li', '.gy_list li', '.list-content li'],
        'title_selector': 'a',
        'date_selector': 'span',
        'link_attr': 'href',
        'encoding': 'utf-8',
    },
    'nda': {
        'name': '国家数据局',
        'type': 'html_list',
        'url': 'https://www.nda.gov.cn/sjj/zwgk/tzgg/list/index_pc_1.html',
        'base_url': 'https://www.nda.gov.cn',
        'list_selectors': ['.u-list li', '.list_con li', '.news-list li', '.content-list li', '.list-item'],
        'title_selector': 'a',
        'date_selector': 'span, .date, .time',
        'link_attr': 'href',
        'encoding': 'utf-8',
    },
    'most': {
        'name': '科技部科技政策',
        'type': 'html_list',
        'url': 'https://www.most.gov.cn/satp/',
        'base_url': 'https://www.most.gov.cn',
        'list_selectors': ['.list_con li', '.news_list li', '.content_list li', '.list-box li'],
        'title_selector': 'a',
        'date_selector': 'span',
        'link_attr': 'href',
        'encoding': 'utf-8',
    },
    'miit_policy': {
        'name': '工信部政策文件',
        'type': 'html_list',
        'url': 'https://www.miit.gov.cn/zwgk/index.html',
        'base_url': 'https://www.miit.gov.cn',
        'list_selectors': ['.clist_con li', '.gy_list li', '.list-content li'],
        'title_selector': 'a',
        'date_selector': 'span',
        'link_attr': 'href',
        'encoding': 'utf-8',
    },
    'cac': {
        'name': '国家网信办',
        'type': 'html_list',
        'url': 'https://www.cac.gov.cn/wxzw/A0937index_1.htm',
        'base_url': 'https://www.cac.gov.cn',
        'list_selectors': ['.news-normal li', '.list_box li', '.news_list li', '.list_con li', '.list-item'],
        'title_selector': 'a',
        'date_selector': 'span, .date',
        'link_attr': 'href',
        'encoding': 'utf-8',
    },
    'ndrc': {
        'name': '国家发改委',
        'type': 'html_list',
        'url': 'https://www.ndrc.gov.cn/xxgk/',
        'base_url': 'https://www.ndrc.gov.cn',
        'list_selectors': ['.list_con li', '.news_list li', '.u-list li', '.list-box li', '.list-item'],
        'title_selector': 'a',
        'date_selector': 'span, .date',
        'link_attr': 'href',
        'encoding': 'utf-8',
    },
    'caai': {
        'name': '中国人工智能学会',
        'type': 'html_list',
        'url': 'https://www.caai.cn/site/term/14.html',
        'base_url': 'https://www.caai.cn',
        'list_selectors': ['.news_list li', '.list_con li', '.content-list li', '.news-item'],
        'title_selector': 'a',
        'date_selector': 'span, .date, .time',
        'link_attr': 'href',
        'encoding': 'utf-8',
    },
}


def fetch_url(url, session=None, encoding=None):
    """智能 URL 抓取（带反爬对策）"""
    if session is None:
        session = create_session()

    headers = get_headers(url)

    try:
        response = session.get(url, headers=headers, timeout=30, allow_redirects=True)
        response.raise_for_status()

        # 处理编码
        if encoding:
            response.encoding = encoding
        else:
            response.encoding = response.apparent_encoding

        return response.text

    except requests.exceptions.SSLError:
        # 处理证书问题（部分政府网站证书配置有问题）
        try:
            response = session.get(url, headers=headers, timeout=30, verify=False)
            if encoding:
                response.encoding = encoding
            else:
                response.encoding = response.apparent_encoding
            return response.text
        except Exception as e:
            print(f"[ERROR] SSL 失败 {url}: {e}")
            return None
    except Exception as e:
        print(f"[ERROR] 抓取失败 {url}: {e}")
        return None


def parse_html_list_enhanced(source_key, source_config, session):
    """增强版 HTML 列表解析"""
    items = []
    url = source_config['url']

    try:
        from bs4 import BeautifulSoup

        # 延时防爬
        smart_delay(2.0)

        html = fetch_url(url, session, source_config.get('encoding'))
        if not html:
            return items

        # 检查是否被拦截
        blocked_keywords = ['访问过于频繁', '验证码', 'captcha', '您的访问被拦截', '请开启JavaScript']
        if any(kw in html for kw in blocked_keywords):
            print(f"[WARN] {source_config['name']}: 可能被拦截")
            return items

        soup = BeautifulSoup(html, 'html.parser')

        # 尝试多种选择器
        list_items = []
        for selector in source_config['list_selectors']:
            list_items = soup.select(selector)
            if list_items:
                print(f"[INFO] {source_config['name']}: 使用选择器 {selector}")
                break

        if not list_items:
            print(f"[WARN] {source_config['name']}: 未找到列表项")
            # 输出页面结构供调试
            all_lists = soup.find_all(['ul', 'ol'])
            if all_lists:
                print(f"[DEBUG] 页面中找到 {len(all_lists)} 个列表")
            return items

        for li in list_items[:15]:  # 限制数量
            try:
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

                if title and link and len(title) > 5:  # 过滤无效标题
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

    except Exception as e:
        print(f"[ERROR] HTML 解析失败 {url}: {e}")

    return items


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
        return None

    formats = [
        '%Y-%m-%d',
        '%Y/%m/%d',
        '%Y年%m月%d日',
        '%Y-%m-%d %H:%M:%S',
        '%Y/%m/%d %H:%M:%S',
    ]

    date_str = date_str.strip()

    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.isoformat()
        except:
            continue

    # 正则提取
    match = re.search(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', date_str)
    if match:
        try:
            dt = datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            return dt.isoformat()
        except:
            pass

    return None


def generate_item_id(item):
    """生成唯一 ID"""
    content = f"{item['title']}{item['link']}"
    return hash(content) & 0xFFFFFFFF


def generate_rss(items, title="政府政策聚合", description="聚合工信部、科技部、数据局等多个政策来源"):
    """生成 RSS XML"""
    items_xml = ''

    for item in items[:100]:
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
    # 按来源分组统计
    source_stats = {}
    for item in items:
        src = item['source']
        source_stats[src] = source_stats.get(src, 0) + 1

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

    # 来源统计 HTML
    stats_html = ''
    for src, count in sorted(source_stats.items(), key=lambda x: -x[1]):
        stats_html += f'<div class="stat"><div class="stat-number">{count}</div><div class="stat-label">{src}</div></div>'

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
        .stats {{ display: flex; justify-content: center; gap: 20px; margin: 20px 0; flex-wrap: wrap; }}
        .stat {{ text-align: center; padding: 10px; }}
        .stat-number {{ font-size: 20px; font-weight: bold; color: #1a73e8; }}
        .stat-label {{ color: #666; font-size: 12px; max-width: 80px; }}
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
                <div class="stat-number">{len(source_stats)}</div>
                <div class="stat-label">来源数量</div>
            </div>
        </div>
        <div class="stats" style="margin-top:10px;">{stats_html}</div>
        <p style="color: #888; font-size: 14px;">最后更新: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>
    <h2>最新政策</h2>
    {html_items}
    <div class="footer">
        数据来源: 工信部、科技部、国家数据局、发改委等
    </div>
</body>
</html>"""


def fetch_source(source_key, source_config, session):
    """抓取单个数据源"""
    print(f"[INFO] 正在抓取: {source_config['name']}")

    items = parse_html_list_enhanced(source_key, source_config, session)

    print(f"[OK] {source_config['name']}: 获取 {len(items)} 条")
    return items


def main():
    print(f"[{datetime.now()}] 开始抓取政策数据...")
    print("=" * 60)

    all_items = []
    session = create_session()

    # 串行抓取（避免频率过高被封）
    for source_key, source_config in SOURCES.items():
        try:
            items = fetch_source(source_key, source_config, session)
            all_items.extend(items)
        except Exception as e:
            print(f"[ERROR] {source_key} 抓取失败: {e}")

        # 源间延时
        time.sleep(random.uniform(3, 5))

    print("=" * 60)

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

    # 生成 RSS 和 HTML
    rss_content = generate_rss(unique_items)
    html_content = generate_html(unique_items)

    # 保存
    os.makedirs('public', exist_ok=True)

    with open('public/policy.xml', 'w', encoding='utf-8') as f:
        f.write(rss_content)

    with open('public/policy.html', 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"[OK] RSS 已生成: public/policy.xml ({len(unique_items)} 条)")
    print(f"[OK] HTML 已生成: public/policy.html")


if __name__ == '__main__':
    main()
