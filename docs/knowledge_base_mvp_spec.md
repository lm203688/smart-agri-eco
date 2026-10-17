# 智慧农业生态 · 知识库 MVP 规格说明书

> **版本**: v1.0
> **日期**: 2026-10-15
> **状态**: 待批准（Gate 1）
> **对应审计**: `docs/knowledge_system_audit_2026-10-15.md`（813 行完整诊断）
> **文档类型**: 实施规格说明书（非研究稿）
> **阅读对象**: 项目维护者、Reviewer、后续 Sprint 执行者

---

## 0. 定位

### 0.1 本文档解决什么问题

审计报告（v1.0）诊断出：**项目缺少可被 AI 直接消费的结构化知识中间层**。
本文档给出 **MVP 规格**——用最小代价把这个中间层搭起来，使：

1. AI（Agent / MCP 客户端）能通过统一工具调用检索和验证知识
2. 知识条目具备可追溯的来源和可计算的置信度
3. 现有 83 个 recipe 能被"翻译"成结构化知识条目

### 0.2 MVP 边界声明

**MVP 必须做到**：
- 3 个 MCP 工具端到端可用（search / trace / verify）
- 10 个首批知识条目真实入库（不是骨架占位）
- 3 个 YAML schema 完成定义
- 与现有 21 个 MCP 工具无冲突，通过既有门禁

**MVP 明确不做**：
- 不实现知识图的完整图数据库（先用文件 + 内存图）
- 不做 embedding 向量索引（Sprint 3 之后再说）
- 不做多租户/权限（G1 前不需要）
- 不做知识自动发现（仅手工录入 + 半自动抽取）
- 不替换现有配方系统（共存）

### 0.3 与 G1 出口指标的关系

MVP 直接服务 G1：
- `agri_knowledge_search` 计入"外部工具调用"，为 G1 指标（≥500 次调用）做贡献
- 知识可追溯是 AgriTrust 徽章的**知识源基础**（M11-T1 已上线，但缺知识库支撑）
- 与 M12-K1（检索/图谱 MCP）呼应，为其提供**知识源**

---

## 1. 核心交付物（可验收清单）

| # | 交付物 | 形式 | 验收标准 |
|---|--------|------|---------|
| D1 | 三层知识模型规格 | 本文档 §2 | 定义完备，可指导实现 |
| D2 | YAML Schema v1 | `schemas/knowledge_*.schema.json` ×3 | JSON Schema 校验通过 |
| D3 | 首批 10 个知识条目 | `knowledge/knowledge_items/*.yaml` | 全部通过 schema 校验 |
| D4 | 本体 v0（30 概念 + 8 关系） | `knowledge/ontology/v0.yaml` | 覆盖 §2.2 清单 |
| D5 | `agri_knowledge_search` 工具 | MCP 工具 + 测试 | ≥500ms p99，覆盖 10 项种子 |
| D6 | `agri_knowledge_trace` 工具 | MCP 工具 + 测试 | 完整溯源链回溯 |
| D7 | `agri_knowledge_verify` 工具 | MCP 工具 + 测试 | 置信度计算与降级 |
| D8 | 质量评估脚本 | `scripts/evaluate_knowledge_quality.py` | 输出 §8 指标 JSON |

**Gate 1（设计批准）**：本文档 + 审计报告被 review 通过
**Gate 2（Sprint 1 交付）**：D1-D4 + D5 完成，通过全部门禁
**Gate 3（Sprint 2 交付）**：D6 完成，8 个 knowledge_item 有完整溯源
**Gate 4（Sprint 3 交付）**：D7 + D8 完成，质量指标基线可查

---

## 2. 三层知识模型

### 2.1 第 1 层：知识条目（KnowledgeItem）

**定义**：单一知识事实的可执行表达。一条 = 一个可被验证、可被引用、可被追溯的最小知识单元。

**YAML Schema**：

