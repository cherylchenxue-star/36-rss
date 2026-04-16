#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抓取36kr融资快讯并生成静态RSS文件
用于GitHub Actions定时运行
"""

import requests
from datetime import datetime, timezone, timedelta
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


SMART_TAG_KEYWORDS = {
    "人工智能": ["人工智能", "AI", "AIGC", "生成式AI", "大模型", "机器学习", "深度学习", "算法", "神经网络", "智能算力", "NLP", "计算机视觉", "CV", "多模态"],
    "机器人": ["机器人", "人形机器人", "具身智能", "工业机器人", "服务机器人", "扫地机器人", "无人机", "机械臂", "灵巧手"],
    "半导体": ["半导体", "芯片", "集成电路", "晶圆", "EDA", "封测", "光刻", "先进制程", "GPU", "MCU", "传感器芯片"],
    "新能源": ["新能源", "光伏", "风电", "储能", "氢能", "锂电池", "动力电池", "充电桩", "清洁能源", "钠电池", "固态电池"],
    "电动汽车": ["新能源汽车", "电动车", "电动汽车", "智能网联汽车", "自动驾驶", "车联网", "智能驾驶", "辅助驾驶", "激光雷达"],
    "航空航天": ["航空航天", "商业航天", "卫星", "火箭", "eVTOL", "低空经济", "大飞机", "航空发动机", "航天器"],
    "生物医药": ["生物医药", "医疗器械", "创新药", "疫苗", "基因治疗", "CXO", "医疗健康", "数字医疗", "体外诊断", "手术机器人"],
    "金融科技": ["金融科技", "数字金融", "区块链", "数字货币", "支付", "普惠金融", "保险科技", "财富管理"],
    "企业服务": ["企业服务", "SaaS", "云计算", "大数据", "低代码", "数字化转型", "协同办公", "CRM", "ERP", "RPA"],
    "先进制造": ["先进制造", "智能制造", "工业互联网", "高端装备", "3D打印", "增材制造", "工业软件", "数控机床"],
    "新材料": ["新材料", "复合材料", "化工材料", "稀土", "高性能纤维", "纳米材料", "石墨烯", "碳纤维"],
    "物联网/硬件": ["物联网", "IoT", "智能硬件", "智能家居", "可穿戴设备", "传感器", "智能穿戴", "VR", "AR", "MR"],
    "消费零售": ["新零售", "电商", "跨境电商", "直播带货", "新消费", "食品饮料", "美妆", "个护", "潮玩", "宠物经济"],
    "教育": ["教育", "在线教育", "职业教育", "素质教育", "教育科技", "K12", "EdTech", "智慧教育"],
    "文娱游戏": ["游戏", "电竞", "影视", "动漫", "文创", "短视频", "直播", "音乐", "体育", "剧本杀", "密室逃脱"],
    "物流供应链": ["物流", "供应链", "仓储", "快递", "冷链", "即时配送", "智慧物流", "供应链金融科技"],
    "农业科技": ["农业", "智慧农业", "农机", "乡村振兴", "预制菜", "种业", "养殖", "农产品"],
    "能源电力": ["电力", "电网", "核电", "火电", "水电", "输配电", "虚拟电厂", "特高压", "智慧电网"],
    "环保双碳": ["环保", "双碳", "碳中和", "碳达峰", "节能减排", "循环经济", "绿色金融", "碳交易", "污染治理"],
    "汽车出行": ["汽车", "整车", "零部件", "二手车", "共享出行", "网约车", "租车", "汽车后市场"],
    "本地生活": ["本地生活", "餐饮", "外卖", "酒旅", "民宿", "社区团购", "生鲜电商", "到家服务"],
    "出海/全球化": ["出海", "全球化", "跨境", "外贸", "一带一路", "国际化", "海外市场"],
    "建筑地产": ["房地产", "建筑", "建材", "智慧城市", "物业管理", "家装", "室内设计"],
    "网络安全": ["网络安全", "信息安全", "数据安全", "隐私计算", "密码学", "零信任", "态势感知"],
}


def extract_smart_tags(text: str, trade_list: list = None):
    """基于标题+正文关键词匹配提取智能标签，并合并结构化行业标签"""
    if not text:
        text = ""
    text_lower = text.lower()
    tags = []
    for tag, keywords in SMART_TAG_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text_lower:
                tags.append(tag)
                break
    # 合并 projectCard.tradeList 中的结构化标签
    if trade_list:
        for t in trade_list:
            name = t.get("name") if isinstance(t, dict) else t
            if name and isinstance(name, str):
                tags.append(name)
    # 去重保序，最多6个
    return list(dict.fromkeys(tags))[:6]


def extract_tags(item, material):
    """提取智能标签/行业标签（兼容旧版结构化字段 + 新版关键词）"""
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
    # 可能路径 3: projectCard.tradeList 作为兜底
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
            raw_content = material.get('widgetContent', '')
            content = raw_content
            pub_time_ms = material.get('publishTime', 0)

            if not title:
                continue

            if pub_time_ms:
                pub_date = datetime.fromtimestamp(pub_time_ms / 1000, tz=timezone.utc).isoformat()
            else:
                pub_date = datetime.now(timezone.utc).isoformat()

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

            # 智能标签：先通过关键词+tradeList提取，再合并结构化标签
            trades = safe_get(project_card, "tradeList", default=[])
            tags = extract_smart_tags(f"{title} {content}", trades)
            structured_tags = extract_tags(item, material)
            for t in structured_tags:
                if t not in tags:
                    tags.append(t)
            tags = tags[:6]

            # 如果 projectCard 没有公司名，仅尝试从引号中简单提取，避免误识别
            if not company_name:
                m = re.search(r'[“"「『]([^”"」』]{2,20})[”"」』]', title)
                if m:
                    company_name = m.group(1)

            # detail_article 的 widgetContent 经常是完全不相关的推荐语，需要过滤
            if route_base == 'detail_article' and content:
                has_company = company_name and company_name in content
                has_funding = any(kw in content for kw in ['融资', '轮', '投资', '领投', '跟投', '获', '完成', '亿元', '万美元'])
                if not (has_company or has_funding):
                    content = ''

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
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            dt_cst = dt.astimezone(timezone(timedelta(hours=8)))
            pub_date_str = dt_cst.strftime('%a, %d %b %Y %H:%M:%S +0800')
        except:
            pub_date_str = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8))).strftime('%a, %d %b %Y %H:%M:%S +0800')

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
        <lastBuildDate>{datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8))).strftime('%a, %d %b %Y %H:%M:%S +0800')}</lastBuildDate>
        <generator>36kr RSS Generator</generator>
        {items_xml}
    </channel>
</rss>"""

    return rss


