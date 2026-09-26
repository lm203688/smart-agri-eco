#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_engine_v5.py —— bp_screen（农业项目投资初筛引擎）回归测试

覆盖范围：
  A. 零依赖约束        导入不触发第三方 import；pdf/pandas/openpyxl 为函数内 lazy import
  B. 门禁死代码修复    两个 metric 名必须与 normalize 产出键一致
  C. 正则抽取修复      net_margin / rd_pct / pipeline_certs 三处实测错误值回归
  D. eia_passed 修复   养殖类环评字段必须可提取（旧版永远返回 None）
  E. 核验语义         去重；绝不产出 verified；每条带官方复核入口
  F. 合理性校验层      越界值置空 + 记录 observation
  G. 区间化诚实性      区间宽度必须随缺失/可疑字段数增长，禁止「假精确」
  H. 冷启动           空 DB 自动建表 + 灌 15 条种子；synthetic/benchmark 标注
  I. 分类置信度门槛    低置信度不自动评分
  J. MCP 集成         第 10 个工具 agri_bp_screen 注册一致性与两种入参模式

隔离：全部用例走 AGRI_BP_DB 指向的临时库，不触碰 bp_screen/data/cases.db 真实数据。
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import tempfile
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# 隔离数据库：必须在 import bp_screen 之前设好，避免污染真实数据
_TMP_DB = os.path.join(tempfile.gettempdir(), "bp_screen_test_v5.db")
if os.path.exists(_TMP_DB):
    os.remove(_TMP_DB)
os.environ["AGRI_BP_DB"] = _TMP_DB

import bp_screen  # noqa: E402
from bp_screen import (classifier, db, extractor, gap, parser, rules, sanity, scorer,
                       verifier)  # noqa: E402

_BP_FILE = os.path.join(_ROOT, "bp_screen", "_sample", "BP-金玉种业商业计划书.txt")
with open(_BP_FILE, "r", encoding="utf-8") as _f:
    BP_TEXT = _f.read()


