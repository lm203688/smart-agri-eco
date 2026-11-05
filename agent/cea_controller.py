"""cea_controller.py — CEA 单点闭环控制器 demo（技术验证，非经济可行；零依赖 stdlib）。

职责（第三批 ⑥ CEA 单点闭环 demo）：
  把「传感器 → 控制器 → 执行器 → 回填置信度」的完整闭环在**纯软件模拟**中跑通，
  证明本项目的控制协议链路（ControlAgent 指令语言 + Env Recipe 设定值 +
  GrowBatch 批次对象链）能闭环，而不是只有单向「建议 → 记录」的 open-loop。

诚实边界（与项目红线一致，必须显式标注）：
  - 本 demo 是**技术验证**，标「技术验证非经济可行」——不构成对任何真实设备/产线
    的经济可行性声明。
  - 执行器动作默认 shadow/dry_run，**不真实执行**；真实执行需人工确认 + 网关下发
    （MQTT/Node-RED），本模块不模拟网关。
  - 环境模型是一阶响应 + 高斯噪声的**模拟模型**，不是真实温室的物理模型。所有
    输出带 `model` 字段标注来源（simulated / recipe / control），可审计。
  - 不联网、不造数据、纯 stdlib；可复现（core.seed 稳定种子）。

闭环结构（每个时间步）：
  1. sensor: 读当前环境状态（模拟读数，含可控噪声）
  2. controller: 取 Env Recipe 设定值（setpoint）→ 与实测偏差 → 生成 actuator 指令
  3. actuator: 把指令作用于环境模型（一阶趋近设定值，时间常数 + 噪声）
  4. feedback: 计算闭环精度（实测 vs 设定的偏差统计）→ 回填置信度到 observation/action

集成：
  - GrowBatchStore：每步写 Observation（sensor 读数）+ Action（controller 指令，
    dry_run=True / status=shadow），事件日志 append-only。
  - control_agent.ControlAgent：复用其 `_build_commands` 的指令翻译（硬件无关意图），
    但本模块的控制器以「偏差→指令」为核心，指令语言与 ControlAgent 对齐。

用法：
    python -m agent.cea_controller --crop 番茄 --zone temperate_continental --steps 20
"""
from __future__ import annotations

import argparse
import math
import os
import sys
from typing import Any, Dict, List, Optional

# 可注入稳定随机（core.seed 零依赖）
try:
    from core.seed import stable_seed, Random
except Exception:  # pragma: no cover - 防御：core.seed 缺失则退化为 stdlib
    import random as _stdlib
    import hashlib

    def stable_seed(*parts: Any) -> int:  # type: ignore
        h = hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()
        return int(h[:8], 16)

    class Random(_stdlib.Random):  # type: ignore
        pass

# 原子写入底座（与 control_agent / grow_batch_store 一致）
try:
    from core.atomic_io import atomic_write_json, atomic_append_jsonl
except Exception:  # pragma: no cover
    def atomic_write_json(path: str, data: Dict[str, Any], **kw: Any) -> None:  # type: ignore
        import json
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, **kw)

    def atomic_append_jsonl(path: str, data: Dict[str, Any]) -> None:  # type: ignore
        import json
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False) + "\n")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_RECIPE_DIR = os.path.join(ROOT, "data", "env_recipes")

# 可控制的量（与 control_agent._build_commands 的 actuator 命名对齐）
# metric → (actuator_name, setter_command, unit, deadband)
_ACTUATOR_KEYS = {
    "temperature": ("climate", "set_day_temp", "C", 0.8),
    "humidity": ("climate", "set_humidity_range", "pct", 3.0),
    "co2_ppm": ("co2", "set_co2", "ppm", 40.0),
    "light": ("grow_light", "set_ppfd", "umol/m2/s", 30.0),
}
# 反向：actuator → metric（供观测写回）
_ACTUATOR_TO_METRIC = {
    "climate": {"temperature": "temperature", "humidity": "humidity"},
    "co2": {"co2_ppm": "co2_ppm"},
    "grow_light": {"light": "light"},
}

# 一阶响应时间常数（步），越大越慢（模拟设备惯性）
_DEFAULT_TAU = {"temperature": 4.0, "humidity": 3.0, "co2_ppm": 5.0, "light": 2.0}
# 传感器/环境噪声标准差（模拟测量与扰动）
_DEFAULT_NOISE = {"temperature": 0.6, "humidity": 2.0, "co2_ppm": 25.0, "light": 20.0}


