"""
smart_summary.py — 路径 C 核心算法 (v2)
纯规则,无 LLM,0 成本
"""
import re
import html
import time
import urllib.request
import urllib.parse
import json as json_mod
from typing import List


META_KEYWORDS = [
    "免责声明", "Copyright", "All Rights Reserved", "©",
    "未经授权", "不得转载", "投稿邮箱", "联系作者",
    "本文约", "建议阅读", "作者\\s*\\|", "编辑\\s*\\|", "记者\\s*\\|",
    "微信扫一扫", "扫码关注", "关注我们", "联系我们",
    "Discover more", "Read more", "Continue reading",
    "Sign up", "Subscribe to", "Related articles",
    "编者按", "栏目聚焦", "专题为", "专题页面",
]

ACTION_WORDS_ZH = [
    "推出", "发布", "上线", "融资", "收购", "合作", "签约",
    "投资", "成立", "完成", "达到", "突破", "获", "拿到",
    "拿下", "达成", "落地", "上市", "首发", "披露",
]

ACTION_WORDS_EN = [
    "launched", "launches", "released", "unveiled", "introduces",
    "acquired", "acquires", "raised", "funding", "partners",
    "announces", "signed", "closes", "completes", "joins",
    "debuts", "introduces", "rolls out", "ships", "starts",
]

BIZ_WORDS = [
    "融资", "种子轮", "天使轮", "A轮", "B轮", "C轮", "估值", "市值",
    "营收", "净利润", "亏损", "收购", "并购", "投资", "退出", "回报",
    "Series A", "Series B", "IPO", "valuation", "raised",
    "acquired", "revenue", "profit", "loss", "merger",
]

WEAK_WORDS = [
    "可能", "或许", "或将", "预计", "认为", "觉得", "希望",
    "maybe", "perhaps", "could", "might", "may",
]

# 雷峰网"专题索引页"特征
INDEX_PAGE_PATTERNS = [
    r"本专题为.+的.+专题",
    r"专题内容全部来自",
    r"在这里你能看到",
    r"读懂智能与未来",
    r"看未来的世界",
]


def is_index_page(text: str) -> bool:
    """判断是否是专题索引页(非新闻)"""
    hits = sum(1 for p in INDEX_PAGE_PATTERNS if re.search(p, text))
    return hits >= 1


def is_meta_text(text: str) -> bool:
    for kw in META_KEYWORDS:
        if re.search(kw, text):
            return True
    return False


def split_paragraphs(text: str) -> List[str]:
    if not text:
        return []
    paras = re.split(r"\n+", text)
    result = []
    for p in paras:
        p = p.strip()
        if not p or len(p) < 20:
            continue
        if is_meta_text(p):
            continue
        result.append(p)
    return result


def split_sentences(paragraph: str) -> List[str]:
    pattern = r"(?<=[.!?。！？])\s+|(?<=[.!?。！？])(?=[A-Z一-鿿])"
    sents = re.split(pattern, paragraph)
    return [s.strip() for s in sents if s.strip() and len(s.strip()) > 15]


def score_sentence(sent: str, position: int, total: int) -> float:
    score = 0.0
    s_lower = sent.lower()

    # 数字
    numbers = re.findall(r"\d+(?:\.\d+)?%?|[一二三四五六七八九十百千万亿]+", sent)
    score += min(len(numbers) * 1.5, 4.0)

    # 动作
    for w in ACTION_WORDS_ZH + ACTION_WORDS_EN:
        if w in sent or w.lower() in s_lower:
            score += 1.0
            break

    # 商业
    for w in BIZ_WORDS:
        if w in sent or w.lower() in s_lower:
            score += 1.5
            break

    # 实体
    caps = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b", sent)
    score += min(len(caps) * 0.8, 2.0)

    # 弱信号
    for w in WEAK_WORDS:
        if w in sent or w.lower() in s_lower:
            score -= 0.5
            break

    # 长度
    slen = len(sent)
    if 25 <= slen <= 120:
        score += 1.0
    elif 120 < slen <= 200:
        score += 0.3
    elif slen < 20 or slen > 250:
        score -= 0.5

    # 位置
    if total > 0:
        pos_ratio = position / total
        if pos_ratio < 0.3:
            score += 1.0
        elif pos_ratio < 0.6:
            score += 0.3

    return score