```yaml
# schemas/knowledge_item.schema.json (核心字段，完整字段见 §附录 A)

id: ki-YYYYMMDD-NNN           # 全局唯一，日期+序号
title: "玉米 4 叶期追氮推荐量"    # 一句话标题
type: recommendation            # 枚举：recommendation / threshold / method / pattern / constraint / fact
domain: cropping                # 枚举：cropping / irrigation / pest / soil / climate / facility / seed / policy
region: "North_Central_China"   # 可选；区域限定
version: 1                      # 语义化版本
supersedes: []                  # 被本条取代的旧条目 id 列表

content:
  # 结构化内容：按 type 不同而结构不同
  recommendation:
    input_conditions:
      - 条件字段: 条件值（支持范围/列表）
    output_action:
      action: "追氮"
      amount: 15                # 数值
      unit: kg/亩
      timing: 4_leaves          # 时相
    rationale: "华北平原夏玉米 4 叶期氮素需求峰值..."
    confidence: 0.85

threshold:
  variable: "soil.ph"
  range: {min: 6.5, max: 7.5}
  severity_if_out: warning

method:
  steps: ["步骤 1", "步骤 2", ...]
  preconditions: [...]

pattern:
  trigger_condition: "..."
  typical_response: "..."

constraint:
  rule: "..."
  scope: "..."

provenance:                     # 溯源链，见 §5
  - source_type: expert
    source_id: "Zhang_2024"
    confidence_contribution: 0.3
  - source_type: research
    source_id: "CN-CMA-2022-08"
    confidence_contribution: 0.4

confidence:
  score: 0.85                   # 0-1
  level: high                   # high/medium/low
  calculated_at: 2026-10-15T10:00:00Z
  calculation_method: "manual_weighted_v1"

verification:
  last_verified_at: 2026-10-15
  verified_by: "manual_review"
  verification_log: [...]

metadata:
  owner: "cropping_team"
  tags: ["corn", "nitrogen", "topdressing"]
  created_at: 2026-10-15
  updated_at: 2026-10-15
  changelog: []

relations:
  related_to: [ki-20261015-001]
  contradicts: []
  refines: []
  applies_to: ["recipe:corn-4leaf-n15"]
```

### 2.2 第 2 层：本体（Ontology）

**定义**：领域概念、关系、属性的规范化定义。用于：
- 跨知识条目的语义关联
- 自动校验（如"pest_type 必须在 `pest_types` 集合内"）
- 未来 LLM 结构化输出的约束

**MVP v0 本体覆盖（30 概念 + 8 关系）**：

| 概念类别 | 具体概念 | 数量 |
|---------|---------|-----|
| 农业主体 | Crop, Plant, Pest, Disease, Weed, Animal, Microorganism | 7 |
| 环境与资源 | Soil, Water, Air, Climate, Nutrient, Equipment, Material | 7 |
| 时间与空间 | Season, GrowthStage, TimePeriod, Region, Coordinate | 5 |
| 动作与方法 | Activity, Technique, Treatment, Recommendation, Constraint | 5 |
| 知识与信息 | Knowledge, Source, Confidence, Quality, Evidence | 5 |
| **概念合计** | | **30** |

**8 种关系类型**：

| 关系 | 含义 | 示例 |
|-----|------|------|
| `applies_to` | 知识适用于对象 | recommendation.applies_to.recipe |
| `depends_on` | 依赖前置 | recommendation.depends_on.threshold |
| `refines` | 精化更粗的 | region-specific.refines.general |
| `contradicts` | 与另一条冲突 | new.found.contradicts.old.rule |
| `supersedes` | 取代旧版 | v2.supersedes.v1 |
| `derived_from` | 派生自 | pattern.derived_from.recommendation |
| `validates` | 支持验证 | experiment.validates.recommendation |
| `excludes` | 排除适用 | region_exclusion.excludes.recommendation |

