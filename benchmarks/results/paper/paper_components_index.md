# 论文组件索引 · benchmarks/results/paper/

全部数字来自 `benchmarks/results/*.json`，禁止手写进正文。


| 文件 | 论文位置 | 数据源 |
| --- | --- | --- |
| table_1_bench_stats.md | Evaluation §Bench | `stat_summary.json` |
| table_2_baseline_compare.md | Evaluation §Baseline | `baseline_comparison.json` |
| table_3_conformal.md | Evaluation §Conformal | `stat_summary.json` |
| table_4_ablation.md | Evaluation §Ablation（**gap**） | 未做，诚实占位 |
| figure_3_phenology_scatter.svg | Evaluation §Phenology | `phenology_consistency.json` |
| figure_4_koppen_heatmap.svg | Evaluation §Köppen | `koppen_consistency.json` |

**生成命令**：`python scripts/paper_tables.py`


**诚实缺口**（Limitations 段必写）：

1. `koppen_grid` 为启发式投影，非 Beck et al. (2018) 1km 真实栅格

2. WOFOST 参数表仅覆盖 7/152 作物（另 23 种在扩展表，~90 种无 T_BASE 来源）

3. `execution_log` 当前全部为 shadow，无真实硬件闭环

4. 消融实验（Table 4）当前**未做**——投 SoftwareX 须主动披露


**投稿目标**：SoftwareX（冲刺，IF 3.4-6.5）— 只需 S1 + S2-A 完成（本目录已满足）

