# AgriTrust — 智慧农业生态可信建议层

> 让每条农业建议都有据可查、有度可评、有条件可依

---

## 定位

AgriTrust 是智慧农业生态项目的**可信执行层**——对标 SwarmLabs 的 VeritasGuard。它将项目已有的三块数据能力统一命名、打包，为每条 Agent 输出附加：

- **证据链**（数据源 + 分区依据 + 作物研究出处）
- **置信度评分**（rubric 5 项校验）
- **可复现证书**（SHA256 数字签名）

---

## 数据来源

| 数据文件 | 内容 | 用途 |
|---------|------|------|
| `data/zone_meta/global_zones.json` | 6 个 Köppen 气候带农业分区元数据 | 气候/土壤/水文基准 |
| `data/crop_adapt_db.json` | 76 种作物 × 6 气候带适配数据 | 作物推荐基础 |
| `skills/registry/*.json` | 6 个农业 Skill 机读注册表 | 能力复用与组合 |

---

## Rubric 5 项校验

| 检查项 | 通过条件 | 含义 |
|--------|---------|------|
| `data_sources_traced` | ≥ 3 个独立数据源 | 建议不是凭空编造 |
| `zone_coverage_ok` | ≥ 5 个气候带有作物数据 | 建议覆盖全球主要农业区 |
| `recency_ok` | 数据距当前 ≤ 3 年 | 建议基于新鲜数据 |
| `adapt_score_verified` | ≥ 90% 作物有适配度评分 | 推荐有量化依据 |
| `scene_adapted` | 每个作物含种植场景适配 | 建议针对具体场景 |

---

## 使用方法

```bash
# 生成可复现证书
python -m core.trust_layer

# 在 Python 中使用
from core.trust_layer import issue_certificate
cert = issue_certificate(run_id="my-run", inputs={"scene": "balcony", "crop": "生菜"})
print(cert["signature"])  # SHA256 签名
print(cert["rubric"]["full_pass"])  # True/False
```

---

## 证书内容

```json
{
  "layer": "AgriTrust — 智慧农业生态可信建议层",
  "version": "1.0",
  "certificate_id": "my-run",
  "issued_at": "2026-08-27T09:40:00",
  "data_coverage": {
    "total_zone_meta": 6,
    "zones_with_crops": 6,
    "total_crops": 76,
    "score_coverage_pct": 1.0
  },
  "rubric": {
    "passed": 5,
    "total": 5,
    "full_pass": true
  },
  "signature": "sha256..."
}
```

---

## 当前状态

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 数据源溯源 | ✅ | 6 个权威数据源（WorldClim/FAO 等） |
| 气候带覆盖 | ✅ | 6 个气候带全部有作物数据 |
| 数据新鲜度 | ✅ | 2026 年数据 |
| 适配度评分 | ✅ | 76/76 作物含适配度评分 |
| 场景适配 | ✅ | 每个作物含 suitable_scenes |
| 病虫害知识库 | ⚠️ 待建 | pest_diagnose Skill 框架就位，数据待填充 |
| 设备推荐库 | ⚠️ 待建 | device_recommend Skill 框架就位，数据待填充 |

---

## 与 SwarmLabs 的对应关系

| SwarmLabs (VeritasGuard) | 智慧农业生态 (AgriTrust) |
|--------------------------|------------------------|
| `data/trust_surface.json` | `data/zone_meta/global_zones.json` + `data/crop_adapt_db.json` |
| `engine/traceability.py` | 每条建议的溯源链（数据源 + 分区 + 作物研究） |
| `core/task_contract.py` | Agent 输出契约（docs/agent_output_contract.md） |
| 163 个物理模型 | 76 种作物 × 6 气候带适配数据 |
| SHA256 数字签名 | SHA256 数字签名（同样机制） |
