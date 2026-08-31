# 智慧农业生态 · Skill 注册表贡献指南

本目录存放农业 AI 助手的**机器可读 Skill 定义**（JSON），由 `schema.json` 约束。

## 现有 Skill

| Skill ID | 名称 | 领域 |
|----------|------|------|
| `climate_match` | 气候分区匹配 | 气候/水文 |
| `crop_adapt` | 作物-分区适配推荐 | 作物选择 |
| `growth_plan` | 种植计划生成 | 生长管理 |
| `pest_diagnose` | 病虫害诊断 | 植保 |
| `device_recommend` | 设备/工具推荐 | 设施/装备 |
| `supply_match` | 供需撮合 | 生态流通 |

## 如何新增一个 Skill

1. 复制任一现有 JSON 为 `your_skill_id.json`
2. 按 `schema.json` 填写字段，至少包含：
   - `id` / `name` / `version` / `domain`
   - `purpose`（用途）、`inputs`、`outputs`、`data_sources`
   - `safety_boundary`（安全边界，必填）
   - `reuse_value`（生态复用价值）
3. 校验合法性：
   ```bash
   python -c "import json; json.load(open('skills/registry/your_skill_id.json', encoding='utf-8'))"
   ```
4. 在 `agent/` 下实现对应 Agent 方法，并在 `orchestrator.py` 串入流水线
5. 在 `docs/agent_output_contract.md` 中登记该 Skill 的输出字段

## 命名约定

- `id` 用蛇形小写，全局唯一
- `version` 语义化（1.0 / 1.1 ...）
- `data_sources` 必须可追责（公开数据集 / 文献 / 实测），不可写"LLM 生成"

## 验收门槛

- 每个 Skill 必须能在 `scripts/verify_all.py` 中被真实数据驱动（无 PLACEHOLDER）
- 每个 Skill 输出必须符合 `docs/agent_output_contract.md` 的四段式契约
