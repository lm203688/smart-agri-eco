# Table 2 · 外部 Baseline 对比

- **数据源**：`benchmarks/results/baseline_comparison.json`
- **原方案**：FAO GAEZ v4 分区交叉表（推荐项）
- **是否替换**：✓（原因：仓库内无 GAEZ 数据；GAEZ v4 原始栅格为数 GB 级 GeoTIFF，需 geopandas/rasterio，违反本项目核心纯标准库的零依赖硬约束。、GAEZ v4 需按 FAO 条款署名说明用途，离线自动化无法自动完成署名链条。）
- **替代数据**：data/zone_meta/global_zones.json -> climate_baseline（NASA POWER，public domain，每分区附 url + accessed_at + years_used，可独立复核）

| 项目 | 类型 | 值 |
|---|---|---|
| Part 1 · 分区 Köppen 复算 | n | 8 |
| Part 1 · 主字母一致（字面 mm/月） | agree | 2/8 |
| Part 1 · 主字母一致（mm/日 年化后） | agree | 8/8 |
| Part 1 · 全型一致（mm/日 年化后） | agree | 6/8 |
| Part 2 · 配方温度偏差（均值） | ℃ | -3.899 |
| Part 2 · 配方温度偏差（std） | ℃ | 5.993 |
| Part 2 · RMSE | ℃ | 7.133 |
| Part 2 · CCC | — | 0.658 |
| Part 3 · 声明数据源 | list | NASA POWER |
| Part 3 · 声称但未能核实 | list | （无） |
| Part 3 · 实际使用但未声称 | list | fetch_monthly_climate (NASA POWER / Open-Meteo) |