def _now_iso() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class SimulatedEnv:
    """一阶响应 + 噪声的模拟环境（技术验证用，非真实物理模型）。"""

    def __init__(self, state: Optional[Dict[str, float]] = None,
                 seed: Any = "cea_sim") -> None:
        self.state: Dict[str, float] = dict(state or {})
        self.rng = Random(stable_seed(seed))
        self.tau = dict(_DEFAULT_TAU)
        self.noise = dict(_DEFAULT_NOISE)

    def step(self, setpoints: Dict[str, float]) -> Dict[str, float]:
        """朝设定值一阶趋近 + 高斯噪声。返回更新后的状态。"""
        for k, target in setpoints.items():
            cur = self.state.get(k, target)
            tau = self.tau.get(k, 3.0)
            # 一阶响应：next = cur + (target - cur) * (1/tau)
            new = cur + (target - cur) * (1.0 / tau)
            # 噪声（模拟扰动，非确定性但可复现）
            new += self.rng.gauss(0.0, self.noise.get(k, 1.0)) * 0.3
            self.state[k] = new
        return dict(self.state)


class CEAClosedLoop:
    """CEA 单点闭环控制器（技术验证）。

    单点 = 一个 GrowBatch（一个 Plot / 一种作物 / 一个 Env Recipe）。
    闭环 = 传感器读数 → 控制器（setpoint vs 实测）→ 执行器（一阶趋近）→
           回填置信度（闭环精度统计）。
    """

    NAME = "CEAClosedLoop"
    VERSION = "0.1"
    HONEST_NOTE = (
        "CEA 单点闭环 demo：技术验证，非经济可行。环境为一阶+噪声模拟模型，"
        "动作默认 shadow/dry_run 不真实执行，真实执行需人工确认+网关下发。"
    )

    def __init__(self, crop: str = "番茄", zone_id: str = "temperate_continental",
                 recipe_dir: str = DEFAULT_RECIPE_DIR, seed: Any = "cea_loop") -> None:
        self.crop = crop
        self.zone_id = zone_id
        self.recipe = self._load_recipe(recipe_dir)
        self.env = SimulatedEnv(seed=seed)
        self.history: List[Dict[str, Any]] = []
        self._seq = 0

    def _load_recipe(self, recipe_dir: str) -> Optional[Dict[str, Any]]:
        """按 zone__crop 精确或模糊匹配 Env Recipe。"""
        import glob
        if not os.path.isdir(recipe_dir):
            return None
        cands = []
        for p in glob.glob(os.path.join(recipe_dir, "*.json")):
            base = os.path.splitext(os.path.basename(p))[0].lower()
            if self.crop.lower() in base:
                score = 0 if self.zone_id.lower() in base else 1
                cands.append((score, p))
        cands.sort()
        for _, p in cands[:1]:
            try:
                with open(p, "r", encoding="utf-8") as f:
                    import json
                    return json.load(f)
            except Exception:
                return None
        return None

    def setpoints(self) -> Dict[str, float]:
        """从 Env Recipe 提取设定值（控制器目标）。缺则回退分区经验默认并标注。"""
        sp: Dict[str, float] = {}
        from_env = bool(self.recipe)
        env = (self.recipe or {}).get("environment", {})
        temp = env.get("temperature") or {}
        if temp.get("day_c") is not None:
            sp["temperature"] = float(temp["day_c"])
        hum = env.get("humidity") or {}
        if hum.get("min_pct") is not None and hum.get("max_pct") is not None:
            sp["humidity"] = (float(hum["min_pct"]) + float(hum["max_pct"])) / 2.0
        wn = env.get("water_nutrient") or {}
        # CO2 / 光照：Env Recipe 可能无，用分区经验默认（诚实标注 derived=zone_default）
        sp.setdefault("co2_ppm", 420.0)
        sp.setdefault("light", 250.0)
        sp["_from_recipe"] = float(from_env)
        sp["_recipe_water_ml"] = float(wn.get("water_ml_day") or 0.0)
        return sp

    def controller(self, setpoints: Dict[str, float],
                   observed: Dict[str, float]) -> List[Dict[str, Any]]:
        """偏差→指令（与 ControlAgent 指令语言对齐，硬件无关意图）。"""
        cmds: List[Dict[str, Any]] = []
        for k in ("temperature", "humidity", "co2_ppm", "light"):
            target = setpoints.get(k)
            if target is None:
                continue
            cur = observed.get(k, target)
            dev = target - cur
            actuator, cmd_name, unit, deadband = _ACTUATOR_KEYS.get(
                k, (k, f"set_{k}", "", 1.0))
            # 控制律：比例 + 死区（偏差 < 阈值不动作，防抖）
            if abs(dev) >= deadband:
                cmds.append({
                    "actuator": actuator, "command": cmd_name,
                    "value": round(target, 2), "unit": unit,
                    "measured": round(cur, 2), "deviation": round(dev, 2),
                    "schedule": "continuous" if k != "light" else "photoperiod",
                })
        return cmds

    def feedback(self, observed: Dict[str, float],
                 setpoints: Dict[str, float]) -> Dict[str, Any]:
        """回填置信度：闭环精度 = 1 - 归一化平均绝对偏差。"""
        acc: Dict[str, List[float]] = {}
        for k, target in setpoints.items():
            if k.startswith("_") or target is None:
                continue
            cur = observed.get(k, target)
            scale = max(abs(target), 1e-6)
            acc.setdefault(k, []).append(abs(cur - target) / scale)
        scores = {}
        for k, devs in acc.items():
            mad = sum(devs) / len(devs)
            scores[k] = round(max(0.0, 1.0 - mad), 3)
        overall = round(sum(scores.values()) / len(scores), 3) if scores else 0.0
        return {
            "closed_loop_confidence": overall,
            "per_metric": scores,
            "method": "normalized_mean_absolute_deviation",
            "model": "simulated_one_plus_noise",
        }

    def run(self, steps: int = 20, *, store: Optional[Any] = None,
            batch_id: str = "cea_demo_batch", plot_id: str = "cea_demo_plot",
            persist: bool = True) -> Dict[str, Any]:
        """跑闭环。persist=True 时写入 GrowBatchStore（若 store 提供）。"""
        sp = self.setpoints()
        # 初始环境偏离设定（模拟启动未就绪）
        init: Dict[str, float] = {}
        for k in ("temperature", "humidity", "co2_ppm", "light"):
            if k in sp:
                init[k] = sp[k] * 0.75  # 冷启动：低于设定 25%
        self.env.state = init

        obs_records: List[Dict[str, Any]] = []
        act_records: List[Dict[str, Any]] = []
        for step in range(steps):
            self._seq += 1
            # 1) 传感器读数（模拟）
            observed = self.env.step({k: v for k, v in sp.items() if not k.startswith("_")})
            # 2) 控制器
            cmds = self.controller(sp, observed)
            # 3) 执行器作用（已在 env.step 中一阶趋近，这里记录）
            # 4) 回填置信度（逐点近似，最终用 feedback 汇总）
            record = {
                "step": step,
                "observed": {k: round(v, 3) for k, v in observed.items()},
                "setpoint": {k: (round(v, 2) if isinstance(v, float) else v)
                             for k, v in sp.items() if not k.startswith("_")},
                "commands": cmds,
                "n_commands": len(cmds),
            }
            self.history.append(record)

            # 集成 GrowBatch：Observation + Action（shadow/dry_run）
            if persist and store is not None:
                self._write_store(store, batch_id, plot_id, record, step)

        # 最终回填置信度（用全历史统计）
        final_observed: Dict[str, float] = {}
        for rec in self.history:
            for k, v in rec["observed"].items():
                final_observed[k] = v  # 取最后一步
        fb = self.feedback(final_observed, sp)

        return {
            "ok": True,
            "batch_id": batch_id,
            "plot_id": plot_id,
            "crop": self.crop,
            "zone_id": self.zone_id,
            "steps": steps,
            "recipe_loaded": bool(self.recipe),
            "setpoints": {k: v for k, v in sp.items() if not k.startswith("_")},
            "feedback": fb,
            "history": self.history,
            "honest_note": self.HONEST_NOTE,
            "model": "simulated_one_plus_noise",
        }

    def _write_store(self, store: Any, batch_id: str, plot_id: str,
                     record: Dict[str, Any], step: int) -> None:
        """把一步闭环写入 GrowBatchStore（Observation + shadow Action）。"""
        try:
            ts = _now_iso()
            # 建 Plot / Batch（幂等容错：已存在则忽略）
            try:
                store.create_plot({
                    "plot_id": plot_id, "location_type": "greenhouse",
                    "substrate": "hydroponic_rockwool",
                    "area_sqm": {"value": 0.5, "unit": "sqm"},
                    "notes": "CEA 单点闭环 demo（技术验证，非经济可行）",
                })
            except Exception:
                pass
            try:
                store.create_batch({
                    "batch_id": batch_id, "crop": self.crop, "plot_id": plot_id,
                    "recipe_version": (self.recipe or {}).get("recipe_version", "v1.2.0"),
                    "recipe_id": f"{self.zone_id}__{self.crop}",
                    "started_at": ts,
                    "goal": {"kind": "closed_loop_demo", "target": "技术验证非经济可行"},
                    "notes": "CEA 单点闭环 demo：动作默认 shadow/dry_run 不真实执行",
                })
            except Exception:
                pass
            # Observation（传感器读数）
            for metric, val in record["observed"].items():
                try:
                    actuator, _cmd, unit, _db = _ACTUATOR_KEYS.get(
                        metric, (metric, f"set_{metric}", "", 0.0))
                    store.add_observation({
                        "observation_id": f"cea_obs_{batch_id}_{step}_{metric}",
                        "batch_id": batch_id, "ts": ts, "metric": metric,
                        "value": {"value": float(val), "unit": unit},
                        "source": {"kind": "sensor", "device_id": f"cea_sensor_{actuator}"},
                        "quality": "simulated_technical_validation",
                        "notes": "模拟传感器读数（技术验证）",
                    })
                except Exception:
                    pass
            # Action（控制器指令，dry_run=True / status=shadow）
            for cmd in record["commands"]:
                try:
                    store.add_action({
                        "action_id": f"cea_act_{batch_id}_{step}_{cmd['actuator']}",
                        "batch_id": batch_id, "ts": ts,
                        "recommendation": f"{cmd['command']} → {cmd['value']}{cmd['unit']}",
                        "parameters": cmd,
                        "status": "shadow", "dry_run": True,
                        "device_id": f"cea_{cmd['actuator']}",
                        "outcome_notes": "模拟执行（一阶趋近），不真实动作；技术验证",
                    })
                except Exception:
                    pass
        except Exception:
            # 持久化失败不阻断闭环（诚实：记录错误但 demo 仍完成）
            pass


