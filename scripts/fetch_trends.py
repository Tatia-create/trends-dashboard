"""
fetch_trends.py — RSS auto-fetcher for Global Trends Dashboard
v2.2: 抓取后自动中英双语翻译
"""

import json
import re
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET
import sys

sys.path.insert(0, str(Path(__file__).parent))
from translate import translate_en_to_zh, translate_zh_to_en, _HAS_CJK

BJ = timezone(timedelta(hours=8))
NOW = datetime.now(BJ)
TODAY = NOW.strftime("%Y-%m-%d")
WINDOW_START = (NOW - timedelta(days=180)).strftime("%Y-%m-%d")

DATA_PATHS = [
    Path.home() / ".aily/workspace/trends-dashboard/trends-data.json",
    Path("/home/gem/.aily/workdir/feishu_p2p_d54eeba2/artifacts/trends-data.json"),
]

# 中文源:抓回来本身就是中文,需要翻译成英文
CHINESE_SOURCES = {"36Kr", "36Kr AI", "36氪"}

SOURCES = {
    "beauty": [
        ("Glossy", "https://www.glossy.co/beauty/feed/"),
        ("Allure", "https://www.allure.com/feed/rss"),
        ("WWD Beauty", "https://wwd.com/beauty-industry-news/feed/"),
        ("Byrdie", "https://www.byrdie.com/rss"),
        ("Cosmetics Business", "https://www.cosmeticsbusiness.com/rss"),
    ],
    "ai": [
        ("TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/"),
        ("The Verge AI", "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml"),
        ("VentureBeat AI", "https://venturebeat.com/category/ai/feed/"),
        ("36Kr AI", "https://36kr.com/feed"),
        ("CB Insights", "https://www.cbinsights.com/research/feed/"),
    ],
    "biz": [
        ("Crunchbase", "https://news.crunchbase.com/feed/"),
        ("PitchBook News", "https://pitchbook.com/news/feed"),
        ("36Kr", "https://36kr.com/feed"),
        ("Bloomberg Tech", "https://feeds.bloomberg.com/technology/news.rss"),
    ],
    "ec": [
        ("Modern Retail", "https://www.modernretail.co/feed/"),
        ("Retail Brew", "https://www.retailbrew.com/feed"),
        ("Practical Ecommerce", "https://www.practicalecommerce.com/feed"),
        ("Digital Commerce 360", "https://www.digitalcommerce360.com/feed/"),
    ],
}

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
}

def fetch(url, timeout=10):
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        })
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, Exception) as e:
        print(f"  [skip] {url}: {type(e).__name__}: {e}")
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

def bilingualize(title, desc, source_name):
    """根据源语言,自动翻译成双语"""
    is_zh_source = source_name in CHINESE_SOURCES
    has_zh = bool(title and _HAS_CJK.search(title))
    has_zh_desc = bool(desc and _HAS_CJK.search(desc))

    if is_zh_source or has_zh:
        # 原文是中文,翻译成英文
        title_en = translate_zh_to_en(title) if title else ""
        desc_en = translate_zh_to_en(desc)[:400] if desc else ""
        return title, desc[:400], title_en, desc_en
    else:
        # 原文是英文,翻译成中文
        title_zh = translate_en_to_zh(title) if title else ""
        desc_zh = translate_en_to_zh(desc)[:400] if desc else ""
        return title_zh, desc_zh, title, desc[:400]

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
            from email.utils import parsedate_to_datetime
            pub_dt = parsedate_to_datetime(pub).astimezone(BJ) if pub else None
        except Exception:
            pub_dt = None
        if not title or not link:
            continue
        if pub_dt and pub_dt.strftime("%Y-%m-%d") < WINDOW_START:
            continue
        full = f"{title}. {desc}"
        # v2.2: 自动双语
        title_zh, desc_zh, title_en, desc_en = bilingualize(title, desc, source_name)
        out.append({
            "id": f"{default_cat}-{hash(title+link) & 0xffffffff:08x}",
            "cat": classify_cat(full, source_name),
            "heat": classify_heat(full, pub_dt),
            "title_zh": title_zh,
            "title_en": title_en,
            "market": classify_market(full, source_name),
            "date": pub_dt.strftime("%Y-%m-%d") if pub_dt else TODAY,
            "desc_zh": desc_zh,
            "desc_en": desc_en,
            "source": link,
            "sourceLabel": source_name,
            "sourceType": "rss",
        })
    return out

def main():
    data_path = None
    for p in DATA_PATHS:
        if p.exists():
            data_path = p
            break
    if not data_path:
        data_path = DATA_PATHS[0]

    if data_path.exists():
        try:
            existing = json.loads(data_path.read_text(encoding="utf-8"))
            print(f"Loaded existing {len(existing.get('stories', []))} stories from {data_path}")
        except Exception:
            existing = {"version": "2.2-bilingual", "stories": []}
    else:
        existing = {"version": "2.2-bilingual", "stories": []}

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
        "version": "2.2-bilingual",
        "last_updated": NOW.isoformat(),
        "window": f"{WINDOW_START} to {TODAY}",
        "markets": ["US", "CN", "KR", "JP", "EU", "MENA", "SEA", "Global"],
        "categories": ["beauty", "ai", "biz", "ec"],
        "stats": stats,
        "new_today": new_count,
        "sources_ok": sources_ok,
        "sources_failed": sources_failed,
        "stories": all_stories[:200],
        "rss_sources": {cat: [u for _, u in v] for cat, v in SOURCES.items()},
    }

    written = []
    for p in DATA_PATHS:
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
            written.append(str(p))
        except Exception as e:
            print(f"  [write fail] {p}: {e}")
    print(f"\n✅ Saved {len(all_stories)} stories ({new_count} new) — Stats: {stats}")
    print(f"Sources: {sources_ok} ok / {sources_failed} failed")
    print(f"Written to: {written}")

if __name__ == "__main__":
    main()
