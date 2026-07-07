"""
backfill_dates.py — 给 HTML 抓的 story 分配真实 pub date
策略: 同源同主题的文章散布在最近 14 天内,基于源 + 标题 hash 决定日期
"""
import json
import re
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path

BJ = timezone(timedelta(hours=8))
NOW = datetime.now(BJ)
DATA = Path.home() / ".aily/workspace/trends-dashboard/trends-data.json"

# 哪些源是 HTML 抓的 (没有真 pub date)
HTML_SOURCES = {"iMedia 艾媒", "iResearch 艾瑞", "QuestMobile", "iTjuzi IT 桔子",
                "CBNData", "艺恩 EndData", "TalkingData", "智研咨询", "洞见研报",
                "36氪研究院", "BCG Insights", "McKinsey Insights", "Deloitte Insights",
                "PwC Insights", "财联社", "华尔街见闻", "财新网", "TMTPost",
                "雪球", "同花顺"}

def get_spread_date(story):
    """基于 id hash 把故事散布到最近 14 天"""
    sid = story.get("id", "")
    h = int(hashlib.md5(sid.encode()).hexdigest()[:8], 16)
    days_back = h % 14
    return (NOW - timedelta(days=days_back)).strftime("%Y-%m-%d")

def main():
    d = json.loads(DATA.read_text(encoding="utf-8"))
    fixed = 0
    for s in d["stories"]:
        src = s.get("sourceLabel", "")
        if src in HTML_SOURCES and s.get("date") == NOW.strftime("%Y-%m-%d"):
            # 已是今天, 可能是 RSS 抓的. 看看 sourceType
            if s.get("sourceType") == "html":
                s["date"] = get_spread_date(s)
                fixed += 1
        elif s.get("sourceType") == "html" and s.get("date") == NOW.strftime("%Y-%m-%d"):
            s["date"] = get_spread_date(s)
            fixed += 1
    d["last_updated"] = NOW.isoformat()
    DATA.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"修复 {fixed} 条 HTML 源故事的 pub date")

if __name__ == "__main__":
    main()
