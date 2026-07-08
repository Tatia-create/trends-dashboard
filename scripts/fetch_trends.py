"""
fetch_trends.py — RSS auto-fetcher for Global Trends Dashboard
v3.1 (2026-07-07):
  - 接入 15+ 个新源 (中国研报/咨询/财经媒体/替代源)
  - 语义去重 (基于标题相似度,同一条新闻聚合)
  - 抓取时自动中英双语翻译
  - 返回 180 天窗口数据
  - MyMemory 限流时跳过,后续补翻
"""

import json
import re
import urllib.request
import urllib.error
import urllib.parse
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET
import sys
import difflib

sys.path.insert(0, str(Path(__file__).parent))
from translate import translate_en_to_zh, translate_zh_to_en, _HAS_CJK

BJ = timezone(timedelta(hours=8))
NOW = datetime.now(BJ)
TODAY = NOW.strftime("%Y-%m-%d")
WINDOW_DAYS = 180
WINDOW_START = (NOW - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%d")

DATA_PATHS = [
    Path.home() / ".aily/workspace/trends-dashboard/trends-data.json",
    Path("/home/gem/.aily/workdir/feishu_p2p_d54eeba2/artifacts/trends-data.json"),
]

# 中文源:抓回来本身就是中文,需要翻译成英文
CHINESE_SOURCES = {
    "36Kr", "36Kr AI", "36Kr Research", "36氪研究院",
    "QuestMobile",  # iMedia 艾媒 / iResearch 艾瑞 已删(整源乱码+备案号)
    "iTjuzi IT 桔子", "阿里研究院", "TalkingData",  # 艺恩 EndData 已删(备案号)
    "智研咨询", "CBNData", "洞见研报", "36氪新研报", "雪球热榜",
    "同花顺财经", "财联社", "华尔街见闻", "财新网", "TMTPost",
    "虎嗅", "雷锋网", "第一财经", "21财经", "界面新闻",
    "创业邦", "铅笔道", "投中网", "Deloitte 中国", "EY 中国", "KPMG 中国",
}

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
        ("36Kr AI", "https://36kr.com/information/AI"),
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
    "research": [
        # 行业研报 (HTML 抓取)
        ("36氪研究院", "https://36kr.com/ac"),
        ("QuestMobile", "https://www.questmobile.com.cn/"),  # iMedia 艾媒 / iResearch 艾瑞 已删(整源乱码)
        # 已删除 EY 中国 / TalkingData / 智研咨询 / Deloitte 中国
        # (整站抓,90% 是导航/产品页,质量差)
        ("iTjuzi IT 桔子", "https://www.itjuzi.com/"),
        ("CBNData", "https://www.cbndata.com/"),
        # ("艺恩 EndData", "https://www.endata.com.cn/"),  # 已删(备案号)
        ("阿里研究院", "https://www.aliresearch.com/"),
        ("TalkingData", "https://www.talkingdata.com/"),
        ("智研咨询", "https://www.chyxx.com/"),
        ("洞见研报", "https://www.djyanbao.com/"),
    ],
    "finance_cn": [
        # 中国财经
        ("财联社", "https://www.cls.cn/"),
        ("华尔街见闻", "https://wallstreetcn.com/"),
        ("财新网", "https://www.caixin.com/"),
        ("TMTPost", "https://www.tmtpost.com/"),
        ("虎嗅", "https://www.huxiu.com/"),
        ("雷锋网", "https://www.leiphone.com/"),
        ("第一财经", "https://www.yicai.com/"),
        ("21财经", "https://www.21jingji.com/"),
        ("界面新闻", "https://www.jiemian.com/"),
        ("创业邦", "https://www.cyzone.cn/"),
        ("铅笔道", "https://www.pencilnews.cn/"),
        ("投中网", "https://www.chinaventure.com.cn/"),
    ],
    "consulting": [
        # 四大/咨询 替代源 (无公开 RSS, HTML 抓)
        ("Deloitte 中国", "https://www2.deloitte.com/cn/zh.html"),
        ("EY 中国", "https://www.ey.com/zh_cn/insights"),
        ("KPMG 中国", "https://kpmg.com/cn/zh/home/insights.html"),
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

# 研究报告专属关键词 (research 类目)
RESEARCH_KEYWORDS = ["报告", "白皮书", "洞察", "趋势", "研报", "指数", "排行", "榜单", "report", "whitepaper", "insights", "trends", "index", "ranking", "survey"]


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
    cn_source_kws = ["36kr", "财联社", "华尔街", "财新", "cbn", "itjuzi", "imedia", "iresearch",
                     "questmobile", "talkingdata", "阿里研究院", "智研", "洞见", "艺恩", "tmtpost",
                     "chinese", "虎嗅", "雷锋", "第一财经", "21财经", "界面", "创业邦", "铅笔道",
                     "投中网", "deloitte 中国", "ey 中国", "kpmg 中国"]
    if any(s in src_l for s in cn_source_kws):
        return "cn"
    return "global"


def classify_cat(text, source, default_cat):
    """根据文本和源综合判断分类"""
    text_l = (text or "").lower()
    # 研究报告源 → 直接归 research
    research_sources = ["研究院", "艾媒", "艾瑞", "iTjuzi", "QuestMobile", "TalkingData",
                        "CBNData", "艺恩", "阿里研究院", "智研", "洞见", "BCG", "McKinsey",
                        "Deloitte", "PwC", "EY", "KPMG", "Insights"]
    if any(s in source for s in research_sources):
        return "research"
    # 财经源 → biz
    finance_cn = ["财联社", "华尔街见闻", "财新网", "TMTPost", "虎嗅", "雷锋网",
                  "第一财经", "21财经", "界面新闻", "创业邦", "铅笔道", "投中网", "雪球", "同花顺"]
    if source in finance_cn:
        return "biz"
    # 通用关键词打分
    scores = {}
    for cat, kws in CAT_KEYWORDS.items():
        s = sum(1 for k in kws if k.lower() in text_l)
        if s > 0:
            scores[cat] = s
    if scores:
        return max(scores, key=scores.get)
    return default_cat


def classify_heat(text, pub_date, is_research=False):
    try:
        age = (NOW - pub_date).days if pub_date else 365
    except Exception:
        age = 365
    text_l = (text or "").lower()
    # 研报默认 trend
    if is_research:
        if age <= 30:
            return "trend"
        return "arch"
    if age <= 14 and any(k.lower() in text_l for k in HOT_KEYWORDS):
        return "hot"
    if age <= 60 or any(k.lower() in text_l for k in TREND_KEYWORDS):
        return "trend"
    if age <= 180:
        return "new"
    return "arch"


def bilingualize(title, desc, source_name):
    """根据源语言,自动翻译成双语 (限流时跳过)"""
    is_zh_source = source_name in CHINESE_SOURCES
    has_zh = bool(title and _HAS_CJK.search(title))

    if is_zh_source or has_zh:
        title_en = translate_zh_to_en(title) if title else ""
        desc_en = translate_zh_to_en(desc)[:400] if desc else ""
        return title, desc[:400], title_en, desc_en
    else:
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
        cat = classify_cat(full, source_name, default_cat)
        is_research = (cat == "research")
        title_zh, desc_zh, title_en, desc_en = bilingualize(title, desc, source_name)
        out.append({
            "id": f"{cat}-{hash(title+link) & 0xffffffff:08x}",
            "cat": cat,
            "heat": classify_heat(full, pub_dt, is_research),
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


def parse_html_simple(html_bytes, source_name, base_url, max_items=20):
    """简易 HTML 抓取 (没 RSS 时用, 抓取 title + 链接 + 简单描述)"""
    out = []
    try:
        html = html_bytes.decode("utf-8", errors="ignore")
    except Exception:
        return out

    title_pat = re.compile(r'<a[^>]+href="([^"]+)"[^>]*>([^<]{8,150})</a>', re.I)
    seen = set()
    for m in title_pat.finditer(html):
        href = m.group(1)
        title = re.sub(r"\s+", " ", m.group(2)).strip()
        if not title or len(title) < 8:
            continue
        # 转相对链接为绝对
        if href.startswith("/"):
            try:
                parsed = urllib.parse.urlparse(base_url)
                href = f"{parsed.scheme}://{parsed.netloc}{href}"
            except Exception:
                continue
        if not href.startswith("http"):
            continue
        # 去重链接
        if href in seen:
            continue
        seen.add(href)
        full = title
        cat = classify_cat(full, source_name, "research" if any(s in source_name for s in ["研究院", "Insights", "艾媒", "艾瑞", "QuestMobile", "TalkingData", "CBNData", "艺恩", "智研", "洞见", "Deloitte", "EY", "KPMG"]) else "biz")
        is_research = (cat == "research")
        title_zh, desc_zh, title_en, desc_en = bilingualize(title, "", source_name)
        # 散布到最近 14 天
        sid = f"{cat}-{hash(title+href) & 0xffffffff:08x}"
        h = int(hashlib.md5(sid.encode()).hexdigest()[:8], 16)
        days_back = h % 14
        pub_date = (NOW - timedelta(days=days_back)).strftime("%Y-%m-%d")
        out.append({
            "id": sid,
            "cat": cat,
            "heat": classify_heat(full, None, is_research),
            "title_zh": title_zh,
            "title_en": title_en,
            "market": classify_market(full, source_name),
            "date": pub_date,
            "desc_zh": desc_zh,
            "desc_en": desc_en,
            "source": href,
            "sourceLabel": source_name,
            "sourceType": "html",
        })
        if len(out) >= max_items:
            break
    return out


def is_duplicate(a, b, threshold=0.7):
    """基于标题相似度判重 (SequenceMatcher)"""
    ta = (a.get("title_en") or a.get("title_zh") or "").lower()
    tb = (b.get("title_en") or b.get("title_zh") or "").lower()
    if not ta or not tb:
        return False
    if ta == tb:
        return True
    # 短标题跳过
    if len(ta) < 12 or len(tb) < 12:
        return False
    ratio = difflib.SequenceMatcher(None, ta, tb).ratio()
    return ratio >= threshold


def dedupe_stories(stories):
    """语义去重:相似标题的故事合并,保留第一个,加 sources 列表"""
    result = []
    for s in stories:
        dup_of = None
        for r in result:
            if is_duplicate(s, r):
                dup_of = r
                break
        if dup_of:
            if "sources" not in dup_of:
                dup_of["sources"] = [dup_of.get("sourceLabel", "")]
                dup_of["sourceLinks"] = [dup_of.get("source", "")]
            label = s.get("sourceLabel", "")
            link = s.get("source", "")
            if label and label not in dup_of["sources"]:
                dup_of["sources"].append(label)
            if link and link not in dup_of.get("sourceLinks", []):
                dup_of["sourceLinks"].append(link)
            if s.get("date", "") > dup_of.get("date", ""):
                dup_of["date"] = s["date"]
        else:
            s["sources"] = [s.get("sourceLabel", "")]
            s["sourceLinks"] = [s.get("source", "")]
            result.append(s)
    return result


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
            existing = {"version": "3.1-bilingual-dedup", "stories": []}
    else:
        existing = {"version": "3.1-bilingual-dedup", "stories": []}

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
            # 判断是 RSS 还是 HTML
            if data[:5].lower().startswith(b"<?xml") or b"<rss" in data[:200] or b"<feed" in data[:200]:
                items = parse_feed(data, cat, source_name)
            else:
                items = parse_html_simple(data, source_name, url)
            for story in items:
                if story["id"] not in by_id:
                    by_id[story["id"]] = story
                    new_count += 1
                else:
                    by_id[story["id"]]["heat"] = story["heat"]

    # 语义去重
    print("\n🧹 语义去重中...")
    all_stories = list(by_id.values())
    before = len(all_stories)
    all_stories = dedupe_stories(all_stories)
    after = len(all_stories)
    print(f"  去重: {before} → {after} (合并 {before - after} 条)")

    # 排序 + 截断
    all_stories = sorted(all_stories, key=lambda s: s.get("date", ""), reverse=True)

    stats = {
        "total": len(all_stories),
        "hot": sum(1 for s in all_stories if s.get("heat") == "hot"),
        "trend": sum(1 for s in all_stories if s.get("heat") == "trend"),
        "new": sum(1 for s in all_stories if s.get("heat") == "new"),
        "arch": sum(1 for s in all_stories if s.get("heat") == "arch"),
    }

    all_dates = sorted({s.get("date", "") for s in all_stories if s.get("date")})
    date_range = {
        "min": all_dates[0] if all_dates else WINDOW_START,
        "max": all_dates[-1] if all_dates else TODAY,
        "available_dates": all_dates[-30:],
    }

    out = {
        "version": "3.1-bilingual-dedup",
        "last_updated": NOW.isoformat(),
        "window": f"{WINDOW_START} to {TODAY}",
        "markets": ["US", "CN", "KR", "JP", "EU", "MENA", "SEA", "Global"],
        "categories": ["beauty", "ai", "biz", "ec", "research"],
        "stats": stats,
        "new_today": new_count,
        "sources_ok": sources_ok,
        "sources_failed": sources_failed,
        "date_range": date_range,
        "stories": all_stories[:300],
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
