# -*- coding: utf-8 -*-
"""
L2.5 合理性校验（Sanity Gate）

为什么需要这一层：
    评分引擎的区间化机制（scorer.MISSING_SCORE_SPAN）只覆盖「字段**没抽到**」——
    缺一个字段就拉宽 4 分，最多 ±12。但正则通道还会产生另一类错误：**抽到了，但抽错了**。
    例如把「净利润1800万」当净利率提出 net_margin=1800.0，或把品种名「金玉188」的数字
    当在审登记数提出 pipeline_certs=188。这类字段的值不为空，区间化完全失效，
    最终会输出「总分 71.8（区间 71.8-71.8）」这样的**假精确**结论。

    本层在 normalize 之后、分类/评分之前拦下明显越界的值：置为 None 并记录 observation。
    置 None 后它会自然进入区间化的「缺失」路径，不确定性因此被正确表达出来。

设计原则：
    - 只拦「明显不可能」，不拦「可疑但可能」——宁可漏放，不可误杀。误杀会把真实
      业务形态（如养殖类补贴占比 55%、SaaS 客户集中度 72%）当成提取错误。
    - 拦下的字段进 **observations**（软提示），不进硬告警。判据沿用项目约定：
      「按该值实际决策会不会出问题」——一个越界值会污染评分，但不改变「需深挖」这类结论方向。
    - 绝不猜替代值。缺就是缺。
"""
from __future__ import annotations

# 百分数字段：必须在 [0, 100] 内
PCT_FIELDS = {
    "gross_margin", "gross_margin_prev", "net_margin", "revenue_growth",
    "top5_client_pct", "subsidy_pct", "bio_inventory_pct", "arr_ratio",
    "renewal_rate", "rd_pct", "cash_ratio", "gov_fund_ratio", "irr", "gm_trend_pct",
}

# 允许为负的比率（亏损是真信号，不是提取错误）
PCT_ALLOW_NEGATIVE = {"ue_margin", "net_margin", "revenue_growth", "gross_margin", "subsidy_pct"}

# 计数字段：上界用于识别「把名称/编号里的数字当计数」这一类错误。
# 上界取行业经验上限，不是硬规则——目的是拦「品种名数字」（如玉金188）这一类明显失真，
# 不是给真实业务设天花板。放宽需先说明为什么现有上限会误杀真实案例。
COUNT_BOUNDS = {
    "approved_varieties": (0, 300),      # 隆平高科锚点 40；头部种业数百级
    "safety_certs": (0, 100),
    "reg_certs": (0, 100),               # 农药登记单张成本百万级，同时在审 100+ 不现实
    "pipeline_certs": (0, 60),           # 同上；188 这类值基本是名称/编号被误当计数
    "ue_trend_negative_years": (0, 30),
    "patents": (0, 100000),
    "team_size": (0, 100000),
    "store_count": (0, 1000000),
    "sku_count": (0, 100000),
    "units_sold": (0, 10 ** 9),
    "output_volume": (0, 10 ** 9),
}

# 金额字段：必须为正（营收不能为负/零）
MONEY_MUST_POSITIVE = {"revenue", "revenue_prev", "cash_received", "cash_balance",
                       "monthly_burn", "subsidy_amount", "arr"}

# 比率型：1:N，N 至少为 1
RATIO_MUST_GE_1 = {"invest_output_ratio"}

_LABELS = {
    "gross_margin": "综合毛利率", "net_margin": "净利率", "rd_pct": "研发投入占收入比",
    "top5_client_pct": "前五大客户占比", "subsidy_pct": "补贴收入占比", "ue_margin": "单位经济边际",
    "revenue_growth": "营收增速", "arr_ratio": "ARR 占收入比", "renewal_rate": "续费率",
    "approved_varieties": "审定品种数", "safety_certs": "安全证书数", "reg_certs": "登记证数",
    "pipeline_certs": "在审登记数", "revenue": "营业收入", "monthly_burn": "月均消耗",
    "cash_received": "销售收现", "cash_balance": "现金余额",
}


def check(normalized: dict) -> tuple:
    """
    返回 (cleaned, observations)。

    cleaned:       normalized 的副本，越界值已置 None。
    observations:  [{"field", "label", "observed", "reason", "action"}]，按字段名字典序稳定输出。
    """
    cleaned = dict(normalized)
    obs = []

    def _flag(field: str, observed, reason: str):
        cleaned[field] = None
        obs.append({
            "field": field,
            "label": _LABELS.get(field, field),
            "observed": observed,
            "reason": reason,
            "action": "已置空，不参与评分；计入区间化以表达不确定性",
        })

    for field, v in list(normalized.items()):
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            continue

        if field in PCT_FIELDS:
            if v > 100:
                _flag(field, v, f"百分数字段不应超过 100%，实测 {v:g}——疑似把金额或编号数字当作比率提取")
            elif v < 0 and field not in PCT_ALLOW_NEGATIVE:
                _flag(field, v, f"百分数字段不应为负，实测 {v:g}")

        elif field in COUNT_BOUNDS:
            lo, hi = COUNT_BOUNDS[field]
            if v < lo or v > hi:
                _flag(field, v, f"计数字段合理区间 [{lo}, {hi}]，实测 {v:g}——疑似把名称或编号中的数字当计数")

        elif field in MONEY_MUST_POSITIVE:
            if v <= 0:
                _flag(field, v, f"金额字段应为正数，实测 {v:g}")

        elif field in RATIO_MUST_GE_1:
            if v < 1:
                _flag(field, v, f"1:N 比率 N 应至少为 1，实测 {v:g}")

    obs.sort(key=lambda o: o["field"])
    return cleaned, obs


def summarize(obs: list) -> dict:
    """给报告/日志用的一行摘要。"""
    if not obs:
        return {"suspect_fields": 0, "note": "合理性校验通过，无越界值"}
    return {
        "suspect_fields": len(obs),
        "fields": [o["field"] for o in obs],
        "note": f"{len(obs)} 个字段值越界已置空并计入不确定性区间（详见 observations）",
    }
