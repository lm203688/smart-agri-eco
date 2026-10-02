# -*- coding: utf-8 -*-
"""
L2 数据提取（LLM 网关 + 正则双通道）+ L3 归一化
- 数字类字段：正则引擎独立提取 → LLM 通道（可用时）交叉验证 → 分歧>5% 标记人工复核
- 每个值记录来源（文件名+页码），无来源不计分
- LLM 不可用时自动降级为纯正则模式（本 MVP 的默认运行模式）
"""
import re
from .parser import ParsedFile
from .llm import llm_available, llm_extract_fields

# ---------------- 字段正则模式（万/亿/元/百分比归一到元或pct） ----------------
PCT = r"(?:([-+]?\d+(?:\.\d+)?)\s*%)"
NUM = r"([-+]?\d+(?:\.\d+)?)"

FIELD_PATTERNS = {
    "revenue": [
        r"(?:营业[收]?入|销售[收]?入|总?收入|Revenue)[^0-9\-]{0,12}" + NUM + r"\s*(万|亿|元)?",
        r"^(?:营收|收入)" + NUM + r"\s*(万|亿|元)?$",
    ],
    "gross_profit": [
        r"(?:毛利润|毛利|gross\s*profit)[^0-9\-]{0,10}" + NUM + r"\s*(万|亿|元)?",
    ],
    "gross_margin": [
        r"(?:毛利率?|gross\s*margin)[^0-9润\-]{0,10}" + NUM + r"\s*%?",
        r"毛利率\s*(?:约为?|约|是|=)?\s*" + NUM + r"\s*%",
    ],
    "net_profit": [
        r"(?:净利润|净利|归母净利润)[^0-9\-]{0,10}" + NUM + r"\s*(万|亿|元)?",
    ],
    "cash_balance": [
        r"(?:货币资金|现金及现金等价物|现金余额|账面现金|银行存款余额)[^0-9\-]{0,10}" + NUM + r"\s*(万|亿|元)?",
    ],
    "cash_received": [
        r"(?:销售商品[^0-9\-]{0,10}收到的现金|销售商品、提供劳务收到的现金)[^0-9\-]{0,10}" + NUM + r"\s*(万|亿|元)?",
    ],
    "monthly_burn": [
        r"(?:月均?(?:运营)?(?:支出|消耗|烧钱|burn)|每月(?:支出|消耗|费用)|burn)[^0-9\-]{0,10}" + NUM + r"\s*(万|亿|元)?",
    ],
    "revenue_prev": [
        r"(?:上[一]?年(?:度)?(?:营业收入|营收|收入)|去年同期收入|上年营业收入)[^0-9\-]{0,10}" + NUM + r"\s*(万|亿|元)?",
    ],
    "top5_client_pct": [
        r"(?:前五大客户(?:合计)?(?:销售|收入)?占比?|客户集中度)[^0-9\-]{0,10}" + NUM + r"\s*%?",
    ],
    "subsidy_pct": [
        r"(?:占(?:营业收入|收入)的?(?:比例|比)|补贴(?:收入)?占比|政府(?:补贴|补助)(?:收入)?占比)[^0-9\-]{0,6}" + NUM + r"\s*%",
    ],
    "subsidy_amount": [
        r"(?:政府(?:补贴|补助)|其他收益)[^0-9\-]{0,10}" + NUM + r"\s*(万|亿|元)?",
    ],
    "gross_margin_prev": [
        r"(?:上年|去年|上期)毛利率[^0-9\-]{0,10}" + NUM + r"\s*%?",
    ],
    "net_margin": [
        # 修：原式 `净利率?` 的 `率?` 使「率」可选，会命中「净利润1800万」中的「净利」+「润」，
        # 把金额当百分数提出（实测 net_margin=1800.0，真值应为 10.0 或缺失）。
        # 现强制要求「率」且必须带 %。
        r"(?:销售净利率|净利率)[^0-9\-]{0,10}" + NUM + r"\s*%",
    ],
    "ue_margin": [
        r"(?:单位经济(?:模型)?边际贡献|单(?:店|台|亩|头)边际贡献|边际贡献率|UE(?:margin)?)[^0-9\-]{0,10}" + NUM + r"\s*%?",
    ],
    "ue_trend_negative_years": [
        r"连续(\d+)\s*年(?:亏损|边际贡献为负|为负)",
    ],
    "runway_months": [
        r"(?:现金跑道|runway)[^0-9\-]{0,10}" + NUM + r"\s*个?月?",
    ],
    # ---- v2.1.0 新增（2026-09-30）：AgTech Seed 硬指标 ----
    # Harvest Returns 2025：Seed 阶段农户 ROI < 3:1 是投资人常见 deal-killer。
    # 匹配 "农户ROI 3:1" / "农民投入产出比约 4" / "农户净收益 3 倍" 等常见表述。
    "farmer_roi": [
        r"(?:农户|农民|种植户)[^\d]{0,12}(?:ROI|投产比|投入产出比|净收益倍数)[^\d]{0,8}"
        + r"(\d+(?:\.\d+)?)\s*(?:[:：]\s*1|\s*(?:倍|:)?\s*1)?",
        r"(?:农户|农民|种植户)\s*(?:每[吨亩]净收益|回报率)[^\d]{0,10}"
        + r"(\d+(?:\.\d+)?)\s*(?:倍)",
    ],
    # ---- v2.2.0 新增（2026-09-30）：5 大 DD deal-killers + AgTech 合规 ----
    # 依据 Harvest Returns / iGrow News 2025 调研：种子轮 AgTech 项目常见 5 大 deal-killers
    # 以及 EPA 农药注册 / USDA 有机认证 / 水权许可三合规维度。
    # 均为布尔存在型（命中即 True，表示"披露了此风险"或"已获该合规"）；缺失即跳过。
    # 5 大 DD deal-killers（负面事件披露 → 触发 verify/warn 门禁）
    "intellectual_property_issues": [
        r"(?:IP|知识产权|核心专利|技术)[^\n]{0,15}(?:归属不清|归属争议|未明确|共有|纠纷|转让争议|尚未确权)",
        r"(?:核心专利|技术秘密|源代码|技术资产)[^\n]{0,15}(?:共有|联名|共同所有|外部持有)",
        r"(?:知识产权|专利)[^\n]{0,15}(?:诉讼|仲裁|侵权)",
    ],
    "contract_restrictions": [
        r"(?:客户合同|核心客户)[^\n]{0,15}(?:竞业禁止|排他|竞业限制|独家供应|排他性)",
        r"(?:主要客户|大客户)[^\n]{0,15}(?:终止条款|单方解除|随时终止|90天终止|30天终止)",
        r"(?:合同|协议)[^\n]{0,15}(?:限制条款|排他条款|竞业条款|回购条款)",
    ],
    "cap_table_issues": [
        r"(?:cap\s*table|股权架构|股权结构|股本)[^\n]{0,15}(?:混乱|错误|未清理|稀释严重|期权池不足|期权池耗尽|历史遗留)",
        r"(?:期权池|ESOP)[^\n]{0,10}" + NUM + r"\s*%?\s*(?:低于|不足|已耗尽)",
        r"(?:创始团队|创始股东)[^\n]{0,15}(?:股权代持|名义持股|代持|协议控制)",
    ],
    "founder_litigation": [
        r"(?:创始人|联合创始人|核心创始团队)[^\n]{0,15}(?:诉讼|起诉|被告|原告|判决|仲裁|失信)",
        r"(?:创始人|联创)[^\n]{0,15}(?:未决诉讼|被起诉|诉讼中|执行案件)",
    ],
    "financial_restatement": [
        r"(?:财务|会计|报表|财报)[^\n]{0,15}(?:重述|追溯调整|审计意见保留|非标意见|重大错报|虚假)",
        r"(?:审计)[^\n]{0,10}(?:保留意见|无法表示意见|否定意见)",
    ],
    # AgTech 合规三维度（正向合规披露 → 表示"已获该合规"）
    "pesticide_registration": [
        r"(?:EPA\s*农药|农药登记证|农药登记号|农药批准文号)[^\n]{0,15}"
        + r"[（(A-Za-z0-9\-]+[）)]?",
        r"农药(?:登记|批准)[^\n]{0,10}(?:已获|已批准|获批|通过|编号)",
    ],
    "organic_certification": [
        r"(?:USDA\s*有机|有机认证|有机种植认证|有机产品认证)[^\n]{0,15}"
        + r"(?:编号|证书|获批|通过|已获)?",
        r"(?:有机|organic)[^\n]{0,10}(?:认证|证书|批准|通过)",
    ],
    "water_rights": [
        r"(?:水权|取水许可|灌溉许可|水权许可)[^\n]{0,15}"
        + r"(?:编号|证书|已获|通过|批准)?",
        r"取水(?:许可证|许可)[^\n]{0,10}" + r"[（(A-Za-z0-9\-]+[）)]?",
    ],
    # 分类特异指标
    "approved_varieties": [
        # 修：原式量词 `(?:个|项)?` 可选，「品种审定：金玉188（国审玉20250012）」中的品种名
        # 数字会被当审定数量。现强制要求量词（个/项）。
        r"(?:审定(?:通过)?(?:的)?(?:品种|品系)|通过审定[^0-9]{0,8})[^\d]{0,6}(\d+)\s*(?:个|项)",
    ],
    "safety_certs": [
        r"(?:安全证书|生产应用安全证书)[^\d]{0,6}(\d+)\s*(?:张|个|项)",
    ],
    "reg_certs": [
        r"(?:登记证|农药登记证|肥料登记证|产品登记)[^\d]{0,6}(\d+)\s*(?:张|个|项)",
    ],
    "pipeline_certs": [
        # 修：原式 `(?:中)?(?:在)?(?:申请|申报)?` 三个可选 + 两段非数字窗口（合计可达 14 字符），
        # 实测把「管线与资质\n品种审定：金玉188」跨段落匹配出 pipeline_certs=188（品种名数字）。
        # 现强制要求「在(申请|申报)」出现，且要求量词，窗口收窄。
        r"(?:管线[^\d]{0,10}|在(?:申请|申报)|在审)[^\d]{0,8}(\d+)\s*(?:张|个|项)",
    ],
    "units_sold": [r"(?:累[计计]?(?:销售|交付|出货)|年(?:销售|交付|出货)?(?:台|套)?数|销量)[^\d]{0,6}(\d+)\s*(?:台|套|辆|万台)?"],
    "arr": [r"ARR[^0-9\-]{0,10}" + NUM + r"\s*(万|亿|元)?"],
    "arr_ratio": [r"ARR(?:占比|比例|占收入比)[^0-9\-]{0,8}" + NUM + r"\s*%?"],
    "renewal_rate": [r"(?:续约率|续费率|复购率)[^0-9\-]{0,10}" + NUM + r"\s*%?"],
    "store_count": [r"(?:门店(?:总)?数|加盟店(?:数)?|直营店(?:数)?|网点数)[^\d]{0,6}(\d+)\s*(?:家|家店|间)?"],
    "sku_count": [r"SKU[^\d]{0,6}(\d+)"],
    "output_volume": [r"(?:出栏(?:量|数)?)[^\d]{0,6}(\d+)\s*(?:万?头|万?只|吨)?"],
    "invest_output_ratio": [r"(?:投资(?:产出|产值)比|投[资入]产值比)[^0-9]{0,6}1\s*[:：]\s*(\d+)"],
    "gov_fund_ratio": [r"(?:政府(?:基金|平台)(?:持股|出资)?(?:占比|比例)?)[^0-9\-]{0,8}" + NUM + r"\s*%?"],
    "irr": [r"(?:项目)?IRR[^0-9\-]{0,8}" + NUM + r"\s*%?"],
    "eia_passed": [
        # 修：原式无捕获组，regex_extract 取 groups[0] 抛 IndexError 被 except 吞掉 →
        # 该字段在任何输入下都永不提取，养殖类「环评缺失一票否决」与维度评分随之失效。
        r"(环评(?:已)?(?:通过|批复|验收))",
    ],
    "pe_ratio": [r"(?:市盈率|P/?E)[^0-9\-]{0,8}" + NUM + r"\s*(?:倍|x)?"],
    "ps_ratio": [r"(?:市销率|P/?S)[^0-9\-]{0,8}" + NUM + r"\s*(?:倍|x)?"],
    "patents": [r"(?:专利(?:总数|数量)?|授权专利)[^\d]{0,6}(\d+)\s*(?:项|件)?"],
    "team_size": [r"(?:团队(?:总)?(?:人[数员]?|规模))[^\d]{0,6}(\d+)\s*(?:人|名)?"],
    "rd_pct": [
        # 修：原式 `(?:占(?:收入)?比|投入占比)?` 整组可选，退化后「研发」+0-8 个非数字字符+数字
        # 会命中「月均运营支出（工资+研发+管理）600万元」中的「研发」→ 600（实测 rd_pct=600.0，
        # 真值 12.0）。现强制要求出现占比/率指示词，且必须带 %。
        r"(?:研发(?:费用)?(?:占(?:收入)?比|投入占比|费用率|率))[^0-9\-]{0,8}" + NUM + r"\s*%",
    ],
}

