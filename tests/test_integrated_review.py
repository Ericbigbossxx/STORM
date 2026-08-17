from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from storm_v2.business_performance import read_business_performance
from storm_v2.integrated_review import build_integrated_review, generate_phase3
from storm_v2.snapshot import build_phase2_data


ROOT = Path(__file__).resolve().parents[1]
WORKBOOK = ROOT / "STORM V2 RAW DATA.xlsx"


@unittest.skipUnless(WORKBOOK.exists(), "requires approved local production workbook")
class IntegratedReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.phase2 = build_phase2_data(WORKBOOK, ROOT, date(2026, 8, 13))
        cls.business = read_business_performance(WORKBOOK, ROOT, date(2026, 8, 13))
        cls.review = build_integrated_review(cls.phase2, cls.business)

    def test_sales_and_cm_are_parallel_without_overwrite(self) -> None:
        thd = next(
            row for row in self.review["channel_performance"]
            if row["platform"] == "THD" and row["channel"] == "DS"
        )
        self.assertAlmostEqual(thd["actual_sales"], 38617.77, places=6)
        self.assertEqual(thd["actual_cm"], 0.3752614907688956)
        self.assertEqual(thd["bp_cm"], 0.06783662932032082)
        self.assertEqual(thd["cm_gap"], 0.3074248614485748)
        self.assertEqual((thd["actual_cm_source_reference"], thd["bp_cm_source_reference"], thd["cm_gap_source_reference"]), ("E199", "E224", "E250"))
        self.assertAlmostEqual(thd["sales_vs_overview_gmv_delta"], 0.0, places=6)

    def test_lowes_source_sales_context_delta_is_visible(self) -> None:
        lowes = next(
            row for row in self.review["channel_performance"]
            if row["platform"] == "Lowe's" and row["channel"] == "DS"
        )
        self.assertEqual(lowes["overview_actual_gmv_source_reference"], "F172")
        self.assertAlmostEqual(lowes["overview_actual_gmv"], 23376.48, places=6)
        self.assertAlmostEqual(lowes["sales_vs_overview_gmv_delta"], 134.06, places=6)
        self.assertTrue(any(item["code"] == "CHANNEL_SALES_OVERVIEW_GMV_DELTA" for item in self.review["data_quality"]))

    def test_sku_cm_is_explicitly_unavailable(self) -> None:
        self.assertTrue(self.review["sku_sales_performance"])
        for row in self.review["sku_sales_performance"]:
            self.assertEqual(row["cm_status"], "NOT_AVAILABLE_AT_THIS_LEVEL")
            self.assertIsNone(row["actual_cm"])
            self.assertIsNone(row["bp_cm"])
            self.assertIsNone(row["cm_gap"])

    def test_thd_dfc_remains_independent(self) -> None:
        dfc = self.review["thd_dfc_sellout"]
        self.assertAlmostEqual(dfc["mtd_total"]["gmv"], 28504.78, places=6)
        self.assertEqual(dfc["mtd_total"]["units"], 35.0)
        self.assertEqual(self.review["reconciliation"]["phase2"]["thd_dfc"]["status"], "PASS")
        self.assertTrue(self.review["reconciliation"]["integrated_review"]["checks"]["thd_dfc_independent"])

    def test_business_results_use_channel_level_numbers(self) -> None:
        result = self.review["business_result"]
        self.assertEqual((result["sales_leader"]["platform"], result["sales_leader"]["channel"]), ("THD", "DS"))
        self.assertEqual((result["cm_leader"]["platform"], result["cm_leader"]["channel"]), ("THD", "DS"))
        self.assertEqual((result["biggest_negative_cm_gap"]["platform"], result["biggest_negative_cm_gap"]["channel"]), ("Walmart", "MP"))
        self.assertEqual((result["biggest_positive_cm_gap"]["platform"], result["biggest_positive_cm_gap"]["channel"]), ("THD", "DS"))

    def test_integrated_reconciliation_passes(self) -> None:
        self.assertEqual(self.review["status"], "STORM_V2_PHASE_3_BUSINESS_PERFORMANCE_READY")
        self.assertEqual(self.review["reconciliation"]["business_performance"]["status"], "PASS")
        self.assertEqual(self.review["reconciliation"]["integrated_review"]["status"], "PASS")
        self.assertEqual(self.review["freshness"]["common_sales"]["data_through"], "2026-08-10")
        self.assertIsNone(self.review["freshness"]["cm_business_performance"]["data_through"])

    def test_dashboard_ready_outputs_are_stable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            report_dir = Path(temp)
            first = generate_phase3(
                WORKBOOK, ROOT, snapshot_date=date(2026, 8, 13), report_dir=report_dir
            )
            json_path = report_dir / "weekly_business_review.json"
            markdown_path = report_dir / "weekly_business_review.md"
            csv_path = report_dir / "integrated_business_metrics.csv"
            before = json_path.read_bytes()
            second = generate_phase3(
                WORKBOOK, ROOT, snapshot_date=date(2026, 8, 13), report_dir=report_dir
            )
            self.assertEqual(before, json_path.read_bytes())
            self.assertEqual(first["snapshot_id"], second["snapshot_id"])
            self.assertTrue(markdown_path.exists() and csv_path.exists())
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], "3.0.0-integrated-review")
            self.assertEqual(payload["cm_source_coverage"]["record_count"], 30)


if __name__ == "__main__":
    unittest.main()
