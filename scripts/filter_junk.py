"""
filter_junk.py — 数据质量门 (v3.2 精过滤版)
跑在 fetch_trends 之后,过滤"非新闻" / "产品页" / "乱码" / "真空"
三层过滤:
  1. 整源黑名单(数据质量公认低,无研报价值)
  2. URL 黑名单(产品页/导航/联系页/榜单)
  3. 标题+描述黑名单(备案号/举报/工具页)

设计原则:
  - 研报源(智研/洞见/阿里研究院/艾瑞/EY/Deloitte/KPMG)用 URL+标题精过滤,不放进整源黑名单
  - 严格过滤:宁可漏 1 条真新闻,不放 1 条垃圾

v3.2 改动:
  - 解封智研咨询/洞见/阿里研究院/艾瑞等研报源(从整源黑名单移到 URL 精过滤)
  - EY/Deloitte/KPMG 等国际咨询也改 URL 精过滤
"""
import json
import re
import html as html_mod
from pathlib import Path

DATA = Path.home() / ".aily/workspace/trends-dashboard/trends-data.json"

# ========== 1. 整源黑名单(公认纯垃圾) ==========
SOURCE_BLACKLIST = {
    # 抓回来 90% 是产品页/榜单/导航,无研报价值
    "TalkingData", "QuestMobile", "iTjuzi IT 桔子",
    "CBNData", "iMedia 艾媒", "艺恩 EndData",
    "Econ 论文",  # 整源乱码
    # 智研咨询 / 洞见研报 / 阿里研究院 / iResearch 艾瑞 / EY / Deloitte / KPMG 等
    # 已从整源黑名单移除,改 URL+标题精过滤
}

# ========== 2. URL 黑名单(任何源出现这些路径都过滤) ==========
URL_JUNK_PATTERNS = [
    # 产品/工具/服务页
    r"/product[s]?/", r"/products?\.html", r"/tool[s]?/", r"/solution",
    r"/service[s]?/",
    # 联系/关于/加入
    r"/contact", r"/about-us", r"/about\.html", r"/join", r"/career",
    r"/sitemap", r"/help/?", r"/faq",
    # 榜单/排行
    r"/rank", r"/bangdan", r"/bang?dan", r"/top\d+", r"/chart/rank",
    # 导航/分类页(无具体内容)
    r"/category/", r"/tag/", r"/tags/",
    # 举报/版权
    r"/jubao", r"/report-mail", r"/copyright",
    # 备案号/许可证页
    r"/icp", r"/beian", r"/license",
    # 数据通(艾瑞产品页)
    r"data-claw", r"dataclaw", r"data[_\-]?claw",
]

# ========== 3. URL 白名单(研报源必须有这些关键词才放行) ==========
# 适用于:智研咨询/洞见/阿里研究院/艾瑞/EY/Deloitte/KPMG 等研报源
# 原因:这些源混研报+产品页+榜单,需要白名单过滤
RESEARCH_REPORT_KEYWORDS = [
    r"/report", r"/reports", r"/research", r"/whitepaper",
    r"/study", r"/insight", r"/analysis", r"/publication",
    r"/baogao", r"/yanbao", r"/yanjiu", r"/dongcha", r"/diaocha",
    r"/baipishu", r"/hangye", r"/hangye-yanjiu", r"/qushi",
    r"/trend", r"/forecast", r"/survey", r"/review",
    r"报告", r"研报", r"研究", r"洞察", r"调查", r"趋势", r"白皮书",
    r"年", r"季", r"月报", r"年报", r"季报", r"月", r"周",  # 研报常含时间词
]

RESEARCH_SOURCES = {
    # 国内研报源
    "智研咨询", "洞见研报", "阿里研究院", "iResearch 艾瑞", "艾瑞咨询",
    "CBNData", "艺恩 EndData",  # CBNData / 艺恩 重新评估:有研报价值
    # 国际咨询(有正经报告页,过滤 Careers/Insights 导航)
    "EY 中国", "EY", "Deloitte 中国", "Deloitte", "KPMG 中国", "KPMG",
    "BCG", "McKinsey", "PwC", "波士顿咨询", "麦肯锡", "普华永道",
}

