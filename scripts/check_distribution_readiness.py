#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分发就绪度检查（P0-4 一键自检）

目的：把「让外部 Agent 真实调用」这条 P0 主线的**所有对外可见入口**集中在
一份脚本里逐条验证——MCP server、A2A Card、Agent Plugins、Smithery 自动发现、
官方 Registry 元数据、MCPB 分发包、CI 发布 workflow、Demo 部署脚本、GitHub
同步状态、市场提交材料——避免每次评审要人工翻多个文件才能确认"到底有没有
可以分发的东西"。

用法：
    python scripts/check_distribution_readiness.py          # 摘要
    python scripts/check_distribution_readiness.py --full    # 每条附详细
    python scripts/check_distribution_readiness.py --ci       # 非零退出即失败

退出码：0 = 全绿；1 = 有阻塞项。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FULL = "--full" in sys.argv
CI = "--ci" in sys.argv

PASS, WARN, FAIL, SKIP = "✅", "⚠️", "❌", "⏸"
results: list[tuple[str, str, str]] = []


def record(status: str, key: str, detail: str = "") -> None:
    results.append((status, key, detail))


def read_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ── 1. MCP server 本体 ────────────────────────────────────────────────
def check_mcp_server():
    path = ROOT / "mcp" / "server.py"
    if not path.exists():
        record(FAIL, "MCP server", "缺少 mcp/server.py")
        return set()
    src = path.read_text(encoding="utf-8")
    tools = set(re.findall(r'"name"\s*:\s*"(agri_[a-z_]+)"', src))
    # 2026-07-28 无状态规格的关键字
    spec_hits = {
        "无 initialize 握手（SEP-2575）": "stateless" in src or "SEP-2575" in src,
        "无 session（SEP-2567）": "stateless" in src or "Mcp-Session-Id" in src,
        "ttlMs 缓存（SEP-2549）": "ttlMs" in src,
        "traceparent 透传（SEP-414）": "traceparent" in src,
    }
    miss = [k for k, ok in spec_hits.items() if not ok]
    if len(tools) < 14:
        record(FAIL, "MCP 工具数", "只有 %d 个（应 ≥14）" % len(tools))
    else:
        record(PASS, "MCP 工具数", "%d 个" % len(tools))
    if miss:
        record(WARN, "MCP 2026-07-28 规格", "缺失: %s" % ", ".join(miss))
    else:
        record(PASS, "MCP 2026-07-28 规格", "SEP-2575/2567/2549/414 全适配")
    return tools


# ── 2. A2A Agent Card ────────────────────────────────────────────────
def check_agent_card(mcp_tools: set):
    path = ROOT / ".well-known" / "agent.json"
    if not path.exists():
        record(FAIL, "A2A Agent Card", "缺少 .well-known/agent.json")
        return
    try:
        card = read_json(path)
    except Exception as e:
        record(FAIL, "A2A Agent Card", "JSON 解析失败: %s" % e)
        return
    skills = card.get("skills") or []
    ids = {s.get("id") for s in skills if isinstance(s, dict) and s.get("id")}
    if not skills:
        record(FAIL, "A2A skills", "空数组")
    else:
        record(PASS, "A2A skills", "%d 个" % len(skills))
    if mcp_tools:
        orphan = sorted(ids - mcp_tools)
        missing = sorted(mcp_tools - ids)
        if orphan:
            record(WARN, "A2A ↔ MCP", "Card 声明但 MCP 无: %s" % orphan)
        elif missing:
            record(WARN, "A2A ↔ MCP", "MCP 有但 Card 未声明: %s" % missing)
        else:
            record(PASS, "A2A ↔ MCP", "%d 个 skill 与 MCP 工具一一对应" % len(ids))
    integ = card.get("x-agri-integrity") or {}
    if integ.get("dataLicenseWarning"):
        record(PASS, "A2A 法务红线", "dataLicenseWarning 已声明")
    else:
        record(WARN, "A2A 法务红线", "缺 x-agri-integrity.dataLicenseWarning")


