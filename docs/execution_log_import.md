# execution_log 导入规范（A1 · 闭环数据 A）

> 状态：v1.0.0 · 2026-09-07
> 配套：`schemas/execution_log.schema.json`（单条规范条目）、`agent/execution_log.py`（零依赖导入器）
> 来源：借鉴研发清单 `docs/opensource_scan_complementary.md` 的 A1 项（mcp-kasvanta 活动日志对接 Env Recipe 的 `execution_log`/`outcome`）

---

## 1. 为什么做这个

Env Recipe 协议的核心护城河是 `execution_log` + `outcome`（独占数据 A：配方→执行→结果三元组），事后补字段是数据工程里最贵的错误。`mcp-kasvanta`（drewherron，MIT，Python）用 SQLite 持久记录「你做了什么」（植物/位置/活动/时间/笔记），正好是 execution_log 的天然上游。本规范把 kasvanta 活动记录映射为规范 entry，让孤儿设备/手写记录也能回填 execution_log，先有执行侧数据，再逐步补全 outcome。

---

## 2. 字段映射表（kasvanta → execution_log 规范条目）

| kasvanta 记录字段 | 规范 entry 字段 | 映射说明 |
|---|---|---|
| `plant` | `recipe_ref`（推导） | 格式 `crop:full_cycle:other`；若已知 stage/device 可显式传 `recipe_ref` |
| `location` | `device_id` | 匿名位置即设备/地块 ID，孤儿设备社区可凭此对账 |
| `activity` | `actions_taken` | 单条活动转数组，如 `["浇水"]` |
| `timestamp` | `started_at` | ISO 8601；缺失则占位 `1970-01-01T00:00:00Z` |
| `notes` | `observations` | 自由文本/笔记原样带入 |
| （无） | `actual_params` | kasvanta 不记录设备参数 → 留空对象 + `params_unknown: true` |
| （无） | `outcome_ref` | **不导入**：kasvanta 不追踪产量，需用户/农艺师后续补全 `outcome` |

> 导入为**单向、非破坏**：原 kasvanta 记录不改动，仅生成映射后的 entry 追加进 recipe。

---

## 3. 用法

```python
from agent import execution_log as el

# 单条
entry = el.import_kasvanta_record({
    "plant": "番茄", "location": "阳台A", "activity": "浇水",
    "timestamp": "2026-09-07T08:30:00Z", "notes": "叶尖轻微萎蔫，补 200ml",
})
ok, errs = el.validate_entry(entry)

# 批量
entries = el.import_kasvanta_batch(kasvanta_records)

# 挂到配方
recipe = el.load_recipe("data/examples/sample_env_recipe.json")
for e in entries:
    el.attach_entry(recipe, e)
el.save_recipe("data/env_recipes/xxx.json", recipe)
```

自测：`python agent/execution_log.py`（零依赖，断言 entry 校验通过并成功挂载）。

---

## 4. 后续（闭环补全）

1. **outcome 回填**：kasvanta 无产量字段，需提供「结果回填」入口（用户评分/农艺师标注），把 `outcome` 与 `execution_log` 经 `run_id`/`outcome_ref` 配对。
2. **双向共建**：提案与 kasvanta 维护者共建「配方→执行→结果」开放标准，使任意花园 MCP 的活动日志都能零摩擦导入 Env Recipe，扩大数据 A 的采集面（见 p0f 文档 A1 投递项）。
3. **校验升级**：当前 `validate_entry` 为轻量结构校验；若需完整 JSON Schema 校验，待引入零依赖校验库或手扩枚举/类型检查。
