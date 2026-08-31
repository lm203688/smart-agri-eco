# 农业 AI 助手 · Agent 输出契约

> 所有 Agent 输出必须遵循此契约，确保"每条建议都有据可查、有度可评、有条件可依"。

---

## 强制三段式结构

每条 Agent 输出必须包含以下三个字段：

### 1. `evidence` — 证据链

```json
{
  "data_sources": ["WorldClim 2.1", "FAO GAEZ"],
  "zone_id": "subtropical_wet",
  "zone_name": "亚热带湿润带",
  "climate_class": "Cfa",
  "crop_db_version": "1.0",
  "recommendation_count": 3,
  "data_recency_years": 2
}
```

**规则**：
- `data_sources` 必须列出所有引用的数据源名称和版本
- `zone_id` 必须引用 `data/zone_meta/global_zones.json` 中的真实 zone_id
- `data_recency_years` 标记数据距当前年份（用于判断是否过期）

### 2. `confidence` — 置信度

```json
{
  "rubric_score": 0.85,
  "coverage_pct": 0.7,
  "confidence_note": "该作物在亚热带湿润带的适应数据覆盖度较高，但微气候修正因子缺失"
}
```

**评分规则**：

| 维度 | 权重 | 评分依据 |
|------|------|---------|
| 数据覆盖度 | 40% | 该分区×作物的历史数据密度 |
| 数据新鲜度 | 20% | 数据更新是否在 3 年内 |
| 分区精度 | 20% | 宏观分区 vs 微气候修正 |
| 专家一致性 | 20% | 多条数据源的交叉验证 |

### 3. `constraints` — 适用条件与限制

```json
{
  "applicable_zones": ["subtropical_wet", "mediterranean"],
  "inapplicable_zones": ["arid", "subarctic"],
  "min_temp_c": -2,
  "max_temp_c": 35,
  "min_growing_days": 30,
  "container_suitable": true,
  "known_risks": ["梅雨期蚜虫高发", "夏季高温易抽苔"],
  "manual_review_required": false
}
```

**规则**：
- `applicable_zones` / `inapplicable_zones` 必须明确列出
- `known_risks` 必须包含可操作的风险描述，不能只写"有風險"
- 当置信度 < 0.6 时，`manual_review_required` 必须设为 true

### 4. `recommendation` — 具体建议

```json
{
  "crop": "生菜",
  "adapt_score": 0.92,
  "growth_days": 45,
  "reason": "耐寒、空间小、周期短，适合 beginner",
  "actions": ["播种深度 0.5cm", "每日浇水 100ml", "D15 间苗"],
  "risk_alerts": ["D40-50 注意采收时机，避免抽苔"],
  "rescue_plan": "若出现黄叶 → 检查是否缺氮 → 施用稀释氮肥"
}
```

---

## 完整输出示例（杭州阳台生菜）

```json
{
  "agent": "CropAgent",
  "version": "1.0",
  "evidence": {
    "data_sources": ["WorldClim 2.1", "FAO GAEZ"],
    "zone_id": "subtropical_wet",
    "zone_name": "亚热带湿润带",
    "crop_db_version": "1.0",
    "recommendation_count": 3,
    "data_recency_years": 2
  },
  "confidence": {
    "rubric_score": 0.85,
    "coverage_pct": 0.7,
    "confidence_note": "生菜在亚热带湿润带数据覆盖度高，但用户阳台微气候未建模"
  },
  "constraints": {
    "applicable_zones": ["subtropical_wet", "mediterranean"],
    "inapplicable_zones": ["arid", "subarctic"],
    "min_temp_c": -2,
    "max_temp_c": 35,
    "container_suitable": true,
    "known_risks": ["梅雨期蚜虫高发", "夏季高温易抽苔"]
  },
  "recommendation": {
    "crop": "生菜",
    "adapt_score": 0.92,
    "growth_days": 45,
    "reason": "耐寒、空间小、周期短，适合 beginner",
    "risk_flags": ["夏季高温时易抽苔"],
    "fallback_variety": "耐热品种：罗马生菜"
  }
}
```

---

## 校验规则

每条 Agent 输出发出前必须通过：

```python
def validate_output(output: dict) -> bool:
    assert "evidence" in output, "缺少证据链"
    assert "confidence" in output, "缺少置信度"
    assert "constraints" in output, "缺少适用条件"
    assert "recommendation" in output, "缺少具体建议"
    assert output["confidence"].get("rubric_score", 0) >= 0.0, "置信度必须 >= 0"
    assert output["confidence"].get("rubric_score", 0) <= 1.0, "置信度必须 <= 1"
    if output["confidence"].get("rubric_score", 0) < 0.6:
        assert output["constraints"].get("manual_review_required") == True
    return True
```
