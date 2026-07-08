#!/bin/bash
# update.sh — 趋势仪表盘每日更新 (v3.1)
# 5 步: 1抓取 2过滤 3补翻 4精华 5推送
# 每日 10:30 由 cron 触发
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🚀 update.sh 启动: $(date '+%Y-%m-%d %H:%M:%S')"
echo "📂 工作目录: $SCRIPT_DIR"

# ========== 1. 抓取数据 ==========
echo "📥 [1/5] 抓取 RSS ..."
python3 scripts/fetch_trends.py

# ========== 2. 过滤垃圾(源头屏蔽 + 标题/描述黑名单) ==========
echo "🧹 [2/5] 过滤垃圾条目 ..."
python3 scripts/filter_junk.py

# ========== 3. 补翻 MyMemory 限流漏掉的 ==========
echo "🌐 [3/5] 补翻 ..."
python3 scripts/retranslate_remaining.py || echo "  (无遗漏)"

# ========== 4. 提取精华总结 (路径 C, 0 元) ==========
echo "📝 [4/5] 提取精华 ..."
python3 scripts/extract_summaries.py || echo "  (无新增)"

# ========== 5. 推送 GitHub ==========
echo "🚀 [5/5] 推送 GitHub ..."
TOKEN_FILE="$SCRIPT_DIR/.gh_token"
if [ -f "$TOKEN_FILE" ]; then
    TOKEN=$(cat "$TOKEN_FILE" | tr -d '[:space:]')
    git add trends-data.json scripts/ version-c-bilingual-v3-info.html 2>/dev/null || true
    if git diff --cached --quiet 2>/dev/null; then
        echo "  (无变更,跳过提交)"
    else
        git commit -m "🤖 自动更新:$(date '+%Y-%m-%d %H:%M') [skip ci]" 2>&1 | head -3
        git push origin main 2>&1 | head -3
        echo "  ✅ 已推 GitHub"
    fi
else
    echo "  ⚠️ 无 .gh_token,跳过推送(等手动推)"
fi

echo "🎉 update.sh 完成: $(date '+%Y-%m-%d %H:%M:%S')"
