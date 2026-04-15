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


def safe_get(obj, *keys, default=""):
    """安全多级字典取值"""
    for k in keys:
        if isinstance(obj, dict) and k in obj:
            obj = obj[k]
        else:
            return default
    return obj if obj is not None else default


def extract_investors(item, project_card):
    """从多个可能位置提取投资方列表"""
    investors = []
    # 可能路径 1: projectCard -> lastestFinancingRound -> investorList
    inv_list = safe_get(project_card, "lastestFinancingRound", "investorList", default=[])
    if inv_list:
        for inv in inv_list:
            name = inv.get("name") or inv.get("investorName")
            if name:
                investors.append(name)
    # 可能路径 2: item 根级别的 investorList / investors
    if not investors:
        for key in ("investorList", "investors", "investorNameList"):
            raw = item.get(key, [])
            if isinstance(raw, list):
                for r in raw:
                    if isinstance(r, dict):
                        name = r.get("name") or r.get("investorName")
                        if name:
                            investors.append(name)
                    elif isinstance(r, str):
                        investors.append(r)
    # 可能路径 3: financingInfo -> investorList
    if not investors:
        inv_list = safe_get(item, "financingInfo", "investorList", default=[])
        for inv in inv_list:
            name = inv.get("name") or inv.get("investorName")
            if name:
                investors.append(name)
    return list(dict.fromkeys(investors))  # 去重保序


def extract_tags(item, material):
    """提取智能标签/行业标签"""
    tags = []
    # 可能路径 1: item.tagList / tags / industries
    for key in ("tagList", "tags", "industries", "keywordList"):
        raw = item.get(key, [])
        if isinstance(raw, list):
            for r in raw:
                if isinstance(r, dict):
                    name = r.get("name") or r.get("tagName") or r.get("label")
                    if name:
                        tags.append(name)
                elif isinstance(r, str):
                    tags.append(r)
    # 可能路径 2: material.tagList
    if not tags:
        raw = material.get("tagList", [])
        for r in raw:
            if isinstance(r, dict):
                name = r.get("name") or r.get("tagName")
                if name:
                    tags.append(name)
            elif isinstance(r, str):
                tags.append(r)
    # 可能路径 3: projectCard.tradeList 作为行业标签兜底
    if not tags:
        trades = safe_get(item, "projectCard", "tradeList", default=[])
        for t in trades:
            name = t.get("name")
            if name:
                tags.append(name)
    return list(dict.fromkeys(tags))


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

        props_start = response.text.find('window.__INIT_PROPS__ = ')
        if props_start == -1:
            print("[ERROR] 未找到 __INIT_PROPS__ 数据")
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
            route_base = route.split('?')[0] if '?' in route else route

            if route_base == 'detail_newsflash':
                link = f"https://36kr.com/newsflashes/{item_id}"
            elif route_base == 'detail_article':
                link = f"https://36kr.com/p/{item_id}"
            elif route_base.startswith('detail_'):
                link = f"https://36kr.com/{route_base.replace('detail_', '')}/{item_id}"
            else:
                link = SOURCE_URL

            project_card = item.get('projectCard', {})
            company_name = project_card.get('name', '')
            round_name = safe_get(project_card, "lastestFinancingRound", "name", default="")
            investors = extract_investors(item, project_card)
            tags = extract_tags(item, material)

            # 补充企业详细信息
            company_brief = project_card.get('briefIntro', '')
            company_trades = [t.get('name', '') for t in project_card.get('tradeList', []) if t.get('name')]
            company_city = safe_get(project_card, 'city', 'name', default='')
            company_establish_time = safe_get(project_card, 'establishTime', 'name', default='')

            # 如果 projectCard 没有公司名，从标题兜底解析
            if not company_name:
                m = re.search(r'[「"\'](.+?)[」"\']', title)
                if m:
                    company_name = m.group(1)
                else:
                    m = re.search(r'^([\u4e00-\u9fa5]{2,8})', title)
                    if m:
                        company_name = m.group(1)

            # 构建描述内容
            desc_parts = []
            if company_name:
                desc_parts.append(f"<p><strong>🏢 被投企业：</strong>{company_name}</p>")
            if company_brief:
                desc_parts.append(f"<p>📋 企业简介：{company_brief}</p>")
            if company_trades:
                desc_parts.append(f"<p>🏭 行业类型：{'、'.join(company_trades)}</p>")
            if round_name:
                desc_parts.append(f"<p><strong>🔄 融资轮次：</strong>{round_name}</p>")
            if company_city:
                desc_parts.append(f"<p>📍 所在城市：{company_city}</p>")
            if company_establish_time:
                desc_parts.append(f"<p>📅 成立时间：{company_establish_time}</p>")
            if investors:
                desc_parts.append(f"<p><strong>💼 投资方：</strong>{'、'.join(investors)}</p>")
            if tags:
                desc_parts.append(f"<p><strong>🏷️ 标签：</strong>{'、'.join(tags)}</p>")
            if content:
                desc_parts.append(f"<hr/><p>{content}</p>")

            description = "".join(desc_parts) if desc_parts else (content or title)

            items.append({
                'title': title,
                'link': link,
                'pub_date': pub_date,
                'description': description,
                'company': company_name,
                'round': round_name,
                'investors': investors,
                'tags': tags,
                'company_brief': company_brief,
                'company_trades': company_trades,
                'company_city': company_city,
                'company_establish_time': company_establish_time,
            })

        items.sort(key=lambda x: x.get('pub_date', ''), reverse=True)
        print(f"[OK] 抓取到 {len(items)} 条数据")
        return items

    except Exception as e:
        print(f"[ERROR] 抓取失败: {e}")
        import traceback
        traceback.print_exc()
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

        # 标签作为 category 输出
        categories_xml = ""
        for tag in item.get('tags', [])[:5]:
            categories_xml += f"\n            <category><![CDATA[{tag}]]></category>"

        items_xml += f"""
        <item>
            <title><![CDATA[{item['title']}]]></title>
            <link>{item['link']}</link>
            <guid isPermaLink="false">{guid}</guid>
            <pubDate>{pub_date_str}</pubDate>{categories_xml}
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

    items = fetch_financing_news()

    if not items:
        print("[ERROR] 没有获取到数据")
        return

    rss_content = generate_rss(items)

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
        .item-meta {{ color: #888; font-size: 13px; margin-top: 5px; }}
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
        meta = []
        if item.get('company'):
            meta.append(f"🏢 {item['company']}")
        if item.get('investors'):
            meta.append(f"💼 {'、'.join(item['investors'][:3])}")
        if item.get('tags'):
            meta.append(f"🏷️ {'、'.join(item['tags'][:3])}")
        meta_html = " | ".join(meta) if meta else ""
        html += f"""
    <div class="item">
        <div class="item-title">{item['title']}</div>
        <div class="item-time">{pub_time}</div>
        <div class="item-meta">{meta_html}</div>
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
