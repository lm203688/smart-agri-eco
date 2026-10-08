#!/usr/bin/env bash
# 智慧农业生态 · 一键仓库同步（P0-6）
#
# 用途：把本地工作区与 GitHub main 完全对齐（新增 + 更新 + 删除冗余），单 commit。
#
# 前置：需要一个 fine-grained PAT（只含 lm203688/smart-agri-eco 的
#       Contents: read/write + Workflows: read/write），存成一行文本文件。
#
# 用法：
#   bash scripts/push_all.sh /path/to/pat.txt
#
# 行为：
#   1. 用 sync_check 实时算出差异（不依赖预生成清单，避免清单过期）
#   2. 调 gh_push.py 单 commit 推送
#   3. 推送后自动回读校验（gh_push 内置），再跑一次 sync_check 确认归零
#   4. 提示你删除 PAT 文件（脚本不代删，避免误删）
#
# 退出码：0 = 已完全一致；非 0 = 失败。

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "${HERE}/.." && pwd)"
cd "${ROOT}"

TOKEN_FILE="${1:-}"
if [ -z "${TOKEN_FILE}" ]; then
  echo "用法: bash scripts/push_all.sh /path/to/pat.txt"
  exit 2
fi
if [ ! -f "${TOKEN_FILE}" ]; then
  echo "错误：找不到 PAT 文件 ${TOKEN_FILE}"
  exit 2
fi

MSG="${AGRI_COMMIT_MSG:-feat(dist): MCP 2026-07-28 无状态适配 + A2A Agent Card + Agent Plugins 打包 + 目录整理}"

echo "=== 1/4 计算差异清单 ==="
python - <<'PY' > /tmp/agri_diff.txt
import sys, os
sys.path.insert(0, "scripts")
import sync_check as SC
_, remote = SC.remote_files("")
local = SC.local_files()
missing = sorted(p for p in local if p not in remote)
differ  = sorted(p for p in local if p in remote and local[p] != remote[p])
extra   = sorted(p for p in remote if p not in local)
print("UPSTREAM")
for p in missing + differ:
    print(p)
print("DELETE")
for p in extra:
    print(p)
PY

UPS="$(awk '/^UPSTREAM$/{f=1;next} /^DELETE$/{f=0} f' /tmp/agri_diff.txt | wc -l | tr -d ' ')"
DELS="$(awk '/^DELETE$/{f=1;next} f' /tmp/agri_diff.txt | wc -l | tr -d ' ')"
echo "   待写入 ${UPS} 个 / 待删除 ${DELS} 个"

if [ "${UPS}" = "0" ] && [ "${DELS}" = "0" ]; then
  echo "本地与远端已一致，无需推送。"
  exit 0
fi

echo "=== 2/4 展示删除项（请确认） ==="
awk '/^DELETE$/{f=1;next} f' /tmp/agri_diff.txt | sed 's/^/   - /'

echo "=== 3/4 推送 ==="
ARGS=()
while IFS= read -r line; do ARGS+=("$line"); done < <(awk '/^UPSTREAM$/{f=1;next} /^DELETE$/{f=0} f' /tmp/agri_diff.txt)
python scripts/gh_push.py "${TOKEN_FILE}" "${MSG}" "${ARGS[@]}" --delete $(awk '/^DELETE$/{f=1;next} f' /tmp/agri_diff.txt | tr '\n' ' ')

echo "=== 4/4 复核 ==="
python scripts/sync_check.py || true
echo ""
echo "完成。请立即删除 PAT 文件：rm '${TOKEN_FILE}'"
