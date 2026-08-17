from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from storm_v2.dashboard import (
    PHASE5_READY_STATUS,
    build_dashboard_package,
    generate_dashboard_bindings,
)


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_INPUTS = (
    ROOT / "reports" / "phase2" / "weekly_sales_review.json",
    ROOT / "reports" / "phase4" / "weekly_business_review.json",
)


@unittest.skipUnless(all(path.exists() for path in DASHBOARD_INPUTS), "requires local production review outputs")
class DashboardBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.phase2 = json.loads(
            (ROOT / "reports" / "phase2" / "weekly_sales_review.json").read_text(
                encoding="utf-8"
            )
        )
        cls.phase4 = json.loads(
            (ROOT / "reports" / "phase4" / "weekly_business_review.json").read_text(
                encoding="utf-8"
            )
        )
        cls.package = build_dashboard_package(cls.phase2, cls.phase4)

    def test_frozen_sources_bind_without_recalculation(self) -> None:
        self.assertEqual(self.package["status"], PHASE5_READY_STATUS)
        self.assertEqual(self.package["snapshot_id"], "2026-08-13_b05ff566b9de")
        self.assertEqual(
            self.package["source"]["source_sha256"],
            "B05FF566B9DECC2852460E8FEC12AF8026B0C8D72148F52F974C32F27F1A8833",
        )
        self.assertEqual(self.package["sections"]["executive"]["actual_sales"], 84090.87)
        self.assertEqual(self.package["source"]["source_mutation"], "NONE")

    def test_exact_period_bp_gap_is_not_manufactured(self) -> None:
        executive = self.package["sections"]["executive"]
        self.assertIsNone(executive["bp_sales"])
        self.assertIsNone(executive["sales_gap"])
        self.assertIsNone(executive["sales_attainment"])
        sku = self.package["sections"]["sku_sales_performance"]
        self.assertEqual(sku["bp_status"], "BP_NOT_AVAILABLE_EXACT_PERIOD")
        self.assertEqual(sku["top_5_detractors"], [])
        self.assertEqual(sku["top_5_overperformers"], [])
        self.assertEqual(sku["applied_default_sort"], "actual_sales_descending_fallback")

    def test_channel_exception_is_data_driven(self) -> None:
        rows = self.package["sections"]["channel_performance"]["rows"]
        worst_cm = min(rows, key=lambda row: row["actual_cm"])
        highest_burden = max(
            rows, key=lambda row: row["known_operating_cost_burden_rate"]
        )
        self.assertEqual((worst_cm["platform"], worst_cm["channel"]), ("Walmart", "MP"))
        self.assertEqual(
            (highest_burden["platform"], highest_burden["channel"]),
            ("Walmart", "MP"),
        )

    def test_sku_has_no_artificial_cm_cost_or_dimensions(self) -> None:
        section = self.package["sections"]["sku_sales_performance"]
        self.assertEqual(section["rows"][0]["sku"], "WBP52TS")
        for row in section["rows"]:
            self.assertIsNone(row["actual_cm"])
            self.assertIsNone(row["tacos"])
            self.assertIsNone(row["platform"])
            self.assertEqual(row["cm_status"], "NOT_AVAILABLE_AT_THIS_LEVEL")
            self.assertEqual(row["operating_status"], "NOT_AVAILABLE_AT_THIS_LEVEL")
        self.assertFalse(section["sku_cm_artificially_allocated"])
        self.assertFalse(section["sku_operating_cost_artificially_allocated"])

    def test_thd_dfc_remains_independent(self) -> None:
        dfc = self.package["sections"]["thd_dfc_sellout"]
        self.assertEqual(dfc["scope"], "THD_DFC_CONSUMER_SELLOUT_INDEPENDENT")
        self.assertAlmostEqual(dfc["mtd_total"]["gmv"], 28504.78, places=6)
        self.assertEqual(dfc["mtd_total"]["units"], 35.0)
        self.assertEqual(dfc["sell_in_comparison_status"], "NOT_RECONCILED_DIFFERENT_SCOPE")
        self.assertEqual(dfc["profitability_status"], "NOT_CREATED")

    def test_acceptance_and_feishu_gates_are_explicit(self) -> None:
        statuses = {item["id"]: item["status"] for item in self.package["acceptance_review"]}
        self.assertEqual(len(statuses), 20)
        self.assertEqual(statuses["2"], "NO")
        self.assertEqual(statuses["17"], "PARTIAL")
        self.assertTrue(self.package["weekly_meeting_simulation"]["ready_achieved"])
        self.assertEqual(
            self.package["weekly_meeting_simulation"]["result"],
            "READY_WITH_SOURCE_LIMITATIONS",
        )
        self.assertEqual(
            self.package["feishu_asset_audit"]["live_audit_status"],
            "NATIVE_DASHBOARD_CREATED_AND_VISUALLY_VERIFIED",
        )
        self.assertFalse(self.package["feishu_asset_audit"]["base_created"])
        self.assertTrue(self.package["feishu_asset_audit"]["data_model_created"])
        self.assertEqual(self.package["feishu_asset_audit"]["live_counts"]["fields"], 78)
        self.assertEqual(self.package["feishu_asset_audit"]["live_counts"]["views"], 15)
        self.assertEqual(self.package["feishu_asset_audit"]["records_created"], 88)
        self.assertEqual(len(self.package["dashboard"]["native_components"]), 10)
        self.assertEqual(len(self.package["dashboard"]["layout"]), 6)
        trend_sections = [
            item["section"]
            for item in self.package["dashboard"]["layout"]
            if "Daily trend" in item["components"]
        ]
        self.assertEqual(trend_sections, ["THD DFC Sell-out"])

    def test_generated_binding_is_stable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            report_dir = Path(temp)
            first = generate_dashboard_bindings(ROOT, report_dir)
            before = (report_dir / "dashboard_binding.json").read_bytes()
            second = generate_dashboard_bindings(ROOT, report_dir)
            self.assertEqual(before, (report_dir / "dashboard_binding.json").read_bytes())
            self.assertEqual(first, second)
            self.assertTrue((report_dir / "dashboard_review.md").exists())
            self.assertTrue((report_dir / "phase5_completion_report.md").exists())
            self.assertTrue((report_dir / "feishu_live_audit.md").exists())


if __name__ == "__main__":
    unittest.main()
