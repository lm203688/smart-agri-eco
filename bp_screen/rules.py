# -*- coding: utf-8 -*-
"""
声明式规则库（判断规则库 Rules Store —— 三库分离之一）
所有评分逻辑以数据结构表达，评分引擎只做解释执行。
修改规则 = 修改本文件并 bump RULES_VERSION，历史报告锁定旧版本。
"""

RULES_VERSION = "v2.0.0"
RELEASED = "2026-09-20"

# 版本变更日志：每次改规则必须 bump RULES_VERSION 并在此追加一行。
# 历史报告锁定生成时的版本（rule_versions 表），旧报告不随本文件变更而重算。
VERSION_HISTORY = [
    "v1.0.0 (2026-09-18) 首版：六分类 / 五闸 / 六评分卡 / 一票否决。",
    "v2.0.0 (2026-09-20) 并入智慧农业生态项目，修死门禁两处："
    "cash_ratio 闸的 metric 原写 cash_to_revenue、bio_asset 闸原写 bio_asset_pct，"
    "与 extractor.normalize 实际产出的 cash_ratio / bio_inventory_pct 均不匹配，"
    "导致这两个闸在任何输入下都永不触发（静默死代码）。",
]

# ============================================================
# 六分类定义（L5 分类器）
# ============================================================
CATEGORIES = {
    "seeds": {
        "name": "①种业与生物育种",
        "keywords": ["品种", "性状", "种质", "安全证书", "审定", "授权费", "育种", "亲本", "杂交种", "转基因", "分子标记"],
        "asset_signal": "ip",   # 核心资产 = 技术/IP
        "client_signal": "b",
        "revenue_signal": "license",
        "benchmarks": {"gross_margin": 40.0, "net_margin": 13.0, "pe_anchor": 24.0},
        "bench_names": ["隆平高科", "史记生物"],
    },
    "agmach": {
        "name": "②农机装备与机器人",
        "keywords": ["农机", "设备", "台数", "亩均作业", "经销商", "拖拉机", "植保无人机", "播种机", "收割机", "补贴"],
        "asset_signal": "asset",
        "client_signal": "b",
        "revenue_signal": "oneoff",
        "benchmarks": {"gross_margin": 30.0, "ps_anchor": 6.9},
        "bench_names": ["极飞科技"],
    },
    "digag": {
        "name": "③智慧农业SaaS/数字农业",
        "keywords": ["软件订阅", "SaaS", "ARR", "数据服务", "政企客户", "系统项目", "物联网平台", "遥感", "数字农业", "智慧农场"],
        "asset_signal": "ip",
        "client_signal": "bg",
        "revenue_signal": "subscription",
        "benchmarks": {"gross_margin": 51.0, "ps_anchor": 15.0},
        "bench_names": ["托普云农"],
    },
    "bioinputs": {
        "name": "④生物农资与合成生物",
        "keywords": ["菌种", "发酵", "登记证", "生物农药", "微生物制剂", "生物肥", "合成生物", "菌株", "生物刺激素"],
        "asset_signal": "ip",
        "client_signal": "b",
        "revenue_signal": "oneoff",
        "benchmarks": {"gross_margin": 45.0},
        "bench_names": ["慕恩生物"],
    },
    "supply": {
        "name": "⑤供应链与品牌食品",
        "keywords": ["SKU", "门店", "加盟", "品牌", "GMV", "复购", "冷链", "供应链", "生鲜", "预制菜", "渠道"],
        "asset_signal": "channel",
        "client_signal": "c",
        "revenue_signal": "oneoff",
        "benchmarks": {"gross_margin": 25.0, "ps_anchor": 3.0},
        "bench_names": ["锅圈食汇", "十月稻田"],
    },
    "livestock": {
        "name": "⑥规模化养殖与县域基建",
        "keywords": ["出栏量", "环评", "猪场", "养殖", "县域", "政府基金", "IRR", "重资产", "饲料", "屠宰", "种猪"],
        "asset_signal": "asset",
        "client_signal": "bg",
        "revenue_signal": "oneoff",
        "benchmarks": {"gross_margin": 15.0, "invest_output_ratio": 10.0},
        "bench_names": ["唐人神县域项目"],
    },
}

