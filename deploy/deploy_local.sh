#!/usr/bin/env bash
# 智慧农业生态 · 本地一键部署脚本（在 Windows / macOS / Linux 本机执行）
# 用途：把项目上传到 ECS 并触发远端部署，全程无需手工 scp。
#
# 前置（只需做一次）：
#   1. 本机装好 ssh / scp（Windows 用 OpenSSH，Win10+ 自带）。
#   2. 把 SSH 私钥配好：ssh-copy-id root@<ECS_IP>  （或把 deploy_config 里改为你能登录的用户）
#
# 用法：
#   bash deploy/deploy_local.sh                     # 用 deploy_config.sh 里的默认值
#   ECS_IP=150.158.119.119 PORT=8001 bash deploy/deploy_local.sh
#
# 退出码：0 成功；非 0 表示某步失败（已打印原因）。

set -euo pipefail

# ---------- 读默认配置（可覆盖） ----------
HERE="$(cd "$(dirname "$0")" && pwd)"
if [ -f "${HERE}/deploy_config.sh" ]; then
  # shellcheck disable=SC1091
  source "${HERE}/deploy_config.sh"
fi
ECS_IP="${ECS_IP:-150.158.119.19}"
ECS_USER="${ECS_USER:-root}"
REMOTE_APP_DIR="${REMOTE_APP_DIR:-/opt/agri-eco}"
PORT="${PORT:-8001}"
PROJECT_ROOT="$(cd "${HERE}/.." && pwd)"

SSH_OPTS="-o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 -o BatchMode=yes"

log() { echo "[$(date '+%F %T')] $*"; }

log "=== 智慧农业生态 · 本地部署开始 ==="
log "项目: ${PROJECT_ROOT}"
log "目标: ${ECS_USER}@${ECS_IP}:${REMOTE_APP_DIR}"

# ---------- 1. 连通性检查 ----------
log "检查 SSH 连通性..."
if ! ssh ${SSH_OPTS} "${ECS_USER}@${ECS_IP}" 'echo ok' >/dev/null 2>&1; then
  log "错误：无法免密登录 ${ECS_USER}@${ECS_IP}"
  log "请先执行：ssh-copy-id ${ECS_USER}@${ECS_IP}   （输入一次密码即可）"
  exit 1
fi
log "SSH 连通正常"

# ---------- 2. 远端建目录 ----------
ssh ${SSH_OPTS} "${ECS_USER}@${ECS_IP}" "mkdir -p ${REMOTE_APP_DIR}"

# ---------- 3. 同步代码（rsync 优先，退化到 scp） ----------
EXCLUDES='--exclude=.git --exclude=.workbuddy --exclude=__pycache__ --exclude=.venv --exclude=node_modules --exclude=data/feedback_log.json'

if command -v rsync >/dev/null 2>&1; then
  log "用 rsync 同步（带排除项）..."
  # Windows Git Bash 自带 rsync；否则退化
  rsync -az --delete ${EXCLUDES} -e "ssh ${SSH_OPTS}" "${PROJECT_ROOT}/" "${ECS_USER}@${ECS_IP}:${REMOTE_APP_DIR}/"
else
  log "rsync 不可用，用 tar + ssh 管道同步（保留权限、带排除）..."
  tar -czf - -C "${PROJECT_ROOT}" \
      --exclude='.git' --exclude='.workbuddy' --exclude='__pycache__' \
      --exclude='.venv' --exclude='node_modules' \
      --exclude='data/feedback_log.json' . \
    | ssh ${SSH_OPTS} "${ECS_USER}@${ECS_IP}" "tar -xzf - -C ${REMOTE_APP_DIR}"
fi
log "代码同步完成"

# ---------- 4. 远端启动部署脚本 ----------
log "在远端执行部署脚本（装 Docker / 构建 / 启动 / 验证）..."
ssh ${SSH_OPTS} "${ECS_USER}@${ECS_IP}" \
  "cd ${REMOTE_APP_DIR} && APP_DIR=${REMOTE_APP_DIR} PORT=${PORT} bash deploy/setup_ecs.sh"

log ""
log "=== 部署完成 ==="
log "站点: http://${ECS_IP}:${PORT}"
log "健康检查: curl http://${ECS_IP}:${PORT}/api/cities"
