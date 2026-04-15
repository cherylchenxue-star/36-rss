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

            # 如果 projectCard 没有公司名，仅尝试从引号中简单提取，避免误识别
            if not company_name:
                m = re.search(r'[“"「『]([^”"」』]{2,20})[”"」』]', title)
                if m:
                    company_name = m.group(1)

            # 构建描述内容
            desc_parts = []
            if company_name:
                desc_parts.append(f"<p><strong>🏢 被投企业：</strong>{company_name}</p>")
            if round_name:
                desc_parts.append(f"<p><strong>🔄 融资轮次：</strong>{round_name}</p>")
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
                'content': content,
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

    # 生成时间轴 HTML 预览页
    timeline_items = []
    for idx, item in enumerate(items[:50]):
        try:
            dt = datetime.fromisoformat(item['pub_date'].replace('Z', '+00:00'))
            date_str = dt.strftime('%Y-%m-%d')
            time_str = dt.strftime('%H:%M')
        except:
            date_str = datetime.now().strftime('%Y-%m-%d')
            time_str = datetime.now().strftime('%H:%M')

        tags_html = ""
        for tag in item.get('tags', [])[:4]:
            tags_html += f'<span class="px-2 py-0.5 bg-blue-50 text-blue-600 text-xs rounded-full">{tag}</span>'

        meta = []
        if item.get('company'):
            meta.append(f"🏢 {item['company']}")
        if item.get('round'):
            meta.append(f"🔄 {item['round']}")
        if item.get('investors'):
            meta.append(f"💼 {'、'.join(item['investors'][:3])}")
        meta_html = " · ".join(meta) if meta else ""

        summary = item.get('content', '')
        # 摘要控制在 160 字以内
        if len(summary) > 160:
            summary = summary[:160] + "…"

        side_class = "md:flex-row" if idx % 2 == 0 else "md:flex-row-reverse"
        date_align = "md:text-right md:pr-8" if idx % 2 == 0 else "md:text-left md:pl-8"
        card_align = "md:pl-8" if idx % 2 == 0 else "md:pr-8"

        timeline_items.append(f"""
        <div class="relative flex flex-col {side_class} items-start md:items-stretch mb-8 md:mb-0 md:min-h-[120px]">
          <!-- 桌面端日期 -->
          <div class="hidden md:block md:w-1/2 {date_align} pt-1">
            <div class="text-sm font-semibold text-blue-600">{time_str}</div>
            <div class="text-xs text-slate-400">{date_str}</div>
          </div>
          <!-- 圆点 -->
          <div class="absolute left-3 md:left-1/2 md:-translate-x-1/2 top-1 w-3 h-3 rounded-full bg-blue-500 border-2 border-white shadow z-10"></div>
          <!-- 内容卡片 -->
          <div class="pl-10 md:pl-0 md:w-1/2 {card_align} pb-8">
            <!-- 移动端日期 -->
            <div class="md:hidden mb-1">
              <div class="text-sm font-semibold text-blue-600">{time_str}</div>
              <div class="text-xs text-slate-400">{date_str}</div>
            </div>
            <div class="bg-white rounded-xl p-5 shadow-sm hover:shadow-md transition border border-slate-100">
              <a href="{item['link']}" target="_blank" class="block text-base font-bold text-slate-900 hover:text-blue-600 mb-2 leading-snug">{item['title']}</a>
              <div class="flex flex-wrap gap-2 mb-2">{tags_html}</div>
              <div class="text-xs text-slate-500 mb-2">{meta_html}</div>
              <p class="text-sm text-slate-600 leading-relaxed">{summary}</p>
            </div>
          </div>
        </div>
        """)

    timeline_html = "\n".join(timeline_items)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>36kr 融资快讯 RSS</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/font-awesome@4.7.0/css/font-awesome.min.css">
  <style>
    .timeline-line {{
      position: absolute;
      left: 0.875rem;
      top: 0;
      bottom: 0;
      width: 2px;
      background: linear-gradient(to bottom, #bfdbfe, #60a5fa, transparent);
    }}
    @media (min-width: 768px) {{
      .timeline-line {{
        left: 50%;
        transform: translateX(-50%);
      }}
    }}
  </style>
</head>
<body class="bg-gradient-to-br from-slate-50 to-slate-100 text-slate-800 min-h-screen">
  <div class="max-w-5xl mx-auto px-4 py-12">
    <!-- Header -->
    <div class="text-center mb-12">
      <h1 class="text-3xl font-bold text-slate-900 mb-2">36kr 融资快讯</h1>
      <p class="text-slate-500 mb-6">最新一级市场股权融资动态</p>
      <div class="inline-flex flex-wrap items-center justify-center gap-3 bg-white px-6 py-3 rounded-full shadow-sm">
        <span class="text-sm text-slate-600">当前数据: <strong class="text-slate-900">{len(items)}</strong> 条</span>
        <span class="hidden sm:inline w-px h-4 bg-slate-200"></span>
        <span class="text-sm text-slate-400">更新于 {datetime.now().strftime('%Y-%m-%d %H:%M')}</span>
      </div>
      <div class="mt-5">
        <a href="rss.xml" class="inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-5 py-2 rounded-full text-sm font-medium transition shadow-sm">
          <i class="fa fa-rss"></i> RSS 订阅
        </a>
      </div>
    </div>

    <!-- Timeline -->
    <div class="relative">
      <div class="timeline-line"></div>
      {timeline_html}
    </div>

    <p class="text-center text-slate-400 text-sm mt-8 pb-8">
      数据来源于 <a href="https://pitchhub.36kr.com/financing-flash" class="text-blue-600 hover:underline">36kr PitchHub</a>
    </p>
  </div>
</body>
</html>"""

    with open('public/index.html', 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"[OK] RSS已生成: public/rss.xml")
    print(f"[OK] 时间轴预览页已生成: public/index.html")
    print(f"[OK] 共 {len(items)} 条数据")


if __name__ == '__main__':
    main()
