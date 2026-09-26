# -*- coding: utf-8 -*-
"""
L6 核验（登记证/审定/环评）

【重要】LOCAL_REGISTRY 是**本地示例库，不是官方数据源**。
    - 里面 7 个审定品种、4 个登记证号、2 个安全证书编号均为演示数据。
    - 因此本模块绝不产出 status="verified"。本地命中只给 status="local_hit"，
      语义是「与示例库中的样例字符串一致」，可用于格式校验参考，
      **不能**作为「该证照已获官方批准」的结论。
    - 每条结果都带 official_source：告诉调用方真正要去查哪个官方系统。

生产接入方向（诚实标注，未接通）：
    - 审定品种 → 农业农村部种业管理司 / 全国农业技术推广服务中心品种信息查询
    - 农药肥料登记证 → 农业农村部农药检定所 / 中国农药信息网 chinapesticide.org.cn
    - 安全证书 → 农业农村部农业转基因生物安全委员会公告
    - 环评批复 → 生态环境部门建设项目环评公示系统
    注：EPPO（eppo.int）是植物保护组织的有害生物数据库，**不是**品种审定或农药登记
    数据源，不能用它做证照核验。评估文档早期误标为「接 EPPO」，此处更正。

核验三档：
    local_hit    与本地示例库字符串一致（格式参考，非官方核验）
    unverified   文本声称有相关资质，但未提供可核验的编号/名称，需人工
    not_found    文本中未发现相关资质表述
"""
from .rules import CATEGORIES

# 本地示例库（DEMO，非官方数据源）
LOCAL_REGISTRY = {
    # 审定品种（种业管理司公告格式：品种名 + 国审玉2025xxxx）
    "审定": ["金玉188", "郑单958", "中科玉505", "裕丰303", "登海605", "先玉335", "隆平206"],
    # 农药/肥料登记证号段（中国农药信息网格式：PD20xx-xxxx / 农肥准字）
    "登记": ["PD20250012", "PD20241137", "微生物菌剂2025-0210", "农肥准字2025-3571"],
    # 安全证书（农业转基因生物安全证书编号格式）
    "安全证书": ["农基安证字(2025)第011号", "农基安证字(2024)第052号"],
}

DEMO_REGISTRY = True

# 真正的官方核验入口（供报告提示调用方去查）
OFFICIAL_SOURCES = {
    "审定品种": "农业农村部种业管理司 / 全国农业技术推广服务中心品种信息查询",
    "安全证书": "农业农村部农业转基因生物安全委员会公告",
    "农药/肥料登记证": "农业农村部农药检定所 / 中国农药信息网 chinapesticide.org.cn",
    "环评批复": "生态环境部门建设项目环评公示系统",
}

_LOCAL_HIT_NOTE = ("与本地示例库样例字符串一致，仅可用于格式校验参考；"
                   "示例库非官方数据源，不得作为「证照已获批」结论。"
                   "正式结论需在官方系统按编号复核。")
_UNVERIFIED_NOTE = "文本声称有此资质但未提供可核验编号，需人工向企业索取后在官方系统复核。"


def verify(normalized: dict, all_text: str, category: str) -> list:
    """对分类特异证照做核验：从文本比对证照名 → 输出三档状态 + 官方复核入口。"""
    results = []
    seen = set()  # 修：去重（type, value）。旧版对 ["审定","品种审定"] 两条 kw 各扫一遍，
                  # 同一条证照会被追加两次，实测金玉188/郑单958 各重复出现一次。

    def _add(r: dict):
        key = (r["type"], r["value"])
        if key in seen:
            return
        seen.add(key)
        r.setdefault("official_source", OFFICIAL_SOURCES.get(r["type"], "-"))
        results.append(r)

    if category == "seeds":
        # 审定品种：只扫一遍，不再按 kw 循环
        hit_names = [n for n in LOCAL_REGISTRY["审定"] if n in all_text]
        for name in hit_names:
            _add({"type": "审定品种", "value": name, "status": "local_hit",
                  "source": "本地示例库（DEMO，非官方数据源）", "note": _LOCAL_HIT_NOTE})
        for cert in LOCAL_REGISTRY["安全证书"]:
            if cert in all_text:
                _add({"type": "安全证书", "value": cert, "status": "local_hit",
                      "source": "本地示例库（DEMO，非官方数据源）", "note": _LOCAL_HIT_NOTE})
        # 声称有审定但无可核验的具体品种名
        claimed = any(kw in all_text for kw in ("审定", "品种审定"))
        if claimed and not hit_names:
            _add({"type": "审定品种", "value": "声称有审定品种，未提供可核验编号",
                  "status": "unverified", "source": "-", "note": _UNVERIFIED_NOTE})
        elif claimed and hit_names:
            # 命中示例库不等于官方核验——补一条复核提示，避免调用方把 local_hit 当过闸
            _add({"type": "审定品种", "value": "，".join(hit_names),
                  "status": "unverified", "source": "-",
                  "note": "命中本地示例库，仍需按审定编号（国审玉2025xxxx）在官方系统复核后方可视为已核定。"})

    if category == "bioinputs":
        for cert in LOCAL_REGISTRY["登记"]:
            if cert in all_text:
                _add({"type": "农药/肥料登记证", "value": cert, "status": "local_hit",
                      "source": "本地示例库（DEMO，非官方数据源）", "note": _LOCAL_HIT_NOTE})
        reg = normalized.get("reg_certs")
        if reg and not any(r["type"] == "农药/肥料登记证" and r["status"] == "local_hit" for r in results):
            _add({"type": "农药/肥料登记证", "value": f"声称 {int(reg)} 张，未提供编号",
                  "status": "unverified", "source": "-", "note": _UNVERIFIED_NOTE})

    if category == "livestock":
        # 修：eia_passed 旧版永不提取（正则无捕获组），养殖类环评判断实际从未生效；
        # 现 eia_passed 可提为布尔值，此处优先采信字段，其次退回文本关键词。
        has_eia = bool(normalized.get("eia_passed"))
        if not has_eia and "环评" in all_text:
            has_eia = None  # 只出现「环评」二字，不足以判定已通过
        _add({"type": "环评批复",
              "value": "文本出现「环评已通过/批复/验收」表述" if has_eia
                       else ("文本出现「环评」表述但未声明通过" if has_eia is None
                             else "未发现环评材料"),
              "status": "unverified" if has_eia else "not_found",
              "source": "-",
              "note": ("养殖类必验：索取环评批复文号后在生态环境部门公示系统复核。"
                       "文本自述不构成批复证据。")})
    return results


def verify_text_certs(all_text: str) -> list:
    return verify({}, all_text, "seeds") + verify({}, all_text, "bioinputs")
