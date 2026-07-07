#!/bin/bash
set -e

# 1. 抓取 30+ 源,产出 trends-data.json
python3 scripts/fetch_trends.py

# 2. 检查 stats
STATS=$(python3 -c "import json; d=json.load(open('trends-data.json')); s=d.get('stats',{}); print(f\"total={s.get('total',0)} hot={s.get('hot',0)} trend={s.get('trend',0)} new_today={d.get('new_today',0)}\")")
echo "📊 Stats: $STATS"

# 3. 自动 commit
if [[ -n "$(git status --porcelain)" ]]; then
  git config user.name "aily-bot"
  git config user.email "aily-bot@users.noreply.github.com"
  git add -A
  git commit -m "🤖 auto-update: $(date -u '+%Y-%m-%d %H:%M UTC') - $STATS" || true
  git push origin main
  echo "✅ Pushed to GitHub"
else
  echo "⏭  No changes"
fi
