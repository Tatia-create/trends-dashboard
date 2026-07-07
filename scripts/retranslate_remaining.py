"""
retranslate_remaining.py — 补翻被 MyMemory 限流漏掉的英文/中文
策略: 只翻缓存里没的,带 2 秒 sleep 避免再被限流
"""
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from translate import _HAS_CJK, _call_mymemory, _load_cache, _save_cache, translate_en_to_zh, translate_zh_to_en

DATA = Path.home() / ".aily/workspace/trends-dashboard/trends-data.json"
CACHE = _load_cache()

def needs_zh(s): return bool(s) and not _HAS_CJK.search(s)
def needs_en(s): return bool(s) and _HAS_CJK.search(s)

d = json.loads(DATA.read_text(encoding="utf-8"))
fixed = 0
for s in d["stories"]:
    # 标题
    for field, func, check in [
        ("title_zh", translate_en_to_zh, needs_zh),
        ("title_en", translate_zh_to_en, needs_en),
        ("desc_zh", lambda x: translate_en_to_zh(x)[:400], needs_zh),
        ("desc_en", lambda x: translate_zh_to_en(x)[:400], needs_en),
    ]:
        v = s.get(field, "")
        if check(v) and v not in [r.get(field) for r in d["stories"]]:
            # 只在缓存里没有时翻
            cache_key = f"en->zh-CN::{v[:200]}" if "zh" in field else f"zh-CN->en::{v[:200]}"
            if cache_key in CACHE:
                s[field] = CACHE[cache_key]
                fixed += 1
            else:
                new = func(v)
                if new != v:
                    s[field] = new
                    fixed += 1
                    time.sleep(2.0)  # 节流

DATA.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"补翻 {fixed} 处")