CLASSIFY_CONFIDENCE_THRESHOLD = 70.0   # 分类置信度 <70% → 强制人工确认

# ============================================================
# 通用五闸（L7 评分前置，任一爆雷 = 红色预警，不直接淘汰）
# 分类适配：adaptations 覆盖默认红线
# ============================================================
GATES = [
    {
        "id": "cash_ratio", "name": "现金收入比", "metric": "cash_ratio",
        "default": 70.0, "op": "lt", "severity": "warn",
        "extract_fields": ["revenue", "cash_received"],
        "adaptations": {"livestock": 50.0},
        "note": "销售收现/营收；⑥政府回款慢，红线放宽至50%",
    },
    {
        "id": "client_concentration", "name": "前五大客户占比", "metric": "top5_client_pct",
        "default": 60.0, "op": "gt", "severity": "warn",
        "extract_fields": ["top5_client_pct"],
        "adaptations": {"digag": 70.0},
        "note": "③政企SaaS大客户常见，70%才预警",
    },
    {
        "id": "margin_gap", "name": "毛利率低于赛道基准", "metric": "gross_margin_vs_benchmark",
        "default": -5.0, "op": "lt", "severity": "warn",
        "extract_fields": ["gross_margin"],
        "note": "毛利率 - 分类基准 < -5pct 触发",
    },
    {
        "id": "unit_economics", "name": "单位经济", "metric": "ue_margin",
        "default": 0.0, "op": "le", "severity": "warn",
        "extract_fields": ["ue_margin"],
        "note": "单店/单台/单亩边际贡献 ≤ 0",
    },
    {
        "id": "runway", "name": "现金跑道", "metric": "runway_months",
        "default": 18.0, "op": "lt", "severity": "warn",
        "extract_fields": ["cash_balance", "monthly_burn"],
        "adaptations": {"seeds": 24.0, "bioinputs": 24.0},
        "note": "①④研发周期长，红线放宽至24月",
    },
    {
        "id": "bio_asset", "name": "生物资产/存货占比", "metric": "bio_inventory_pct",
        "default": 50.0, "op": "gt", "severity": "verify",
        "extract_fields": ["bio_inventory_pct"],
        "note": ">50% 需实地盘点，触发核查项",
    },
]

# ============================================================
# 六张评分卡（每张 6 维度，权重合计 100）
# 维度评分 0-100，加权得总分；缺失维度降权并输出区间
# thresholds 为得分阶梯（从高到低匹配第一个满足的）
# ============================================================
COMMON_DIMS = {
    "finance": {
        "id": "finance", "name": "财务质量", "weight": 20,
        "metric": "gross_margin", "field": "gross_margin", "unit": "pct",
        "thresholds": [
            {"score": 90, "op": "gte", "vs": "bench+10"},
            {"score": 75, "op": "gte", "vs": "bench"},
            {"score": 55, "op": "gte", "vs": "bench-5"},
            {"score": 30, "op": "gte", "vs": "bench-15"},
            {"score": 10, "op": "lt", "vs": "bench-15"},
        ],
        "missing": "downweight",
    },
    "growth": {
        "id": "growth", "name": "成长性", "weight": 15,
        "metric": "revenue_growth", "field": "revenue_growth", "unit": "pct",
        "thresholds": [
            {"score": 90, "op": "gte", "value": 50},
            {"score": 75, "op": "gte", "value": 30},
            {"score": 55, "op": "gte", "value": 15},
            {"score": 30, "op": "gte", "value": 5},
            {"score": 10, "op": "lt", "value": 5},
        ],
        "missing": "downweight",
    },
    "cashflow": {
        "id": "cashflow", "name": "现金流与跑道", "weight": 15,
        "metric": "runway_months", "field": "runway_months", "unit": "month",
        "thresholds": [
            {"score": 90, "op": "gte", "value": 30},
            {"score": 75, "op": "gte", "value": 24},
            {"score": 55, "op": "gte", "value": 18},
            {"score": 30, "op": "gte", "value": 12},
            {"score": 10, "op": "lt", "value": 12},
        ],
        "missing": "downweight",
    },
    "policy": {
        "id": "policy", "name": "政策与合规风险", "weight": 10,
        "metric": "subsidy_dependency", "field": "subsidy_pct", "unit": "pct", "invert": True,
        "thresholds": [
            {"score": 90, "op": "lte", "value": 5},
            {"score": 70, "op": "lte", "value": 15},
            {"score": 45, "op": "lte", "value": 30},
            {"score": 15, "op": "gt", "value": 30},
        ],
        "missing": "downweight",
    },
}

