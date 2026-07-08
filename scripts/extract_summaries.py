"""
extract_summaries.py — 自动从 desc_full 提取 2-4 句精华
0 元,纯规则,无 LLM
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from smart_summary import smart_summary

DATA = Path.home() / ".aily/workspace/trends-dashboard/trends-data.json"

def needs_extract(text):
    """判断是否需要提取精华(>200 字符 或 含明显元数据)"""
    if not text or len(text) < 50:
        return False
    if len(text) <= 200:
        return False
    return True

def main():
    d = json.loads(DATA.read_text(encoding="utf-8"))
    extracted = 0
    for s in d["stories"]:
        for field in ["desc_full_zh", "desc_full_en"]:
            v = s.get(field, "")
            if needs_extract(v):
                summary = smart_summary(v, target_sentences=2, max_chars=200)
                if summary and len(summary) < len(v) - 30:
                    s[field] = summary
                    extracted += 1
    DATA.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ 精华提取完成:{extracted} 条")

if __name__ == "__main__":
    main()
