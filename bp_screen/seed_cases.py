# -*- coding: utf-8 -*-
"""
种子案例库：15 个基准锚点案例（metrics 仅含对标锚点值，用于报告对标条与分类基准）

来源诚实标注（重要，勿删）：
    - is_benchmark=1 的 8 条：公开上市公司财务锚点，取自公开财报/招股书，可外部复核。
      但 metrics 只是对标锚点，不代表该公司完整财务画像。
    - is_benchmark=0 的 7 条：**合成案例**，公司名、财务指标、尽调结局均为虚构，
      仅用于给评分引擎做压力测试与正/负对照。source 字段标 "synthetic"。
    - 报告与对外材料引用案例时，必须按 source 区分，不得把 synthetic 案例当成真实尽调样本。
      合成案例的「预设结局」不是真实结局——旧版文案写作「真实结局」已修正。
"""
from . import db

SEED_CASES = [
    # ① 种业与生物育种
    {"name": "隆平高科", "category": "seeds", "is_benchmark": 1, "outcome": "上市种业龙头",
     "metrics": {"gross_margin": 38.0, "net_margin": 13.0, "pe": 24.0, "approved_varieties": 40, "revenue_growth": 12.0}},
    {"name": "史记生物", "category": "seeds", "is_benchmark": 1, "outcome": "育种平台（案例对标）",
     "metrics": {"gross_margin": 42.0, "net_margin": 11.0, "pe": 24.0, "approved_varieties": 12, "revenue_growth": 25.0}},
    {"name": "某生物育种公司A（正对照）", "category": "seeds", "is_benchmark": 0, "outcome": "验证通过案例：预设结局=通过尽调并完成融资",
     "metrics": {"revenue": 180000000, "gross_margin": 41.0, "revenue_growth": 28.0, "approved_varieties": 6,
                 "safety_certs": 2, "cash_balance": 220000000, "monthly_burn": 6000000,
                 "top5_client_pct": 38.0, "subsidy_pct": 8.0, "ue_margin": 32.0, "runway_months": 36.7}},
    # ② 农机装备
    {"name": "极飞科技", "category": "agmach", "is_benchmark": 1, "outcome": "植保无人机龙头",
     "metrics": {"gross_margin": 30.0, "ps": 6.9, "units_sold": 80000, "revenue_growth": 20.0}},
    {"name": "某智能农机公司B", "category": "agmach", "is_benchmark": 0, "outcome": "压力测试案例：预设结局=未通过尽调",
     "metrics": {"revenue": 90000000, "gross_margin": 18.0, "revenue_growth": 8.0, "units_sold": 150,
                 "cash_balance": 25000000, "monthly_burn": 5000000, "top5_client_pct": 72.0,
                 "subsidy_pct": 55.0, "ue_margin": 2.0, "runway_months": 5.0}},
    # ③ 智慧农业SaaS
    {"name": "托普云农", "category": "digag", "is_benchmark": 1, "outcome": "上市智慧农业企业",
     "metrics": {"gross_margin": 51.0, "ps": 15.0, "arr_ratio": 45.0, "renewal_rate": 85.0, "revenue_growth": 18.0}},
    {"name": "某数字农业SaaS公司C", "category": "digag", "is_benchmark": 0, "outcome": "正对照案例：完成A轮融资",
     "metrics": {"revenue": 60000000, "gross_margin": 54.0, "revenue_growth": 40.0, "arr_ratio": 38.0,
                 "renewal_rate": 80.0, "cash_balance": 45000000, "monthly_burn": 3500000,
                 "top5_client_pct": 55.0, "subsidy_pct": 10.0, "ue_margin": 30.0, "runway_months": 12.9}},
    # ④ 生物农资与合成生物
    {"name": "慕恩生物", "category": "bioinputs", "is_benchmark": 1, "outcome": "微生物组平台",
     "metrics": {"gross_margin": 48.0, "reg_certs": 34, "pipeline_certs": 20, "revenue_growth": 35.0}},
    {"name": "某微生物制剂公司D", "category": "bioinputs", "is_benchmark": 0, "outcome": "压力案例：尽调后发现管线注水",
     "metrics": {"revenue": 30000000, "gross_margin": 32.0, "revenue_growth": 15.0, "reg_certs": 1,
                 "pipeline_certs": 1, "cash_balance": 12000000, "monthly_burn": 2500000,
                 "top5_client_pct": 65.0, "subsidy_pct": 22.0, "ue_margin": 8.0, "runway_months": 4.8}},
    # ⑤ 供应链与品牌食品
    {"name": "锅圈食汇", "category": "supply", "is_benchmark": 1, "outcome": "万店连锁（上市）",
     "metrics": {"gross_margin": 22.0, "ps": 2.0, "store_count": 10000, "ue_margin": 12.0, "revenue_growth": 15.0}},
    {"name": "十月稻田", "category": "supply", "is_benchmark": 1, "outcome": "农产品品牌上市",
     "metrics": {"gross_margin": 17.0, "ps": 3.0, "store_count": 5000, "ue_margin": 8.0, "revenue_growth": 20.0}},
    {"name": "某生鲜供应链公司E", "category": "supply", "is_benchmark": 0, "outcome": "压力案例：单店模型未跑通，扩张停滞",
     "metrics": {"revenue": 150000000, "gross_margin": 12.0, "revenue_growth": 6.0, "store_count": 320,
                 "cash_balance": 18000000, "monthly_burn": 5500000, "top5_client_pct": 48.0,
                 "subsidy_pct": 3.0, "ue_margin": -8.0, "ue_trend_negative_years": 3, "runway_months": 3.3}},
    # ⑥ 养殖与县域基建
    {"name": "唐人神县域项目", "category": "livestock", "is_benchmark": 1, "outcome": "县域产业链标杆",
     "metrics": {"gross_margin": 16.0, "invest_output_ratio": 10.0, "ue_margin": 9.0, "revenue_growth": 12.0}},
    {"name": "某县域养殖项目F", "category": "livestock", "is_benchmark": 0, "outcome": "正对照：政府基金参投",
     "metrics": {"revenue": 500000000, "gross_margin": 15.0, "revenue_growth": 10.0, "invest_output_ratio": 8.0,
                 "cash_balance": 120000000, "monthly_burn": 8000000, "top5_client_pct": 42.0,
                 "subsidy_pct": 12.0, "ue_margin": 7.0, "eia_passed": 1, "runway_months": 15.0}},
    {"name": "某养殖项目G（无环评）", "category": "livestock", "is_benchmark": 0, "outcome": "否决案例：环保停产",
     "metrics": {"revenue": 200000000, "gross_margin": 13.0, "revenue_growth": 5.0, "invest_output_ratio": 2.5,
                 "cash_balance": 30000000, "monthly_burn": 6000000, "subsidy_pct": 25.0,
                 "ue_margin": 1.0, "eia_passed": 0, "runway_months": 5.0}},
]


def seed():
    if len(db.all_cases()) > 0:
        return False
    for c in SEED_CASES:
        # 修：明确区分来源，避免合成案例被当成真实尽调样本引用。
        # benchmark=公开上市公司财务锚点（可外部复核）；其余为合成案例（指标与结局均为虚构）。
        src = "benchmark" if c["is_benchmark"] else "synthetic"
        db.insert_case(c["name"], c["category"], c["metrics"], c["outcome"],
                       c["is_benchmark"], source=src)
    return True
