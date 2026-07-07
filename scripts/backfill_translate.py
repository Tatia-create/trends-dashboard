"""
backfill_translate.py — 把现有 trends-data.json 里所有 story 翻译成中英双语

策略:
- 若 title_zh / desc_zh 含英文(无中文)→ 翻译成中文
- 若 title_en / desc_en 含中文 → 翻译成英文
- 用 translate.py 的本地缓存,二次运行只翻没翻过的
- MyMemory 匿名限 5000 词/天,分批 sleep 节流

用法:
    python3 backfill_translate.py [--limit 50] [--dry-run]
"""
import json
import re
import sys
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).parent))
from translate import translate_en_to_zh, translate_zh_to_en, save_cache, _HAS_CJK

BJ = timezone(timedelta(hours=8))
DATA_PATH = Path.home() / ".aily/workspace/trends-dashboard/trends-data.json"

def is_english_only(s: str) -> bool:
    """判断是否纯英文 (无 CJK)"""
    if not s: return False
    return not _HAS_CJK.search(s)

def is_chinese_only(s: str) -> bool:
    """判断是否含中文"""
    if not s: return False
    return bool(_HAS_CJK.search(s))

def needs_zh_translation(s: str) -> bool:
    """zh 字段需要翻译 = 存在且是英文(无中文)"""
    return bool(s) and is_english_only(s)

def needs_en_translation(s: str) -> bool:
    """en 字段需要翻译 = 存在且含中文"""
    return bool(s) and is_chinese_only(s)

def main():
    dry = "--dry-run" in sys.argv
    limit = None
    for i, a in enumerate(sys.argv):
        if a == "--limit" and i + 1 < len(sys.argv):
            limit = int(sys.argv[i + 1])

    if not DATA_PATH.exists():
        print(f"❌ {DATA_PATH} 不存在")
        return
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    stories = data.get("stories", [])
    print(f"📊 共 {len(stories)} 条 story")

    # 优先级:HOT > TRENDING > NEW > ARCHIVED
    heat_order = {"hot": 0, "trend": 1, "new": 2, "arch": 3}
    stories_sorted = sorted(stories, key=lambda s: heat_order.get(s.get("heat", "arch"), 99))

    if limit:
        stories_sorted = stories_sorted[:limit]

    translated_zh = 0
    translated_en = 0
    skipped = 0
    start = time.time()

    for i, story in enumerate(stories_sorted):
        tid = story.get("id", "?")
        title_zh = story.get("title_zh", "")
        title_en = story.get("title_en", "")
        desc_zh = story.get("desc_zh", "")
        desc_en = story.get("desc_en", "")

        # 翻译 zh 字段
        if needs_zh_translation(title_zh):
            if not dry:
                story["title_zh"] = translate_en_to_zh(title_zh)
                translated_zh += 1
        elif title_zh:
            skipped += 1

        if needs_zh_translation(desc_zh):
            if not dry:
                story["desc_zh"] = translate_en_to_zh(desc_zh)[:400]
                translated_zh += 1

        # 翻译 en 字段(中文源)
        if needs_en_translation(title_en):
            if not dry:
                story["title_en"] = translate_zh_to_en(title_en)
                translated_en += 1
        elif needs_en_translation(title_en) is False and title_en:
            pass

        if needs_en_translation(desc_en):
            if not dry:
                story["desc_en"] = translate_zh_to_en(desc_en)[:400]
                translated_en += 1

        # 进度
        if (i + 1) % 10 == 0:
            elapsed = time.time() - start
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            print(f"  [{i+1}/{len(stories_sorted)}] zh={translated_zh} en={translated_en} skip={skipped} rate={rate:.1f}/s")
            if not dry:
                save_cache()
                # 增量写盘,防中断
                DATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        # 防止 MyMemory 限流
        if not dry and (translated_zh + translated_en) % 5 == 0 and (translated_zh + translated_en) > 0:
            time.sleep(1.0)

    if not dry:
        # 更新 metadata
        data["version"] = "2.2-bilingual"
        data["last_updated"] = datetime.now(BJ).isoformat()
        DATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        save_cache()

    print(f"\n✅ 完成: zh 翻译 {translated_zh} 处, en 翻译 {translated_en} 处, 跳过 {skipped} 处")
    print(f"⏱ 耗时 {time.time()-start:.1f}s")

if __name__ == "__main__":
    main()