def _load_mcp_server():
    """按路径加载 mcp/server.py（其包名 mcp 与标准库冲突，不能直接 import）。"""
    path = os.path.join(_ROOT, "mcp", "server.py")
    spec = importlib.util.spec_from_file_location("mcp_server_v5", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# A. 零依赖约束
# ---------------------------------------------------------------------------
class TestZeroDependency(unittest.TestCase):
    """导入 bp_screen 不得触发任何第三方依赖；pdf/pandas/openpyxl 必须是函数内 lazy import。"""

    def test_no_third_party_imported_on_package_import(self):
        banned = {"fastapi", "uvicorn", "httpx", "pdfplumber", "pandas", "openpyxl"}
        imported = set(sys.modules)
        leaked = banned & imported
        self.assertFalse(leaked, f"导入 bp_screen 泄漏第三方模块：{leaked}")

    def test_pdf_excel_imports_are_lazy(self):
        """pdfplumber / pandas / openpyxl 必须出现在缩进行（函数体内），不能是顶层 import。"""
        p = os.path.join(_ROOT, "bp_screen", "parser.py")
        with open(p, "r", encoding="utf-8") as f:
            lines = f.readlines()
        lazy = {}
        for ln, line in enumerate(lines, 1):
            for mod in ("pdfplumber", "pandas", "openpyxl"):
                if re.match(r"\s*import\s+%s" % mod, line):
                    indent = len(line) - len(line.lstrip())
                    lazy[mod] = (ln, indent)
        self.assertEqual(set(lazy), {"pdfplumber", "pandas", "openpyxl"},
                         "parser.py 应恰好包含这三处第三方 import")
        for mod, (ln, indent) in lazy.items():
            self.assertGreater(indent, 0,
                               f"{mod} 在 parser.py:L{ln} 是顶层 import（缩进 0），违反 lazy 约束")

    def test_core_modules_use_only_stdlib(self):
        """除 web.py 外，所有子模块的顶层 import 必须都在标准库 + 包内相对导入范围。"""
        stdlib = set(sys.stdlib_module_names)
        offenders = []
        pkg_dir = os.path.join(_ROOT, "bp_screen")
        for fn in sorted(os.listdir(pkg_dir)):
            if not fn.endswith(".py") or fn in ("web.py",):
                continue
            with open(os.path.join(pkg_dir, fn), "r", encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    # 缩进行 = 函数体内 lazy import，不在本测试约束范围
                    if line.startswith((" ", "\t")):
                        continue
                    if s.startswith("from __future__"):
                        continue
                    if s.startswith("from ."):
                        continue
                    if s.startswith("from "):
                        body = s[5:].strip().split(" import ")[0].strip()
                        mods = [body] if body else []
                    elif s.startswith("import "):
                        body = s[7:].strip()
                        mods = [p.strip().split(" as ")[0].strip() for p in body.split(",")]
                    else:
                        continue
                    for mod in mods:
                        top = mod.split(".")[0]
                        if top in stdlib or top == "bp_screen":
                            continue
                        offenders.append((fn, s[:70]))
        self.assertFalse(offenders, f"顶层出现非标准库 import：{offenders}")


# ---------------------------------------------------------------------------
# B. 门禁死代码修复
# ---------------------------------------------------------------------------
class TestGateMetricFix(unittest.TestCase):
    """旧版两个门禁的 metric 名与 normalize 产出键不一致，导致永不触发。"""

    def _gate(self, gid):
        for g in rules.GATES:
            if g["id"] == gid:
                return g
        self.fail(f"门禁 {gid} 不存在")

    def test_cash_ratio_gate_metric_matches_normalize_output(self):
        """normalize 产出的是 cash_ratio（server.py 补数路径也写这个键），不是 cash_to_revenue。"""
        g = self._gate("cash_ratio")
        self.assertEqual(g["metric"], "cash_ratio",
                         "cash_ratio 闸的 metric 必须与 normalize 产出键一致，否则该闸永不触发")

    def test_bio_asset_gate_metric_matches_gap_levels(self):
        """GAP_LEVELS 用的是 bio_inventory_pct。"""
        g = self._gate("bio_asset")
        self.assertEqual(g["metric"], "bio_inventory_pct")

    def test_all_gate_metrics_are_producible_or_special(self):
        """每个门禁 metric 要么能被 normalize 产出，要么是评分引擎特判的派生量。

        用真实 BP 文本：cash_ratio 只有在 revenue 与 cash_received 同时存在时才会被派生，
        用占位文本会误判为「产不出」（旧版死代码正是因此一直没被发现）。
        """
        special = {"gross_margin_vs_benchmark"}  # scorer 内部计算：毛利率 vs 分类基准
        pf = parser.ParsedFile(filename="bp.txt", ftype="text",
                               pages=[{"text": BP_TEXT, "source": "inline"}], error="")
        ext, _ = extractor.extract([{"filename": "bp.txt", "parsed": pf}])
        n = extractor.normalize(ext)
        producible = set(n.keys())
        for g in rules.GATES:
            m = g["metric"]
            self.assertTrue(m in producible or m in special or g.get("severity") == "verify",
                            f"门禁 {g['id']} 的 metric={m} 既不在 normalize 产出中，也不是特判派生量；"
                            f"该闸会成为静默死代码")

    def test_cash_ratio_only_derived_when_inputs_present(self):
        """记录真实行为：cash_ratio 是条件派生字段，输入缺失时该键不存在而非为 0。"""
        pf = parser.ParsedFile(filename="t.txt", ftype="text",
                               pages=[{"text": "这是一段没有财务数据的文本", "source": "inline"}], error="")
        ext, _ = extractor.extract([{"filename": "t.txt", "parsed": pf}])
        n = extractor.normalize(ext)
        self.assertNotIn("cash_ratio", n)

    def test_cash_ratio_gate_actually_fires_when_breached(self):
        """回归锁：现金收入比低于红线时必须真的爆雷（旧版恒不触发）。"""
        n = {"cash_ratio": 50.0, "category": "seeds"}
        fired = scorer.run_gates(n, "seeds")
        ids = [g["id"] for g in fired]
        self.assertIn("cash_ratio", ids,
                      f"现金收入比 50% 低于红线 70% 却未触发门禁，实际 fired={ids}")


# ---------------------------------------------------------------------------
# C. 正则抽取修复
# ---------------------------------------------------------------------------
class TestRegexExtractionFix(unittest.TestCase):
    """三处实测抽取错误：1800.0 / 600.0 / 188.0。"""

    @classmethod
    def setUpClass(cls):
        pf = parser.ParsedFile(filename="bp.txt", ftype="text",
                               pages=[{"text": BP_TEXT, "source": "inline"}], error="")
        ext, _ = extractor.extract([{"filename": "bp.txt", "parsed": pf}])
        cls.norm = extractor.normalize(ext)

    def test_net_margin_not_treated_as_amount(self):
        """旧版把「净利润1800万」当净利率提出 1800.0。真值应由 净利润/营业收入 派生 = 10.0。"""
        v = self.norm.get("net_margin")
        self.assertIsNotNone(v, "样例 BP 有净利润与营收，净利率应能被派生")
        self.assertLessEqual(v, 100, f"net_margin={v} 超过 100，仍是把金额当比率")
        self.assertAlmostEqual(v, 10.0, delta=0.5,
                               msg=f"net_margin 应为 1800万/18000万=10%，实测 {v}")

    def test_net_margin_derivation_flagged(self):
        self.assertIn("net_margin_derived", self.norm, "派生值必须标注来源，不可伪装为原文提取")

    def test_rd_pct_not_matched_from_expense_line(self):
        """旧版命中「月均运营支出（工资+研发+管理）600万」提出 rd_pct=600.0。真值 12.0。"""
        v = self.norm.get("rd_pct")
        self.assertIsNotNone(v, "BP 明确写了「研发费用占收入比12%」，应能提取")
        self.assertLessEqual(v, 100, f"rd_pct={v} 超过 100，仍是被误匹配")
        self.assertAlmostEqual(v, 12.0, delta=0.5, msg=f"rd_pct 应为 12，实测 {v}")

    def test_pipeline_certs_not_matched_from_variety_name(self):
        """旧版跨段落匹配把品种名「金玉188」当在审登记数，提出 188.0。"""
        v = self.norm.get("pipeline_certs")
        if v is not None:
            self.assertLess(v, 100,
                            f"pipeline_certs={v} 明显是把名称/编号数字当计数（旧版为 188）")

    def test_cert_counts_require_quantifier(self):
        """审定/安全/登记数正则必须强制量词，否则「品种审定：金玉188」会被误匹配。"""
        for field in ("approved_varieties", "safety_certs", "reg_certs", "pipeline_certs"):
            pats = extractor.FIELD_PATTERNS[field]
            for p in pats:
                self.assertRegex(p, r"\(\?:[张个项]",
                                 f"{field} 的正则 {p[:40]} 未强制量词（张/个/项）")

    def test_approved_varieties_value(self):
        self.assertEqual(self.norm.get("approved_varieties"), 6.0)

    def test_safety_certs_value(self):
        self.assertEqual(self.norm.get("safety_certs"), 2.0)


# ---------------------------------------------------------------------------
# D. eia_passed 修复
# ---------------------------------------------------------------------------
class TestEiaPassedFix(unittest.TestCase):
    """旧版正则无捕获组 → groups[0] 抛 IndexError 被 except 吞掉 → 字段永远提取不到。"""

    def test_regex_has_capture_group(self):
        for p in extractor.FIELD_PATTERNS["eia_passed"]:
            self.assertGreaterEqual(len(re.findall(r"\(", p)), 1,
                                    "eia_passed 正则必须至少一个捕获组")
        self.assertIn("eia_passed", extractor.BOOL_FIELDS,
                      "eia_passed 必须声明为布尔存在型字段，否则数值转换失败会被静默跳过")

    def test_extracted_as_true_when_text_declares_pass(self):
        pf = parser.ParsedFile(filename="bp.txt", ftype="text", pages=[{
            "text": "本项目已取得环评批复，环评已通过生态环境部门验收。", "source": "inline"}], error="")
        ext, _ = extractor.extract([{"filename": "bp.txt", "parsed": pf}])
        self.assertIn("eia_passed", ext, "声明环评通过时 eia_passed 必须被提取（旧版永远缺失）")
        self.assertIs(ext["eia_passed"]["value"], True)

    def test_false_when_no_eia_mention(self):
        pf = parser.ParsedFile(filename="bp.txt", ftype="text", pages=[{
            "text": "公司主营玉米种业授权。", "source": "inline"}], error="")
        ext, _ = extractor.extract([{"filename": "bp.txt", "parsed": pf}])
        self.assertNotIn("eia_passed", ext)

    def test_non_bool_field_still_skipped_on_conversion_failure(self):
        """安全约束：只有显式声明的布尔字段才能用 True 兜底，不能把任意正则失败都变成 True。"""
        for f in extractor.BOOL_FIELDS:
            self.assertIn(f, extractor.FIELD_PATTERNS)
        self.assertEqual(len(extractor.BOOL_FIELDS), 1, "当前只应声明 eia_passed 一个布尔字段")


# ---------------------------------------------------------------------------
# E. 核验语义
# ---------------------------------------------------------------------------
class TestVerifierSemantics(unittest.TestCase):
    def test_no_verified_status_emitted(self):
        """LOCAL_REGISTRY 是演示数据，模块绝不产出 verified。"""
        results = verifier.verify({"reg_certs": 3}, BP_TEXT, "seeds")
        for r in results:
            self.assertNotEqual(r["status"], "verified",
                                f"{r} 产出 verified，会冒充官方核验")
            self.assertIn(r["status"], ("local_hit", "unverified", "not_found"))

    def test_no_duplicate_type_value_pairs(self):
        """旧版对 ['审定','品种审定'] 两条 kw 各扫一遍，同一证照重复出现。"""
        results = verifier.verify({}, BP_TEXT, "seeds")
        seen = [(r["type"], r["value"]) for r in results]
        self.assertEqual(len(seen), len(set(seen)),
                         f"核验结果存在重复条目：{seen}")

    def test_every_result_carries_official_source(self):
        """每条核验结果必须告诉调用方真正该查哪个官方系统。"""
        for cat in ("seeds", "bioinputs", "livestock"):
            for r in verifier.verify({}, BP_TEXT, cat):
                self.assertIn("official_source", r, f"{cat} 的核验结果缺 official_source")
                self.assertNotIn(r["official_source"], ("", None),
                                 f"{cat} 的 {r['type']} 缺官方复核入口")

    def test_local_hit_note_disclaims_official_status(self):
        hits = [r for r in verifier.verify({}, BP_TEXT, "seeds") if r["status"] == "local_hit"]
        self.assertTrue(hits, "样例 BP 含本地示例库中的品种名，应有 local_hit")
        for r in hits:
            self.assertIn("非官方", r["note"], f"local_hit 必须声明不是官方核验：{r['note'][:60]}")

    def test_demo_registry_flag(self):
        self.assertTrue(verifier.DEMO_REGISTRY)

    def test_livestock_eia_verifies_from_field(self):
        """养殖类环评判断应采信 eia_passed 字段（旧版因字段永不提取而失效）。"""
        r = verifier.verify({"eia_passed": True}, "", "livestock")
        eia = [x for x in r if x["type"] == "环评批复"]
        self.assertEqual(len(eia), 1)
        self.assertEqual(eia[0]["status"], "unverified")
        self.assertIn("已通过", eia[0]["value"])

    def test_eppo_not_claimed_as_cert_source(self):
        """EPPO 是有害生物数据库，不是品种审定/农药登记数据源。"""
        blob = json.dumps(verifier.OFFICIAL_SOURCES, ensure_ascii=False).lower()
        self.assertNotIn("eppo", blob)


# ---------------------------------------------------------------------------
# F. 合理性校验层
# ---------------------------------------------------------------------------
class TestSanityGate(unittest.TestCase):
    def test_old_buggy_values_all_caught(self):
        """把旧版的三个实测错误值直接喂进来，必须全部拦下。"""
        cleaned, obs = sanity.check({
            "net_margin": 1800.0,   # 旧版错误值
            "rd_pct": 600.0,        # 旧版错误值
            "pipeline_certs": 188,  # 旧版错误值
            "revenue": 1.8e8,       # 合法，应保留
        })
        self.assertIsNone(cleaned["net_margin"])
        self.assertIsNone(cleaned["rd_pct"])
        self.assertIsNone(cleaned["pipeline_certs"])
        self.assertEqual(cleaned["revenue"], 1.8e8)
        self.assertEqual(len(obs), 3)

    def test_observations_recorded_with_reason_and_action(self):
        _, obs = sanity.check({"net_margin": 1800.0})
        self.assertEqual(len(obs), 1)
        o = obs[0]
        for k in ("field", "label", "observed", "reason", "action"):
            self.assertIn(k, o)
        self.assertEqual(o["observed"], 1800.0)

    def test_legit_extreme_values_not_killed(self):
        """误杀比漏放更糟：真实业务形态不能被当提取错误。"""
        cleaned, obs = sanity.check({
            "top5_client_pct": 72.0,   # SaaS 大客户集中，真实
            "subsidy_pct": 55.0,       # 农机补贴依赖，真实
            "ue_margin": -12.0,        # 亏损是真信号，不是提取错误
            "revenue_growth": -20.0,   # 收入下滑也是真信号
            "gross_margin": 98.0,      # 高端软件，真实
            "approved_varieties": 40,  # 隆平高科锚点
            "units_sold": 80000,       # 极飞科技锚点
        })
        self.assertEqual(obs, [], f"合法业务形态被误杀：{obs}")
        self.assertEqual(cleaned["ue_margin"], -12.0)
        self.assertEqual(cleaned["units_sold"], 80000)

    def test_boundary_values_accepted(self):
        _, obs = sanity.check({"gross_margin": 0.0, "revenue_growth": 0.0})
        self.assertEqual(obs, [])

    def test_non_numeric_ignored(self):
        _, obs = sanity.check({"_unit_note": "文本", "category": "seeds", "eia_passed": True})
        self.assertEqual(obs, [])

    def test_summary_shape(self):
        s = sanity.summarize([])
        self.assertEqual(s["suspect_fields"], 0)
        s2 = sanity.summarize(sanity.check({"net_margin": 1800.0})[1])
        self.assertEqual(s2["suspect_fields"], 1)
        self.assertEqual(s2["fields"], ["net_margin"])


# ---------------------------------------------------------------------------
# G. 区间化诚实性
# ---------------------------------------------------------------------------
class TestIntervalHonesty(unittest.TestCase):
    """核心回归：区间宽度必须随缺失/可疑字段数增长，禁止输出假精确结论。"""

    def _card(self, n):
        return scorer.evaluate("seeds", n)["card"]

    def _baseline_fields(self):
        return {"revenue": 1.8e8, "gross_profit": 7.38e7, "gross_margin": 41.0,
                "net_profit": 1.8e7, "net_margin": 10.0,
                "cash_balance": 2.2e8, "cash_received": 1.58e8, "cash_ratio": 87.78,
                "monthly_burn": 6e6, "runway_months": 36.7,
                "top5_client_pct": 38.0, "subsidy_pct": 8.0, "ue_margin": 32.0,
                "revenue_growth": 28.0, "approved_varieties": 6.0, "safety_certs": 2.0}

    def test_full_data_yields_tight_interval(self):
        c = self._card(self._baseline_fields())
        lo, hi = c["total_range"]
        self.assertIsNotNone(c["total"])
        self.assertLessEqual(hi - lo, 0.01, f"字段齐全时区间应极窄，实测 [{lo}, {hi}]")

    def test_missing_fields_widen_interval(self):
        full = self._card(self._baseline_fields())
        n = self._baseline_fields()
        del n["revenue_growth"]
        del n["cash_balance"]
        del n["monthly_burn"]
        sparse = self._card(n)
        self.assertGreater(sparse["card_total_range_width"] if False else
                           sparse["total_range"][1] - sparse["total_range"][0],
                           full["total_range"][1] - full["total_range"][0],
                           "缺失字段必须拉宽区间")

    def test_suspect_values_flow_into_interval_as_missing(self):
        """关键：抽错值经 sanity 置空后，必须真的让区间变宽（堵住假精确漏洞）。

        用评分卡真实维度字段（gross_margin / revenue_growth）来验证——只有参与
        评分的字段置空才会改变区间宽度，这是 scorer 的真实行为。
        """
        buggy = {"gross_margin": 150.0, "revenue_growth": 500.0}
        clean, obs = sanity.check(buggy)
        self.assertEqual(sorted(o["field"] for o in obs),
                         ["gross_margin", "revenue_growth"])
        for f in buggy:
            self.assertIsNone(clean.get(f))

        n_full = self._baseline_fields()
        n_buggy = dict(n_full, **clean)
        c_full = self._card(n_full)
        c_buggy = self._card(n_buggy)
        w_full = c_full["total_range"][1] - c_full["total_range"][0]
        w_buggy = c_buggy["total_range"][1] - c_buggy["total_range"][0]
        self.assertGreater(w_buggy, w_full,
                           f"可疑字段置空后区间宽度 {w_buggy} 未大于全数据 {w_full}")

    def test_non_scoring_field_errors_do_not_widen_interval(self):
        """诚实标注边界：不参与评分的字段抽错，sanity 会记录但不改变区间宽度。

        net_margin / rd_pct / pipeline_certs 不在 seeds 评分卡的维度字段里
        （dims = approved_varieties / gross_margin / revenue_growth / ue_margin
        / runway_months / subsidy_pct）。旧版这三值造成假精确，是因为 sanity 层
        不存在且评分卡也不引用它们——两头都不管。现在 sanity 会把它们记录进
        observations 让调用方看见，但区间确实不变。
        """
        buggy = {"net_margin": 1800.0, "rd_pct": 600.0, "pipeline_certs": 188}
        clean, obs = sanity.check(buggy)
        self.assertEqual(len(obs), 3, "三个可疑值都应被记录")
        for f in buggy:
            self.assertIsNone(clean.get(f))

        n_full = self._baseline_fields()
        n_buggy = dict(n_full, **clean)
        w_full = self._card(n_full)["total_range"][1] - self._card(n_full)["total_range"][0]
        w_buggy = self._card(n_buggy)["total_range"][1] - self._card(n_buggy)["total_range"][0]
        self.assertEqual(w_buggy, w_full,
                         "非评分字段置空不应改变区间宽度（诚实边界）")

    def test_band_capped_at_12(self):
        """区间半宽上限 12（4 分/个缺失维度，最多 3 个计入）。"""
        n = {"revenue": 1.0}  # 几乎全缺
        c = self._card(n)
        if c["total"] is not None:
            self.assertLessEqual(c["total_range"][1] - c["total_range"][0], 24)

    def test_all_dims_missing_yields_no_total(self):
        """全部维度缺失 → 不给总分（而不是给一个假的分数）。"""
        c = scorer.score_card("seeds", {}, [])
        self.assertIsNone(c["total"])
        self.assertIsNone(c["total_range"])
        self.assertEqual(len(c["missing_dimensions"]), 6,
                         "seeds 评分卡应有 6 个维度全缺失")

    def test_empty_input_vetoed_not_faked(self):
        """空输入触发一票否决 → verdict 是 FAIL，而不是编造一个通过结论。"""
        r = scorer.evaluate("seeds", {})
        self.assertTrue(r["vetoes_fired"], "空输入应触发一票否决")
        self.assertEqual(r["verdict"], "FAIL")
        self.assertIn("一票否决", r["verdict_reason"])
        self.assertIsNone(r["card"]["total"])


# ---------------------------------------------------------------------------
# H. 冷启动与种子数据
# ---------------------------------------------------------------------------
class TestColdStart(unittest.TestCase):
    def test_fresh_db_auto_initializes(self):
        self.assertEqual(len(db.all_cases()), 15, "冷启动应自动灌 15 条种子案例")

    def test_seed_source_labels_split_benchmark_vs_synthetic(self):
        """8 条公开公司锚点标 benchmark，7 条合成案例标 synthetic。"""
        cases = db.all_cases()
        bench = [c for c in cases if c["is_benchmark"]]
        synth = [c for c in cases if not c["is_benchmark"]]
        self.assertEqual(len(bench), 8)
        self.assertEqual(len(synth), 7)
        for c in bench:
            self.assertEqual(c["source"], "benchmark", f"{c['name']} 来源标注错误：{c['source']}")
        for c in synth:
            self.assertEqual(c["source"], "synthetic", f"{c['name']} 来源标注错误：{c['source']}")

    def test_synthetic_cases_do_not_claim_real_outcome(self):
        """文案诚实性：合成案例不得写「真实结局」（虚构公司不可能有真实尽调结局）。"""
        for c in db.all_cases():
            self.assertNotIn("真实结局", c["outcome"], f"{c['name']} 声称真实结局：{c['outcome'][:50]}")

    def test_rule_version_registered(self):
        db.ensure_ready()
        c = db._conn()
        row = c.execute("SELECT version, active FROM rule_versions WHERE active=1").fetchone()
        c.close()
        self.assertIsNotNone(row)
        self.assertEqual(row["version"], rules.RULES_VERSION)

    def test_rules_version_bumped_with_history(self):
        self.assertEqual(rules.RULES_VERSION, "v2.0.0")
        self.assertGreaterEqual(len(rules.VERSION_HISTORY), 2)
        self.assertIn("cash_to_revenue", rules.VERSION_HISTORY[-1],
                      "版本历史必须记录死门禁修复，否则下次改规则的人不知道坑在哪")


# ---------------------------------------------------------------------------
# I. 分类置信度门槛
# ---------------------------------------------------------------------------
class TestConfidenceGate(unittest.TestCase):
    def test_low_confidence_does_not_auto_score(self):
        r = bp_screen.screen_text("这是一段与农业投资完全无关的文本，讲的是量子纠缠与咖啡烘焙。",
                                  company="测试")
        self.assertEqual(r["status"], "need_classify",
                         f"无关文本不应自动评分，status={r['status']}")
        self.assertNotIn("score", r) or self.assertIsNone(r.get("score"))

    def test_valid_bp_reaches_done(self):
        r = bp_screen.screen_text(BP_TEXT, company="金玉种业")
        self.assertEqual(r["status"], "done")
        self.assertEqual(r["category"], "seeds")
        self.assertGreaterEqual(r["cls"]["confidence"], rules.CONFIDENCE_THRESHOLD
                                if hasattr(rules, "CONFIDENCE_THRESHOLD") else 70)

    def test_screen_fields_invalid_category(self):
        r = bp_screen.screen_fields({"revenue": 1.0}, category="quantum")
        self.assertEqual(r["status"], "need_classify")

    def test_screen_fields_missing_category_and_text(self):
        r = bp_screen.screen_fields({"revenue": 1.0})
        self.assertEqual(r["status"], "need_classify")

    def test_screen_fields_forces_category(self):
        r = bp_screen.screen_fields({"revenue": 1.8e8, "gross_margin": 41.0,
                                     "ue_margin": 32.0, "runway_months": 36.7,
                                     "approved_varieties": 6.0}, category="seeds")
        self.assertEqual(r["status"], "done")
        self.assertEqual(r["category"], "seeds")
        self.assertEqual(r["cls"]["confidence"], 100.0)

    def test_text_mode_accepts_category_override(self):
        """text 模式必须接受 category 覆盖，解开 need_classify 死路。

        旧版 screen_text 不接受 category 参数，而 need_classify 的 note 却提示
        「去 screen_fields 传 category 强制指定」——MCP tool 的 text 模式又静默
        丢弃 category 参数，用户被指向一条走不通的路。
        """
        thin = "主营杂交水稻种子。已审定品种4个。2023年营收8000万元，毛利3200万元。"
        blocked = bp_screen.screen_text(thin, company="测试")
        self.assertEqual(blocked["status"], "need_classify",
                         "先确认这段文本确实卡在 need_classify")

        r = bp_screen.screen_text(thin, company="测试", category="seeds")
        self.assertEqual(r["status"], "done", f"人工确认分类后应完成评分，status={r['status']}")
        self.assertEqual(r["category"], "seeds")
        self.assertEqual(r["cls"].get("source"), "human_confirmed")
        self.assertFalse(r["cls"].get("need_confirm"))

    def test_text_mode_invalid_category_rejected(self):
        r = bp_screen.screen_text("营收8000万元。", category="quantum")
        self.assertEqual(r["status"], "invalid_category",
                         f"非法分类必须显式报错，不能静默忽略，status={r['status']}")
        self.assertIn("六分类", r["note"])

    def test_text_mode_confirmed_category_noted_as_human(self):
        r = bp_screen.screen_text(BP_TEXT, company="金玉种业", category="seeds")
        self.assertEqual(r["status"], "done")
        self.assertEqual(r["cls"].get("source"), "human_confirmed")

    def test_sanity_applied_to_structured_input_too(self):
        """外部传入的结构化字段同样要过合理性校验。"""
        r = bp_screen.screen_fields({"net_margin": 1800.0, "revenue": 1.8e8,
                                     "gross_margin": 41.0, "ue_margin": 32.0,
                                     "runway_months": 36.7, "approved_varieties": 6.0},
                                    category="seeds")
        obs = r["channel_flags"]["sanity_observations"]
        self.assertEqual(len(obs), 1)
        self.assertIsNone(r["normalized"]["net_margin"])


# ---------------------------------------------------------------------------
# J. 端到端 + MCP 集成
# ---------------------------------------------------------------------------
class TestEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = bp_screen.screen_text(BP_TEXT, company="金玉种业")

    def test_pipeline_produces_all_layers(self):
        for k in ("status", "category", "cls", "normalized", "evaluation", "gaps",
                  "verify_results", "report", "verdict", "score", "score_range",
                  "rules_version", "llm_mode", "channel_flags", "archive"):
            self.assertIn(k, self.r, f"管线结果缺 {k}")

    def test_report_has_eleven_blocks(self):
        blocks = [k for k in self.r["report"] if k.startswith("block_")]
        self.assertEqual(len(blocks), 11, f"报告应为 11 区块，实测 {len(blocks)}：{blocks}")

    def test_verdict_is_one_of_three(self):
        self.assertIn(self.r["verdict"], ("通过", "需深挖", "淘汰"))

    def test_score_in_range(self):
        lo, hi = self.r["score_range"]
        self.assertLessEqual(lo, self.r["score"])
        self.assertGreaterEqual(hi, self.r["score"])

    def test_decision_path_not_empty(self):
        path = self.r["evaluation"]["decision_path"]
        self.assertGreater(len(path), 0, "决策路径为空，归因能力失效")
        self.assertTrue(all("trace" in p or "type" in p for p in path))

    def test_counterfactual_present(self):
        self.assertIn("counterfactual", self.r["evaluation"])

    def test_gaps_three_levels(self):
        for lvl in ("fatal", "critical", "normal"):
            self.assertIn(lvl, self.r["gaps"])

    def test_llm_mode_reports_degraded_state(self):
        self.assertIn("regex 单通道", self.r["llm_mode"],
                      "未配置 LLM key 时必须明确报告降级模式，不能让调用方误以为走了双通道")

    def test_archive_tree_records_file_role(self):
        self.assertIn("tree", self.r["archive"])


class TestMCPIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = _load_mcp_server()

    def test_tool_registered(self):
        names = [t["name"] for t in self.m.TOOLS]
        self.assertIn("agri_bp_screen", names)
        for new_tool in ("agri_reconcile_climate", "agri_resolve_recipe", "agri_query_lineage"):
            self.assertIn(new_tool, names, f"新增工具未注册：{new_tool}")
        self.assertEqual(len(names), 13, f"应为 13 个工具，实测 {len(names)}")

    def test_tools_and_dispatch_consistent(self):
        self.assertEqual(set(t["name"] for t in self.m.TOOLS), set(self.m._DISPATCH),
                         "TOOLS 与 _DISPATCH 必须一一对应，否则调用会 404 或 schema 缺失")

    def test_dispatch_points_to_correct_function(self):
        self.assertIs(self.m._DISPATCH["agri_bp_screen"], self.m._tool_bp_screen)

    def test_new_tools_dispatched(self):
        self.assertIs(self.m._DISPATCH["agri_reconcile_climate"], self.m._tool_reconcile_climate)
        self.assertIs(self.m._DISPATCH["agri_resolve_recipe"], self.m._tool_resolve_recipe)
        self.assertIs(self.m._DISPATCH["agri_query_lineage"], self.m._tool_query_lineage)

    def test_schema_requires_neither_but_documents_both(self):
        t = next(x for x in self.m.TOOLS if x["name"] == "agri_bp_screen")
        props = t["inputSchema"]["properties"]
        for p in ("text", "fields", "category", "company"):
            self.assertIn(p, props, f"schema 缺 {p}")
        self.assertNotIn("required", t["inputSchema"],
                         "text 与 fields 是二选一，不能把任一列为 required")

    def test_missing_args_returns_error_not_exception(self):
        r = self.m._tool_bp_screen({})
        self.assertIn("error", r)

    def test_fields_mode_returns_verdict(self):
        r = self.m._tool_bp_screen({
            "fields": {"revenue": 1.8e8, "gross_margin": 41.0, "net_profit": 1.8e7,
                       "cash_received": 1.58e8, "cash_balance": 2.2e8, "monthly_burn": 6e6,
                       "top5_client_pct": 38.0, "subsidy_pct": 8.0, "ue_margin": 32.0,
                       "approved_varieties": 6, "safety_certs": 2},
            "category": "seeds", "company": "金玉种业"})
        self.assertNotIn("error", r)
        self.assertIn(r["verdict"], ("通过", "需深挖", "淘汰"))
        self.assertIsInstance(r["score"], (int, float))
        self.assertEqual(r["rules_version"], rules.RULES_VERSION)

    def test_text_mode_end_to_end(self):
        r = self.m._tool_bp_screen({"text": BP_TEXT, "company": "金玉种业"})
        self.assertNotIn("error", r)
        self.assertEqual(r["category"], "seeds")
        self.assertEqual(r["status"], "done")

    def test_boundary_disclaimer_always_present(self):
        r = self.m._tool_bp_screen({"text": BP_TEXT})
        self.assertIn("boundary", r)
        self.assertGreaterEqual(len(r["boundary"]), 4)
        self.assertTrue(any("不构成投资决策建议" in b for b in r["boundary"]))
        self.assertTrue(any("不是官方核验" in b for b in r["boundary"]))

    def test_verify_results_pass_through(self):
        r = self.m._tool_bp_screen({"text": BP_TEXT})
        self.assertTrue(r["verify_results"])
        for v in r["verify_results"]:
            self.assertNotEqual(v["status"], "verified")

    def test_jsonrpc_dispatch_resolves_new_tool(self):
        """JSON-RPC 层必须能路由到新工具（不是只加了字典）。"""
        resp = self.m._handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        tools = resp["result"]["tools"]
        self.assertIn("agri_bp_screen", [t["name"] for t in tools])


# ---------------------------------------------------------------------------
# K. LLM 网关配置行为
# ---------------------------------------------------------------------------
class TestLLMGateway(unittest.TestCase):
    def test_env_read_at_call_time_not_import_time(self):
        """import 后再设环境变量必须生效（旧版在 import 时读取，配置变更无效）。"""
        old_url, old_key = os.environ.pop("AGRI_VISION_URL", None), os.environ.pop(
            "AGRI_VISION_KEY", None)
        try:
            self.assertFalse(bp_screen.llm.llm_available())
            os.environ["AGRI_VISION_URL"] = "http://127.0.0.1:9"
            os.environ["AGRI_VISION_KEY"] = "dummy"
            self.assertTrue(bp_screen.llm.llm_available(),
                            "import 后设置环境变量必须被感知（旧版读不进去）")
            os.environ.pop("AGRI_VISION_URL"); os.environ.pop("AGRI_VISION_KEY")
        finally:
            for k, v in (("AGRI_VISION_URL", old_url), ("AGRI_VISION_KEY", old_key)):
                if v is not None:
                    os.environ[k] = v
                else:
                    os.environ.pop(k, None)

    def test_bp_specific_vars_override_vision_vars(self):
        old = {k: os.environ.get(k) for k in ("AGRI_BP_LLM_URL", "AGRI_BP_LLM_KEY",
                                               "AGRI_BP_LLM_MODEL", "AGRI_VISION_MODEL")}
        try:
            os.environ["AGRI_BP_LLM_URL"] = "http://a"
            os.environ["AGRI_BP_LLM_KEY"] = "k"
            os.environ["AGRI_BP_LLM_MODEL"] = "m-a"
            os.environ["AGRI_VISION_MODEL"] = "m-b"
            url, key, model = bp_screen.llm._config()
            self.assertEqual(url, "http://a")
            self.assertEqual(model, "m-a")
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_no_third_party_http_client(self):
        """必须用标准库 urllib，不能有真正的 httpx 依赖（旧版 import httpx）。

        注意：只查 import 语句，不查裸字符串 —— llm.py 的 docstring 里会提到
        「不依赖 httpx」来说明设计取舍，那是合法文档而非依赖。
        """
        src = open(os.path.join(_ROOT, "bp_screen", "llm.py"), encoding="utf-8").read()
        for line in src.splitlines():
            stripped = line.split("#")[0].strip()
            self.assertFalse(
                stripped.startswith(("import httpx", "from httpx")),
                f"发现了真正的 httpx 导入：{stripped}")
        self.assertIn("urllib.request", src)

    def test_llm_failure_returns_empty_dict_not_raise(self):
        """LLM 网关不可达时静默降级为 {}，由正则通道兜底。"""
        old = (os.environ.get("AGRI_BP_LLM_URL"), os.environ.get("AGRI_BP_LLM_KEY"))
        try:
            os.environ["AGRI_BP_LLM_URL"] = "http://127.0.0.1:1"   # 不可达端口
            os.environ["AGRI_BP_LLM_KEY"] = "dummy"
            out = bp_screen.llm.llm_extract_fields([{"filename": "a", "text": "营收1亿元"}])
            self.assertEqual(out, {})
        finally:
            for k, v in (("AGRI_BP_LLM_URL", old[0]), ("AGRI_BP_LLM_KEY", old[1])):
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


if __name__ == "__main__":
    unittest.main(verbosity=2)