**本体文件结构**（`knowledge/ontology/v0.yaml`）：

```yaml
version: "v0"
created: 2026-10-15
concepts:
  - name: Crop
    category: agent
    description: "被种植的植物物种"
    properties:
      - name: variety
        type: string
        required: false
  # ... 其余 29 个
relations:
  - name: applies_to
    direction: directed
    multiplicity: "many-to-many"
    description: "知识条目适用于具体对象"
```

### 2.3 第 3 层：知识图（KnowledgeGraph）

**定义**：由所有 knowledge_item + 其 relations 构成的有向图。用于图查询、路径分析、影响传播。

**MVP 实现方式**：
- 存储：不引入图数据库（Neo4j 等）
- 加载：从 `knowledge/knowledge_items/*.yaml` 扫描构建内存图
- 查询：Python 内存遍历，支持 depth ≤3 的关系链查询

**图构建规则**：
1. 每个 knowledge_item 成为图的一个节点（label = type）
2. 每个 relations 字段中的项成为边（label = 关系类型）
3. 每个 ontology 概念实例可注册为图节点（用于跨条目关联）

**MVP 支持的图查询**（`agri_knowledge_search` 内部实现）：
- `neighbors(node_id, depth=1..3)` — 邻域查询
- `path(from, to, max_depth=5)` — 路径查找
- `subgraph(type_filter, tag_filter)` — 子图过滤

---

## 3. 数据目录结构

```
knowledge/
├── README.md                           # 知识库使用说明
├── knowledge_items/                    # 第 1 层：所有知识条目
│   ├── corn/                           # 按作物分目录
│   │   ├── ki-20261015-001.yaml        # 玉米 4 叶期追氮
│   │   ├── ki-20261015-002.yaml        # 玉米花期水肥
│   │   └── ...
│   ├── irrigation/
│   │   ├── ki-20261015-003.yaml
│   │   └── ...
│   ├── pest/
│   │   └── ki-20261015-005.yaml
│   ├── soil/
│   │   └── ki-20261015-007.yaml
│   └── _templates/
│       ├── recommendation.yaml
│       ├── threshold.yaml
│       ├── method.yaml
│       └── pattern.yaml
├── ontology/
│   ├── v0.yaml                         # 本体 v0
│   └── CHANGELOG.md
├── provenance/                         # 溯源记录
│   ├── sources/                        # 外部来源登记
│   │   ├── expert_zhang.yaml
│   │   ├── research_CMA-2022.yaml
│   │   └── experiment_trial-2026.yaml
│   └── verification_log.jsonl          # 验证事件流
├── quality/
│   ├── evaluation_report.json          # 质量指标快照
│   └── quality_history.jsonl           # 历史质量追踪
└── tools/                              # 辅助脚本（可选）
    └── export_to_markdown.py           # 导出人可读版本
```

**首批 10 个知识条目选题**（对齐 G1 优先级）：

| # | ID | 领域 | 内容 |
|---|----|------|-----|
| 1 | ki-20261015-001 | cropping | 华北夏玉米 4 叶期追氮推荐量 |
| 2 | ki-20261015-002 | cropping | 华北夏玉米大喇叭口期施肥时机 |
| 3 | ki-20261015-003 | irrigation | 华北小麦冬灌时机判断阈值 |
| 4 | ki-20261015-004 | soil | 华北酸性土壤（pH<5.5）施石灰方案 |
| 5 | ki-20261015-005 | pest | 棉铃虫低龄幼虫防治阈值 |
| 6 | ki-20261015-006 | cropping | 冬小麦返青期水肥管理 |
| 7 | ki-20261015-007 | soil | 盐碱地改良（pH>8.5）技术路线 |
| 8 | ki-20261015-008 | climate | 华北春旱预警阈值 |
| 9 | ki-20261015-009 | cropping | 东北春玉米播期选择 |
| 10 | ki-20261015-010 | policy | 化肥减量增效政策约束 |