SCORING_CARDS = {
    "seeds": {
        "category": "seeds",
        "dims": [
            {   # 分类特异：管线维度
                "id": "pipeline", "name": "品种管线与知识产权", "weight": 25,
                "metric": "approved_varieties", "field": "approved_varieties", "unit": "count",
                "thresholds": [
                    {"score": 90, "op": "gte", "value": 8},
                    {"score": 70, "op": "gte", "value": 4},
                    {"score": 45, "op": "gte", "value": 1},
                    {"score": 10, "op": "lt", "value": 1},
                ],
                "missing": "downweight",
            },
            dict(COMMON_DIMS["finance"]),
            dict(COMMON_DIMS["growth"]),
            {
                "id": "unit_econ", "name": "授权费与单位经济", "weight": 15,
                "metric": "ue_margin", "field": "ue_margin", "unit": "pct",
                "thresholds": [
                    {"score": 90, "op": "gte", "value": 40},
                    {"score": 70, "op": "gte", "value": 25},
                    {"score": 45, "op": "gte", "value": 10},
                    {"score": 10, "op": "lt", "value": 10},
                ],
                "missing": "downweight",
            },
            dict(COMMON_DIMS["cashflow"]),
            dict(COMMON_DIMS["policy"]),
        ],
        # 一票否决（估值锚不进否决链 —— P0修正）
        "vetoes": [
            {
                "id": "no_variety", "name": "无审定品种且无安全证书管线",
                "condition": {"field": "approved_varieties", "op": "lt", "value": 1,
                              "and_field": "safety_certs", "and_op": "lt", "and_value": 1},
                "message": "种业项目无审定品种且无安全证书管线 = 无商业化载体，否决",
            },
        ],
        "valuation_hint": {"type": "PE", "anchor": 24.0, "note": "对标隆平高科 PE≈24x；仅作参考区间，不构成否决"},
    },
    "agmach": {
        "category": "agmach",
        "dims": [
            {
                "id": "pipeline", "name": "装机量与服务网络", "weight": 25,
                "metric": "units_sold", "field": "units_sold", "unit": "count",
                "thresholds": [
                    {"score": 90, "op": "gte", "value": 5000},
                    {"score": 70, "op": "gte", "value": 1000},
                    {"score": 45, "op": "gte", "value": 200},
                    {"score": 10, "op": "lt", "value": 200},
                ],
                "missing": "downweight",
            },
            dict(COMMON_DIMS["finance"]),
            dict(COMMON_DIMS["growth"]),
            {
                "id": "unit_econ", "name": "单台经济性", "weight": 15,
                "metric": "ue_margin", "field": "ue_margin", "unit": "pct",
                "thresholds": [
                    {"score": 90, "op": "gte", "value": 35},
                    {"score": 70, "op": "gte", "value": 20},
                    {"score": 45, "op": "gte", "value": 5},
                    {"score": 10, "op": "lt", "value": 5},
                ],
                "missing": "downweight",
            },
            dict(COMMON_DIMS["cashflow"]),
            dict(COMMON_DIMS["policy"]),
        ],
        "vetoes": [
            {
                "id": "subsidy_trap", "name": "补贴依赖过高",
                "condition": {"field": "subsidy_pct", "op": "gt", "value": 50},
                "message": "政府补贴占收入>50% = 生存依赖政策而非市场，否决",
            },
        ],
        "valuation_hint": {"type": "PS", "anchor": 6.9, "note": "对标极飞 PS≈6.9x（毛利率跨过30%拐点后）；仅作参考"},
    },
    "digag": {
        "category": "digag",
        "dims": [
            {
                "id": "pipeline", "name": "ARR与订阅质量", "weight": 25,
                "metric": "arr_ratio", "field": "arr_ratio", "unit": "pct",
                "thresholds": [
                    {"score": 90, "op": "gte", "value": 60},
                    {"score": 70, "op": "gte", "value": 35},
                    {"score": 45, "op": "gte", "value": 15},
                    {"score": 10, "op": "lt", "value": 15},
                ],
                "missing": "downweight",
            },
            dict(COMMON_DIMS["finance"]),
            dict(COMMON_DIMS["growth"]),
            {
                "id": "unit_econ", "name": "客户留存与复购", "weight": 15,
                "metric": "renewal_rate", "field": "renewal_rate", "unit": "pct",
                "thresholds": [
                    {"score": 90, "op": "gte", "value": 90},
                    {"score": 70, "op": "gte", "value": 75},
                    {"score": 45, "op": "gte", "value": 55},
                    {"score": 10, "op": "lt", "value": 55},
                ],
                "missing": "downweight",
            },
            dict(COMMON_DIMS["cashflow"]),
            dict(COMMON_DIMS["policy"]),
        ],
        "vetoes": [
            {
                "id": "fake_saas", "name": "伪SaaS：零ARR且单一政企客户>70%",
                "condition": {"field": "arr_ratio", "op": "lt", "value": 5,
                              "and_field": "top5_client_pct", "and_op": "gt", "and_value": 70},
                "message": "零订阅收入+极端客户集中 = 项目制外包伪装SaaS，否决",
            },
        ],
        "valuation_hint": {"type": "PS", "anchor": 15.0, "note": "对标托普云农 PS≈15x（毛利51%的订阅结构）；仅作参考"},
    },
    "bioinputs": {
        "category": "bioinputs",
        "dims": [
            {
                "id": "pipeline", "name": "登记证管线", "weight": 25,
                "metric": "reg_certs", "field": "reg_certs", "unit": "count",
                "thresholds": [
                    {"score": 90, "op": "gte", "value": 20},
                    {"score": 70, "op": "gte", "value": 8},
                    {"score": 45, "op": "gte", "value": 2},
                    {"score": 10, "op": "lt", "value": 2},
                ],
                "missing": "downweight",
            },
            dict(COMMON_DIMS["finance"]),
            dict(COMMON_DIMS["growth"]),
            {
                "id": "unit_econ", "name": "产能与单位经济", "weight": 15,
                "metric": "ue_margin", "field": "ue_margin", "unit": "pct",
                "thresholds": [
                    {"score": 90, "op": "gte", "value": 35},
                    {"score": 70, "op": "gte", "value": 20},
                    {"score": 45, "op": "gte", "value": 5},
                    {"score": 10, "op": "lt", "value": 5},
                ],
                "missing": "downweight",
            },
            dict(COMMON_DIMS["cashflow"]),
            dict(COMMON_DIMS["policy"]),
        ],
        "vetoes": [
            {
                "id": "no_cert", "name": "登记证为零且管线<2",
                "condition": {"field": "reg_certs", "op": "lt", "value": 1,
                              "and_field": "pipeline_certs", "and_op": "lt", "and_value": 2},
                "message": "生物农资无登记证 = 无法合法销售，管线<2 = 无储备，否决",
            },
        ],
        "valuation_hint": {"type": "PS", "anchor": 8.0, "note": "管线型生物农资 PS≈6-10x 区间；仅作参考"},
    },
    "supply": {
        "category": "supply",
        "dims": [
            {
                "id": "pipeline", "name": "渠道与SKU质量", "weight": 25,
                "metric": "store_count", "field": "store_count", "unit": "count",
                "thresholds": [
                    {"score": 90, "op": "gte", "value": 2000},
                    {"score": 70, "op": "gte", "value": 500},
                    {"score": 45, "op": "gte", "value": 100},
                    {"score": 10, "op": "lt", "value": 100},
                ],
                "missing": "downweight",
            },
            dict(COMMON_DIMS["finance"]),
            dict(COMMON_DIMS["growth"]),
            {
                "id": "unit_econ", "name": "单店/单SKU经济", "weight": 15,
                "metric": "ue_margin", "field": "ue_margin", "unit": "pct",
                "thresholds": [
                    {"score": 90, "op": "gte", "value": 20},
                    {"score": 70, "op": "gte", "value": 10},
                    {"score": 45, "op": "gte", "value": 0},
                    {"score": 10, "op": "lt", "value": 0},
                ],
                "missing": "downweight",
            },
            dict(COMMON_DIMS["cashflow"]),
            dict(COMMON_DIMS["policy"]),
        ],
        "vetoes": [
            {
                "id": "neg_ue", "name": "单店边际连续为负",
                "condition": {"field": "ue_margin", "op": "lt", "value": -5,
                              "and_field": "ue_trend_negative_years", "and_op": "gte", "and_value": 2},
                "message": "单店边际贡献<-5%且连续2年恶化 = 增长越快失血越快，否决",
            },
        ],
        "valuation_hint": {"type": "PS", "anchor": 2.5, "note": "对标锅圈PS≈2x、十月稻田PS≈3x；仅作参考"},
    },
    "livestock": {
        "category": "livestock",
        "dims": [
            {
                "id": "pipeline", "name": "产能与项目质量", "weight": 25,
                "metric": "invest_output_ratio", "field": "invest_output_ratio", "unit": "ratio",
                "thresholds": [
                    {"score": 90, "op": "gte", "value": 10},
                    {"score": 70, "op": "gte", "value": 6},
                    {"score": 45, "op": "gte", "value": 3},
                    {"score": 10, "op": "lt", "value": 3},
                ],
                "missing": "downweight",
            },
            dict(COMMON_DIMS["finance"]),
            dict(COMMON_DIMS["growth"]),
            {
                "id": "unit_econ", "name": "头均经济性", "weight": 15,
                "metric": "ue_margin", "field": "ue_margin", "unit": "pct",
                "thresholds": [
                    {"score": 90, "op": "gte", "value": 15},
                    {"score": 70, "op": "gte", "value": 8},
                    {"score": 45, "op": "gte", "value": 0},
                    {"score": 10, "op": "lt", "value": 0},
                ],
                "missing": "downweight",
            },
            dict(COMMON_DIMS["cashflow"]),
            dict(COMMON_DIMS["policy"]),
        ],
        "vetoes": [
            {
                "id": "no_eia", "name": "环评缺失",
                "condition": {"field": "eia_passed", "op": "eq", "value": 0},
                "message": "养殖项目无环评 = 合规硬伤（复产即关停风险），否决",
            },
        ],
        "valuation_hint": {"type": "IRR", "anchor": None, "note": "重资产项目看 IRR/投资产值比（对标唐人神1:10）；估值锚不适用PE，仅作参考"},
    },
}

