#!/bin/bash
# update.sh — 全球趋势仪表盘每日更新脚本
# 在定时任务里跑: 抓取 → 推送 GitHub → Pages 自动部署
# 一切全自动, 用户无需任何操作

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ========== 1. 抓取数据 ==========
echo "📥 [1/3] 抓取 RSS ..."
python3 scripts/fetch_trends.py

# ========== 2. 推送 GitHub ==========
echo "🚀 [2/3] 推送 GitHub ..."
TOKEN_FILE="$SCRIPT_DIR/.gh_token"
if [[ ! -f "$TOKEN_FILE" ]]; then
  echo "❌ Token file not found: $TOKEN_FILE"
  exit 1
fi
TOKEN=$(cat "$TOKEN_FILE")
REPO="Tatia-create/trends-dashboard"
DATA_FILE="$SCRIPT_DIR/trends-data.json"

# 拿 sha (文件已存在的话)
SHA=$(python3 - <<PYEOF
import urllib.request, json
TOKEN = "$TOKEN"
req = urllib.request.Request(
    "https://api.github.com/repos/$REPO/contents/trends-data.json",
    headers={"Authorization": f"Bearer {TOKEN}", "User-Agent":"aily-bot"}
)
try:
    with urllib.request.urlopen(req, timeout=15) as r:
        print(json.loads(r.read())["sha"])
except Exception:
    print("")
PYEOF
)

# 编码 + 推送
python3 - <<PYEOF
import urllib.request, urllib.error, json, base64
TOKEN = "$TOKEN"
REPO = "$REPO"
SHA = "$SHA"
with open("$DATA_FILE","rb") as f: b64 = base64.b64encode(f.read()).decode()
body = {"message":"🤖 auto-update: $(date -u '+%Y-%m-%d %H:%M UTC')", "content":b64}
if SHA: body["sha"] = SHA
data = json.dumps(body).encode()
req = urllib.request.Request(
    f"https://api.github.com/repos/{REPO}/contents/trends-data.json",
    data=data,
    headers={"Authorization":f"Bearer {TOKEN}","Content-Type":"application/json","User-Agent":"aily-bot"},
    method="PUT"
)
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        resp = json.loads(r.read())
        print(f"  ✅ Pushed: {resp.get('commit',{}).get('sha','')[:8]}")
except urllib.error.HTTPError as e:
    print(f"  ❌ Push failed: {e.code} {e.read().decode()[:200]}")
    exit(1)
PYEOF

# ========== 3. 报告 ==========
echo "📊 [3/3] 生成状态报告 ..."
python3 -c "
import json
d = json.load(open('$DATA_FILE'))
s = d.get('stats',{})
print(f'总故事: {s.get(\"total\",0)} | 🔥HOT: {s.get(\"hot\",0)} | 🟧TREND: {s.get(\"trend\",0)} | NEW: {d.get(\"new_today\",0)}')
print(f'源状态: {d.get(\"sources_ok\",0)} ok / {d.get(\"sources_failed\",0)} failed')
print(f'窗口: {d.get(\"window\",\"\")}')
"

echo "✅ 完成。Pages 1-2 分钟内自动更新。"