---

## 4. 置信度模型（MVP 简化版）

### 4.1 计算规则

**加权求和 + 衰减因子**：

```
confidence.score = Σ(source.confidence_contribution) × recency_factor × verification_factor
```

其中：
- `recency_factor = 1.0` 若 last_verified_at 距今 ≤1 年，`0.85` 若 1-2 年，`0.7` 若 2-3 年，`0.5` 若 >3 年
- `verification_factor = 1.0` 若 verified_by ∈ {field_trial, expert_confirm}，`0.9` 若 = manual_review，`0.75` 若 = source_reported

### 4.2 分级

| score 范围 | level | 行为 |
|-----------|-------|------|
| ≥0.80 | high | 直接可用于决策 |
| 0.60-0.80 | medium | 可用于决策但标注置信度 |
| 0.40-0.60 | low | 仅供参考，触发"需验证"提示 |
| <0.40 | deprecated | 应被替代或删除 |

### 4.3 降级与升级

- **自动降级**：`confidence.score` 每 6 个月复算一次，`recency_factor` 自然下降
- **人工升级**：验证事件（field_trial / expert_confirm）将 `verification_factor` 提升并刷新时间戳
- **强制废弃**：被 `supersedes` 引用的条目，`verification.last_verified_at` 不再更新

---

## 5. 溯源模型

### 5.1 溯源链结构

每条 knowledge_item 的 `provenance` 是一个有序列表，每项包含：

```yaml
provenance:
  - source_type: expert | research | experiment | field_trial | ai_generated | policy
    source_id: "Zhang_2024"         # 唯一标识
    source_ref: "path or URL"        # 完整引用
    confidence_contribution: 0.3     # 该来源对本条置信度的贡献权重
    accessed_at: 2026-10-15
    verified_at: 2026-10-15
    verifier: "manual_review"
```

### 5.2 溯源链追溯规则

1. **正向追溯**（本条 → 来源）：直接读取 `provenance[].source_ref`
2. **反向追溯**（来源 → 使用本来源的所有条目）：扫描 `knowledge/knowledge_items/**/*.yaml` 匹配 `source_id`
3. **链式追溯**（来源 → 派生条目）：若 knowledge_item A 引用 knowledge_item B，则 A 的 provenance 需包含 B 的 id，形成溯源链

### 5.3 溯源链完整性校验

`scripts/check_knowledge_provenance.py` 校验规则：
- [ ] 所有 `provenance[].source_id` 都能在 `knowledge/provenance/sources/` 找到对应登记
- [ ] 所有 `verification_log[].verifier` 非空
- [ ] 若 `provenance` 为空，`confidence.level` 必须 ≤ low（禁止无溯源的高置信）
- [ ] `supersedes` 引用必须指向真实存在的 id

---

## 6. MCP 接口

### 6.1 `agri_knowledge_search`（Sprint 1）

**功能**：搜索知识库中的条目，支持多条件过滤 + 全文关键字。

**请求参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `query` | string | 否 | 全文搜索（匹配 title + content + tags） |
| `type` | string | 否 | 条目类型过滤 |
| `domain` | string | 否 | 领域过滤 |
| `region` | string | 否 | 区域过滤 |
| `tags` | list[string] | 否 | 标签过滤（AND 语义） |
| `min_confidence` | float | 否 | 最低置信度 |
| `limit` | int | 否 | 默认 20，最大 100 |
| `offset` | int | 否 | 分页偏移 |

**响应**：

```json
{
  "total": 42,
  "limit": 20,
  "offset": 0,
  "results": [
    {
      "id": "ki-20261015-001",
      "title": "玉米 4 叶期追氮推荐量",
      "type": "recommendation",
      "domain": "cropping",
      "region": "North_Central_China",
      "confidence": {"score": 0.85, "level": "high"},
      "snippet": "华北平原夏玉米 4 叶期追氮 15 kg/亩..."
    }
  ],
  "query_time_ms": 12
}
```

