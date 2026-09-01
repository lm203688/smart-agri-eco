"""可插拔视觉后端（OpenAI 兼容视觉对话接口）。

配置（环境变量）：
  AGRI_VISION_URL   视觉接口 base URL（可含 /v1，会自动拼 /chat/completions）
  AGRI_VISION_KEY   API Key（Bearer）
  AGRI_VISION_MODEL 模型名（默认 gpt-4o-mini）

行为约束（保证离线可用、不中断主流程）：
  - 未配置 AGRI_VISION_URL / AGRI_VISION_KEY，或 image_reference 为空 → 返回 None（调用方规则降级）。
  - 任何异常（网络/超时/解析失败）→ 返回 None。
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Optional

DEFAULT_PROMPT = (
    "你是植物病虫害诊断专家。请结合作物【%s】诊断这张图片，用中文简洁输出：\n"
    "1) 病害/虫害名称 2) 严重程度(轻/中/重) 3) 关键症状 4) 3 条处理建议。"
)


def call_vision_backend(
    image_reference: str,
    crop: str = "",
    symptom: str = "",
    prompt_template: Optional[str] = None,
) -> Optional[str]:
    """调用 OpenAI 兼容视觉接口；不可用时返回 None。"""
    url = os.environ.get("AGRI_VISION_URL")
    key = os.environ.get("AGRI_VISION_KEY")
    if not url or not key or not image_reference:
        return None
    model = os.environ.get("AGRI_VISION_MODEL", "gpt-4o-mini")
    prompt = (prompt_template or DEFAULT_PROMPT) % (crop or "未知")
    if symptom:
        prompt += "\n用户补充症状：%s" % symptom
    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": image_reference}},
            ],
        }],
        "max_tokens": 800,
    }
    try:
        req = urllib.request.Request(
            url.rstrip("/") + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": "Bearer %s" % key,
                     "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"].strip()
    except Exception:
        return None
