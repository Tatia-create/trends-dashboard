"""
fetch_trends.py — 全球趋势 RSS 自动抓取 v3.0
==================================================
覆盖行业: 美妆/AI/电商/投融资/移动/研报/快消
30+ 个公开 RSS 源, 容错降级: 源失败不阻断其他源
产出: trends-data.json
"""

import json
import re
import urllib.request
import urllib.error
import socket
from datetime import datetime, timezone, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET
from email.utils import parsedate_to_datetime

BJ = timezone(timedelta(hours=8))
NOW = datetime.now(BJ)
TODAY = NOW.strftime("%Y-%m-%d")
WINDOW_START = (NOW - timedelta(days=180)).strftime("%Y-%m-%d")

DATA_PATH = Path("trends-data.json")

# ============================================================
# SOURCES — 30+ 公开 RSS, 按行业分组
# ============================================================
SOURCES = {
    # ============ 美妆 / 时尚 ============
    "beauty": [
        ("Glossy", "https://www.glossy.co/beauty/feed/"),
        ("Allure", "https://www.allure.com/feed/rss"),
        ("WWD Beauty", "https://wwd.com/beauty-industry-news/feed/"),
        ("Byrdie", "https://www.byrdie.com/rss"),
        ("Cosmetics Business", "https://www.cosmeticsbusiness.com/rss"),
        ("Beauty Independent", "https://www.beautyindependent.com/feed/"),
    ],
    # ============ AI / 科技 ============
    "ai": [
        ("TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/"),
        ("The Verge AI", "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml"),
        ("VentureBeat AI", "https://venturebeat.com/category/ai/feed/"),
        ("CB Insights", "https://www.cbinsights.com/research/feed/"),
        ("MIT Tech Review", "https://www.technologyreview.com/feed/"),
        ("36Kr AI", "https://36kr.com/feed"),
    ],
    # ============ 投融资 / 商业 ============
    "biz": [
        ("Crunchbase", "https://news.crunchbase.com/feed/"),
        ("PitchBook News", "https://pitchbook.com/news/feed"),
        ("36Kr", "https://36kr.com/feed"),
        ("Bloomberg Tech", "https://feeds.bloomberg.com/technology/news.rss"),
        ("Hacker News Front", "https://hnrss.org/frontpage"),
        ("IT 桔子", "https://www.itjuzi.com/rss"),
    ],
    # ============ 电商 / 零售 ============
    "ec": [
        ("Modern Retail", "https://www.modernretail.co/feed/"),
        ("Retail Brew", "https://www.retailbrew.com/feed"),
        ("Practical Ecommerce", "https://www.practicalecommerce.com/feed"),
        ("Digital Commerce 360", "https://www.digitalcommerce360.com/feed/"),
        ("eMarketer", "https://www.emarketer.com/content/feeds/latest.rss"),
    ],
    # ============ 研报 / 行业洞察 ============
    "research": [
        ("艾瑞咨询", "https://www.iresearch.cn/portal/rss"),
        ("阿里研究院", "https://www.aliresearch.com/rss"),
        ("QuestMobile", "https://www.questmobile.com.cn/research/feed"),
        ("CBN Data", "https://www.cbndata.com/feed"),
        ("TalkingData", "https://www.talkingdata.com/blog/feed"),
        ("艺恩", "https://www.endata.com.cn/feed"),
    ],
    # ============ 移动 / 消费 ============
    "mobile": [
        ("36氪研究院", "https://36kr.com/feed"),
        ("36氪开氪", "https://36kr.com/feed"),
        ("智研咨询", "https://www.chyxx.com/feed"),
    ],
}

# ============================================================
# CLASSIFICATION KEYWORDS
# ============================================================
HOT_KEYWORDS = [
    "launch", "launches", "launching", "ipo", "debut", "raises",
    "files for", "billion", "acquires", "acquired", "merger", "megadeal",
    "破", "上市", "首发", "首店", "发布", "推出", "重磅", "融资", "亿",
]
TREND_KEYWORDS = [
    "funding", "partnership", "expansion", "expands", "growing", "growth",
    "valued at", "valuation", "investment", "secures",
    "合作", "增长", "扩张", "升级", "发布", "推出",
]

