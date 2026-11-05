# CEA 单点闭环 demo（第三批 ⑥ · 技术验证 · 非经济可行）

> 定位：**技术验证**，不是市场主场景（第一英里 = 区域大田样板做透，G1 真实入口）。
> 诚实边界：本 demo 不构成对任何真实设备/产线经济可行性的声明。

## 1. 目标

把「传感器 → 控制器 → 执行器 → 回填置信度」的**完整闭环**在纯软件模拟中跑通，
证明本项目控制协议链路（`ControlAgent` 指令语言 + `Env Recipe` 设定值 +
`GrowBatch` 批次对象链）能闭环，而不是只有单向「建议 → 记录」的 open-loop。

## 2. 模块

| 文件 | 职责 |
| --- | --- |
| `agent/cea_controller.py` | 闭环控制器（`SimulatedEnv` 一阶+噪声环境、`CEAClosedLoop` 闭环、`controller` 偏差→指令、`feedback` 回填置信度） |
| `scripts/demo_cea_closed_loop.py` | CLI demo 入口（打印闭环轨迹 + 置信度） |

## 3. 闭环结构（每个时间步）

1. **sensor**：读当前环境状态（`SimulatedEnv.step`，一阶响应 + 高斯噪声，可复现 `core.seed`）
2. **controller**：取 `Env Recipe` 设定值（setpoint）→ 与实测偏差 → 生成 actuator 指令
3. **actuator**：指令作用于环境模型（一阶趋近设定值，时间常数 + 噪声）
4. **feedback**：闭环精度 = `1 - 归一化平均绝对偏差`，回填到 observation/action

## 4. 集成

- **GrowBatchStore**：每步写 Observation（sensor 读数）+ Action（controller 指令，
  `dry_run=True / status=shadow`），事件日志 append-only。
- **control_agent.ControlAgent**：闭环控制器的 actuator 命名与 `_build_commands`
  标准指令语言对齐（`climate / co2 / grow_light` 是其集合 `{climate, co2, fan,
  fertigation, grow_light, irrigation}` 的子集），可无缝互操作。
- **Env Recipe**：`data/env_recipes/{zone}__{crop}.json`，设定值优先取 recipe，
  缺则分区经验默认（诚实标注 `derived=zone_default`）。

## 5. 运行

```bash
# 不持久化（快速验证闭环）
python scripts/demo_cea_closed_loop.py --crop 番茄 --zone temperate_continental --steps 12

# 持久化到 GrowBatchStore（隔离目录，不污染 data/）
python -c "
import sys; sys.path.insert(0,'.')
from agent.cea_controller import CEAClosedLoop
from agent.grow_batch_store import GrowBatchStore
store = GrowBatchStore('.tmp_test/cea_batches')
loop = CEAClosedLoop(crop='番茄', zone_id='temperate_continental')
r = loop.run(steps=10, store=store, persist=True)
print('closed_loop_confidence=', r['feedback']['closed_loop_confidence'])
"
```

## 6. 结果示例（实测，`temperate_continental` × 番茄 × 12 步）

```
closed_loop_confidence=0.989
per_metric={'temperature': 0.999, 'humidity': 0.997, 'co2_ppm': 0.998, 'light': 0.963}
```

轨迹：step 0 观测 `{temp 22.6, hum 53.9, co2 340.9, light 213.6}`（冷启动偏离设定 25%），
step 7-11 已收敛到设定附近（`temp 27.9~28.0`，`cmd=0` 死区内无指令）。

## 7. 诚实边界（硬约束）

- **技术验证，非经济可行**：不声称任何真实设备/产线的经济性。
- **动作默认 shadow/dry_run，不真实执行**：真实执行需人工确认 + 网关下发
  （MQTT/Node-RED，见 `control_agent.py` 头部诚实标注）。
- **环境是模拟模型**（一阶 + 噪声），非真实温室物理模型；输出带 `model` 字段可审计。
- **不联网、不造数据、纯 stdlib**；可复现（`core.seed` 稳定种子）。

## 8. 与 G1 的关系

本 demo 是**技术验证**，不是 G1 计数来源。G1（外部 agent 真实调用 ≥500 次 /
独立调用方 ≥20）仍需外部 agent 真实来调用，本 demo 证明的是**协议链路可用**，
而非「被依赖」。达标前不宣称"被依赖"（Chief 红线）。
