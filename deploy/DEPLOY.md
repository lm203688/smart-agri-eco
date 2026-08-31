# 智慧农业生态 · 公网部署指南

> 本文件说明**部署流程**，不涉及任何账号登录或密钥操作。
> 执行部署需要你本人在对应云账号操作（属硬阻塞项，AI 不代操作）。

## 目标

把 `app/demo_server.py`（零第三方依赖，仅 Python 标准库）部署到公网，
让评委 / 内测用户能直接打开「输入坐标 → 四 Agent 方案 + AgriTrust 证书」。

---

## 推荐路径：腾讯云 ECS（一条命令）

你已有 ECS `150.158.119.19`（上面已跑 ATEX :8420 与 HealthLens，本项目用 **:8000**，不冲突）。

### 一次性前置（只做一次）

```bash
# 1. 本机配好 SSH 免密登录（输入一次密码即可）
ssh-copy-id root@150.158.119.19

# 2. 复制部署配置模板（默认值已填好，按需改）
cd 智慧农业生态
cp deploy/deploy_config.example.sh deploy/deploy_config.sh
```

### 每次部署

```bash
bash deploy/deploy_local.sh
```

脚本自动完成：SSH 连通性检查 → rsync 同步代码（排除 `.git`/`.workbuddy`/`__pycache__`）
→ 远端自动装 Docker（如缺）→ 构建镜像 → 启动容器 → 健康检查 → 跑 `verify_all.py`。

成功后访问：

```
http://150.158.119.19:8000
```

### 验证

```bash
curl http://150.158.119.19:8000/api/cities
curl -X POST http://150.158.119.19:8000/api/recommend \
  -H 'Content-Type: application/json' \
  -d '{"lat":30.2741,"lon":120.1551,"scene":"balcony","floor":15,"orientation":"south","purpose":"食用","space_sqm":1.5,"difficulty":"beginner","budget_cny":500}'
```

---

## 域名 + HTTPS（可选，建议做）

纯 IP + 端口能访问，但拿域名做演示更正式：

1. 把域名解析（或 CF 代理）指向 ECS IP。
2. 把 `deploy/nginx.conf` 复制到 ECS：
   ```bash
   scp deploy/nginx.conf root@150.158.119.19:/etc/nginx/conf.d/agri-eco.conf
   ssh root@150.158.119.19 "sed -i 's/agri.your-domain.com/你的域名/' /etc/nginx/conf.d/agri-eco.conf"
   ```
   ⚠️ 注意：`nginx.conf` 反代到 `127.0.0.1:8000`，而 `docker-compose.prod.yml` 映射了 `8000:8000` 到宿主机，两者能直接对上。
3. 在 ECS 上签证书并重启：
   ```bash
   apt-get install -y certbot python3-certbot-nginx && nginx -t && certbot --nginx
   ```

---

## 方案 B：Cloudflare

- **CF Pages**：仅支持静态 + Pages Functions（JS），**不能直接跑 Python 服务**。
  - 可选做法：Pages Functions 做反向代理壳，后端仍指向 ECS（即上面的方案 A）。
- **CF Workers Containers**：可跑容器，但需在 CF 控制台绑定仓库并授权
  （`cfut_` 类权限——你此前在 aishield.tools 上即卡在此类授权）。
- 结论：**建议直接走方案 A（ECS）**，最短路径。

---

## 本地预览（不部署也能看）

```bash
python app/demo_server.py        # 打开 http://127.0.0.1:8000
```

---

## CI（每次 push 自动验证）

`.github/workflows/ci.yml` 已在仓库中。push 到 main 后 GitHub Actions 自动跑：

| 步骤 | 内容 |
|------|------|
| 单测 | `python -m unittest scripts.test_agents` |
| 端到端 | `python scripts/verify_all.py` |
| Trust 层 | `python -m core.trust_layer` |
| 反馈闭环 | `python -m engine.flywheel` |
| Skill 注册表 | 全部 JSON 合法性 |
| 数据自检 | 每气候带作物 ≥18 种 |

Python 3.10 / 3.11 / 3.12 三版本矩阵。

> 硬阻塞：需要在 GitHub 上启用 Actions，PAT 需含 `Workflows:write`（你已知此权限缺口）。
> 本地已逐条模拟验证过全部 6 步，均 PASS。

---

## 部署后待办

- [ ] 决定域名（或直接使用 IP）
- [ ] ECS 安全组放通 8000（或 80/443）
- [ ] 如需 HTTPS：`certbot --nginx` 或 CF 代理开 SSL
- [ ] 把公网地址回填到 `README.md` 与 `docs/project_evaluation.md` 的 Demo 链接
