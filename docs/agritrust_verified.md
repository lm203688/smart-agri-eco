# AgriTrust Verified — 可信性验证说明

## 当前信任级别

✅ **TRUSTED** — Rubric 5/5

## 如何独立复算验证

外部消费者可以独立验证任何 Env Recipe 输出的可信性：

```bash
# 1. 获取当前信任标记
python -c "from core.trust_layer import get_trust_mark; import json; print(json.dumps(get_trust_mark(), indent=2))"

# 2. 独立复算 signature（应与信任标记中的 signature 一致）
python scripts/verify_trust_mark.py from-mark <mark.json>

# 3. 比对 signature
# 如果复算结果与信任标记中的 signature 一致，说明数据未被篡改
```

## 信任标记字段结构

```json
{
  "cert_id": "trust-mark",
  "signature": "79811f53bccc05b26bfb46d23e6eeb0d6fc475a60b29796ded7a840d90c65d1f",
  "signature_prefix": "79811f53bccc",
  "issued_at": "2026-10-14T13:18:11",
  "verification_cmd": "python scripts/verify_trust_mark.py from-mark <mark.json>",
  "status": "trusted",
  "rubric_passed": "5/5",
  "degraded_reasons": []
}
```

## 信任等级定义

| 状态 | 含义 | Rubric 阈值 |
|------|------|-------------|
| `trusted` | 数据一致，可复算验证通过 | 5/5 |
| `degraded` | 部分数据不可验证（降级运行） | < 5/5 |
| `unknown` | 信任层未初始化 | - |

## 数据血缘追溯

每条 Env Recipe 输出的 `_trust_mark` 字段包含：
- **cert_id**: 证书标识符
- **signature**: SHA-256 数据一致性签名
- **signature_prefix**: 前 12 字符（可嵌入徽章供人眼验证）
- **verification_cmd**: 独立复算命令

## 当前状态

- 签名: `79811f53bccc05b26bfb46d23e6eeb0d6fc475a60b29796ded7a840d90c65d1f`
- 签发时间: `2026-10-14T13:18:11`
- 复算命令: `python scripts/verify_trust_mark.py from-mark <mark.json>`
