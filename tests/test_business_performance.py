from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path

from storm_v2.business_performance import read_business_performance


ROOT = Path(__file__).resolve().parents[1]
WORKBOOK = ROOT / "STORM V2 RAW DATA.xlsx"
@unittest.skipUnless(WORKBOOK.exists(), "requires approved local production workbook")
class BusinessPerformanceReaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = read_business_performance(WORKBOOK, ROOT, date(2026, 8, 13))

    def _record(self, level: str, scenario: str, **dimensions):
        matches = [
            row
            for row in self.data.records
            if row["analysis_level"] == level
            and row["scenario"] == scenario
            and all(row[key] == value for key, value in dimensions.items())
        ]
        self.assertEqual(len(matches), 1)
        return matches[0]

    def test_source_hash_period_and_coverage(self) -> None:
        self.assertRegex(self.data.source["source_sha256"], r"^[0-9A-F]{64}$")
        self.assertEqual(self.data.period["period_label"], "Aug MTD")
        self.assertEqual(self.data.coverage["record_count"], 30)
        self.assertEqual(self.data.coverage["business_record_count"], 34)
        self.assertEqual(self.data.coverage["channel_actual_gmv_context_count"], 4)
        self.assertEqual(self.data.coverage["by_level"], {"CHANNEL": 12, "BRAND": 6, "POWER_SOURCE": 12})
        self.assertEqual(self.data.coverage["by_scenario"], {"ACTUAL": 10, "BP": 10, "ACTUAL_VS_BP": 10})

    def test_source_values_and_references_are_exact(self) -> None:
        actual = self._record("BRAND", "ACTUAL", brand="Badger")
        bp = self._record("BRAND", "BP", brand="Badger")
        gap = self._record("BRAND", "ACTUAL_VS_BP", brand="Badger")
        self.assertEqual((actual["metric_value"], actual["source_reference"]), (0.024460019457085962, "D35"))
        self.assertEqual((bp["metric_value"], bp["source_reference"]), (-0.01011225113160365, "K35"))
        self.assertEqual((gap["metric_value"], gap["source_reference"]), (0.03457227058868961, "R35"))
        self.assertTrue(all(row["metric_value"] == row["raw_value"] for row in self.data.records))

    def test_source_reported_cm_is_not_recalculated(self) -> None:
        self.assertTrue(all(row["metric_origin"] == "SOURCE_REPORTED" for row in self.data.records))
        gap = self._record("CHANNEL", "ACTUAL_VS_BP", platform="Walmart", channel="MP")
        self.assertEqual(gap["source_reference"], "H250")
        self.assertEqual(gap["metric_value"], -0.6102849651094329)
        self.assertEqual(self.data.reconciliation["derived_metric_audit"], [])

    def test_level_integrity_does_not_propagate_parent_cm(self) -> None:
        for row in self.data.records:
            if row["analysis_level"] == "CHANNEL":
                self.assertIsNotNone(row["platform"])
                self.assertIsNotNone(row["channel"])
                self.assertIsNone(row["brand"])
                self.assertIsNone(row["power_source"])
                self.assertIsNone(row["sku"])
            elif row["analysis_level"] == "BRAND":
                self.assertIsNotNone(row["brand"])
                self.assertIsNone(row["platform"])
                self.assertIsNone(row["channel"])
                self.assertIsNone(row["power_source"])
                self.assertIsNone(row["sku"])
            else:
                self.assertIsNotNone(row["power_source"])
                self.assertIsNone(row["platform"])
                self.assertIsNone(row["channel"])
                self.assertIsNone(row["brand"])
                self.assertIsNone(row["sku"])

    def test_unknown_cm_day_does_not_inherit_sales_freshness(self) -> None:
        self.assertIsNone(self.data.period["data_through"])
        self.assertTrue(all(row["data_through"] is None for row in self.data.records))
        self.assertTrue(all(row["period_start"] is None and row["period_end"] is None for row in self.data.records))

    def test_scenario_and_percentage_point_units_are_distinct(self) -> None:
        for row in self.data.records:
            if row["metric_name"] == "gmv":
                self.assertEqual(row["unit"], "USD")
                self.assertEqual(row["value_scale"], "absolute")
                continue
            if row["scenario"] == "ACTUAL_VS_BP":
                self.assertEqual(row["metric_name"], "contribution_margin_rate_gap")
                self.assertEqual(row["unit"], "percentage_points")
            else:
                self.assertEqual(row["metric_name"], "contribution_margin_rate")
                self.assertEqual(row["unit"], "ratio")
            self.assertEqual(row["value_scale"], "fraction_of_one")

    def test_duplicate_sections_are_not_double_read(self) -> None:
        identities = {
            (
                row["analysis_level"], row["platform"], row["channel"], row["brand"],
                row["power_source"], row["metric_name"], row["scenario"],
            )
            for row in self.data.records
        }
        self.assertEqual(len(identities), len(self.data.records))
        self.assertEqual(self.data.reconciliation["status"], "PASS")

    def test_core_cm_cells_have_no_business_quality_warning(self) -> None:
        self.assertFalse(self.data.quality_issues)
        self.assertTrue(all(row["data_quality_status"] == "VALID" for row in self.data.records))


if __name__ == "__main__":
    unittest.main()