# ============================================================
# 分档规则
# ============================================================
GRADES = {"pass": 75.0, "dig": 60.0}   # >=75 通过 / 60-75 需深挖 / <60 淘汰
GRADE_LABELS = {"pass": "通过（进入尽调）", "dig": "需深挖", "fail": "淘汰"}

# 缺失数据时的区间半宽（数据不足输出分数区间，不用估算冒充）
MISSING_SCORE_SPAN = 7.0

# ============================================================
# 提取字段总清单（L2 提取管线的目标 JSON Schema 字段）
# field -> {label, type, patterns(正则), synonyms, unit_hint, category_only}
# ============================================================
FIELD_SCHEMA = {
    "revenue":            {"label": "营业收入", "type": "money", "synonyms": ["营业收入", "营收", "销售总收入", "主营业务收入", "总收入"], "unit_hint": "元/万元/亿元"},
    "cash_received":      {"label": "销售商品收到的现金", "type": "money", "synonyms": ["销售商品、提供劳务收到的现金", "销售商品收到的现金", "销售收现"], "unit_hint": "元/万元/亿元"},
    "gross_margin":       {"label": "综合毛利率", "type": "pct", "synonyms": ["综合毛利率", "毛利率"], "unit_hint": "%"},
    "revenue_growth":     {"label": "营收增速", "type": "pct", "synonyms": ["营收增速", "收入增速", "营收增长", "同比增长", "营收年增长"], "unit_hint": "%"},
    "top5_client_pct":    {"label": "前五大客户占比", "type": "pct", "synonyms": ["前五大客户", "前5大客户", "客户集中度", "前五大客户占比"], "unit_hint": "%"},
    "cash_balance":       {"label": "现金余额", "type": "money", "synonyms": ["货币资金", "现金余额", "现金及现金等价物", "账面现金"], "unit_hint": "元/万元/亿元"},
    "monthly_burn":       {"label": "月均消耗", "type": "money", "synonyms": ["月均消耗", "月度烧钱", "月均支出", "每月运营成本"], "unit_hint": "元/万元/亿元"},
    "subsidy_pct":        {"label": "补贴收入占比", "type": "pct", "synonyms": ["补贴收入", "政府补助", "补贴占比", "政府补贴"], "unit_hint": "%"},
    "bio_inventory_pct":  {"label": "生物资产/存货占流动资产比", "type": "pct", "synonyms": ["生物资产", "存货占流动资产", "消耗性生物资产"], "unit_hint": "%"},
    "gross_profit":       {"label": "毛利润", "type": "money", "synonyms": ["毛利润", "毛利"], "unit_hint": "元/万元/亿元"},
    # 分类特异字段
    "approved_varieties": {"label": "审定品种数", "type": "count", "synonyms": ["审定品种", "通过审定", "国审品种", "省审品种"], "category_only": ["seeds"]},
    "safety_certs":       {"label": "安全证书数", "type": "count", "synonyms": ["安全证书", "生物安全证书", "转基因安全证书"], "category_only": ["seeds"]},
    "units_sold":         {"label": "累计装机/销售台数", "type": "count", "synonyms": ["装机量", "累计销售", "台数", "保有量", "出货量"], "category_only": ["agmach"]},
    "arr_ratio":          {"label": "ARR占收入比", "type": "pct", "synonyms": ["ARR", "订阅收入", "经常性收入", "年经常性收入"], "category_only": ["digag"]},
    "renewal_rate":       {"label": "续费率", "type": "pct", "synonyms": ["续费率", "续约率", "留存率", "复购率"], "category_only": ["digag", "supply"]},
    "reg_certs":          {"label": "农药/肥料登记证数", "type": "count", "synonyms": ["登记证", "农药登记证", "肥料登记证", "产品登记"], "category_only": ["bioinputs"]},
    "pipeline_certs":     {"label": "在审登记证数", "type": "count", "synonyms": ["在审", "申报中", "管线产品", "在登记中"], "category_only": ["bioinputs"]},
    "store_count":        {"label": "门店/网点数", "type": "count", "synonyms": ["门店数", "门店", "网点", "加盟店", "门店数量"], "category_only": ["supply"]},
    "ue_margin":          {"label": "单位经济边际", "type": "pct", "synonyms": ["单店毛利", "单台毛利", "头均毛利", "亩均收益", "边际贡献", "单店模型"], "unit_hint": "%"},
    "ue_trend_negative_years": {"label": "UE连续为负年数", "type": "count", "synonyms": ["连续亏损", "持续亏损"], "category_only": ["supply"]},
    "invest_output_ratio":{"label": "投资产值比", "type": "ratio", "synonyms": ["投资产值比", "投资/产值", "产值比"], "category_only": ["livestock"]},
    "eia_passed":         {"label": "环评状态", "type": "bool", "synonyms": ["环评", "环境影响评价", "环评批复", "环保验收"], "category_only": ["livestock"]},
    "company_name":       {"label": "企业名称", "type": "text", "synonyms": ["公司名称", "企业名称", "项目公司"]},
}

