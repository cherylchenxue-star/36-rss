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
from bs4 import BeautifulSoup

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


def clean_article_text(text):
    """清理 mobile 文章页尾部杂质并截断摘要"""
    if not text:
        return text
    # 切除常见尾部模板内容
    cut_markers = [
        '本文由「', '你可能也喜欢这些文章', '评论区', '暂无评论',
        '寻求报道', '转载说明', '违规转载必究', '本文图片来自：',
        '寻求免费曝光', '关注36氪', '打开微信分享',
    ]
    for marker in cut_markers:
        idx = text.find(marker)
        if idx != -1:
            text = text[:idx]
    text = text.strip()
    # 截断到合理长度，尽量在句号处结束
    max_len = 1500
    if len(text) > max_len:
        trunc = text[:max_len]
        # 找最后一个句号、问号或感叹号
        last_punct = max(trunc.rfind('。'), trunc.rfind('？'), trunc.rfind('！'), trunc.rfind('\n'))
        if last_punct > max_len * 0.6:
            text = trunc[:last_punct + 1]
        else:
            text = trunc + '…'
    return text.strip()


def fetch_article_content(item_id):
    """抓取 36kr 文章详情页正文（通过 mobile 域名绕过 WAF）"""
    url = f'https://m.36kr.com/p/{item_id}'
    headers = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9',
    }
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.encoding = resp.apparent_encoding
        soup = BeautifulSoup(resp.text, 'html.parser')
        for sel in ['.kr-mobile-article', '.article-body-main', '.body-content-wrapper-main']:
            el = soup.select_one(sel)
            if el:
                for s in el.find_all(['script', 'style']):
                    s.decompose()
                text = el.get_text('\n', strip=True)
                if len(text) > 50:
                    return clean_article_text(text)
    except Exception:
        pass
    return None