**约束**：
- 内存中扫描，非实时索引（MVP 数据量 ≤100 条，性能可接受）
- p99 响应时间 ≤500ms（G1 门禁要求）

### 6.2 `agri_knowledge_trace`（Sprint 2）

**功能**：查询指定知识条目的完整溯源链。

**请求参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `knowledge_id` | string | 是 | 知识条目 id |
| `depth` | int | 否 | 溯源深度，默认 1 |
| `direction` | string | 否 | forward/backward/both，默认 forward |

**响应**：

```json
{
  "knowledge_id": "ki-20261015-001",
  "chain": {
    "forward": {
      "sources": [
        {
          "source_type": "expert",
          "source_id": "Zhang_2024",
          "source_ref": "https://...",
          "confidence_contribution": 0.3
        }
      ],
      "verification_log": [...]
    },
    "backward": {
      "used_by": ["ki-20261015-003", "ki-20261015-007"]
    }
  },
  "graph_neighbors": {
    "related_to": ["ki-20261015-002"],
    "contradicts": [],
    "refines": []
  },
  "trace_time_ms": 18
}
```

### 6.3 `agri_knowledge_verify`（Sprint 3）

**功能**：触发知识条目的置信度重算与验证状态更新。

**请求参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `knowledge_id` | string | 是 | |
| `verification_type` | string | 是 | field_trial / expert_confirm / manual_review / source_reported |
| `verifier` | string | 是 | 验证人标识 |
| `result` | string | 否 | 验证结果摘要 |
| `force_recalc` | bool | 否 | 强制重算置信度 |

**响应**：

```json
{
  "knowledge_id": "ki-20261015-001",
  "verification": {
    "verified_at": "2026-10-15T10:00:00Z",
    "verified_by": "Zhang",
    "result_summary": "现场验证：华北玉米 4 叶期追氮推荐量与实测吻合"
  },
  "confidence_update": {
    "old_score": 0.72,
    "new_score": 0.88,
    "delta": 0.16,
    "new_level": "high",
    "factors": {
      "recency_factor": 1.0,
      "verification_factor": 1.0
    }
  }
}
```

---

## 7. 三阶段交付计划

### Sprint 1（Sprint M1，2 周）— 骨架与种子

**目标**：三层模型可运行，10 个种子知识条目入库，`agri_knowledge_search` 工具可用。

| 工作项 | 交付物 | 工作量 |
|-------|--------|-------|
| S1-1 | 定义 3 个 YAML schema | 4 小时 |
| S1-2 | 编写 30 概念 + 8 关系本体 v0 | 3 小时 |
| S1-3 | 创建目录结构 + README | 1 小时 |
| S1-4 | 填充 10 个种子知识条目 | 8 小时 |
| S1-5 | 实现 `agri_knowledge_search` 工具 | 6 小时 |
| S1-6 | 编写单测（≥15 用例） | 4 小时 |
| S1-7 | 全部门禁跑通 | 2 小时 |
| **合计** | | **28 小时** |

**验收**：
- [ ] 10 个 knowledge_item 通过 schema 校验
- [ ] `agri_knowledge_search` 在 MCP 中可调用，返回 10 条种子
- [ ] 新增单测 ≥15 项，全套 785+15=800 项全绿
- [ ] §六 门禁 14 项全绿

### Sprint 2（Sprint M2，2 周）— 溯源与关联

**目标**：溯源链完整可追溯，`agri_knowledge_trace` 上线，首批 8 个条目完成链式追溯。

| 工作项 | 交付物 | 工作量 |
|-------|--------|-------|
| S2-1 | 实现溯源链校验脚本 | 4 小时 |
| S2-2 | 完成 8 个条目的溯源登记（provenance/sources/） | 6 小时 |
| S2-3 | 实现 `agri_knowledge_trace` 工具 | 6 小时 |
| S2-4 | 知识图内存构建 + 邻域/路径查询 | 5 小时 |
| S2-5 | 本体校验（引用完整性） | 3 小时 |
| S2-6 | 单测（≥15 项）+ 门禁 | 4 小时 |
| **合计** | | **28 小时** |