def main():
    print(f"[{datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8))).isoformat()}] 开始抓取...")

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
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            dt_cst = dt.astimezone(timezone(timedelta(hours=8)))
            date_str = dt_cst.strftime('%Y-%m-%d')
            time_str = dt_cst.strftime('%H:%M')
        except:
            now_cst = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8)))
            date_str = now_cst.strftime('%Y-%m-%d')
            time_str = now_cst.strftime('%H:%M')

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
        <span class="text-sm text-slate-400">更新于 {datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M')}</span>
      </div>
      <div class="mt-5 flex flex-wrap items-center justify-center gap-3">
        <a href="rss.xml" class="inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-5 py-2 rounded-full text-sm font-medium transition shadow-sm">
          <i class="fa fa-rss"></i> RSS 订阅
        </a>
        <a href="https://github.com/cherylchenxue-star/36-rss/actions/workflows/update-rss.yml" target="_blank" class="inline-flex items-center gap-2 bg-slate-700 hover:bg-slate-800 text-white px-5 py-2 rounded-full text-sm font-medium transition shadow-sm">
          <i class="fa fa-refresh"></i> 手动刷新
        </a>
      </div>
      <p class="text-xs text-slate-400 mt-2">手动刷新将跳转 GitHub Actions 执行最新抓取</p>
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