def extract_investors_from_text(text):
    """从文章正文中提取投资机构"""
    if not text:
        return []
    investors = []
    sentences = re.split(r'[。；\n]', text)
    for sent in sentences:
        sent = sent.strip()
        if not sent or ('融资' not in sent and '投资' not in sent):
            continue
        # 贪婪匹配，停在句中最后一个"领投/跟投/投资"
        pattern = r'由(.{2,300})(?:等[^。；\n]{0,20}跟投|等[^。；\n]{0,20}领投|联合领投|领投|跟投|投资|参投|出资)'
        for raw in re.findall(pattern, sent):
            raw = raw.replace('联合领投', '、').replace('领投', '、').replace('跟投', '、').replace('出资', '、').replace('参投', '、')
            parts = re.split(r'[,，、和与\s]+', raw)
            for p in parts:
                p = p.strip()
                if not p or len(p) < 2 or len(p) > 25:
                    continue
                p = re.sub(r'^(由高|由|获|获得|拿到|来自)', '', p)
                p = p.strip('、，,和与由')
                if not p:
                    continue
                skip_words = {'此', '本轮', '其中', '以及', '等', '多家', '数家', '知名', '头部', '顶级', '国际', '国内', '一线', '原有', '现有', '老股东', '新股东', '财务基金', '股东', '机构'}
                if p in skip_words or p.startswith('等') or p.endswith('等'):
                    continue
                p = re.sub(r'(等多家机构|等财务基金|等股东|等机构)$', '', p)
                investors.append(p)
        # 投资方为XXX
        for raw in re.findall(r'投资方为(.{2,60}?)[。，,；\n]', sent):
            raw = raw.strip()
            if raw:
                parts = re.split(r'[,，、和与\s]+', raw)
                for p in parts:
                    p = p.strip()
                    if p and 2 <= len(p) <= 25 and p not in {'此', '本轮', '其中', '以及', '等', '一家'}:
                        investors.append(p)
        # "来自XX的融资"
        for p in re.findall(r'来自([\u4e00-\u9fa5a-zA-Z0-9（）()]+?)(?:的|数千|数亿|上百万|数百万|数千万|上亿|近亿元|亿元|万元|美元|美金|人民币|融资|投资|注资)', sent):
            p = p.strip()
            if p and 2 <= len(p) <= 25 and p not in {'此', '本轮', '其中', '以及', '等', '来自'}:
                investors.append(p)
    return list(dict.fromkeys(investors))


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

            # detail_article 需要从详情页抓取真正正文
            if route_base == 'detail_article' and item_id:
                article_text = fetch_article_content(item_id)
                if article_text:
                    content = article_text

            # 从正文/摘要中补充投资机构（newsflash 和 article 都适用）
            if content:
                text_investors = extract_investors_from_text(content)
                for inv in text_investors:
                    if inv not in investors:
                        investors.append(inv)

            # 智能标签：先通过关键词+tradeList提取，再合并结构化标签
            trades = safe_get(project_card, "tradeList", default=[])
            tags = extract_smart_tags(f"{title} {content}", trades)
            structured_tags = extract_tags(item, material)
            for t in structured_tags:
                if t not in tags:
                    tags.append(t)
            tags = tags[:6]

            # 如果 projectCard 没有公司名，尝试从标题提取
            if not company_name:
                # 优先匹配标题开头的公司名：粗门完成... / 攀峰智能完成... / 快快游戏获...
                m = re.match(r'^([\u4e00-\u9fa5]{2,10})(?:完成|获|获得|拿到|宣布)', title)
                if m:
                    company_name = m.group(1)
                else:
                    # 其次匹配引号中的名称
                    m = re.search(r'[“"「『]([^”"」』]{2,20})[”"」』]', title)
                    if m:
                        company_name = m.group(1)

            # 对 article 类型的公司进行校验：若抓取到了正文，但公司名未出现在正文中，则很可能是误识别
            if route_base == 'detail_article' and company_name and content and company_name not in content:
                # 再试试标题里是否真包含这家公司（去除引号后精确子串）
                clean_title = title.replace('"', '').replace('“', '').replace('”', '').replace('「', '').replace('」', '')
                if company_name not in clean_title:
                    company_name = ''

            # detail_article 若详情页抓取失败，原始 widgetContent 又明显不相关，则过滤掉
            # 注意：只对抓取失败的 article 做此校验；抓取成功的直接信任正文
            if route_base == 'detail_article' and raw_content and content == raw_content:
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

        # 投资方单独列出（自定义命名空间）
        investors_xml = ""
        for inv in item.get('investors', [])[:10]:
            investors_xml += f"\n            <kr:investor><![CDATA[{inv}]]></kr:investor>"

        # 公司名和轮次也单独输出
        extra_xml = ""
        if item.get('company'):
            extra_xml += f"\n            <kr:company><![CDATA[{item['company']}]]></kr:company>"
        if item.get('round'):
            extra_xml += f"\n            <kr:round><![CDATA[{item['round']}]]></kr:round>"

        items_xml += f"""
        <item>
            <title><![CDATA[{item['title']}]]></title>
            <link>{item['link']}</link>
            <guid isPermaLink="false">{guid}</guid>
            <pubDate>{pub_date_str}</pubDate>{categories_xml}{extra_xml}{investors_xml}
            <description><![CDATA[{item.get('description', item['title'])}]]></description>
        </item>
        """

    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:kr="https://36kr.com/rss-extension">
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

    # 统计数据
    total_count = len(items)
    today_str = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%d')
    today_count = sum(1 for it in items if it.get('pub_date', '').startswith(today_str))

    # 标签统计
    tag_counts = {}
    for it in items:
        for t in it.get('tags', []):
            tag_counts[t] = tag_counts.get(t, 0) + 1
    sorted_tags = sorted(tag_counts.items(), key=lambda x: -x[1])[:15]

    # 标签颜色映射
    TAG_COLORS = {
        '人工智能': {'color': '#9333ea', 'bg': '#f3e8ff'},
        '机器人': {'color': '#2563eb', 'bg': '#dbeafe'},
        '半导体': {'color': '#4f46e5', 'bg': '#e0e7ff'},
        '新能源': {'color': '#16a34a', 'bg': '#dcfce7'},
        '电动汽车': {'color': '#ea580c', 'bg': '#ffedd5'},
        '航空航天': {'color': '#0ea5e9', 'bg': '#e0f2fe'},
        '生物医药': {'color': '#dc2626', 'bg': '#fee2e2'},
        '金融科技': {'color': '#ca8a04', 'bg': '#fef9c3'},
        '企业服务': {'color': '#059669', 'bg': '#d1fae5'},
        '先进制造': {'color': '#db2777', 'bg': '#fce7f3'},
        '新材料': {'color': '#7c3aed', 'bg': '#ede9fe'},
        '物联网/硬件': {'color': '#0891b2', 'bg': '#cffafe'},
        '消费零售': {'color': '#e11d48', 'bg': '#ffe4e6'},
        '教育': {'color': '#65a30d', 'bg': '#ecfccb'},
        '文娱游戏': {'color': '#f59e0b', 'bg': '#fef3c7'},
        '物流供应链': {'color': '#6366f1', 'bg': '#e0e7ff'},
        '农业科技': {'color': '#22c55e', 'bg': '#dcfce7'},
        '能源电力': {'color': '#f97316', 'bg': '#ffedd5'},
        '环保双碳': {'color': '#14b8a6', 'bg': '#ccfbf1'},
        '汽车出行': {'color': '#3b82f6', 'bg': '#dbeafe'},
        '本地生活': {'color': '#ec4899', 'bg': '#fce7f3'},
        '出海/全球化': {'color': '#8b5cf6', 'bg': '#ede9fe'},
        '建筑地产': {'color': '#78716c', 'bg': '#f5f5f4'},
        '网络安全': {'color': '#ef4444', 'bg': '#fee2e2'},
    }

    def tag_style(tag):
        tc = TAG_COLORS.get(tag, {'color': '#6b7280', 'bg': '#f3f4f6'})
        return f'color:{tc["color"]};background:{tc["bg"]};border-color:{tc["color"]}30;'

    # 生成侧边栏标签云
    tag_cloud_html = ""
    for name, count in sorted_tags:
        style = tag_style(name)
        tag_cloud_html += f'''
            <button class="px-2.5 py-1 rounded-lg text-xs font-medium border transition-all hover:scale-105 cursor-default" style="{style}">
              {name} <span class="opacity-60">{count}</span>
            </button>'''

    # 生成新闻卡片列表
    now_cst = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8)))
    cards_html = ""
    for idx, item in enumerate(items[:50]):
        rank = idx + 1
        is_top3 = rank <= 3

        try:
            dt = datetime.fromisoformat(item['pub_date'].replace('Z', '+00:00'))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            dt_cst = dt.astimezone(timezone(timedelta(hours=8)))
            date_str = dt_cst.strftime('%Y-%m-%d %H:%M')
            # 相对时间
            diff_h = (now_cst - dt_cst).total_seconds() / 3600
            if diff_h < 1:
                    time_rel = f"{int(diff_h * 60)}分钟前"
            elif diff_h < 24:
                time_rel = f"{int(diff_h)}小时前"
            else:
                time_rel = f"{int(diff_h / 24)}天前"
        except:
            date_str = now_cst.strftime('%Y-%m-%d %H:%M')
            time_rel = ""

        # 排名徽章
        if is_top3:
            rank_badge = f'''<span class="w-7 h-7 rounded-lg bg-gradient-to-br from-indigo-500 to-indigo-700 text-white flex items-center justify-center text-sm font-bold shadow-md">{rank}</span>'''
        else:
            rank_badge = f'''<span class="w-7 h-7 rounded-lg bg-gray-100 text-gray-500 flex items-center justify-center text-sm font-medium">{rank}</span>'''

        # 标签
        tags_html = ""
        for tag in item.get('tags', [])[:4]:
            style = tag_style(tag)
            tags_html += f'''<span class="inline-block px-2 py-0.5 rounded text-xs font-medium border" style="{style}">{tag}</span>'''

        # 摘要
        summary = item.get('content', '')
        if len(summary) > 200:
            summary = summary[:200] + "…"

        # 元信息：公司、轮次、投资方
        meta_parts = []
        if item.get('company'):
            meta_parts.append(f'<span class="text-indigo-600 font-medium">{item["company"]}</span>')
        if item.get('round'):
            meta_parts.append(f'<span class="text-gray-500">{item["round"]}</span>')
        if item.get('investors'):
            meta_parts.append(f'<span class="text-gray-500">{"、".join(item["investors"][:3])}</span>')
        meta_html = " · ".join(meta_parts) if meta_parts else ""

        cards_html += f'''
        <article class="bg-white rounded-xl shadow-sm hover:shadow-lg transition-all duration-250 p-5 sm:p-6 border-l-[3px] border-transparent hover:border-l-indigo-500 hover:-translate-y-0.5">
          <div class="flex items-start gap-4">
            <div class="flex-shrink-0 mt-0.5">{rank_badge}</div>
            <div class="flex-1 min-w-0">
              <a href="{item['link']}" target="_blank" rel="noopener noreferrer" class="group block">
                <h2 class="text-base sm:text-lg font-semibold text-gray-900 leading-snug group-hover:text-indigo-700 transition-colors" style="display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;">
                  {item['title']}
                </h2>
              </a>
              <div class="mt-2 flex flex-wrap gap-1.5">
                {tags_html}
              </div>
              <p class="mt-2.5 text-sm text-gray-500 leading-relaxed" style="display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;">
                {summary}
              </p>
              <div class="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-gray-400">
                {meta_html}
                <span class="flex items-center space-x-1 ml-auto">
                  <i class="fa fa-clock-o"></i>
                  <span>{date_str}</span>
                </span>
                {f'<span class="text-gray-500 font-medium">{time_rel}</span>' if time_rel else ''}
              </div>
            </div>
          </div>
        </article>
        '''

    update_time = now_cst.strftime('%Y-%m-%d %H:%M')

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>每日融资动态</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/font-awesome@4.7.0/css/font-awesome.min.css">
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;600;700&display=swap">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans SC', sans-serif; }}
    .headline-font {{ font-family: 'Noto Serif SC', Georgia, serif; }}
    .gradient-header {{
      background: linear-gradient(135deg, #1e1b4b 0%, #312e81 50%, #4338ca 100%);
    }}
    .live-indicator {{
      animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
    }}
    @keyframes pulse {{
      0%, 100% {{ opacity: 1; }}
      50% {{ opacity: 0.4; }}
    }}
    .shadow-card {{
      box-shadow: 0 1px 3px 0 rgba(0,0,0,0.05), 0 4px 12px 0 rgba(0,0,0,0.08);
    }}
  </style>
</head>
<body class="bg-gray-50 min-h-screen">

  <!-- 顶部导航 -->
  <header class="gradient-header text-white shadow-lg sticky top-0 z-50">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
      <div class="flex items-center justify-between h-16">
        <div class="flex items-center space-x-3">
          <div class="w-9 h-9 bg-white/15 rounded-lg flex items-center justify-center backdrop-blur">
            <i class="fa fa-line-chart text-yellow-400 text-lg"></i>
          </div>
          <div>
            <h1 class="text-lg font-bold tracking-wide headline-font">每日融资动态</h1>
            <p class="text-xs text-indigo-200 -mt-0.5">聚合 36kr PitchHub 最新一级市场融资</p>
          </div>
        </div>
        <div class="flex items-center space-x-4">
          <div class="hidden sm:flex items-center space-x-2 text-sm text-indigo-200">
            <span class="w-2 h-2 bg-green-400 rounded-full live-indicator"></span>
            <span>{update_time}</span>
          </div>
          <a href="rss.xml" target="_blank"
             class="hidden sm:flex items-center space-x-1.5 bg-white/15 hover:bg-white/25 px-3 py-1.5 rounded-lg text-sm transition-colors backdrop-blur">
            <i class="fa fa-rss text-orange-300"></i>
            <span>RSS 订阅</span>
          </a>
        </div>
      </div>
    </div>
  </header>

  <!-- 统计栏 -->
  <div class="bg-white border-b border-gray-200 shadow-sm">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3">
      <div class="flex items-center justify-between flex-wrap gap-3">
        <div class="flex items-center space-x-6 text-sm">
          <div class="flex items-center space-x-2">
            <i class="fa fa-newspaper-o text-gray-400"></i>
            <span class="text-gray-500">今日融资</span>
            <span class="font-bold text-indigo-700 text-lg">{total_count}</span>
            <span class="text-gray-400">条</span>
          </div>
          <div class="hidden sm:flex items-center space-x-2">
            <span class="w-1.5 h-1.5 rounded-full bg-green-500"></span>
            <span class="text-gray-500">今日新增</span>
            <span class="font-semibold text-gray-700">{today_count}</span>
          </div>
          <div class="hidden sm:flex items-center space-x-2">
            <span class="w-1.5 h-1.5 rounded-full bg-indigo-500"></span>
            <span class="text-gray-500">标签</span>
            <span class="font-semibold text-gray-700">{len(tag_counts)}</span>
          </div>
        </div>
        <a href="https://github.com/cherylchenxue-star/36-rss/actions/workflows/update-rss.yml" target="_blank"
           class="flex items-center space-x-1.5 text-sm text-gray-500 hover:text-indigo-600 px-3 py-1.5 rounded-lg hover:bg-gray-100 transition-colors">
          <i class="fa fa-refresh"></i>
          <span>手动刷新</span>
        </a>
      </div>
    </div>
  </div>

  <!-- 主体内容 -->
  <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
    <div class="flex flex-col lg:flex-row gap-6">

      <!-- 左侧：新闻列表 -->
      <div class="flex-1 min-w-0">
        <div id="news-list" class="space-y-4">
          {cards_html}
        </div>
      </div>

      <!-- 右侧：侧边栏 -->
      <aside class="w-full lg:w-80 space-y-5">
        <!-- 热门标签 -->
        <div class="bg-white rounded-xl shadow-card p-5">
          <h3 class="text-sm font-bold text-gray-800 mb-4 flex items-center">
            <i class="fa fa-tags text-indigo-500 mr-2"></i>
            热门赛道
          </h3>
          <div class="flex flex-wrap gap-2">
            {tag_cloud_html}
          </div>
        </div>

        <!-- 关于 -->
        <div class="bg-gradient-to-br from-indigo-50 to-purple-50 rounded-xl p-5 border border-indigo-100">
          <h3 class="text-sm font-bold text-indigo-800 mb-2">关于本站</h3>
          <p class="text-xs text-indigo-600/80 leading-relaxed">
            自动抓取 36kr PitchHub 最新一级市场股权融资动态，智能提取赛道标签与投资机构，助你第一时间掌握创投市场核心风向。
          </p>
          <div class="mt-3 flex items-center space-x-3">
            <a href="rss.xml" target="_blank"
               class="inline-flex items-center space-x-1 text-xs text-indigo-600 hover:text-indigo-800 font-medium">
              <i class="fa fa-rss"></i>
              <span>RSS 源</span>
            </a>
            <span class="text-indigo-300">|</span>
            <span class="text-xs text-indigo-500/60">数据每 5h 更新</span>
          </div>
        </div>
      </aside>
    </div>
  </main>

  <!-- 底部 -->
  <footer class="bg-white border-t border-gray-200 mt-12">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
      <div class="flex flex-col sm:flex-row items-center justify-between text-xs text-gray-400">
        <p>每日融资动态 · 数据源自 <a href="https://pitchhub.36kr.com/financing-flash" target="_blank" class="text-indigo-500 hover:underline">36kr PitchHub</a></p>
        <p class="mt-2 sm:mt-0">仅供信息参考，不代表本站立场</p>
      </div>
    </div>
  </footer>

</body>
</html>'''

    with open('public/index.html', 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"[OK] RSS已生成: public/rss.xml")
    print(f"[OK] 时间轴预览页已生成: public/index.html")
    print(f"[OK] 共 {len(items)} 条数据")


if __name__ == '__main__':
    main()
