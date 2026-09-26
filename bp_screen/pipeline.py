# -*- coding: utf-8 -*-
"""
L0-L8 编排层（从原 full-stack/backend/server.py 抽出，去掉 FastAPI 耦合）

原 server.py 把管线逻辑写在 HTTP handler 里，导致「评分引擎」与「Web 层」强绑定，
脱离 FastAPI 就跑不起来。本模块只保留纯数据流的九层序列，Web 层（web.py）与 MCP 层
（mcp/server.py）都只是它的薄调用方。

九层序列：
  L0 归档      archiver.archive        文件角色判定 + 冲突检测
  L1 解析      parser.parse_file       txt/md/docx 零依赖；pdf/xlsx 依赖缺失时降级跳过
  L2 提取      extractor.extract       正则通道 A；LLM 通道 B 可用时交叉验证
  L3 归一化    extractor.normalize     单位统一 + 派生指标
  L2.5 合理性  sanity.check            【新增】拦下越界值（如把品种名数字当计数），
                                           置空后自然进入区间化路径，不产生假精确结论
  L5 分类      classifier.classify     六分类 + 置信度；<70 需人工确认
  L6 核验      verifier.verify         证照核验；本地库命中只标 local_hit，不冒充官方
  L4 缺口      gap.detect              三级缺口 + 补数提示
  L7 评分      scorer.evaluate         五闸 → 六评分卡 → 一票否决 → 三档
  L8 报告      report.build_report     统一 11 区块报告（block_meta/verdict/path/card/gates/verify/gaps/bench/dd/extract/files）

用法：
    from bp_screen.pipeline import screen_text, screen_fields, run_pipeline

    # 路径一：直接给文本（MCP / 单元测试用，无需落盘）
    result = screen_text("金玉种业商业计划书……", company="金玉种业")

    # 路径二：直接给已抽取字段（跳过 L0-L3，用于已有结构化数据）
    result = screen_fields({"revenue": 1.8e8, "approved_varieties": 6}, category="seeds")

    # 路径三：给文件路径列表（Web 层用）
    result = run_pipeline([("/path/a.pdf", "a.pdf"), ("/path/b.txt", "b.txt")], company="X")
"""
from __future__ import annotations

import os
import uuid

from . import (archiver, classifier, db, extractor, gap, parser, report as report_builder,
               rules, sanity, scorer, verifier)

from .llm import llm_available

# 分类置信度低于此值 → 要求人工确认，不自动进评分
CONFIDENCE_THRESHOLD = 70.0

# 文本直接传入时的虚拟文件名（报告溯源用）
_TEXT_FILENAME = "inline_text.txt"