MARKET_KEYWORDS = {
    "us": ["US", "U.S.", "America", "American", "United States", "美国", "北美", "NYC", "Silicon Valley", "San Francisco", "Sephora", "Ulta"],
    "cn": ["China", "Chinese", "China-based", "中国", "国内", "上海", "Beijing", "Hangzhou", "深圳", "广州", "抖音", "快手", "小红书", "天猫", "京东", "完美日记", "花西子"],
    "kr": ["Korea", "Korean", "K-beauty", "Seoul", "韩国", "首尔", "COSRX", "Sulwhasoo", "Innisfree", "Amorepacific", "雪花秀"],
    "jp": ["Japan", "Japanese", "Tokyo", "日本", "东京", "Shiseido", "资生堂", "SK-II", "SKII"],
    "eu": ["UK", "U.K.", "Britain", "Europe", "European", "EU", "Paris", "London", "Milan", "英国", "欧洲", "巴黎", "米兰", "德国", "France", "Germany"],
    "ae": ["UAE", "Dubai", "MENA", "Saudi", "海湾", "迪拜", "中东"],
    "sea": ["Southeast Asia", "Singapore", "Indonesia", "Thailand", "TikTok Shop", "Shopee", "Lazada", "东南亚"],
    "global": ["global", "worldwide", "全球", "world", "international"],
}

CAT_KEYWORDS = {
    "beauty": ["beauty", "skincare", "cosmetics", "makeup", "fragrance", "护肤", "美妆", "化妆品", "品牌", "Sephora", "Ulta", "shade", "ingredient", "retinol", "serum"],
    "ai": ["AI", "artificial intelligence", "model", "LLM", "GPT", "Claude", "Gemini", "openai", "anthropic", "deepmind", "neural", "machine learning", "大模型", "人工智能", "智能"],
    "biz": ["raises", "funding", "IPO", "valuation", "billion", "VC", "venture", "investment", "融资", "估值", "上市", "投资", "收购"],
    "ec": ["shopify", "amazon", "tiktok shop", "ecommerce", "e-commerce", "DTC", "retail", "store", "sales", "commerce", "店铺", "电商", "零售", "铺货"],
    "research": ["report", "research", "study", "whitepaper", "report", "研报", "报告", "研究", "白皮书", "洞察"],
    "mobile": ["mobile", "app", "android", "ios", "用户", "MAU", "DAU", "活跃", "渗透率"],
}

# ============================================================
# HELPERS
# ============================================================
def fetch(url, timeout=10):
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        })
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, socket.timeout, Exception) as e:
        print(f"  [skip] {url}: {type(e).__name__}")
        return None

def strip_html(s):
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:500]

def classify_market(text, source):
    text_l = (text or "").lower()
    for market in ["us", "cn", "kr", "jp", "eu", "ae", "sea"]:
        for kw in MARKET_KEYWORDS[market]:
            if kw.lower() in text_l:
                return market
    src_l = (source or "").lower()
    if "36kr" in src_l or "chinese" in src_l:
        return "cn"
    return "global"

def classify_cat(text, source):
    text_l = (text or "").lower()
    scores = {}
    for cat, kws in CAT_KEYWORDS.items():
        s = sum(1 for k in kws if k.lower() in text_l)
        if s > 0:
            scores[cat] = s
    if scores:
        return max(scores, key=scores.get)
    return "biz"

def classify_heat(text, pub_date):
    try:
        age = (NOW - pub_date).days if pub_date else 365
    except Exception:
        age = 365
    text_l = (text or "").lower()
    if age <= 14 and any(k.lower() in text_l for k in HOT_KEYWORDS):
        return "hot"
    if age <= 60 or any(k.lower() in text_l for k in TREND_KEYWORDS):
        return "trend"
    if age <= 180:
        return "new"
    return "arch"