**验收**：
- [ ] 8 个条目具备完整溯源链
- [ ] `agri_knowledge_trace` 返回 forward + backward 双向链
- [ ] 新增单测 ≥15 项，全套 815 项全绿

### Sprint 3（Sprint M3，2 周）— 置信度与质量

**目标**：置信度模型可计算可追溯，`agri_knowledge_verify` 上线，质量指标基线建立。

| 工作项 | 交付物 | 工作量 |
|-------|--------|-------|
| S3-1 | 实现置信度计算引擎（v1 加权） | 4 小时 |
| S3-2 | 实现 `agri_knowledge_verify` 工具 | 6 小时 |
| S3-3 | 质量评估脚本 + 指标看板 | 4 小时 |
| S3-4 | 6 个月自动降级 cron（可选） | 2 小时 |
| S3-5 | 83 个 recipe → knowledge_item 转换脚本 | 8 小时 |
| S3-6 | 转换 20 个代表性 recipe 作为第二批条目 | 6 小时 |
| S3-7 | 单测（≥15 项）+ 门禁 | 4 小时 |
| **合计** | | **34 小时** |

**验收**：
- [ ] `agri_knowledge_verify` 可触发置信度重算
- [ ] 质量报告 JSON 输出，含 §8 所有指标
- [ ] 至少 20 个原 recipe 转为 knowledge_item
- [ ] 全套 830 项单测全绿

---

## 8. 验收标准

### 8.1 功能验收

| 指标 | 目标值 | 测量方法 |
|------|-------|---------|
| 知识库条目总数 | ≥10（Sprint 1）/ ≥30（Sprint 3） | `find knowledge/knowledge_items -name "*.yaml" \| wc -l` |
| Schema 校验通过率 | 100% | `scripts/check_knowledge_schema.py` |
| 溯源链完整性 | ≥80%（Sprint 2）/ ≥90%（Sprint 3） | 覆盖率 = 有溯源的条目 / 总条目 |
| 平均置信度 | ≥0.65 | `quality/evaluation_report.json` |
| MCP 工具端到端调用成功率 | ≥99% | 门禁测试 |
| p99 响应时间 | ≤500ms | `agri_recipe_bench` 记录 |

### 8.2 质量验收

- [ ] **不编造**：所有 provenance 引用必须可点击访问或存在于本地文件
- [ ] **可追溯**：每条 entry 至少 1 个 source，≥3 项 source 才允许 `confidence ≥0.7`
- [ ] **零破坏**：现有 83 个 recipe、21 个 MCP 工具、11 个 schema、门禁 14 项全部保持绿
- [ ] **可撤销**：`knowledge/` 目录整体删除不影响主系统运行（除新加的 3 个 MCP 工具外）

### 8.3 结构验收

- [ ] 三层模型全部实现（条目 / 本体 / 图）
- [ ] 目录结构与 §3 一致
- [ ] 每个 schema 有对应示例文件
- [ ] 每份 YAML 通过对应 schema 校验
- [ ] 本体 v0 覆盖 §2.2 全部 30 概念 + 8 关系

### 8.4 集成验收（与 G1 对齐）

- [ ] 新增 3 个 MCP 工具通过 `python scripts/test_mcp_server.py`
- [ ] 新增 3 个 MCP 工具的分类、描述、参数符合现有 MCP 规范
- [ ] `scripts/check_agent_card.py` 通过（工具总数从 21 → 24）
- [ ] `scripts/check_distribution_readiness.py` 通过
- [ ] `python -m unittest discover -s scripts -p "test_*.py"` 全绿
- [ ] `python -m benchmarks.ratchet_modules --strict` 27/27