def _run_inner(texts: list, company: str, aid: str, category_override: str = None) -> dict:
    """texts: [{"filename", "parsed": ParsedFile}]，全部解析成功后进入 L2。

    category_override：人工确认后的分类（或调用方明确指定）。传入且合法时优先于
    自动分类——否则置信度低的 BP 只能永远卡在 need_classify，用户拿 note 里的提示
    去 screen_fields 重跑，而 MCP tool 的 text 模式并不接受 category，形成死路。
    """
    tree, primary, verify_files = archiver.archive(
        [{"filename": p["filename"], "ftype": p["parsed"].ftype, "parsed": p["parsed"]}
         for p in texts])

    parsed_ok = [p for p in texts if not p["parsed"].error]
    all_text = "\n".join(parser.full_text(p["parsed"]) for p in parsed_ok)

    # L2 提取（双通道）
    primary_files = [{"filename": p["filename"], "parsed": p["parsed"]} for p in primary]
    extracted, per_file_extracted = extractor.extract(primary_files)
    cross_flags = {k: v["dual_check"] for k, v in extracted.items()
                   if isinstance(v, dict) and v.get("dual_check")}

    # L3 归一化
    n = extractor.normalize(extracted)

    # L2.5 合理性校验（新增层）
    n, sanity_observations = sanity.check(n)

    # L5 分类
    cls = classifier.classify(all_text, n)
    category = cls["category"]

    # 人工确认 / 调用方指定的分类优先于自动分类
    if category_override:
        if category_override in rules.CATEGORIES:
            cls["category"] = category_override
            cls["need_confirm"] = False
            cls["source"] = "human_confirmed"
            category = category_override
        else:
            return {"status": "invalid_category",
                    "note": (f"category={category_override} 不在六分类中："
                             f"{sorted(rules.CATEGORIES)}"),
                    "rules_version": rules.RULES_VERSION}

    result = {
        "aid": aid,
        "company": company,
        "rules_version": rules.RULES_VERSION,
        "rules_released": rules.RELEASED,
        "llm_mode": ("llm+regex 双通道" if llm_available()
                     else "regex 单通道（未配置 AGRI_VISION_URL/KEY 或 AGRI_BP_LLM_URL/KEY，降级模式）"),
        "channel_flags": {"cross_flags": cross_flags,
                          "sanity_observations": sanity_observations,
                          "sanity_summary": sanity.summarize(sanity_observations)},
        "archive": {"tree": tree,
                    "primary": [p["filename"] for p in primary],
                    "verify": [v["filename"] for v in verify_files]},
    }

    # 分类置信度过低 → 不评分，要求人工确认（避免用错分类去套错评分卡）。
    # 人工已确认（source=human_confirmed）时不再拦——但 confidence 保持实测值不篡改，
    # 让调用方仍能看见「自动分类其实没把握」这个信息。
    if not category or cls.get("confidence", 0) < CONFIDENCE_THRESHOLD:
        if cls.get("source") != "human_confirmed":
            result.update({
                "status": "need_classify",
                "cls": cls,
                "normalized": n,
                "note": (f"分类置信度 {cls.get('confidence', 0)} 低于阈值 {CONFIDENCE_THRESHOLD}，"
                         "请人工确认分类后重跑（text 与 fields 模式均可传 category 强制指定）"),
            })
            return result

    # L6 核验 / L4 缺口 / L7 评分 / L8 报告
    verify_results = verifier.verify(n, all_text, category)
    gaps = gap.detect(n, category)
    conflicts = archiver.detect_conflicts(per_file_extracted)
    evaluation = scorer.evaluate(category, n)

    rep = report_builder.build_report(
        aid, company, category, cls, n, evaluation, gaps,
        {"tree": tree, "primary": [p["filename"] for p in primary],
         "verify": [v["filename"] for v in verify_files]},
        verify_results, conflicts,
        [{"filename": f["filename"], "role": f.get("role", ""),
          "role_name": f.get("role_name", ""), "status": f.get("status", "")} for f in tree])
    rep["cross_flags"] = cross_flags
    rep["llm_mode"] = result["llm_mode"]
    rep["sanity_observations"] = sanity_observations
    rep["sanity_summary"] = result["channel_flags"]["sanity_summary"]

    result.update({
        "status": "done",
        "category": category,
        "category_name": rules.CATEGORIES[category]["name"],
        "cls": cls,
        "normalized": n,
        "evaluation": evaluation,
        "gaps": gaps,
        "verify_results": verify_results,
        "conflicts": conflicts,
        "report": rep,
        "verdict": evaluation.get("verdict_name"),
        "score": evaluation.get("card", {}).get("total"),
        "score_range": evaluation.get("card", {}).get("total_range"),
    })
    return result


def screen_text(text: str, company: str = "", mode: str = "text",
                aid: str = None, filename: str = None, category: str = None) -> dict:
    """
    路径一：直接给文本。不落盘，适合 MCP tool 与单元测试。

    mode: "text" / "md" / "docx"（决定 ftype，影响解析切分；text 与 md 解析逻辑相同）
    category: 人工确认后的分类（六分类 id 之一）。传入时优先于自动分类，
              用于解开「置信度低 → need_classify → 但 text 模式无法指定分类」的死路。
    """
    aid = aid or uuid.uuid4().hex[:8]
    fn = filename or _TEXT_FILENAME
    ext = os.path.splitext(fn)[1].lower()
    ftype = {"docx": "docx", ".docx": "docx", ".md": "md"}.get(ext, "text")
    # parser.parse_file 需要真实路径；文本模式直接构造 ParsedFile
    pf = parser.ParsedFile(filename=fn, ftype=ftype,
                           pages=[{"text": text, "source": "inline"}], error="")
    return _run_inner([{"filename": fn, "parsed": pf}], company, aid,
                      category_override=category)