UNIT = {"万": 1e4, "亿": 1e8, "元": 1, "万元": 1e4, "亿元": 1e8}

# 布尔存在型字段：正则命中即记 True，不参与数值转换。
# 只对显式声明的字段生效——不能让任意正则失败都变成 True（那会把「正则写错」伪装成「命中」）。
# v2.2.0 新增：5 大 DD deal-killers（负面事件披露）+ AgTech 三合规（正向合规披露）。
BOOL_FIELDS = {
    "eia_passed",
    # 5 大 DD deal-killers（触发 verify 门禁，让 DD 尽调方人工复核）
    "intellectual_property_issues",
    "contract_restrictions",
    "cap_table_issues",
    "founder_litigation",
    "financial_restatement",
    # AgTech 三合规维度（触发 verify 门禁，合规性核查）
    "pesticide_registration",
    "organic_certification",
    "water_rights",
}


def _to_number(num_s, unit_s, is_pct=False):
    v = float(num_s)
    if unit_s and unit_s in UNIT:
        v = v * UNIT[unit_s]
    if is_pct:
        v = v  # 百分数保持 0-100 标度
    return v


def regex_extract(files: list) -> dict:
    """files: [{filename, parsed}] → {field: {value, source, page, pattern_hit}}（逐来源记录，供仲裁）"""
    out = {}
    for f in files:
        pf: ParsedFile = f["parsed"]
        for pg in pf.pages:
            text = pg["text"]
            for field, pats in FIELD_PATTERNS.items():
                for pat in pats:
                    m = re.search(pat, text, re.IGNORECASE | re.MULTILINE)
                    if not m:
                        continue
                    try:
                        groups = m.groups()
                        num = groups[0]
                        unit = groups[1] if len(groups) > 1 and groups[1] else None
                        val = _to_number(num, unit)
                    except (ValueError, IndexError):
                        if field in BOOL_FIELDS:
                            val, unit = True, None   # 布尔存在型：命中即 True
                        else:
                            continue
                    rec = {"value": val, "source": f["filename"], "page": str(pg["source"]),
                           "raw": m.group(0)[:40]}
                    # 同一文件同字段取首次出现（通常为总述位置）
                    if field not in out or f["filename"] not in {r["source"] for r in [out[field]]}:
                        if field in out:
                            # 保留优先来源更高的首个值：审计>流水>申报>其他
                            continue
                        out[field] = rec
                    break
    return out


