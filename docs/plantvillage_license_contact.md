# PlantVillage 商用许可沟通材料

> 起草日期：2026-09-20
> 状态：**待用户审核并发送**（AI 不代发对外邮件）
> 关联：`docs/data_sources_verified.md` 第三节的 PlantVillage 行；本文件不替代那份的核验结论

---

## 1. 为什么需要这封信

`spMohanty/PlantVillage-Dataset` 的 README **没有 LICENSE 文件**，只要求引用 Mohanty et al. 2016 论文。这意味着：

- **无明示授权 ≠ 默认可商用**。缺 license 时默认版权保留（all rights reserved），商用与再分发都存在法律不确定性。
- HuggingFace / Meta-Album / 部分 Kaggle 镜像**单方面声称 CC0 1.0**，但这不是原仓库的声明，不构成本项目可用的依据。
- 本项目若把 PlantVillage 图写入 Env Recipe 的 `sources[].license` 字段（混合许可治理已落地），无法填出可信值，只能标 `license: "unknown"`——现有回归测试会把它标为「未知许可需人工确认」，**这是已知且故意保留的风险位**。

**不阻塞的替代路径**：PlantDoc（CC BY 4.0，2,598 图 / 13 物种 / 17 类病害）许可明确可直接商用，建议先用它跑通视觉管线。本信只为「在 PlantDoc 之上叠加 PlantVillage 扩规模」这一可选增量争取授权。

---

## 2. 收件人

PlantVillage 论文作者（Mohanty et al. 2016, "Using Deep Learning for Image-Based Plant Disease Detection"）：

- **Shubhasish M. Mohanty**（第一作者，论文通讯作者）——EPFL VSP Lab
  邮箱（论文页）：`shubhasish.mohanty@epfl.ch`
- **David P. Hughes**（合著者，植物病理学家）
  邮箱（论文页）：`david.hughes@epfl.ch`

> 发送前请人工核对一次论文 PDF 里的最新联系信息（论文 2016 年发表，作者可能已换单位）。
> 也可同时抄送 `plantvillage@psu.edu` 若站点页面列出该地址。

---

## 3. 邮件正文（英文，可直接复制）

**Subject:** License clarification request — PlantVillage dataset (non-commercial research use → possible commercial extension)

**Body:**

Dear Dr. Mohanty and Dr. Hughes,

My name is [YOUR NAME], and I maintain an open-source agricultural knowledge project (GitHub: `lm203688/smart-agri-eco`) focused on environment-recipe-based crop cultivation guidance.

I would like to clarify the licensing terms for the **PlantVillage dataset** (`spMohanty/PlantVillage-Dataset`), which derives from your 2016 paper "Using Deep Learning for Image-Based Plant Disease Detection".

**What I have checked:** the repository README requests attribution to Mohanty et al. 2016 but does not include a LICENSE file, and I could not find a license statement on plantvillage.psu.edu. Some third-party mirrors (e.g. certain HuggingFace and Kaggle listings) claim CC0 1.0, but those are not your declarations, so I do not treat them as authoritative.

**What I need to know:**

1. Are we permitted to use PlantVillage images **for training a disease-detection model** in our open-source project (MIT-licensed code, data itself not redistributed by us)?
2. If the training uses PlantVillage, are we permitted to **publish the derived model weights**, given we would not redistribute the original images?
3. If neither is permitted, is there a licensing channel through which commercial or redistribution rights could be obtained (e.g. a paid license or a CC-BY-NC option)?

**How we plan to comply, whatever you decide:**

- Cite Mohanty et al. 2016 in every place the dataset is referenced.
- Record the licence verbatim in our per-source licensing field (`sources[].license`) rather than a blanket project-level statement.
- If you confirm a non-commercial-only restriction, we will publish that restriction explicitly and restrict commercial redistribution accordingly.

For transparency: we have already stood up a fully compliant fallback — **PlantDoc** (CC BY 4.0, 2,598 images / 13 species / 17 disease classes, real-world scene photos) — so this clarification is needed only to extend coverage on top of that baseline, not to unblock our release.

Thank you for your time and for making PlantVillage available to the community in the first place.

Best regards,
[YOUR NAME]
[GitHub link] · [Your email]

---

## 4. 发送后的记录动作（回写本项目）

收到回复后，按结论更新三处，让许可状态可追溯：

1. `docs/data_sources_verified.md` 第三节的 PlantVillage 行——把「⚠️ license 缺失」替换为实际条款（或「作者确认仅非商用」）。
2. `data/env_recipes/*.json` 中引用 PlantVillage 的 `sources[].license` 字段——从 `unknown` 改为确认值。
3. 若作者要求署名格式，同步到对应配方的 `sources[].citation`。

**收到回复前不要改这三处**——保持 `unknown` 是当前正确的诚实状态。
