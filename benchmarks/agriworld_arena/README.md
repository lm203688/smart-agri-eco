# AgriWorld-Arena — 多智能体农业策略竞赛

A2-η 任务：让不同种植策略在同一作物+气候条件下竞争，输出排行榜。

## 用法

```bash
# 全量竞赛
python benchmarks/agriworld_arena/run_arena.py

# 指定作物
python benchmarks/agriworld_arena/run_arena.py --crops potato wheat

# JSON 输出
python benchmarks/agriworld_arena/run_arena.py --json
```

## 策略列表

1. **baseline** — 标准条件（对照组）
2. **high_light** — 高光照高水肥
3. **high_temp** — 高温环境
4. **water_stress** — 水分胁迫
5. **high_co2** — 高 CO2
6. **dual_track** — 双轨推荐（机理+启发式）
7. **mpc** — MPC 闭环控制（模拟器）