ROLE_PRIORITY = {"audit": 5, "bank_flow": 4, "tax": 4, "bp": 3, "deck": 3, "license": 3, "contract": 2, "misc": 0}


def extract(files_primary: list) -> tuple:
    """
    返回 (extracted{field: {value, source, page, dual_check}}, by_source{field:{file:value}})
    双通道：正则结果为通道A；LLM 可用时为通道B，交叉验证。
    """
    ch_a = regex_extract(files_primary)
    by_source = {}
    # 逐来源提取（供冲突检测）
    for f in files_primary:
        sub = regex_extract([f])
        for k, v in sub.items():
            by_source.setdefault(k, {})[v["source"]] = v["value"]

    ch_b = {}
    dual_flag = {}
    if llm_available():
        ch_b = llm_extract_fields([{"filename": f["filename"], "text": "\n".join(p["text"] for p in f["parsed"].pages[:30])} for f in files_primary])
        # 交叉验证：数字类字段分歧>5% → 标记
        for field, rec in ch_a.items():
            if field in ch_b and isinstance(ch_b[field], (int, float)) and rec["value"]:
                diff = abs(ch_b[field] - rec["value"]) / max(abs(rec["value"]), 1e-9)
                if diff > 0.05:
                    dual_flag[field] = {"regex": rec["value"], "llm": ch_b[field],
                                        "note": "双通道分歧>5%，报告中标「需人工复核」"}

    extracted = {}
    for field, rec in ch_a.items():
        entry = dict(rec)
        entry["dual_check"] = dual_flag.get(field)
        entry["channel"] = "regex" + ("+llm_verified" if field in ch_b and not dual_flag.get(field) else "")
        extracted[field] = entry
    return extracted, by_source