# ============================================================
# 数据缺口分级（L4）——致命/重要/一般
# ============================================================
GAP_LEVELS = {
    "fatal": {
        "fields": ["revenue", "gross_margin"],
        "guidance": "无法形成评分结论的必需字段",
    },
    "critical": {
        "fields": ["cash_balance", "revenue_growth", "top5_client_pct", "monthly_burn", "subsidy_pct", "ue_margin"],
        "guidance": "影响核心维度得分，缺失将导致分数区间大幅放宽",
    },
    "normal": {
        "fields": ["bio_inventory_pct", "cash_received", "gross_profit"],
        "guidance": "影响五闸完整性与细节判读",
    },
}

# 补数建议的人话模板（field -> 话术）
SUPPLEMENT_HINTS = {
    "revenue": "请提供利润表或审计报告中的「营业收入」（近一年或 TTM）；手机拍照上传也可以，系统可 OCR 识别。",
    "gross_margin": "请提供毛利润或营业成本数据（利润表上半部分），或直接标注毛利率数字。",
    "cash_balance": "请提供最近一期资产负债表中的「货币资金」科目，或银行对账单截图。",
    "monthly_burn": "请提供月均运营支出（工资+房租+研发等），或近三个月管理费用合计。",
    "revenue_growth": "请提供上一年度营业收入（用于计算同比增速），或直接说明增速。",
    "top5_client_pct": "请说明前五大客户合计收入占比（BP 客户章节或审计附注中通常有）。",
    "subsidy_pct": "请提供政府补贴/补助金额（利润表「其他收益」科目或附注）。",
    "ue_margin": "请提供单店/单台/头均的边际贡献测算（BP 的单位经济模型章节），或营收与可变成本。",
    "cash_received": "请提供现金流量表「销售商品、提供劳务收到的现金」。",
    "bio_inventory_pct": "请提供流动资产明细（资产负债表附注），含存货与生物资产科目。",
}

