# -*- coding: utf-8 -*-
"""L0 多文件智能归档：文件类型判定 → 用途仲裁 → 冲突预警"""
import re
from .parser import ParsedFile, full_text

# 文件角色与判定信号
ROLES = {
    "bp":        {"name": "商业计划书", "kw": ["商业计划", "商业计划书", "BP", "融资计划", "公司简介", "项目介绍", "投资价值", "业务模式"],
                  "priority": 3, "use": "primary"},
    "audit":     {"name": "审计/财务报表", "kw": ["审计报告", "资产负债表", "利润表", "现金流量表", "财务报表", "审计", "会计师事务所", "标准无保留"],
                  "priority": 5, "use": "primary"},
    "bank_flow": {"name": "银行流水", "kw": ["银行流水", "对账单", "账户明细", "交易明细"],
                  "priority": 4, "use": "primary"},
    "tax":       {"name": "纳税申报", "kw": ["纳税申报", "增值税申报", "企业所得税", "完税证明"],
                  "priority": 4, "use": "primary"},
    "license":   {"name": "资质/证书", "kw": ["品种审定公告", "登记证编号", "环评批复", "资质证书", "许可证", "营业执照", "荣誉证书"],
                  "priority": 3, "use": "verify"},
    "contract":  {"name": "合同/订单", "kw": ["合同", "订单", "采购协议", "销售合同", "框架协议", "战略协议"],
                  "priority": 2, "use": "support"},
    "deck":      {"name": "路演材料", "kw": ["路演", "Présentation", "presentation", "融资材料", "项目推介"],
                  "priority": 3, "use": "primary"},
    "misc":      {"name": "其他资料", "kw": [], "priority": 0, "use": "archive"},
}


def _detect_role(filename, text_head):
    text_head = text_head[:3000]
    scores = {}
    for role, conf in ROLES.items():
        s = 0
        for kw in conf["kw"]:
            if kw in filename:
                s += 6      # 文件名命中权重高
            if kw in text_head:
                s += 2
        scores[role] = s
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "misc"
    # 财务角色优先：审计>流水>tax > BP（数据更可信）
    return best


def archive(files: list) -> tuple:
    """
    files: [{filename, ftype, role, parsed: ParsedFile}]
    返回 (archive_tree, primary_files, verify_files)
    """
    tree, primary, verify = [], [], []
    for f in files:
        pf: ParsedFile = f["parsed"]
        head = pf.pages[0]["text"] if pf.pages else ""
        role = f.get("role") or _detect_role(f["filename"], head)
        conf = ROLES.get(role, ROLES["misc"])
        entry = {
            "filename": f["filename"], "ftype": f["ftype"], "role": role,
            "role_name": conf["name"], "use": conf["use"],
            "pages": len(pf.pages), "error": pf.error,
            "status": "ok" if not pf.error and pf.pages else ("error" if pf.error else "empty"),
        }
        tree.append(entry)
        if conf["use"] == "primary" and entry["status"] == "ok":
            primary.append({**f, "role": role})
        elif conf["use"] == "verify" and entry["status"] == "ok":
            verify.append({**f, "role": role})
    return tree, primary, verify


def detect_conflicts(extracted_by_source: dict) -> list:
    """extracted_by_source: {field: {source_file: value}} → 同字段跨来源差异>30% 预警"""
    out = []
    for field, srcs in extracted_by_source.items():
        if len(srcs) < 2:
            continue
        vals = [v for v in srcs.values() if isinstance(v, (int, float))]
        if len(vals) < 2:
            continue
        lo, hi = min(vals), max(vals)
        base = abs(hi) if hi else 1
        if base != 0 and (hi - lo) / abs(hi) > 0.30:
            out.append({
                "field": field,
                "values": {k: round(v, 4) if isinstance(v, float) else v for k, v in srcs.items() if isinstance(v, (int, float))},
                "deviation_pct": round((hi - lo) / abs(hi) * 100, 1) if hi else None,
                "note": "来源间差异>30%：按更可信来源（审计>流水>申报>BP）计分，差异本身计入收入质量扣分",
            })
    return out
