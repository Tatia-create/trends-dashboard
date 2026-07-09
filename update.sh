#!/bin/bash
# update.sh — 趋势仪表盘每日更新 (v3.2)
# 5 步: 1抓取 2过滤 3补翻 4精华 5推送
# 每日 10:30 由 cron 触发
# v3.2 改动: 推送改用 GitHub Contents API (不依赖 git 仓库元数据)
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

# ========== 5. 推送 GitHub (Contents API) ==========
echo "🚀 [5/5] 推送 GitHub (Contents API) ..."
TOKEN_FILE="$SCRIPT_DIR/.gh_token"
if [ ! -f "$TOKEN_FILE" ]; then
    echo "  ⚠️ 无 .gh_token,跳过推送"
    exit 0
fi
TOKEN=$(cat "$TOKEN_FILE" | tr -d '[:space:]')
REPO="Tatia-create/trends-dashboard"

# 5a. 升级 ?v=N
HTML="$SCRIPT_DIR/version-c-bilingual-v3-info.html"
if [ -f "$HTML" ]; then
    # 找当前 vN → 下一版
    CUR_V=$(grep -oE '\?v=[0-9]+' "$HTML" | head -1 | grep -oE '[0-9]+')
    if [ -n "$CUR_V" ]; then
        NEW_V=$((CUR_V + 1))
        sed -i "s/?v=${CUR_V}/?v=${NEW_V}/g" "$HTML"
        echo "  ?v=${CUR_V} → ?v=${NEW_V}"
    else
        # 没找到 v,加 ?v=14
        sed -i 's|version-c-bilingual-v3-info.html|version-c-bilingual-v3-info.html?v=14|g' "$HTML"
        echo "  加 ?v=14"
    fi
fi

# 5b. 推 3 个文件 (Contents API)
push_file() {
    local PATH_REMOTE=$1
    local PATH_LOCAL=$2
    local MSG=$3
    if [ ! -f "$PATH_LOCAL" ]; then
        echo "  ⚠️ $PATH_LOCAL 不存在,跳过"
        return
    fi
    python3 - <<PYEOF
import urllib.request, json, base64, sys
TOKEN = "$TOKEN"
REPO = "$REPO"
PATH = "$PATH_REMOTE"
MSG = "$MSG"
def get_sha():
    req = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/contents/{PATH}",
        headers={"Authorization": f"Bearer {TOKEN}", "User-Agent":"aily-cron"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())["sha"]
    except urllib.error.HTTPError as e:
        if e.code == 404: return ""
        raise
with open("$PATH_LOCAL","rb") as f:
    b64 = base64.b64encode(f.read()).decode()
body = {"message": MSG, "content": b64}
sha = get_sha()
if sha: body["sha"] = sha
req = urllib.request.Request(
    f"https://api.github.com/repos/{REPO}/contents/{PATH}",
    data=json.dumps(body).encode(),
    headers={"Authorization": f"Bearer {TOKEN}", "Content-Type":"application/json", "User-Agent":"aily-cron"},
    method="PUT"
)
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read())
        print(f"  ✅ {PATH}  {d.get('commit',{}).get('sha','')[:8]}")
except urllib.error.HTTPError as e:
    print(f"  ❌ {PATH}  {e.code} {e.read().decode()[:150]}")
    sys.exit(1)
PYEOF
}

push_file "trends-data.json" "$SCRIPT_DIR/trends-data.json" "🤖 自动更新:$(date '+%Y-%m-%d %H:%M')"
push_file "version-c-bilingual-v3-info.html" "$HTML" "🔄 缓存破坏 $(date '+%Y-%m-%d %H:%M')"

echo "🎉 update.sh 完成: $(date '+%Y-%m-%d %H:%M:%S')"