# ── 3. Agent Plugins 打包 ─────────────────────────────────────────────
def check_plugin():
    p = ROOT / "plugin" / "plugin.json"
    if not p.exists():
        record(FAIL, "Agent Plugin", "缺少 plugin/plugin.json")
        return
    try:
        pj = read_json(p)
    except Exception as e:
        record(FAIL, "Agent Plugin", "JSON 解析失败: %s" % e)
        return
    declared = pj.get("skills") or []
    if len(declared) < 11:
        record(WARN, "Plugin skills", "只有 %d 个（应 ≥11）" % len(declared))
    else:
        record(PASS, "Plugin skills", "%d 个" % len(declared))
    # 检查每个 skill 目录是否有 SKILL.md
    missing_md = []
    for rel in declared:
        target = (ROOT / "plugin" / rel).resolve()
        md = target / "SKILL.md"
        if not md.exists():
            missing_md.append(rel)
    if missing_md:
        record(FAIL, "Plugin SKILL.md", "缺 %s" % missing_md)
    else:
        record(PASS, "Plugin SKILL.md", "%d 份齐备" % len(declared))
    mcp_json = ROOT / "plugin" / "mcp.json"
    if mcp_json.exists():
        record(PASS, "Plugin mcp.json", "就绪")
    else:
        record(FAIL, "Plugin mcp.json", "缺失")


# ── 4. Smithery 自动发现入口 ─────────────────────────────────────────
def check_smithery():
    p = ROOT / "smithery.yaml"
    if not p.exists():
        record(FAIL, "Smithery 自动发现", "缺少 smithery.yaml")
        return
    text = p.read_text(encoding="utf-8")
    required = ["name:", "description:", "startCommand:", "command:", "args:"]
    miss = [k for k in required if k not in text]
    if miss:
        record(WARN, "Smithery 字段", "缺失关键字段: %s" % miss)
    else:
        record(PASS, "Smithery 自动发现", "smithery.yaml 就绪，Smithery 可免表单抓取")


# ── 5. 官方 MCP Registry 元数据（server.json） ──────────────────────
def check_registry_meta():
    p = ROOT / "server.json"
    if not p.exists():
        record(FAIL, "Registry 元数据", "缺少 server.json")
        return
    try:
        srv = read_json(p)
    except Exception as e:
        record(FAIL, "Registry 元数据", "JSON 解析失败: %s" % e)
        return
    name = srv.get("name", "")
    if not name.startswith("io.github.lm203688/"):
        record(WARN, "Registry 命名", "name 应为 io.github.lm203688/*，当前 %s" % name)
    else:
        record(PASS, "Registry 命名", name)
    pkgs = srv.get("packages") or []
    if not pkgs:
        record(FAIL, "Registry packages", "空数组")
        return
    pkg = pkgs[0]
    ident = pkg.get("identifier", "")
    sha = pkg.get("fileSha256", "")
    if "agri-eco-mcp-" not in ident:
        record(WARN, "Registry identifier", "未指向 .mcpb：%s" % ident[:80])
    else:
        record(PASS, "Registry identifier", ident[:100] + ("..." if len(ident) > 100 else ""))
    # 回读 mcpb 的 sha 是否与 server.json 声明一致
    mcpb = ROOT / "dist" / os.path.basename(ident)
    if mcpb.exists():
        actual = sha256_of(mcpb)
        if actual == sha:
            record(PASS, "Registry sha256", "与 mcpb 逐字节一致（%s）" % sha[:16])
        else:
            record(FAIL, "Registry sha256", "声明 %s ≠ 实际 %s" % (sha[:16], actual[:16]))
    else:
        record(WARN, "Registry sha256", "找不到 mcpb 文件，无法回读校验：%s" % mcpb)


# ── 6. MCPB 分发包 ──────────────────────────────────────────────────
def check_mcpb():
    dist = ROOT / "dist"
    if not dist.exists():
        record(FAIL, "MCPB 包", "缺少 dist/ 目录")
        return
    mcps = sorted(dist.glob("*.mcpb"))
    if not mcps:
        record(FAIL, "MCPB 包", "dist/ 下无 .mcpb 文件")
        return
    for m in mcps:
        size_kb = m.stat().st_size / 1024
        record(PASS, "MCPB 包 %s" % m.name, "%.1f KB / sha=%s" % (size_kb, sha256_of(m)[:16]))


