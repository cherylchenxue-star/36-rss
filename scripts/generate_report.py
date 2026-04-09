#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub Action 脚本：读取 RSS 并生成日报
"""

import os
import sys
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from html.parser import HTMLParser


class HTMLStripper(HTMLParser):
    """去除 HTML 标签"""
    def __init__(self):
        super().__init__()
        self.reset()
        self.fed = []

    def handle_data(self, d):
        self.fed.append(d)

    def get_data(self):
        return ''.join(self.fed)


def strip_html(html):
    s = HTMLStripper()
    s.feed(html)
    return s.get_data()


def fetch_rss(url):
    """获取 RSS 内容"""
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"[ERROR] 获取 RSS 失败: {e}")
        return None


def parse_rss(xml_content):
    """解析 RSS XML"""
    items = []
    try:
        root = ET.fromstring(xml_content)
        for item in root.findall('.//item'):
            title = item.find('title').text or ''
            link = item.find('link').text or ''
            pub_date = item.find('pubDate').text or ''
            description = item.find('description').text or ''

            # 清理标题（去除 CDATA）
            title = title.replace('<![CDATA[', '').replace(']]>', '')

            # 提取纯文本描述
            desc_text = strip_html(description)

            items.append({
                'title': title,
                'link': link,
                'pub_date': pub_date,
                'description': desc_text.strip()
            })
    except Exception as e:
        print(f"[ERROR] 解析 RSS 失败: {e}")

    return items


def generate_markdown_report(items, output_path):
    """生成 Markdown 格式报告"""
    today = datetime.now().strftime('%Y-%m-%d')

    md = f"""# 📰 36kr 融资快讯日报

**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**数据来源**: [36kr PitchHub](https://pitchhub.36kr.com/financing-flash)

---

## 今日融资动态（{len(items)} 条）

"""

    for i, item in enumerate(items, 1):
        md += f"""
### {i}. {item['title']}

- **发布时间**: {item['pub_date']}
- **原文链接**: [{item['link']}]({item['link']})
- **详情**: {item['description'][:200]}...

---
"""

    # 添加统计信息
    md += f"""
## 📊 统计

- 总计: {len(items)} 条融资新闻
- 抓取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

*本报告由 GitHub Action 自动生成*
"""

    # 保存报告
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(md)

    print(f"[OK] 报告已生成: {output_path}")
    return md


def main():
    # 从环境变量获取 RSS URL
    rss_url = os.environ.get('RSS_URL', 'http://localhost:5000/rss')

    print(f"[*] 正在获取 RSS: {rss_url}")

    # 获取 RSS
    xml_content = fetch_rss(rss_url)
    if not xml_content:
        print("[ERROR] 无法获取 RSS 内容")
        sys.exit(1)

    # 解析 RSS
    items = parse_rss(xml_content)
    print(f"[*] 解析到 {len(items)} 条数据")

    # 生成报告
    today = datetime.now().strftime('%Y%m%d')
    output_path = f"reports/daily_report_{today}.md"
    generate_markdown_report(items, output_path)

    print("[OK] 完成!")


if __name__ == '__main__':
    main()