# ============================================================
# 深挖清单模板（进入尽调必问，按分类）
# ============================================================
DEEP_DIGS = {
    "seeds": [
        "核心亲本材料的权属是否清晰（自研/授权/合作单位分成）？",
        "审定品种未来 2 年推广面积与市占率的第三方佐证（种业管理处数据/经销商台账）",
        "安全证书对应性状的商业化时间表与品种权许可协议",
        "生物育种研发投入资本化政策与在建管线估值口径",
    ],
    "agmach": [
        "补贴政策依赖度：剔除购置补贴后的真实终端价格与毛利",
        "台均作业量/单台回本周期的真实运营数据（抽样 10 台跟踪）",
        "经销商库存与终端动销（防止压货虚增收入）",
        "关键部件供应链国产化率与关税风险",
    ],
    "digag": [
        "ARR 口径验证：合同负债科目与续约合同原件",
        "政企客户的预算来源（是否专项债/项目制，可持续性）",
        "数据资产的确权与合规（农业数据出境与隐私）",
        "项目制收入与订阅收入的毛利拆分",
    ],
    "bioinputs": [
        "登记证编号逐一在中国农药信息网复核（真伪与有效期限）",
        "菌种/专利的来源与独占性（高校院所转让协议）",
        "产能利用率与发酵成本曲线（规模化的单位成本下降证据）",
        "田间试验数据的第三方复现（农业农村部指定机构报告）",
    ],
    "supply": [
        "单店/单SKU UE 的实地抽验（选 3 家门店看流水）",
        "复购率口径（App 下单复购 vs 渠道整体复购）",
        "冷链与仓配的自有/外包比例及成本锁定",
        "加盟模式下的食品安全责任与抽检记录",
    ],
    "livestock": [
        "环评批复文号与验收报告（生态环境部门公示系统核对）",
        "生物资产盘点：存栏量的第三方盘点报告",
        "政府基金参投的回购/对赌条款细则",
        "疫病防控体系与保险覆盖（非瘟/禽流感预案）",
    ],
}

for _cid, _card in SCORING_CARDS.items():
    _card["deep_dig"] = DEEP_DIGS.get(_cid, [])