def parse_feed(xml_bytes, default_cat, source_name):
    out = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return out
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    items = root.findall(".//item") or root.findall(".//atom:entry", ns)
    for it in items[:15]:
        title = strip_html(it.findtext("title") or it.findtext("atom:title", "", ns))
        desc = strip_html(it.findtext("description") or it.findtext("atom:summary", "", ns) or it.findtext("atom:content", "", ns))
        link = (it.findtext("link") or "").strip()
        if not link:
            l = it.find("atom:link", ns)
            link = l.get("href", "") if l is not None else ""
        pub = it.findtext("pubDate") or it.findtext("atom:published", "", ns) or ""
        try:
            pub_dt = parsedate_to_datetime(pub).astimezone(BJ) if pub else None
        except Exception:
            pub_dt = None
        if not title or not link:
            continue
        if pub_dt and pub_dt.strftime("%Y-%m-%d") < WINDOW_START:
            continue
        full = f"{title}. {desc}"
        out.append({
            "id": f"{default_cat}-{hash(title+link) & 0xffffffff:08x}",
            "cat": classify_cat(full, source_name),
            "heat": classify_heat(full, pub_dt),
            "title_zh": title,
            "title_en": title,
            "market": classify_market(full, source_name),
            "date": pub_dt.strftime("%Y-%m-%d") if pub_dt else TODAY,
            "desc_zh": desc[:300],
            "desc_en": desc[:300],
            "source": link,
            "sourceLabel": source_name,
            "sourceType": "rss",
        })
    return out

# ============================================================
# MAIN
# ============================================================
def main():
    if DATA_PATH.exists():
        try:
            existing = json.loads(DATA_PATH.read_text(encoding="utf-8"))
            print(f"Loaded existing {len(existing.get('stories', []))} stories")
        except Exception:
            existing = {"version": "3.0", "stories": []}
    else:
        existing = {"version": "3.0", "stories": []}

    by_id = {s.get("id"): s for s in existing.get("stories", []) if s.get("id")}
    new_count = 0
    sources_ok = 0
    sources_failed = 0

    for cat, sources in SOURCES.items():
        for source_name, url in sources:
            print(f"Fetching {source_name}...")
            data = fetch(url)
            if not data:
                sources_failed += 1
                continue
            sources_ok += 1
            for story in parse_feed(data, cat, source_name):
                if story["id"] not in by_id:
                    by_id[story["id"]] = story
                    new_count += 1
                else:
                    by_id[story["id"]]["heat"] = story["heat"]

    all_stories = sorted(by_id.values(), key=lambda s: s.get("date", ""), reverse=True)

    stats = {
        "total": len(all_stories),
        "hot": sum(1 for s in all_stories if s.get("heat") == "hot"),
        "trend": sum(1 for s in all_stories if s.get("heat") == "trend"),
        "new": sum(1 for s in all_stories if s.get("heat") == "new"),
        "arch": sum(1 for s in all_stories if s.get("heat") == "arch"),
    }

    out = {
        "version": "3.0",
        "last_updated": NOW.isoformat(),
        "window": f"{WINDOW_START} to {TODAY}",
        "markets": ["US", "CN", "KR", "JP", "EU", "MENA", "SEA", "Global"],
        "categories": ["beauty", "ai", "biz", "ec", "research", "mobile"],
        "stats": stats,
        "new_today": new_count,
        "sources_ok": sources_ok,
        "sources_failed": sources_failed,
        "stories": all_stories[:300],
        "rss_sources": {cat: [u for _, u in v] for cat, v in SOURCES.items()},
    }

    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ Saved {len(all_stories)} stories ({new_count} new) — Stats: {stats}")
    print(f"Sources: {sources_ok} ok / {sources_failed} failed")

if __name__ == "__main__":
    main()