---

## 9. 与现有资产的关系

### 9.1 现有资产映射

| 现有资产 | MVP 中的角色 | 处理策略 |
|---------|-------------|---------|
| 83 个 recipe YAML | 部分转为 knowledge_item | Sprint 3 转换 20 个代表性 recipe |
| 21 个 MCP 工具 | 保持不变 + 新增 3 个 | 完全兼容，无冲突 |
| 11 个 JSON schema | 保持不变 + 新增 3 个 | 独立 schema，不合并 |
| 130+ scripts | 保持不变 + 新增 5 个 | 知识库专用脚本 |
| CORE_OBJECTIVE | 保持为权威源 | 知识库服务其目标，不覆盖 |
| AgriRecipeBench | 保持不变 | 未来可加入知识库测试子集 |

### 9.2 依赖关系

- **MVP 无强外部依赖**：纯 YAML + 标准库，不引入 Neo4j / Redis / pgvector
- **可选增强**：Sprint 4+ 可引入 `fastembed`（本地 embedding）+ `lancedb`（向量库），但不在 MVP 范围

### 9.3 与审计发现的对齐

| 审计发现（813 行报告） | MVP 应对 |
|----------------------|---------|
| 4.1 无统一知识模型 | §2 三层模型 + 3 schema |
| 4.2 置信度未量化 | §4 加权模型 + verify 工具 |
| 4.3 无溯源链 | §5 溯源模型 + trace 工具 |
| 4.4 分散无索引 | `agri_knowledge_search` 工具 |
| 4.5 本体缺失 | §2.2 30 概念 + 8 关系本体 v0 |
| 4.6 无知识分类 | YAML 中 `type/domain/region/tags` 字段 |
| 4.7 无验证机制 | verify 工具 + 验证日志 |
| 4.8 缺质量评估 | `evaluate_knowledge_quality.py` |
| 4.9 与现有资产割裂 | §9.1 映射 + Sprint 3 转换 20 recipe |
| 4.10 无知识生命周期 | version + supersedes + 自动降级 |

---

## 10. 明确不做什么（Out of Scope）

为避免范围蔓延，明确以下内容**不在 MVP 范围内**：

1. **不实现图数据库**：MVP 用内存图，不上 Neo4j / NebulaGraph
2. **不做向量索引**：embedding 检索在 Sprint 4+ 才考虑
3. **不做多租户**：G1 前无需求
4. **不做权限控制**：MCP 层已有统一访问控制
5. **不做知识自动发现**：MVP 阶段手工录入 + 半自动抽取
6. **不替换配方系统**：knowledge 与 recipe 共存，Sprint 3 才做转换
7. **不做 LLM 生成知识条目**：MVP 只允许 AI 辅助录入、不允许 AI 独立创建条目
8. **不做跨项目知识联邦**：单仓库内自洽
9. **不做知识订阅推送**：MVP 只支持拉取（search），不支持推送（push）
10. **不做 UI 界面**：MCP 是唯一入口

---

## 11. 风险与依赖

### 11.1 技术风险

| 风险 | 概率 | 影响 | 缓解 |
|------|-----|------|------|
| MCP 工具超时（>500ms） | 低 | 中 | MVP 数据量小（≤100 条），内存扫描足够；后续再优化 |
| 知识条目质量参差 | 中 | 高 | Sprint 1 只填 10 个高标准条目，避免批量低质量 |
| 溯源链断裂 | 中 | 中 | `check_knowledge_provenance.py` 强制校验 |
| Schema 频繁变更 | 中 | 低 | 语义化版本号 + `supersedes` 字段 |
| 与 G1 时间冲突 | 中 | 高 | Sprint 划分严格 2 周一段，Sprint 1 独立可交付 |

### 11.2 依赖项

