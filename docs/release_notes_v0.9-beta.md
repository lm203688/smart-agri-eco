# 智慧农业生态 v0.9-beta 发行说明

**发行日期**：2026-10-06
**形态**：开发者预览版 · 邀请制 · GitHub Release
**仓库**：lm203688/smart-agri-eco

## 一句话定位
全球农业环境配置知识底座 + 城市种植生成箱；核心资产 **Env Recipe**（作物×阶段×箱体 →
温湿/光谱/PPFD/CO₂/EC/pH/水肥/气流/异常），以 Agent-native（MCP）可机读、可执行、可校准方式分发。

## 本版交付
- **8 分区全建模**：新增 hot_arid（迪拜等）/ highland（拉萨等）真实气候基线 + 6 配套作物定向 P3 校准，
  KG `grows_in` 110 → 116（8 区全有作物邻接）。
- **116 份 Env Recipe**（8 分区），**113 已用 NASA POWER + Open-Meteo 双源校准**（含 `measured_calibration` 实证）。
- **14 个 MCP 工具**，7 Agent 编排（Climate/Crop/Growth/Eco + 按需 Pest/Nutrition/Season）。
- **505 项单测全绿（3 skip）**，`verify_all` PASS，`data_quality_gate` 全 PASS。
- **合成样本污染守卫硬化**：`_is_synthetic` 大小写不敏感 + 独立词匹配，堵住大写 `Demo` 绕过。
- **病虫害视觉诊断：离线规则降级**（无外部依赖）。`AGRI_VISION_*` 未配置时自动 `rule_based`，不中断主流程；
  云端 VLM 为可选插拔。

## 已知限制（邀请制阶段明示）
- RSI HCI=0.333，未达 v1.0 门禁（≥0.6）；4 项 RSI 中 3 项需真实数据/迭代，非工程可关。
- WorldClim 2.1 栅格管道 / agstack pestmodels 对接本轮暂不纳入（维持 5 程序化源）。
- 4 项 pending evals（E1–E4）需外部条件，内测 2–4 周可关闭。

## 快速开始
```bash
# 可选：配置云端视觉后端；不配即离线规则降级
export AGRI_VISION_URL=...    # OpenAI 兼容视觉接口 base URL
export AGRI_VISION_KEY=...
# 运行
python -m agent.pest_agent 番茄 "叶片黄色斑点，背面白色粉状物"
```

## 升级指引（自 v0.9-alpha）
分区 6→8、配方 110→116、校准 107→113、单测 477→504、MCP 13→14；
迪拜/拉萨由「未建模拒答」改为 v1.1 已闭环路由。
