"""
translate.py — 轻量级翻译层 (MyMemory API)
免费匿名额度 5000 词/天,自动节流 + 跳过缓存。
用法:
    from translate import translate_en_to_zh, translate_zh_to_en
    zh = translate_en_to_zh("Some English text")
    en = translate_zh_to_en("一些中文")
"""
import time
import json
import re
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path
from datetime import datetime, timezone, timedelta

BJ = timezone(timedelta(hours=8))
CACHE_FILE = Path.home() / ".aily/workspace/trends-dashboard/.translate_cache.json"

# 中文标点 + 中文字符
_HAS_CJK = re.compile(r'[\u4e00-\u9fff]')

def _load_cache():
    try:
        if CACHE_FILE.exists():
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}

def _save_cache(cache):
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[translate] cache save failed: {e}")

CACHE = _load_cache()

def _call_mymemory(text: str, target: str) -> str | None:
    """单次调用 MyMemory,失败返回 None"""
    if not text or not text.strip():
        return ""
    try:
        url = "https://api.mymemory.translated.net/get?" + urllib.parse.urlencode({
            "q": text[:500],  # 单次限 500 字符
            "langpair": f"en|{target}" if target.startswith("zh") else f"{target}|en",
        })
        req = urllib.request.Request(url, headers={"User-Agent": "aily-trends-bot/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
            if data.get("responseStatus") == 200:
                translated = data.get("responseData", {}).get("translatedText", "").strip()
                # MyMemory 偶尔返回 WARNING 信息,过滤
                if "MYMEMORY WARNING" in translated or "PLEASE SELECT" in translated:
                    return None
                return translated
    except Exception as e:
        print(f"[translate] mymemory error: {e}")
    return None

def _translate(text: str, source: str, target: str) -> str:
    """source/target 均为 'en' 或 'zh-CN'"""
    if not text or not text.strip():
        return text or ""
    # 已是目标语言 → 跳过
    if target.startswith("zh") and _HAS_CJK.search(text):
        return text
    if target == "en" and not _HAS_CJK.search(text):
        return text
    # 缓存命中
    cache_key = f"{source}->{target}::{text[:200]}"
    if cache_key in CACHE:
        return CACHE[cache_key]
    # API 调用
    result = _call_mymemory(text, target)
    if result:
        CACHE[cache_key] = result
        # 每 30 次保存一次缓存
        if len(CACHE) % 30 == 0:
            _save_cache(CACHE)
        time.sleep(0.4)  # 节流
        return result
    # 失败 → 返回原文
    return text

def translate_en_to_zh(text: str) -> str:
    return _translate(text, "en", "zh-CN")

def translate_zh_to_en(text: str) -> str:
    return _translate(text, "zh-CN", "en")

def save_cache():
    _save_cache(CACHE)
