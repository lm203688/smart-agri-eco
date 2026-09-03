#!/usr/bin/env bash
# 智慧农业生态 · ECS 端一键部署脚本
# 用途：在腾讯云服务器上执行，完成 Docker 安装（如缺）、目录准备、构建、启动、健康检查。
# 用法（在 ECS 上）：
#   bash setup_ecs.sh                 # 默认 /opt/agri-eco，端口 8001
#   APP_DIR=/root/agri-eco PORT=9000 bash setup_ecs.sh
#
# 说明：
#   - 仅用 Docker 官方镜像 python:3.11-slim，无需本地 pip 依赖。
#   - 不修改本机已有服务（ATEX 8420 / HealthLens 不受影响）。
#   - 幂等：可重复执行（down 后再 up）。

set -euo pipefail

APP_DIR="${APP_DIR:-/opt/agri-eco}"
PORT="${PORT:-8001}"
COMPOSE_FILE="deploy/docker-compose.prod.yml"

log() { echo "[$(date '+%F %T')] $*"; }

log "=== 智慧农业生态 · ECS 部署开始 ==="
log "目标目录: ${APP_DIR}"
log "对外端口: ${PORT}"

# ---------- 1. 检查 Docker ----------
if ! command -v docker >/dev/null 2>&1; then
  log "未检测到 Docker，开始安装..."
  curl -fsSL https://get.docker.com | sh
fi
if ! docker compose version >/dev/null 2>&1; then
  log "未检测到 docker compose 插件，尝试安装..."
  apt-get update -y
  apt-get install -y docker-compose-plugin
fi
log "Docker: $(docker --version)"
log "Compose: $(docker compose version)"

# ---------- 2. 检查 compose 文件 ----------
if [ ! -f "${APP_DIR}/${COMPOSE_FILE}" ]; then
  log "错误：未找到 ${APP_DIR}/${COMPOSE_FILE}"
  log "请先用 deploy/deploy_local.sh 把项目上传到 ${APP_DIR}"
  exit 1
fi
cd "${APP_DIR}"

# ---------- 3. 端口占用检查 ----------
if ss -ltn 2>/dev/null | awk '{print $4}' | grep -Eq "[:.]${PORT}\s*$"; then
  log "警告：端口 ${PORT} 已被占用，将先 down 已有容器"
  docker compose -f "${COMPOSE_FILE}" down -t 10 >/dev/null 2>&1 || true
fi

# ---------- 4. 构建并启动 ----------
log "构建镜像..."
docker compose -f "${COMPOSE_FILE}" up -d --build

# ---------- 5. 健康检查 ----------
log "等待服务就绪..."
for i in $(seq 1 30); do
  sleep 2
  if curl -sf --noproxy '*' "http://127.0.0.1:${PORT}/api/cities" >/dev/null 2>&1; then
    log "服务已就绪"
    break
  fi
  if [ "$i" -eq 30 ]; then
    log "错误：服务 60 秒内未就绪，最近日志："
    docker logs --tail 40 agri-eco
    exit 1
  fi
done

# ---------- 6. 端到端验证 ----------
log "运行端到端验证..."
docker compose -f "${COMPOSE_FILE}" exec -T agri-eco python scripts/verify_all.py || {
  log "警告：容器内 verify_all 未通过，但站点可访问。请人工检查。"
}

# ---------- 7. 报告 ----------
PUB_IP=$(curl -s --noproxy '*' ifconfig.me || echo "<请自行填写公网IP>")
log "=== 部署完成 ==="
log "站点地址（端口直连）: http://${PUB_IP}:${PORT}"
log "容器状态:"
docker ps --filter name=agri-eco --format '  {{.Names}}  {{.Status}}  {{.Ports}}'
log ""
log "下一步："
log "  1. 在腾讯云安全组放通 ${PORT} 端口（或 80/443）"
log "  2. 如需域名/HTTPS：把 deploy/nginx.conf 复制到 /etc/nginx/conf.d/agri-eco.conf"
log "     改 server_name，然后 apt-get install -y certbot python3-certbot-nginx && nginx -t && certbot --nginx"
