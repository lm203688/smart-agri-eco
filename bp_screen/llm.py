# -*- coding: utf-8 -*-
"""
LLM 网关（通道B）：OpenAI 兼容协议。无 key 自动降级为纯正则模式（通道A）。

配置复用本项目的网关配置，不新增一套环境变量：
  AGRI_VISION_URL / AGRI_VISION_KEY / AGRI_VISION_MODEL   ← 首选（项目既有，指向 ATEX :8420）
  AGRI_BP_LLM_URL / AGRI_BP_LLM_KEY / AGRI_BP_LLM_MODEL   ← 可选覆盖，仅给初筛器单独指定

命名说明：变量带 VISION 前缀是历史遗留（首个使用方是视觉诊断），但指向的网关是通用
OpenAI 兼容端点，文本抽取同样适用。此处不新增变量，避免为第二个使用方复制一份配置。

实现细节：
  - 环境变量在**调用时**读取而非 import 时。import 时读取会让配置变更和测试注入失效。
  - 用标准库 urllib.request，不依赖 httpx → 保持零第三方依赖。
  - 任何异常（网络/超时/解析失败）静默返回 {}，由正则通道兜底，不中断主流程。
"""
from __future__ import annotations

import json
import os
import urllib.request

_DEFAULT_MODEL = "deepseek-chat"
_TIMEOUT_S = 60

_DEFAULT_FIELDS = [
    "revenue", "gross_margin", "gross_profit", "net_profit", "cash_balance", "cash_received",
    "monthly_burn", "revenue_prev", "revenue_growth", "top5_client_pct", "subsidy_pct",
    "ue_margin", "runway_months", "approved_varieties", "safety_certs", "reg_certs",
    "pipeline_certs", "units_sold", "arr_ratio", "renewal_rate", "store_count", "output_volume",
]


def _config():
    """返回 (base_url, api_key, model)；缺任何一项视为不可用。"""
    url = os.environ.get("AGRI_BP_LLM_URL") or os.environ.get("AGRI_VISION_URL")
    key = os.environ.get("AGRI_BP_LLM_KEY") or os.environ.get("AGRI_VISION_KEY")
    model = (os.environ.get("AGRI_BP_LLM_MODEL") or os.environ.get("AGRI_VISION_MODEL")
             or _DEFAULT_MODEL)
    return url, key, model


def llm_available() -> bool:
    return bool(_config()[0]) and bool(_config()[1])


def llm_extract_fields(docs: list, fields: list = None) -> dict:
    """
    通道B：把文档文本交给 LLM，要求 JSON 输出指定字段。
    失败静默返回 {}（由通道A兜底）。docs: [{filename, text}]
    """
    url, key, model = _config()
    if not url or not key:
        return {}

    field_list = fields or _DEFAULT_FIELDS
    prompt = (
        "你是财务数据抽取器。从下列公司资料文本中提取字段，只输出 JSON（无其他文字），"
        "字段缺失时值设为 null，金额统一为元（数字），比率为百分数数值（0-100，不是小数）：\n"
        + "\n".join(f["filename"] + ":\n" + f["text"][:8000] for f in docs)
        + "\n输出字段：" + ", ".join(field_list)
    )
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 4000,
    }).encode("utf-8")

    try:
        base = url.rstrip("/")
        endpoint = base if base.endswith("/chat/completions") else base + "/chat/completions"
        req = urllib.request.Request(
            endpoint, data=payload, method="POST",
            headers={"Authorization": "Bearer %s" % key, "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
        content = content.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(content)
        out = {}
        for k, v in parsed.items():
            if isinstance(v, bool) or isinstance(v, (int, float)):
                out[k] = v
        return out
    except Exception:
        return {}