def smart_summary(text: str, target_sentences: int = 3, max_chars: int = 280) -> str:
    if not text or len(text) < 30:
        return ""

    paragraphs = split_paragraphs(text)
    if not paragraphs:
        return ""

    all_sents = []
    for p_idx, p in enumerate(paragraphs[:5]):
        sents = split_sentences(p)
        for s_idx, s in enumerate(sents):
            score = score_sentence(s, s_idx, len(sents))
            all_sents.append((s, p_idx, s_idx, score))

    if not all_sents:
        return ""

    all_sents.sort(key=lambda x: -x[3])
    top = all_sents[:target_sentences * 2]

    top.sort(key=lambda x: (x[1], x[2]))

    seen = set()
    final = []
    total_len = 0
    for s, p_idx, s_idx, score in top:
        prefix = s[:20]
        if prefix in seen:
            continue
        seen.add(prefix)
        final.append(s)
        total_len += len(s)
        if len(final) >= target_sentences or total_len >= max_chars:
            break

    if not final:
        return ""

    summary = "。".join(final)
    if not summary.endswith(("。", ".", "!", "?", "！", "？")):
        summary += "。"
    return summary


# 翻译缓存(同 URL 不会重复翻译)
_translation_cache = {}


def translate_to_zh(text: str, retries: int = 2) -> str:
    """
    MyMemory 免费翻译,带缓存+重试+截断
    """
    if not text or not re.search(r"[a-zA-Z]", text):
        return text

    cache_key = text[:100]
    if cache_key in _translation_cache:
        return _translation_cache[cache_key]

    # 截断到 480 字符(API 限制 500)
    payload = text[:480]
    if len(text) > 480:
        payload += "..."

    for attempt in range(retries):
        try:
            url = "https://api.mymemory.translated.net/get?" + urllib.parse.urlencode({
                "q": payload,
                "langpair": "en|zh-CN",
            })
            req = urllib.request.Request(url, headers={"User-Agent": "aily-bot/1.0"})
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json_mod.loads(r.read())
                translated = data.get("responseData", {}).get("translatedText", "")
                if translated and translated.lower() != text.lower():
                    result = html.unescape(translated)
                    _translation_cache[cache_key] = result
                    time.sleep(0.3)  # 限速
                    return result
        except Exception:
            time.sleep(0.5)
            continue

    # 失败 fallback
    _translation_cache[cache_key] = text
    return text


if __name__ == "__main__":
    test1 = """36氪获悉,开普动能航空技术有限责任公司近期连续完成种子轮及天使轮融资,两轮融资合计金额达数千万元人民币,由零以资本领投,新鼎资本跟投。

    开普动能成立于2024年,核心团队来自西门子、罗罗等国际航空企业,专注于 eVTOL 航空电驱系统的研发与制造。

    免责声明:本文不构成投资建议。本文约3000字,建议阅读6分钟。"""
    print("=" * 60)
    print("测试 1: 中文 36氪")
    print("=" * 60)
    print(smart_summary(test1))

    test2 = """An AI agent carried out the technical execution of a real-world ransomware attack for the first known time, but new details show a human still chose the victim, set up the infrastructure, and supplied stolen credentials—meaning this isn't the fully autonomous cybercrime debut it was hyped as last week.

    Anthropic's Threat Intelligence Report revealed the agent performed technical steps like selecting tools and writing ransom notes, while a human operator made every consequential decision."""
    print("\n" + "=" * 60)
    print("测试 2: 英文 TechCrunch")
    print("=" * 60)
    trans = translate_to_zh(test2)
    print(f"[翻译后]: {trans[:300]}")
    print(f"\n[摘要]: {smart_summary(trans)}")