- **人工审核**：Sprint 1 需要专家审核 10 个种子条目的准确性（约 3 小时）
- **外部数据源**：Sprint 2 溯源链需要真实的文献/专家/实验引用（约 5 小时找引用）
- **门禁维护**：每次新增脚本需保证 §六 14 项门禁全绿（每次 30 分钟）

### 11.3 决策点（需用户批准）

1. **知识库目录位置**：`knowledge/`（推荐）vs `docs/knowledge/`（次要）
2. **本体 v0 概念集**：30 个概念是否够？是否需要扩展到 50 个
3. **首批 10 条选题**：是否调整作物/领域覆盖范围
4. **Sprint 3 recipe 转换策略**：全量转换 vs 选择性转换 20 个

---

## 12. 附录

### 附录 A：完整 knowledge_item Schema 字段清单

见 `schemas/knowledge_item.schema.json`（Sprint 1 交付）。

### 附录 B：本体 v0 完整概念表

见 `knowledge/ontology/v0.yaml`（Sprint 1 交付）。

### 附录 C：置信度计算代码示例

```python
def calculate_confidence(item: dict) -> float:
    """MVP v1 置信度计算"""
    from datetime import datetime, timezone
    
    # 1. 来源贡献
    source_sum = sum(
        p.get("confidence_contribution", 0.1)
        for p in item.get("provenance", [])
    )
    
    # 2. 时效因子
    last_verified = item.get("verification", {}).get("last_verified_at")
    if not last_verified:
        recency_factor = 0.5
    else:
        age_days = (datetime.now(timezone.utc) - parse_date(last_verified)).days
        if age_days <= 365:
            recency_factor = 1.0
        elif age_days <= 730:
            recency_factor = 0.85
        elif age_days <= 1095:
            recency_factor = 0.7
        else:
            recency_factor = 0.5
    
    # 3. 验证方式因子
    verified_by = item.get("verification", {}).get("verified_by", "")
    if verified_by in ("field_trial", "expert_confirm"):
        verification_factor = 1.0
    elif verified_by == "manual_review":
        verification_factor = 0.9
    else:
        verification_factor = 0.75
    
    score = round(source_sum * recency_factor * verification_factor, 3)
    return max(0.0, min(1.0, score))
```

### 附录 D：与 G1 出口指标的关系

| G1 指标 | 目标 | MVP 贡献 |
|--------|------|---------|
| MCP 累计外部调用 ≥500 次 | 2026-12 中旬截止 | `agri_knowledge_search` 作为高频工具，预计月调用量 100+ |
| 独立调用方 ≥20 个 | 2026-12 中旬截止 | 知识库是差异化能力，吸引新调用方 |
| P0 全绿 3 个月零外部调用则降级 | 决策门 | MVP 提供持续外部调用能力，降低降级风险 |
| AgriTrust 徽章覆盖率 | 100% recipe 已覆盖 | MVP 补齐"知识源"一环，徽章更完整 |

### 附录 E：文件位置速查

| 组件 | 路径 |
|------|------|
| 本文档 | `docs/knowledge_base_mvp_spec.md` |
| 审计报告 | `docs/knowledge_system_audit_2026-10-15.md` |
| 项目愿景 | `docs/CORE_OBJECTIVE.md` |
| 知识库根目录 | `knowledge/` |
| Schema 目录 | `schemas/knowledge_*.schema.json` |
| MCP 工具实现 | `mcp/server.py`（新增 3 个 tool handler） |
| 知识库单测 | `scripts/test_knowledge_*.py` |
| 质量评估脚本 | `scripts/evaluate_knowledge_quality.py` |
| 溯源校验脚本 | `scripts/check_knowledge_provenance.py` |
| Recipe 转换脚本 | `scripts/convert_recipe_to_knowledge.py` |

---

## 修订记录

| 版本 | 日期 | 变更 | 作者 |
|-----|------|------|------|
| v1.0 | 2026-10-15 | 初版，待 Gate 1 批准 | assistant |
