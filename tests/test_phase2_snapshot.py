from __future__ import annotations

import copy
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from storm_v2.sales_engine import aggregate_sales, attach_baseline, reconcile_common_sales, reconcile_hierarchy
from storm_v2.sales_review import build_review
from storm_v2.snapshot import build_phase2_data, write_snapshot
from storm_v2.thd_dfc_engine import reconcile_dfc


ROOT = Path(__file__).resolve().parents[1]
WORKBOOK = ROOT / "STORM V2 RAW DATA.xlsx"
@unittest.skipUnless(WORKBOOK.exists(), "requires approved local production workbook")
class Phase2SnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = build_phase2_data(WORKBOOK, ROOT, date(2026, 8, 13))
        cls.review = build_review(cls.data)

    def test_source_hash_roles_and_fact_counts(self) -> None:
        self.assertRegex(self.data.source["sha256"], r"^[0-9A-F]{64}$")
        self.assertEqual(len(self.data.sales_facts), 972)
        self.assertEqual(len(self.data.dfc_facts), 4536)
        self.assertEqual(len(self.data.reference_baseline), 540)
        roles = {(item["sheet"], item["section"]): item["role"] for item in self.data.source_roles}
        self.assertEqual(roles[("actual order", "weekly order rows")], "FACT")
        self.assertEqual(roles[("over view", "management summary")], "RECONCILIATION_ONLY")
        self.assertEqual(roles[("2026 acutal cost", "cost and CM")], "EXCLUDED")
        self.assertTrue(all(row["record_role"] == "FACT" for row in self.data.sales_facts))
        self.assertTrue(all(row["metric_domain"] == "THD_DFC_SELLOUT" for row in self.data.dfc_facts))

    def test_real_sales_math_unknown_and_bp_period_gate(self) -> None:
        total = aggregate_sales(self.data.sales_facts)[0]
        self.assertAlmostEqual(total["actual_sales"], 84090.87, places=6)
        self.assertEqual(total["units"], 593.0)
        self.assertEqual(total["orders"], 440)
        self.assertTrue(any(row["sku"] == "KB2618STR" and row["brand"] == "UNKNOWN" for row in self.data.sales_facts))
        skus = aggregate_sales(self.data.sales_facts, ("sku",))
        for row in skus:
            row["period_start"] = "2026-08-01"
            row["period_end"] = "2026-08-10"
        compared, coverage = attach_baseline(skus, self.data.reference_baseline, ("sku",))
        self.assertEqual(coverage["matched_group_count"], 0)
        self.assertTrue(all(row["bp_status"] == "BP_NOT_AVAILABLE" for row in compared))

    def test_raw_normalized_and_hierarchy_reconcile(self) -> None:
        self.assertEqual(reconcile_common_sales(self.data.sales_facts)["status"], "PASS")
        self.assertEqual(reconcile_hierarchy(self.data.sales_facts)["status"], "PASS")
        dfc = reconcile_dfc(self.data.dfc_facts)
        self.assertEqual(dfc["status"], "PASS")
        self.assertEqual(dfc["record_count"], 1134)
        self.assertEqual(dfc["positive_units_zero_gmv_count"], 6)

    def test_review_metrics_trace_to_canonical_facts(self) -> None:
        ids = {row["record_id"] for row in self.data.canonical_records}
        traced_rows = (
            [self.review["executive_sales_snapshot"]]
            + self.review["platform_channel_metrics"]
            + self.review["brand_metrics"]
            + self.review["power_source_metrics"]
            + self.review["sku_metrics"]
            + [self.review["thd_dfc_sellout"]["mtd_total"]]
            + self.review["thd_dfc_sellout"]["mtd_by_sku"]
        )
        for row in traced_rows:
            self.assertTrue(row["trace_record_ids"])
            self.assertTrue(set(row["trace_record_ids"]).issubset(ids))

    def test_snapshot_is_append_only_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = write_snapshot(self.data, root)
            manifest_path = root / self.data.snapshot_id / "manifest.json"
            before = manifest_path.read_bytes()
            second = write_snapshot(self.data, root)
            self.assertFalse(first["reused"])
            self.assertTrue(second["reused"])
            self.assertEqual(before, manifest_path.read_bytes())
            changed = copy.deepcopy(self.data)
            changed.sales_facts[0]["metric_value"] += 1
            with self.assertRaises(FileExistsError):
                write_snapshot(changed, root)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["source_sha256"], self.data.source["sha256"])


if __name__ == "__main__":
    unittest.main()
