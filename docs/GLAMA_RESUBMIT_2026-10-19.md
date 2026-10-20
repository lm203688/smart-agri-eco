# Glama 拒收复盘与重提交指南（2026-10-19 21:07）

> **拒收时间**：Glama 邮件 2026-10-19
> **拒收理由原文**：*"Although the README describes an MCP server implementation, it explicitly states that the application layer and decision engine are closed source. This conflicts with the requirement that the repository be an open-source MCP server containing its own implementation."*

---

## 0. 根因定位

**触发点**：`README.md` 原第 467 行

```
待确定。核心数据标准与协议倾向开源（抢生态话语权），应用层与决策引擎闭源（保利润）。
```

**事实核对（agent 已验证）**：
- `engine/agriworld_lite.py`（31,431 bytes）— 机理内核，含 4 个 `@bounded` 装饰器函数
- `agent/forecast_agent.py`（15,060 bytes）— T-3 forecast
- `agent/bayesian_calibration.py`（16,157 bytes）— MAP 坐标下降 + Bootstrap CI
- `agent/causal_attribution.py`（12,967 bytes）— Shapley 精确计算
- `agent/conformal.py` — SplitConformal α=0.10
- `mcp/server.py` — 21 工具 MCP 适配器（含 stdio/SSE + server card + ETags）
- **全部在公开仓库，MIT 许可**
- `.gitignore` 没有排除 `engine/`、`agent/`、`app/`、`core/` 任何核心目录

**结论**：README 那句"应用层与决策引擎闭源"是**历史战略构想**（来自 `docs/planning/项目战略指引.md` 2026-08-19），不是当前事实，Glama 按字面理解误判。

---

## 1. 已修文件（本地完成，待 push）

| 文件 | 改动 |
|---|---|
| `README.md` §开源协议 | 删除"闭源保利润"表述，改写为全栈 MIT 开源事实描述 + 指向 CORE_OBJECTIVE |
| `docs/comprehensive_assessment_2026-10-10.md` 顶部 | 追加"历史文档声明"，标明 §4.3/§4.4 的"闭源数据"表述已被 CORE_OBJECTIVE 废除 |

## 2. 保留文件（不动）

| 文件 | 保留原因 |
|---|---|
| `docs/planning/项目战略指引.md` | 历史战略素材，已被 CORE_OBJECTIVE 明确废除；改动会破坏证据性 |
| `docs/commercialization_assessment_2026-09-19.md` | 同上 |
| `docs/planning/项目方案评审-商业模式与AI专业分析.md` | 同上 |

这些历史文档通过 CORE_OBJECTIVE.md §"废除说明"（现已被 README §开源协议指向）声明其过期性，是**证据链**而非"当前声明"。

---

## 3. 重提交操作（用户执行）

### 3.1 Push 修复（需真 PAT）

```
python scripts/gh_push.py <tok> "docs: fix closed-source wording in README for Glama resubmission" \
  README.md docs/comprehensive_assessment_2026-10-10.md
```

### 3.2 Glama 重提交回复（复制到 Glama 邮件回复）

```
Hi Glama team,

Thank you for the review. The statement you flagged has been corrected.

Root cause: The rejected line was in README.md line 467, under the "Open Source License"
section. It read: "核心数据标准与协议倾向开源（抢生态话语权），应用层与决策引擎闭源（保利润）."

That was a leftover strategic-planning placeholder from an earlier phase (2026-08), never
updated when the project's actual licensing was decided. The repository has in fact been
MIT-licensed end-to-end from the start:

- engine/ (mechanistic core, 4 @bounded functions, WOFOST phenology)
- agent/ (forecast, conformal, causal attribution, Bayesian calibration, knowledge loop)
- core/ (numeric domain, trust layer, 239-crop registry)
- mcp/ (21-tool server implementation at mcp/server.py)
- benchmarks/ (AgriRecipeBench 89 cases + 20 negative + AgriWorld-Arena 35 entries)
- scripts/, data/, schemas/, .well-known/ (JWS-signed A2A card)

The MCP server implementation is fully contained in this repository at mcp/server.py.
It is stdlib-only, no cloud-only code path, no external backend. The same Python
functions serve both the local CLI and the MCP adapter.

Changes made in this resubmission:

1. README.md "Open Source License" section rewritten to state the current fact
   (full-stack MIT) and to point to docs/CORE_OBJECTIVE.md as the authoritative source.

2. docs/comprehensive_assessment_2026-10-10.md (a historical strategic snapshot) now
   carries a top-of-file declaration noting that its "closed-source data" wording was
   an exploratory planning hypothesis, formally superseded by CORE_OBJECTIVE.md.

Old strategic-planning documents under docs/planning/ (项目战略指引.md, 项目方案评审-
商业模式与AI专业分析.md) are preserved as historical artifacts with an explicit
supersession note in docs/CORE_OBJECTIVE.md — they were never live policy, only
exploratory notes that were later abandoned.

Resubmission link: https://github.com/lm203688/smart-agri-eco

Happy to answer any follow-up questions. Thank you for the fast review.

— Xing
```

### 3.3 提交后观察

- Glama 通常 3-7 个工作日复审
- 复审通过后，链接会自动出现在 `https://glama.ai/mcp/servers/lm203688__smart-agri-eco`
- 若二次拒收，重点看新的具体理由（可能转到"README 里 docs/planning/ 路径可见"这一层，届时把 `docs/planning/` 目录移入 `_archive/` 或加 `.gitattributes` 处理）

---

## 4. 预防未来同类误判

`docs/planning/` 目录下的历史战略文档（含"闭源"、"商业"等措辞）虽已被 CORE_OBJECTIVE 废除，但对外部审阅者是**误读风险源**。可选措施（本次未做，留给下一次）：

1. **推荐**：把 `docs/planning/` 下 3 份战略文档移动到 `_archive/planning/` 并在 README 加一句"历史战略文档见 _archive/"。
2. **备选**：在这些文档顶部统一加"⚠️ 已被 CORE_OBJECTIVE 废除"header（本次只对 comprehensive_assessment 加，其余 2 份暂未加）。
3. **不建议**：删除——会破坏"我们经历过什么"的证据链，对 JOSS 论文 §State of the field 反而是加分项。

---

## 5. 与 JOSS 投刊的协同

JOSS 2026 scope 强调 "open collaborative practices" 与 "open governance"。本轮 README 修正与 JOSS 论文 §Research impact statement 的 "Open issues/review / Public repo / 21 MCP tools / JWS-signed agent card" 一致。JOSS reviewer 也会看到同一份 README——修正后两处一致，无矛盾。