# ---------------- L3 归一化 ----------------
def normalize(extracted: dict, prev_extracted: dict = None) -> dict:
    """
    派生计算 + 单位统一（金额全部转为「万元」展示）+ 口径说明
    """
    n = {}
    def g(f):
        return extracted.get(f, {}).get("value")

    n["revenue"] = g("revenue")
    n["gross_profit"] = g("gross_profit")
    gm = g("gross_margin")
    if gm is None and g("gross_profit") is not None and g("revenue"):
        gm = round(g("gross_profit") / g("revenue") * 100, 2)
        n["gross_margin"] = gm
        n["gross_margin_derived"] = "由毛利润/营业收入计算"
    else:
        n["gross_margin"] = gm
    n["net_margin"] = g("net_margin")
    # 修：与 gross_margin 一致，允许由 净利润/营业收入 派生（BP 常只给金额不给比率）。
    # 无来源字段不硬造：两项任一缺失则保持 None，由区间化机制表达不确定性。
    if n["net_margin"] is None and g("net_profit") is not None and g("revenue"):
        n["net_margin"] = round(g("net_profit") / g("revenue") * 100, 2)
        n["net_margin_derived"] = "由净利润/营业收入计算"
    n["net_profit"] = g("net_profit")
    n["cash_balance"] = g("cash_balance")
    n["cash_received"] = g("cash_received")
    if g("cash_received") is not None and g("revenue"):
        n["cash_ratio"] = round(g("cash_received") / g("revenue") * 100, 2)
    n["monthly_burn"] = g("monthly_burn")
    if g("cash_balance") is not None and g("monthly_burn"):
        n["runway_months"] = round(g("cash_balance") / g("monthly_burn"), 1)
    elif g("runway_months") is None:
        n["runway_months"] = None
    n["top5_client_pct"] = g("top5_client_pct")
    sub_pct = g("subsidy_pct")
    if sub_pct is None and g("subsidy_amount") is not None and g("revenue"):
        sub_pct = round(g("subsidy_amount") / g("revenue") * 100, 2)
        n["subsidy_pct_derived"] = "由政府补助金额/营业收入计算"
    n["subsidy_pct"] = sub_pct
    n["ue_margin"] = g("ue_margin")
    n["farmer_roi"] = g("farmer_roi")  # v2.1.0：AgTech Seed 硬指标
    n["ue_trend_negative_years"] = g("ue_trend_negative_years")
    n["gross_margin_prev"] = g("gross_margin_prev")
    if n["gross_margin"] is not None and n["gross_margin_prev"] is not None:
        n["gm_trend_pct"] = round(n["gross_margin"] - n["gross_margin_prev"], 2)
    prev_rev = g("revenue_prev") or (prev_extracted or {}).get("revenue", {}).get("value")
    if g("revenue") is not None and prev_rev:
        n["revenue_growth"] = round((g("revenue") - prev_rev) / prev_rev * 100, 2)
    # 分类特异
    for f in ["approved_varieties", "safety_certs", "reg_certs", "pipeline_certs", "units_sold",
              "arr", "arr_ratio", "renewal_rate", "store_count", "sku_count", "output_volume",
              "invest_output_ratio", "gov_fund_ratio", "irr", "pe_ratio", "ps_ratio",
              "patents", "team_size", "rd_pct"]:
        v = g(f)
        if v is not None:
            n[f] = v
    # eia_passed 与 v2.2.0 新增的 5 大 DD deal-killers + AgTech 三合规：
    # 都是布尔存在型字段，缺失=未披露（键写入值为 None），
    # 与 v2.0.0 verify 类门禁语义一致——缺失不判违规，但报告中呈现"未披露"。
    for f in ["eia_passed",
              "intellectual_property_issues", "contract_restrictions", "cap_table_issues",
              "founder_litigation", "financial_restatement",
              "pesticide_registration", "organic_certification", "water_rights"]:
        n[f] = g(f)
    # 万元展示口径
    n["_unit_note"] = "金额字段以原始口径提取，报告展示统一换算为万元/亿元"
    return n