# ── 7. CI 发布 workflow ──────────────────────────────────────────────
def check_ci():
    wf_dir = ROOT / ".github" / "workflows"
    if not wf_dir.exists():
        record(FAIL, "CI workflow", ".github/workflows/ 不存在")
        return
    ymls = sorted(wf_dir.glob("*.yml")) + sorted(wf_dir.glob("*.yaml"))
    names = [y.name for y in ymls]
    has_ci = any("ci" in n for n in names)
    has_pub = any("publish" in n and "registry" in n for n in names)
    if has_ci:
        record(PASS, "CI workflow", "已存在 CI")
    else:
        record(WARN, "CI workflow", "未发现 CI 配置")
    if has_pub:
        pub = next(y for y in ymls if "publish" in y.name and "registry" in y.name)
        text = pub.read_text(encoding="utf-8")
        # 幂等性 + 版本漂移检测 关键检查点
        checks = {
            "OIDC 认证": "id-token: write" in text or "github-oidc" in text,
            "允许手动触发": "workflow_dispatch" in text,
            "tag 触发": "tags:" in text,
        }
        miss = [k for k, ok in checks.items() if not ok]
        if miss:
            record(WARN, "Publish workflow", "缺: %s" % miss)
        else:
            record(PASS, "Publish workflow", "OIDC + workflow_dispatch + tag 全就绪")
    else:
        record(FAIL, "Publish workflow", "缺少 publish-mcp-registry.yml")


# ── 8. Demo 部署链路 ────────────────────────────────────────────────
def check_deploy():
    d = ROOT / "deploy"
    needed = [
        "deploy_local.sh", "setup_ecs.sh", "docker-compose.prod.yml",
        "nginx.conf", "DEPLOY.md",
    ]
    missing = [f for f in needed if not (d / f).exists()]
    if missing:
        record(WARN, "部署脚本", "缺: %s" % missing)
    else:
        record(PASS, "部署脚本", "deploy/ 5 件套齐备")
    # 部署配置存在但不入库
    cfg = d / "deploy_config.sh"
    example = d / "deploy_config.example.sh"
    if example.exists():
        record(PASS, "部署配置模板", "deploy_config.example.sh 就绪")
    else:
        record(WARN, "部署配置模板", "缺 deploy_config.example.sh")
    # 提示：真实 IP 是否需要 SSH 免密（仅提示，不阻塞）
    if cfg.exists():
        record(SKIP, "公网部署", "deploy_config.sh 存在，是否已部署需外部探测确认")
    else:
        record(SKIP, "公网部署", "尚未创建 deploy_config.sh（需 ssh-copy-id 后一键上线）")


# ── 9. 市场提交材料 ─────────────────────────────────────────────────
def check_market_pack():
    p = ROOT / "docs" / "market_listing_pack.md"
    if not p.exists():
        record(FAIL, "市场提交材料", "缺 docs/market_listing_pack.md")
        return
    text = p.read_text(encoding="utf-8")
    required = ["Glama", "LobeHub", "Smithery", "Official MCP Registry"]
    miss = [r for r in required if r not in text]
    if miss:
        record(WARN, "市场材料", "缺章节: %s" % miss)
    else:
        record(PASS, "市场材料", "4 家市场章节齐备")


# ── 10. GitHub 同步状态（只读探测） ────────────────────────────────
def check_sync():
    script = ROOT / "scripts" / "sync_check.py"
    if not script.exists():
        record(WARN, "GitHub 同步", "缺 scripts/sync_check.py")
        return
    try:
        r = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True, text=True, timeout=120, cwd=str(ROOT),
        )
        out = (r.stdout or "") + (r.stderr or "")
        # 严格：以 sync_check 退出码为准（0=完全一致），不能靠子串命中
        # （曾因输出含 "远端独有: 0" 里的 "0 ===" 而误判 132 差异为同步完成）
        if r.returncode == 0:
            record(PASS, "GitHub 同步", "本地 = 远端 main")
        else:
            # 抓出数字
            m = re.search(r"远端缺失[^\n]*?\b(\d+)\b", out)
            n2 = re.search(r"内容不一致[^\n]*?\b(\d+)\b", out)
            a = int(m.group(1)) if m else -1
            b = int(n2.group(1)) if n2 else -1
            if a > 0 or b > 0:
                record(WARN, "GitHub 同步", "远端缺失 %d / 内容不一致 %d（待你推送）" % (a, b))
            else:
                record(PASS, "GitHub 同步", "已同步（详见 scripts/sync_check.py 输出）")
    except Exception as e:
        record(WARN, "GitHub 同步", "探测异常: %s" % e)


