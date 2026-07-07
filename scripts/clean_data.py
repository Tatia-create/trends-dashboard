"""
clean_data.py — 数据质量清洗器 (2026-07-07)

功能:
  1. 删 footer/备案号条目(沪ICP备、copyright、隐私政策等)
  2. 修 HTML 转义残留(&nbsp; / &#xff08; 等)
  3. 删乱码/不完整标题(< 4 字符纯符号,匹配人名碎片)
  4. 标记低质量条目(is_dirty=True),v3 卡片默认不显示描述
  5. 输出清洗报告

用法:
  python3 clean_data.py [--dry-run]
  # 干跑(只报告不写)
  python3 clean_data.py --write
  # 实际清洗
"""

import json
import re
import sys
import argparse
from pathlib import Path

DATA = Path("/home/gem/.aily/workspace/trends-dashboard/trends-data.json")

# 1. footer / 备案号 / 版权声明(只匹配强信号,避免"注册资本"误伤)
FOOTER_RE = re.compile(
    r"ICP备|icp备|copyright|©|all rights reserved|powered by|网站地图|sitemap|"
    r"隐私政策|服务条款|使用协议|免责声明|关于我们$|^cookie$|订阅.*rss|app store|google play|"
    r"^登录$|^注册$|^首页$",
    re.I,
)

# 2. HTML 转义残留
HTML_ESC_RE = re.compile(r"&nbsp;|&#\d+;|&[a-z]+;")

# 3. 乱码 / 短串 (纯符号 / 单字符 / 数字串)
GARBAGE_RE = re.compile(r"^[\s\W\d_]+$", re.I)

# 4. 单独棋盘字符
PIECE_RE = re.compile(r"[♟♠♣♥♦●■▲▼◆★☆▢▣▤▥▦▧▨▩]")

# 5. PDF 章节标题
PDF_CHAPTER_RE = re.compile(
    r"^(chapter|section|part|appendix|annex|表|图)\s*\d+", re.I
)


def is_garbage_title(s: str) -> bool:
    s = (s or "").strip()
    if not s:
        return True
    if len(s) < 4:
        return True
    if GARBAGE_RE.match(s):
        return True
    if PIECE_RE.search(s):
        return True
    if PDF_CHAPTER_RE.match(s):
        return True
    return False


def has_footer_signal(s: str) -> bool:
    return bool(FOOTER_RE.search(s or ""))


def clean_html_escape(s: str) -> str:
    """把 HTML 转义还原为正常字符"""
    if not s:
        return s
    s = s.replace("&nbsp;", " ").replace("&#160;", " ")
    s = s.replace("&#xff08;", "（").replace("&#xff09;", "）")
    s = s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    s = s.replace("&quot;", '"').replace("&#39;", "'")
    s = HTML_ESC_RE.sub("", s)  # 残留全部清掉
    return s.strip()


def assess_item(it: dict) -> dict:
    """返回这个条目的质量评估"""
    tz = (it.get("title_zh") or "").strip()
    te = (it.get("title_en") or "").strip()
    dz = (it.get("desc_zh") or "").strip()
    de = (it.get("desc_en") or "").strip()
    src = it.get("source", "?")
    cat = it.get("cat", "?")

    reasons = []

    # 硬删:footer / 备案号
    if has_footer_signal(tz) or has_footer_signal(dz) or has_footer_signal(te):
        reasons.append("footer_signal")

    # 硬删:乱码标题
    if is_garbage_title(tz) and is_garbage_title(te):
        reasons.append("garbage_title")

    # 软标:HTML 转义(可修,不算硬删)
    if HTML_ESC_RE.search(tz) or HTML_ESC_RE.search(te) or HTML_ESC_RE.search(dz) or HTML_ESC_RE.search(de):
        reasons.append("html_escape")

    # 软标:描述为空(只标记,不删)
    if (not dz or len(dz) < 8) and (not de or len(de) < 8):
        reasons.append("empty_desc")

    # 软标:标题 = 描述
    if tz and dz and tz[:30] == dz[:30]:
        reasons.append("title_eq_desc")

    return {
        "id": it.get("id", "?"),
        "title_zh": tz[:50],
        "source": src,
        "cat": cat,
        "reasons": reasons,
        "should_delete": any(r in ("footer_signal", "garbage_title") for r in reasons),
        "can_fix": "html_escape" in reasons,
    }


def run(dry_run: bool = True):
    with open(DATA, encoding="utf-8") as f:
        d = json.load(f)

    items = d.get("stories", [])
    print(f"📂 {DATA.name} · {len(items)} 条\n")

    assessments = [assess_item(it) for it in items]
    to_delete = [a for a in assessments if a["should_delete"]]
    to_fix = [a for a in assessments if a["can_fix"] and not a["should_delete"]]
    low_quality = [a for a in assessments if "empty_desc" in a["reasons"] and not a["should_delete"]]

    print(f"🗑  硬删(footer / 乱码):  {len(to_delete)}")
    for a in to_delete[:5]:
        print(f"     - [{a['cat']}/{a['source']}] {a['title_zh']}  ({','.join(a['reasons'])})")
    if len(to_delete) > 5:
        print(f"     ... 还有 {len(to_delete)-5} 条")

    print(f"\n🔧 可修(HTML 转义):      {len(to_fix)}")
    for a in to_fix[:5]:
        print(f"     - [{a['cat']}/{a['source']}] {a['title_zh']}")
    if len(to_fix) > 5:
        print(f"     ... 还有 {len(to_fix)-5} 条")

    print(f"\n⚠️  低质量(空描述):      {len(low_quality)}")
    print(f"   (这些保留,卡片只显标题,不显描述)")

    print(f"\n📊 净留存:               {len(items) - len(to_delete)} / {len(items)}")

    if dry_run:
        print("\n🟡 DRY RUN — 加 --write 才写文件")
        return

    # ===== 实际清洗 =====
    delete_ids = {a["id"] for a in to_delete}
    fix_ids = {a["id"] for a in to_fix}

    new_stories = []
    for it in items:
        if it["id"] in delete_ids:
            continue
        # 修 HTML 转义
        if it["id"] in fix_ids:
            it["title_zh"] = clean_html_escape(it.get("title_zh"))
            it["title_en"] = clean_html_escape(it.get("title_en"))
            it["desc_zh"] = clean_html_escape(it.get("desc_zh"))
            it["desc_en"] = clean_html_escape(it.get("desc_en"))
        # 标 is_dirty 给 HTML 端使用
        it["is_dirty"] = "html_escape" not in [
            r for a in assessments if a["id"] == it["id"] for r in a["reasons"]
        ] and False or "html_escape" in [
            r for a in assessments if a["id"] == it["id"] for r in a["reasons"]
        ]
        new_stories.append(it)

    d["stories"] = new_stories
    d["stats"] = d.get("stats", {})
    d["stats"]["cleaned_total"] = len(new_stories)
    d["stats"]["removed_in_clean"] = len(to_delete)
    d["stats"]["fixed_html_escape"] = len(to_fix)

    # 写文件
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

    # 备份
    backup = DATA.with_suffix(f".json.bak-{int(__import__('time').time())}")
    with open(backup, "w", encoding="utf-8") as f:
        json.dump({"stories": items, "stats": d.get("stats", {})}, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 清洗完成")
    print(f"   原: {len(items)} → 新: {len(new_stories)}")
    print(f"   备份: {backup.name}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--write", action="store_true", help="实际写文件")
    args = p.parse_args()
    run(dry_run=not args.write)