# ========== 4. 标题黑名单 ==========
TITLE_JUNK_PATTERNS = [
    # 36Kr 杂项
    r"网上有害信息举报", r"举报专区", r"举报邮箱", r"report\d{4}@",
    r"chinaventure\.com\.cn",
    # 产品/品牌页
    r"数据通\s*[A-Za-z]*", r"数据通Claw", r"产品手册", r"使用说明",
    r"联系我们", r"加入我们", r"网站地图",
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

# ========== 5. 描述黑名单 ==========
DESC_JUNK_PATTERNS = [
    r"举报邮箱[:：]\s*\S+@\S+",
    r"^\s*chinaventure\.com\.cn\s*$",
    r"京公网安备\s*\d+号",
]

# ========== 6. 字符异常 ==========
GARBLED_RE = re.compile(r"[\u0400-\u04FF]{2,}|[\u0370-\u03FF]{2,}|йеъхцюѳ|цныфыч")
HTML_ENTITY_RE = re.compile(r"&#?\w+;|&\w+;")

# ========== 7. URL 研报检测 ==========
def is_research_report(url, title, source):
    """研报源需要 URL 或标题含研报关键词才放行"""
    if source not in RESEARCH_SOURCES:
        return True  # 非研报源,不在精过滤范围
    if not url:
        # 没 URL 但有标题,如果标题像研报也放行
        for kw in RESEARCH_REPORT_KEYWORDS:
            if re.search(kw, title or "", re.IGNORECASE):
                return True
        return False  # 没 URL 没关键词,删除
    # 有 URL,任一关键词命中即放行
    text = (url + " " + (title or "")).lower()
    for kw in RESEARCH_REPORT_KEYWORDS:
        if re.search(kw, text, re.IGNORECASE):
            return True
    return False

# ========== 8. 标题=描述 重复检测 ==========
def is_news_duplicate_title_desc(title, desc):
    if not title or not desc:
        return False
    t, d = title.strip(), desc.strip()
    if t == d:
        return True
    shorter, longer = (t, d) if len(t) < len(d) else (d, t)
    if shorter in longer and len(shorter) > 10:
        return True
    return False

# ========== 9. 主函数 ==========
def main():
    if not DATA.exists():
        print(f"  ❌ {DATA} 不存在")
        return
    d = json.loads(DATA.read_text(encoding="utf-8"))
    orig_n = len(d.get("stories", []))
    removed = {
        "整源黑名单": 0,
        "URL黑名单": 0,
        "研报源非研报": 0,
        "标题黑名单": 0,
        "描述黑名单": 0,
        "乱码": 0,
    }
    kept = []
    for s in d["stories"]:
        src = s.get("sourceLabel", "")
        title = s.get("title_zh", "") or s.get("title_en", "") or ""
        desc_zh = s.get("desc_full_zh", "") or s.get("desc_zh", "") or ""
        desc_en = s.get("desc_full_en", "") or s.get("desc_en", "") or ""
        url = s.get("url", "") or s.get("link", "") or ""

        # 1. 整源黑名单
        if src in SOURCE_BLACKLIST:
            removed["整源黑名单"] += 1
            continue

        # 2. URL 黑名单(所有源)
        is_junk_url = False
        for pat in URL_JUNK_PATTERNS:
            if re.search(pat, url, re.IGNORECASE):
                is_junk_url = True
                break
        if is_junk_url:
            removed["URL黑名单"] += 1
            continue

        # 3. 研报源非研报内容(精过滤)
        if not is_research_report(url, title, src):
            removed["研报源非研报"] += 1
            continue

        # 4. 标题黑名单
        is_junk_title = False
        for pat in TITLE_JUNK_PATTERNS:
            if re.search(pat, title, re.IGNORECASE):
                is_junk_title = True
                break
        if is_junk_title:
            removed["标题黑名单"] += 1
            continue

        # 5. 描述黑名单
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

        # 6. 乱码
        full_text = title + desc_zh + desc_en
        if GARBLED_RE.search(full_text):
            removed["乱码"] += 1
            continue

        # 7. HTML 实体解码
        mutated = False
        for field in ["title_zh", "title_en", "desc_zh", "desc_en",
                      "desc_full_zh", "desc_full_en"]:
            v = s.get(field, "")
            if v and HTML_ENTITY_RE.search(v):
                s[field] = html_mod.unescape(v)
                mutated = True

        # 8. 标题=描述 重复 → 标记
        if is_news_duplicate_title_desc(title, desc_zh) or is_news_duplicate_title_desc(title, desc_en):
            s["is_repeat_desc"] = True

        # 9. 真空卡片标记
        if not (desc_zh or desc_en) or all(len(d.strip()) < 20 for d in [desc_zh, desc_en] if d):
            s["is_empty"] = True

        kept.append(s)

    d["stories"] = kept
    d["stats"] = d.get("stats", {})
    d["stats"]["total"] = len(kept)
    DATA.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"原始 {orig_n} 条 → 保留 {len(kept)} 条")
    print("删除明细:")
    for k, v in removed.items():
        if v: print(f"  {k}: {v}")
    # 8 维验证
    garbled = sum(1 for s in kept
                  if GARBLED_RE.search((s.get("title_zh","") or "") + (s.get("title_en","") or "")))
    entity = sum(1 for s in kept
                 if any(HTML_ENTITY_RE.search(s.get(f,"") or "") for f in
                        ["title_zh","desc_zh","desc_full_zh","desc_en","desc_full_en"]))
    blank_src = sum(1 for s in kept if s.get("sourceLabel","") in SOURCE_BLACKLIST)
    no_desc = sum(1 for s in kept if s.get("is_empty"))
    repeat = sum(1 for s in kept if s.get("is_repeat_desc"))
    print("\n8 维验证(保留后):")
    print(f"  乱码: {garbled}")
    print(f"  HTML实体: {entity}")
    print(f"  黑名单源: {blank_src}")
    print(f"  真空卡片(标记): {no_desc}")
    print(f"  重复标题=描述(标记): {repeat}")
    # 研报源统计
    research_kept = sum(1 for s in kept if s.get("sourceLabel") in RESEARCH_SOURCES)
    print(f"  研报源保留: {research_kept}")

if __name__ == "__main__":
    main()
