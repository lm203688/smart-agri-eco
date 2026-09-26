# -*- coding: utf-8 -*-
"""L8 报告组装：统一 11 区块模板（不管输入几个文件，报告结构一致）。

区块清单（block_ 前缀，实测 11 个）：
    block_meta     元信息（规则版本/时间/LLM 模式）
    block_verdict  三档结论 + 总分 + 区间 + 理由
    block_path     决策路径（归因：一票否决 > 五闸爆雷 > 得分贡献）
    block_card     六评分卡明细
    block_gates    五闸爆雷明细
    block_verify   证照核验结果（含官方复核入口）
    block_gaps     三级数据缺口
    block_bench    同类案例对标
    block_dd       尽调深挖清单
    block_extract  提取溯源（字段值 + 来源文件页码）
    block_files    文件角色归档树
"""
import json
from . import db
from .rules import CATEGORIES, SCORING_CARDS


def fmt_amount(v):
    if v is None:
        return "—"
    if abs(v) >= 1e8:
        return f"{v / 1e8:.2f} 亿元"
    if abs(v) >= 1e4:
        return f"{v / 1e4:.1f} 万元"
    return f"{v:g} 元"


def build_report(aid: str, company: str, category: str, cls_result: dict, n: dict,
                 evaluation: dict, gaps: dict, archive_tree: dict, verify_results: list,
                 conflicts: list, files_meta: list) -> dict:
    cat = CATEGORIES.get(category, {})
    card = SCORING_CARDS.get(category, {})
    # 对标条：同分类基准案例
    benchmarks = []
    for c in db.all_cases():
        if c["category"] == category and c["is_benchmark"]:
            m = c["metrics"] if isinstance(c["metrics"], dict) else json.loads(c["metrics"])
            row = {"name": c["name"]}
            for f in ["gross_margin", "net_margin", "pe", "ps", "invest_output_ratio", "revenue_growth"]:
                if f in m:
                    row[f] = m[f]
            benchmarks.append(row)
    bm_gm = cat.get("benchmarks", {}).get("gross_margin")

    # 深挖清单（分类模板 + 实际缺口）
    dd = list(card.get("deep_dig", []))
    for item in gaps.get("critical", {}):
        dd.append(f"关键数据缺失：{item}")
    for c in conflicts:
        dd.append(f"数据冲突核查：{c['field']} 在不同文件间差异 {c['deviation_pct']}%，要求企业提供口径说明")

    report = {
        "report_id": aid,
        "company": company or "未命名项目",
        "rules_version": evaluation["rules_version"],
        "generated_at": db._now_iso(),
        # 区块1 档案树
        "block_files": {
            "title": "① 资料档案：你上传的文件，我们这样用",
            "files": files_meta, "tree": archive_tree,
            "conflicts": conflicts,
        },
        # 区块2 结论
        "block_verdict": {
            "title": "② 初筛结论",
            "verdict": evaluation["verdict"], "verdict_name": evaluation["verdict_name"],
            "verdict_reason": evaluation["verdict_reason"],
            "total": evaluation["card"]["total"],
            "total_range": evaluation["card"]["total_range"],
            "category": category, "category_name": cat.get("name", "未分类"),
            "category_confidence": cls_result.get("confidence"),
            "gate_count": len(evaluation["gates_fired"]),
            "veto_count": len(evaluation["vetoes_fired"]),
        },
        # 区块3 决策路径
        "block_path": {
            "title": "③ 决策路径：这个结论是怎么来的",
            "items": evaluation["decision_path"],
            "counterfactual": evaluation["counterfactual"],
        },
        # 区块4 五闸
        "block_gates": {
            "title": "④ 通用五闸（红线扫描）",
            "fired": evaluation["gates_fired"],
            "n": n,
        },
        # 区块5 评分卡
        "block_card": {
            "title": f"⑤ 评分卡：{card.get('name', '')}",
            "dimensions": evaluation["card"]["dimensions"],
            "total": evaluation["card"]["total"],
            "total_range": evaluation["card"]["total_range"],
            "missing": evaluation["card"]["missing_dimensions"],
        },
        # 区块6 对标条
        "block_bench": {
            "title": "⑥ 同类基准对标",
            "benchmarks": benchmarks, "project": n, "benchmark_gm": bm_gm,
            "bench_names": cat.get("bench_names", []),
        },
        # 区块7 核验
        "block_verify": {"title": "⑦ 证照公开核验", "results": verify_results},
        # 区块8 数据缺口
        "block_gaps": {"title": "⑧ 数据缺口与补数建议", "gaps": gaps},
        # 区块9 深挖清单
        "block_dd": {"title": "⑨ 深挖问题清单（进入尽调必问）", "items": dd},
        # 区块10 提取明细
        "block_extract": {"title": "⑩ 提取数据明细（全量溯源）", "normalized": n},
        # 区块11 版本与合规
        "block_meta": {
            "title": "⑪ 模型版本与免责声明",
            "rules_version": evaluation["rules_version"],
            "case_count": len(db.all_cases()),
            "disclaimer": "本报告为初筛参考（通过/需深挖/淘汰三档），不构成投资决策建议。评分基于公开案例归纳的规则模型，"
                          "数据不足处已标注区间与缺口。所有提取值可溯源至原始文件页码；无来源标注的数值未计入评分。",
        },
    }
    return report


def fmt_row(field, n):
    val = n.get(field)
    if val is None:
        return "缺失"
    if field in ("revenue", "gross_profit", "net_profit", "cash_balance", "cash_received", "monthly_burn", "revenue_prev", "arr", "subsidy_amount"):
        return fmt_amount(val)
    if field in ("gross_margin", "revenue_growth", "top5_client_pct", "subsidy_pct", "ue_margin", "cash_ratio", "arr_ratio", "renewal_rate", "gm_trend_pct", "gov_fund_ratio", "rd_pct", "gross_margin_prev"):
        return f"{val:g}%"
    return f"{val:g}"
