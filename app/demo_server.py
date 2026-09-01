#!/usr/bin/env python3
"""
智慧农业生态 · 交互式 Demo 站点（零依赖）

技术栈：仅 Python 标准库（http.server + json），无需 pip 安装任何包。
启动：
    python app/demo_server.py
    # 默认 http://127.0.0.1:8000

接口：
    GET  /                      返回 index.html（前端页面）
    POST /api/recommend         {"lat","lon","scene","floor","orientation",
                                  "purpose","space_sqm","difficulty","budget_cny"}
                                 -> orchestrator.run_pipeline 结果
    POST /api/certificate       {"scene","crop"} -> trust_layer.issue_certificate 结果
    POST /api/feedback           {"zone_id","crop","survival_rate","yield_rating",
                                  "user_rating","issues","note"} -> 数据飞轮校准 adapt_score
    POST /api/pest_diagnose      {"crop","symptom_description","image_reference",
                                  "growth_stage","environment"} -> PestAgent 病虫害诊断
    POST /api/nutrition_plan      {"crop","scene","growth_stage","growth_days",
                                  "container_volume_l","start_date"} -> NutritionAgent 养分管理

所有建议遵循 docs/agent_output_contract.md 输出契约（evidence/confidence/constraints/recommendation）。
"""

from __future__ import annotations

import json
import os
import sys
import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agent import AgriOrchestrator  # noqa: E402
from agent.pest_agent import PestAgent  # noqa: E402
from agent.nutrition_agent import NutritionAgent  # noqa: E402
from core.trust_layer import issue_certificate  # noqa: E402

PORT = int(os.environ.get("AGRI_DEMO_PORT", "8000"))
HOST = os.environ.get("AGRI_DEMO_HOST", "127.0.0.1")

INDEX_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")

# 预设城市（用于前端下拉，避免依赖地理编码 API）
PRESET_CITIES = [
    {"name": "杭州", "lat": 30.2741, "lon": 120.1551, "zone": "亚热带湿润带"},
    {"name": "北京", "lat": 39.9042, "lon": 116.4074, "zone": "温带大陆性"},
    {"name": "深圳", "lat": 22.5431, "lon": 114.0579, "zone": "亚热带湿润带"},
    {"name": "广州", "lat": 23.1291, "lon": 113.2644, "zone": "亚热带湿润带"},
    {"name": "成都", "lat": 30.5728, "lon": 104.0668, "zone": "亚热带湿润带"},
    {"name": "武汉", "lat": 30.5928, "lon": 114.3055, "zone": "亚热带湿润带"},
    {"name": "乌鲁木齐", "lat": 43.8256, "lon": 87.6168, "zone": "干旱带"},
    {"name": "拉萨", "lat": 29.6520, "lon": 91.1721, "zone": "高原寒带（近似干旱）"},
    {"name": "洛杉矶", "lat": 34.0522, "lon": -118.2437, "zone": "地中海带"},
    {"name": "新加坡", "lat": 1.3521, "lon": 103.8198, "zone": "热带雨林"},
    {"name": "迪拜", "lat": 25.2048, "lon": 55.2708, "zone": "干旱带"},
    {"name": "莫斯科", "lat": 55.7558, "lon": 37.6173, "zone": "亚寒带"},
]


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, obj: dict, status: int = 200):
        body = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            try:
                with open(INDEX_PATH, "r", encoding="utf-8") as f:
                    self._send_html(f.read())
            except Exception as e:
                self._send_html(f"<h1>index.html 缺失：{e}</h1>")
        elif path == "/api/cities":
            self._send_json({"cities": PRESET_CITIES})
        else:
            self._send_json({"error": "not found", "path": path}, status=404)

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            payload = {}

        if path == "/api/recommend":
            try:
                orch = AgriOrchestrator()
                result = orch.run_pipeline(payload)
                result["_meta"] = {
                    "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
                    "preset_zone_hint": _zone_hint(payload),
                }
                self._send_json(result)
            except Exception as e:
                self._send_json({"error": f"pipeline 失败: {e}"}, status=500)
        elif path == "/api/certificate":
            try:
                cert = issue_certificate(
                    run_id="demo",
                    inputs={"scene": payload.get("scene", "balcony"),
                            "crop": payload.get("crop", "")},
                )
                self._send_json(cert)
            except Exception as e:
                self._send_json({"error": f"certificate 失败: {e}"}, status=500)
        elif path == "/api/feedback":
            try:
                from engine.flywheel import record_feedback
                res = record_feedback(
                    zone_id=payload.get("zone_id", ""),
                    crop=payload.get("crop", ""),
                    survival_rate=float(payload.get("survival_rate", 1.0)),
                    yield_rating=float(payload.get("yield_rating", 5.0)),
                    user_rating=float(payload.get("user_rating", 5.0)),
                    issues=payload.get("issues") or [],
                    note=payload.get("note", ""),
                )
                self._send_json(res)
            except Exception as e:
                self._send_json({"error": f"feedback 失败: {e}"}, status=500)
        elif path == "/api/pest_diagnose":
            try:
                agent = PestAgent()
                res = agent.run({
                    "crop": payload.get("crop", ""),
                    "symptom_description": payload.get("symptom_description", ""),
                    "image_reference": payload.get("image_reference", ""),
                    "growth_stage": payload.get("growth_stage", ""),
                    "environment": payload.get("environment"),
                })
                self._send_json(res)
            except Exception as e:
                self._send_json({"error": f"pest_diagnose 失败: {e}"}, status=500)
        elif path == "/api/nutrition_plan":
            try:
                agent = NutritionAgent()
                res = agent.run({
                    "crop": payload.get("crop", ""),
                    "scene": payload.get("scene", ""),
                    "growth_stage": payload.get("growth_stage", ""),
                    "growth_days": payload.get("growth_days"),
                    "container_volume_l": payload.get("container_volume_l"),
                    "start_date": payload.get("start_date", ""),
                })
                self._send_json(res)
            except Exception as e:
                self._send_json({"error": f"nutrition_plan 失败: {e}"}, status=500)
        else:
            self._send_json({"error": "not found", "path": path}, status=404)

    def log_message(self, fmt, *args):
        sys.stderr.write("[demo] " + (fmt % args) + "\n")


def _zone_hint(payload: dict) -> str:
    lat = payload.get("lat")
    lon = payload.get("lon")
    if lat is None:
        return ""
    for c in PRESET_CITIES:
        if abs(c["lat"] - lat) < 0.5 and abs(c["lon"] - (lon or 0)) < 0.5:
            return c["zone"]
    return ""


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print("=" * 56)
    print("🌱 智慧农业生态 · 交互式 Demo")
    print(f"   访问: http://{HOST}:{PORT}")
    print("   零依赖：仅 Python 标准库（http.server）")
    print("=" * 56)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
        server.shutdown()


if __name__ == "__main__":
    main()
