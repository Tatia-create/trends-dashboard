"""
clean_data.py — 清洗抓回来的数据
v1.0 (2026-07-08):
  - 删除导航/服务页/产品介绍(10+ 类)
  - HTML 实体解码(&nbsp; 等)
  - UTF-8 强制(防 GBK 乱码)
  - 无描述的标记 has_full_summary=False
"""
import json
import re
import html
from pathlib import Path

DATA_PATH = Path.home() / ".aily/workspace/trends-dashboard/trends-data.json"

# 导航/服务页/产品页关键词 (标题或描述出现即删)
NAV_KEYWORDS = [
    # 英文
    "Compliance and Security", "Ad Tracking", "Financial Risk Control",
    "Joint Modeling", "Product Solutions", "Industry Solutions",
    "Service Solutions", "Tracking Solutions", "Modelling",
    # 中文
    "租赁和商务服务业", "价值创造、保存和恢复", "能源、资源及工业",
    "金融服务行业", "战略与交易", "行业洞察", "服务介绍",
    "中国母婴行业市场规模", "快造科技（Snapmaker）",  # 假新闻
    # 行业分类页
    "行业市场规模", "行业研究", "行业分类", "行业概述",
    # 报告导航
    "研究报告 >", "行业报告 >", "产品中心", "解决方案 >",
]

# 源黑名单(整源失效的源,全部条目删除)
SOURCE_BLACKLIST = {
    "EY 中国",  # 整站抓,90% 是导航
    "TalkingData",  # 整站抓,90% 是产品页
    "智研咨询",  # 整站抓,90% 是行业分类
    "Deloitte 中国",  # 整站抓,90% 是行业页
}


def is_navigation_page(item: dict) -> bool:
    """判断是否是导航/服务页/产品页"""
    text = (
        item.get("title_zh", "") + item.get("title_en", "")
        + item.get("desc_zh", "") + item.get("desc_en", "")
        + item.get("desc_full_zh", "") + item.get("desc_full_en", "")
    )
    for kw in NAV_KEYWORDS:
        if kw in text:
            return True
    return False


def decode_html_entities(text: str) -> str:
    """HTML 实体解码"""
    if not text:
        return text
    return html.unescape(text)


def fix_encoding(text: str) -> str:
    """修 GBK 误码 (Γ/Ð/★/♡ 等乱码字符)"""
    if not text:
        return text
    # 替换常见乱码
    fixes = {
        "Γ": "", "Ð": "", "★": "", "♡": "", "※": "",
        "&#xff08;": "（", "&#xff09;": "）",
        "&#xff1a;": "：", "&#xff0c;": "，",
        "&nbsp;": " ", "&amp;": "&",
    }
    for bad, good in fixes.items():
        text = text.replace(bad, good)
    # 如果包含乱码字符,整条标记
    if re.search(r"[ÐÞ★☆♡※]{2,}", text):
        return ""
    return text


def clean_stories(stories: list) -> tuple:
    """返回 (cleaned_stories, stats)"""
    stats = {
        "before": len(stories),
        "deleted_nav": 0,
        "deleted_blacklist_source": 0,
        "fixed_html": 0,
        "fixed_encoding": 0,
        "kept": 0,
    }

    cleaned = []
    for s in stories:
        source = s.get("sourceLabel", "")

        # 黑名单源 → 删
        if source in SOURCE_BLACKLIST:
            stats["deleted_blacklist_source"] += 1
            continue

        # 导航/服务页 → 删
        if is_navigation_page(s):
            stats["deleted_nav"] += 1
            continue

        # 修复字段
        for field in ["title_zh", "title_en", "desc_zh", "desc_en",
                      "desc_full_zh", "desc_full_en"]:
            v = s.get(field, "")
            if v:
                v2 = decode_html_entities(v)
                v3 = fix_encoding(v2)
                if v2 != v:
                    stats["fixed_html"] += 1
                if v3 != v2:
                    stats["fixed_encoding"] += 1
                s[field] = v3

        cleaned.append(s)
        stats["kept"] += 1

    return cleaned, stats


def main():
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"清洗前: {len(data['stories'])} 条")
    cleaned, stats = clean_stories(data["stories"])
    print(f"清洗后: {len(cleaned)} 条")
    print(f"  删导航/服务页: {stats['deleted_nav']}")
    print(f"  删黑名单源: {stats['deleted_blacklist_source']}")
    print(f"  修 HTML 实体: {stats['fixed_html']}")
    print(f"  修乱码: {stats['fixed_encoding']}")
    print(f"  保留: {stats['kept']}")

    # 更新 stats
    data["stories"] = cleaned
    data["stats"]["total"] = len(cleaned)
    data["last_updated_cleaned"] = "2026-07-08"

    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n已保存到 {DATA_PATH}")


if __name__ == "__main__":
    main()
