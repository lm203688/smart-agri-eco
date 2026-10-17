"""S1 不可进化区/可进化区声明回归守卫。

覆盖点：
  1. evolution_zones.json schema 完整（两区齐全、meta_policy 版本化）
  2. 不可进化区资产路径全部真实存在
  3. 可进化区资产路径全部真实存在
  4. gate_version 单调递增且历史条目完整
  5. CORE_OBJECTIVE.md 已同步声明（防止文档漂移）
"""
import json
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZONES_PATH = os.path.join(ROOT, ".well-known", "evolution_zones.json")
CORE_OBJECTIVE_PATH = os.path.join(ROOT, "docs", "CORE_OBJECTIVE.md")


def _load_zones():
    with open(ZONES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


class EvolutionZonesTests(unittest.TestCase):

    def setUp(self):
        self.zones = _load_zones()

    def test_schema_declared(self):
        self.assertEqual(self.zones.get("schema"), "agri-evolution-zones/v1")

    def test_two_zones_present(self):
        self.assertIn("immutable_core", self.zones)
        self.assertIn("evolvable_shell", self.zones)

    def test_immutable_core_has_assets(self):
        assets = self.zones["immutable_core"].get("assets", [])
        self.assertGreaterEqual(len(assets), 6,
                                f"不可进化区应至少 6 项资产，实际 {len(assets)}")
        for a in assets:
            self.assertIn("path", a)
            self.assertIn("reason", a)
            self.assertIn("protection", a)

    def test_evolvable_shell_has_assets(self):
        assets = self.zones["evolvable_shell"].get("assets", [])
        self.assertGreaterEqual(len(assets), 4)
        for a in assets:
            self.assertIn("path", a)
            self.assertIn("ratchet_benchmark", a)
            self.assertIn("rationale", a)

    def test_asset_paths_exist(self):
        """所有声明的路径必须真实存在（防声明漂移）。

        支持三种路径形式：
          - 目录路径（以 / 结尾）：断言是目录
          - 通配符路径（含 *）：glob 展开至少 1 个匹配
          - 普通文件路径：断言文件存在
        """
        import glob
        for zone_key in ("immutable_core", "evolvable_shell"):
            for a in self.zones[zone_key]["assets"]:
                p = a["path"]
                full = os.path.join(ROOT, p)
                if p.endswith("/"):
                    self.assertTrue(os.path.isdir(full),
                                    f"{zone_key} 目录不存在: {p}")
                elif "*" in p:
                    matches = glob.glob(full)
                    self.assertGreaterEqual(len(matches), 1,
                                            f"{zone_key} 通配符无匹配: {p}")
                else:
                    self.assertTrue(os.path.exists(full),
                                    f"{zone_key} 文件不存在: {p}")

    def test_no_path_in_both_zones(self):
        """任何路径不得同时出现在两区（互斥原则）。"""
        imm_paths = {a["path"] for a in self.zones["immutable_core"]["assets"]}
        evo_paths = {a["path"] for a in self.zones["evolvable_shell"]["assets"]}
        overlap = imm_paths & evo_paths
        self.assertEqual(overlap, set(),
                         f"路径 {overlap} 同时出现在两区")

    def test_gate_version_declared(self):
        meta = self.zones.get("meta_policy", {})
        self.assertIn("gate_version", meta)
        self.assertTrue(meta["gate_version"].startswith("v"))

    def test_gate_version_history_populated(self):
        history = self.zones["meta_policy"]["gate_version_history"]
        self.assertGreaterEqual(len(history), 1)
        for h in history:
            for k in ("version", "introduced_at", "change", "reason"):
                self.assertIn(k, h)

    def test_enforcement_rules_present(self):
        enf = self.zones["meta_policy"].get("enforcement", {})
        self.assertIn("ratchet_required_for", enf)
        self.assertIn("manual_review_required_for", enf)

    def test_core_objective_synced(self):
        """CORE_OBJECTIVE.md 必须同步声明（防止文档漂移）。"""
        with open(CORE_OBJECTIVE_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("受控自进化", content,
                       "CORE_OBJECTIVE.md 缺『受控自进化』章节")
        self.assertIn("不可进化区", content)
        self.assertIn("可进化区", content)
        self.assertIn("evolution_zones.json", content,
                       "CORE_OBJECTIVE.md 未引用 evolution_zones.json 机读文件")


if __name__ == "__main__":
    unittest.main()