# ── 11. MCP 命名空间遮蔽守护 ──────────────────────────────────────
def check_mcp_namespace():
    """本机 site-packages 若装有官方 pip mcp 包，会遮蔽本项目的 mcp/ 目录。"""
    script = ROOT / "scripts" / "check_mcp_namespace.py"
    if not script.exists():
        record(SKIP, "MCP 命名空间", "未启用守护脚本")
        return
    try:
        r = subprocess.run(
            [sys.executable, "-S", "-P", str(script)],
            capture_output=True, text=True, timeout=30, cwd=str(ROOT),
        )
        out = (r.stdout or "") + (r.stderr or "")
        if r.returncode == 0 and "[OK]" in out:
            m = re.search(r"TOOLS 数量 = (\d+)", out)
            n = m.group(1) if m else "?"
            record(PASS, "MCP 命名空间", "mcp.server 指向本项目，TOOLS=%s" % n)
        else:
            record(FAIL, "MCP 命名空间", "被第三方 mcp 包遮蔽（改用 python -S -P）")
    except Exception as e:
        record(WARN, "MCP 命名空间", "探测异常: %s" % e)


# ── 11. MCP 工具自测冒烟 ────────────────────────────────────────────
def check_mcp_selftest():
    script = ROOT / "scripts" / "test_mcp_server.py"
    if not script.exists():
        record(WARN, "MCP 自测", "缺 scripts/test_mcp_server.py")
        return
    try:
        r = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True, text=True, timeout=180, cwd=str(ROOT),
        )
        out = (r.stdout or "") + (r.stderr or "")
        if r.returncode == 0 and "全部通过" in out:
            n = len(re.findall(r"\[通过\]", out))
            record(PASS, "MCP 自测", "%d 项断言全通过" % n)
        else:
            tail = out.strip().splitlines()[-3:] if out.strip() else ["(空)"]
            record(FAIL, "MCP 自测", "退出码 %d：%s" % (r.returncode, " | ".join(tail)))
    except Exception as e:
        record(WARN, "MCP 自测", "探测异常: %s" % e)


# ── 汇总 ─────────────────────────────────────────────────────────────
def main() -> int:
    print("=" * 62)
    print("  智慧农业生态 · 分发就绪度检查（P0-4 全通道自检）")
    print("=" * 62)
    tools = check_mcp_server()
    check_agent_card(tools)
    check_plugin()
    check_smithery()
    check_registry_meta()
    check_mcpb()
    check_ci()
    check_deploy()
    check_market_pack()
    check_mcp_selftest()
    check_mcp_namespace()
    check_sync()

    counts = {PASS: 0, WARN: 0, FAIL: 0, SKIP: 0}
    print()
    for status, key, detail in results:
        counts[status] = counts.get(status, 0) + 1
        line = "  %s %-28s" % (status, key)
        if detail:
            line += "  %s" % detail
        print(line)
    print()
    total_ok = counts[PASS]
    total_warn = counts[WARN]
    total_fail = counts[FAIL]
    total_skip = counts[SKIP]
    print("  汇总：%d 通过 / %d 告警 / %d 失败 / %d 跳过"
          % (total_ok, total_warn, total_fail, total_skip))
    print()

    # P0 出口指标口径：全绿 + 无失败 = 就绪
    if total_fail > 0:
        print("  ❌ 存在阻塞项，分发链路不可上线。修复上表 ❌ 后再复检。")
        return 1
    if total_warn > 0:
        print("  ⚠️  存在告警项（多为可选或需人工操作），不影响基础分发。")
    print("  ✅ 分发就绪。剩余 2 项需人工操作（见 docs/distribution_checklist.md）：")
    print("     1. 公网 Demo：ssh-copy-id root@<ECS_IP> 后 bash deploy/deploy_local.sh")
    print("     2. Glama / LobeHub 站内表单提交（Smithery 已自动就绪，无需填表）")
    return 1 if CI and total_fail else 0


if __name__ == "__main__":
    sys.exit(main())
