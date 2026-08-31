# 智慧农业生态 · 部署配置模板
# 用法：复制为 deploy/deploy_config.sh 并按实际填写；deploy_local.sh 会自动 source 本文件。
# 也可用环境变量临时覆盖：ECS_IP=1.2.3.4 bash deploy/deploy_local.sh
#
# 注意：本文件不含密钥。SSH 用密钥认证，请把私钥放本机 ~/.ssh/ 并 ssh-copy-id 到 ECS。

# ECS 公网地址（你已知的腾讯云主机；已跑 ATEX:8420 与 HealthLens，本项目用 8000 不冲突）
ECS_IP="150.158.119.19"

# 登录用户
ECS_USER="root"

# 远端项目目录（建议放 /opt 下，避免和已有服务混在一起）
REMOTE_APP_DIR="/opt/agri-eco"

# 对外端口
PORT="8000"