def screen_fields(fields: dict, category: str = None, company: str = "",
                  all_text: str = "", aid: str = None) -> dict:
    """
    路径二：直接给已抽取字段，跳过 L0-L3（归档/解析/提取/归一化）。

    适合：调用方已有结构化数据（比如自己解析过的 BP），只想用规则库做分类+评分。
    仍会跑 L2.5 合理性校验 —— 外部传入的数据同样可能越界。
    category 缺省时由文本推断；传 None 且无文本则退回 seeds（并标注为默认值）。
    """
    aid = aid or uuid.uuid4().hex[:8]
    tree = []
    primary = [{"filename": "structured_input", "ftype": "text", "parsed": None,
                "role": "primary", "role_name": "结构化输入", "status": "ok"}]
    n = dict(fields)
    n, sanity_observations = sanity.check(n)

    cls = classifier.classify(all_text, n) if all_text else {
        "category": category, "confidence": 100.0, "reason": "调用方直接指定分类",
    }
    if category:
        cls = dict(cls)
        cls["category"], cls["confidence"], cls["reason"] = (
            category, 100.0, "调用方强制指定分类")
    category = cls.get("category")

    result = {
        "aid": aid, "company": company,
        "rules_version": rules.RULES_VERSION, "rules_released": rules.RELEASED,
        "llm_mode": "structured（跳过提取层）",
        "channel_flags": {"cross_flags": {}, "sanity_observations": sanity_observations,
                          "sanity_summary": sanity.summarize(sanity_observations)},
        "archive": {"tree": tree, "primary": ["structured_input"], "verify": []},
    }
    if not category or category not in rules.CATEGORIES:
        result.update({"status": "need_classify", "cls": cls, "normalized": n,
                       "note": "缺少有效 category，且无文本可供分类推断"})
        return result

    verify_results = verifier.verify(n, all_text, category)
    gaps = gap.detect(n, category)
    evaluation = scorer.evaluate(category, n)
    rep = report_builder.build_report(
        aid, company, category, cls, n, evaluation, gaps,
        {"tree": {}, "primary": ["structured_input"], "verify": []},
        verify_results, [],
        [{"filename": "structured_input", "role": "primary",
          "role_name": "结构化输入", "status": "ok"}])
    rep["llm_mode"] = result["llm_mode"]
    rep["sanity_observations"] = sanity_observations
    rep["sanity_summary"] = result["channel_flags"]["sanity_summary"]

    result.update({
        "status": "done", "category": category,
        "category_name": rules.CATEGORIES[category]["name"],
        "cls": cls, "normalized": n, "evaluation": evaluation, "gaps": gaps,
        "verify_results": verify_results, "conflicts": [], "report": rep,
        "verdict": evaluation.get("verdict_name"),
        "score": evaluation.get("card", {}).get("total"),
        "score_range": evaluation.get("card", {}).get("total_range"),
    })
    return result


def run_pipeline(files: list, company: str = "", aid: str = None) -> dict:
    """
    路径三：给文件路径列表，跑完整 L0-L8。Web 层用。

    files: [(absolute_path, filename), ...]
    """
    aid = aid or uuid.uuid4().hex[:8]
    parsed = []
    for path, fn in files:
        pf = parser.parse_file(path, fn)
        parsed.append({"filename": fn, "parsed": pf})
    return _run_inner(parsed, company, aid)


def meta() -> dict:
    """给 /api/meta 与 MCP 工具描述用。"""
    return {
        "rules_version": rules.RULES_VERSION,
        "released": rules.RELEASED,
        "version_history": rules.VERSION_HISTORY,
        "confidence_threshold": CONFIDENCE_THRESHOLD,
        "case_count": len(db.all_cases()) if db is not None else 0,
        "llm": ("双通道（LLM+正则交叉验证）" if llm_available() else "降级模式（正则单通道）"),
        "categories": [{"id": k, "name": v["name"]} for k, v in rules.CATEGORIES.items()],
        "gates": [{"id": g["id"], "name": g["name"], "metric": g["metric"],
                   "default": g["default"], "op": g["op"], "severity": g["severity"]}
                  for g in rules.GATES],
        "verify_statuses": ["local_hit（本地示例库命中，非官方核验）",
                            "unverified（需人工在官方系统复核）",
                            "not_found（未发现相关资质表述）"],
    }