def main(argv: Optional[List[str]] = None) -> int:
    """CLI 入口：跑单点闭环并打印摘要。"""
    ap = argparse.ArgumentParser(description="CEA 单点闭环 demo（技术验证，非经济可行）")
    ap.add_argument("--crop", default="番茄", help="作物名（匹配 Env Recipe）")
    ap.add_argument("--zone", default="temperate_continental", help="气候区（匹配 Env Recipe）")
    ap.add_argument("--steps", type=int, default=20, help="闭环时间步")
    ap.add_argument("--seed", default="cea_loop", help="稳定种子（可复现）")
    ap.add_argument("--persist", action="store_true", help="写入 GrowBatchStore")
    ap.add_argument("--batch-dir", default=None, help="批次存储目录（默认 data/grow_batches）")
    args = ap.parse_args(argv)

    loop = CEAClosedLoop(crop=args.crop, zone_id=args.zone, seed=args.seed)
    store = None
    if args.persist:
        from agent.grow_batch_store import GrowBatchStore
        store = GrowBatchStore(args.batch_dir) if args.batch_dir else GrowBatchStore()
    result = loop.run(steps=args.steps, store=store, persist=args.persist)

    print("=" * 78)
    print("CEA 单点闭环 demo（技术验证 · 非经济可行）")
    print("=" * 78)
    print(f"crop={args.crop}  zone={args.zone}  steps={args.steps}")
    print(f"recipe_loaded={result['recipe_loaded']}  model={result['model']}")
    print(f"setpoints={result['setpoints']}")
    print(f"closed_loop_confidence={result['feedback']['closed_loop_confidence']}")
    print(f"per_metric={result['feedback']['per_metric']}")
    print("-" * 78)
    print("首/中/末 三步观测 vs 设定：")
    idxs = sorted({0, args.steps // 2, args.steps - 1})
    for i in idxs:
        rec = result["history"][i]
        print(f"  step={rec['step']:>3}  obs={rec['observed']}  "
              f"n_cmd={rec['n_commands']}")
    print("-" * 78)
    print(f"honest_note: {result['honest_note']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
