"""
filter_junk.py — 数据质量门
在 fetch_trends 之后运行,过滤"非新闻" / "重复" / "空描述"等
单源黑名单 + 标题关键词 + 描述关键词 三层过滤

设计原则:严格过滤(宁可漏 1 条真新闻,不放 1 条垃圾)
"""
import json
import re
import sys
from pathlib import Path

DATA = Path.home() / ".aily/workspace/trends-dashboard/trends-data.json"

# ========== 1. 整源封禁 (源头屏蔽) ==========
SOURCE_BLACKLIST = {
    # 抓回来 90% 是产品页/导航/备案号
    "TalkingData", "智研咨询", "QuestMobile", "iTjuzi IT 桔子",
    "洞见研报", "阿里研究院", "CBNData", "EY 中国", "Deloitte 中国",
    "KPMG 中国", "Deloitte", "EY", "KPMG", "BCG", "McKinsey", "PwC",
    "iMedia 艾媒", "iResearch 艾瑞", "艺恩 EndData",  # 历史污染
    "Econ 论文",  # 整源乱码
}

# ========== 2. 标题黑名单 (非新闻) ==========
TITLE_JUNK_PATTERNS = [
    # 36Kr 杂项
    r"网上有害信息举报", r"举报专区", r"举报邮箱", r"report\d{4}@",
    r"chinaventure\.com\.cn",
    # 产品/品牌页
    r"数据通\s*[A-Za-z]*", r"数据通Claw", r"产品手册", r"使用说明",
    r"联系我们", r"加入我们", r"网站地图", r"sitemap",
    # 备案/许可证
    r"京公网安备", r"ICP\s*证", r"icp.*备", r"营业执照", r"增值电信业务",
    # 搜索结果页
    r"^DeepSeek$", r"^百度一下$", r"^360搜索$", r"^Google$",
    # 工具/服务页
    r"免费工具", r"在线工具", r"登录注册",
    # 重复日期型标题
    r"^New Ecommerce Tools:\s*\w+\s*\d+,?\s*\d{4}\s*$",
    r"^Daily\s+(?:Briefing|Update|Recap)\s*[:：]\s*\w+\s*\d+",
]

# ========== 3. 描述黑名单 ==========
DESC_JUNK_PATTERNS = [
    r"举报邮箱[:：]\s*\S+@\S+",
    r"^\s*chinaventure\.com\.cn\s*$",
    r"京公网安备\s*\d+号",
]

# ========== 4. 字符异常 (西里尔/希腊/未解码实体) ==========
GARBLED_RE = re.compile(r"[\u0400-\u04FF]{2,}|[\u0370-\u03FF]{2,}|йеъхцюѳ|цныфыч")
HTML_ENTITY_RE = re.compile(r"&#?\w+;|&\w+;")

# ========== 5. 描述质量 (真空) ==========
def is_meaningless_desc(text):
    if not text:
        return True
    t = text.strip()
    if len(t) < 20:
        return True
    # 标题+描述完全一样
    return False  # 单独判断在 caller 做

def is_news_duplicate_title_desc(title, desc):
    """标题和 desc 完全一样(去重后会留,但不该有内容)"""
    if not title or not desc:
        return False
    t = title.strip()
    d = desc.strip()
    if t == d:
        return True
    # 标题被 desc 包含(> 80% 字符重叠)
    shorter, longer = (t, d) if len(t) < len(d) else (d, t)
    if shorter in longer and len(shorter) > 10:
        return True
    return False

# ========== 6. 主函数 ==========
def main():
    if not DATA.exists():
        print(f"  ❌ {DATA} 不存在")
        return
    d = json.loads(DATA.read_text(encoding="utf-8"))
    orig_n = len(d.get("stories", []))
    removed = {
        "整源黑名单": 0,
        "标题黑名单": 0,
        "描述黑名单": 0,
        "乱码": 0,
        "HTML实体": 0,
        "真空卡片标记": 0,
    }
    kept_stories = []
    for s in d["stories"]:
        src = s.get("sourceLabel", "")
        title = s.get("title_zh", "") or s.get("title_en", "") or ""
        desc_zh = s.get("desc_full_zh", "") or s.get("desc_zh", "") or ""
        desc_en = s.get("desc_full_en", "") or s.get("desc_en", "") or ""

        # 1. 整源黑名单
        if src in SOURCE_BLACKLIST:
            removed["整源黑名单"] += 1
            continue

        # 2. 标题黑名单
        is_junk_title = False
        for pat in TITLE_JUNK_PATTERNS:
            if re.search(pat, title, re.IGNORECASE):
                is_junk_title = True
                break
        if is_junk_title:
            removed["标题黑名单"] += 1
            continue

        # 3. 描述黑名单
        is_junk_desc = False
        for pat in DESC_JUNK_PATTERNS:
            for desc in (desc_zh, desc_en):
                if re.search(pat, desc, re.IGNORECASE):
                    is_junk_desc = True
                    break
            if is_junk_desc: break
        if is_junk_desc:
            removed["描述黑名单"] += 1
            continue

        # 4. 乱码
        full_text = title + desc_zh + desc_en
        if GARBLED_RE.search(full_text):
            removed["乱码"] += 1
            continue

        # 5. HTML 实体
        if HTML_ENTITY_RE.search(full_text):
            removed["HTML实体"] += 1
            # 不删,只解码(下面处理)

        # 解码 HTML 实体
        for field in ["title_zh", "title_en", "desc_zh", "desc_en",
                      "desc_full_zh", "desc_full_en"]:
            v = s.get(field, "")
            if v and HTML_ENTITY_RE.search(v):
                import html
                s[field] = html.unescape(v)

        # 6. 标题 = 描述 → 标记 is_repeat_desc(前端不显示)
        if is_news_duplicate_title_desc(title, desc_zh) or is_news_duplicate_title_desc(title, desc_en):
            s["is_repeat_desc"] = True
            removed["真空卡片标记"] += 1

        # 7. 真空卡片(没任何 desc)
        if not (desc_zh or desc_en) or all(len(d.strip()) < 20 for d in [desc_zh, desc_en] if d):
            s["is_empty"] = True

        kept_stories.append(s)

    d["stories"] = kept_stories
    d["stats"] = d.get("stats", {})
    d["stats"]["total"] = len(kept_stories)
    DATA.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"原始 {orig_n} 条 → 保留 {len(kept_stories)} 条")
    print(f"删除明细:")
    for k, v in removed.items():
        if v: print(f"  {k}: {v}")
    # 8 维验证
    garbled = sum(1 for s in kept_stories
                  if GARBLED_RE.search((s.get("title_zh","") or "") + (s.get("title_en","") or "")))
    entity = sum(1 for s in kept_stories
                 if any(HTML_ENTITY_RE.search(s.get(f,"") or "") for f in ["title_zh","desc_zh","desc_full_zh","desc_en","desc_full_en"]))
    blank_source = sum(1 for s in kept_stories if s.get("sourceLabel","") in SOURCE_BLACKLIST)
    no_desc = sum(1 for s in kept_stories if s.get("is_empty"))
    repeat = sum(1 for s in kept_stories if s.get("is_repeat_desc"))
    print(f"\n8 维验证(保留后):")
    print(f"  乱码: {garbled}")
    print(f"  HTML实体: {entity}")
    print(f"  黑名单源: {blank_source}")
    print(f"  真空卡片(标记): {no_desc}")
    print(f"  重复标题=描述(标记): {repeat}")

if __name__ == "__main__":
    main()
