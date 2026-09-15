from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from datetime import date
from pathlib import Path

from storm_v2.business_performance import (
    derive_operating_efficiency_metrics,
    read_business_performance,
)
from storm_v2.integrated_review import build_phase4_review, generate_phase4
from storm_v2.snapshot import build_phase2_data


ROOT = Path(__file__).resolve().parents[1]
WORKBOOK = ROOT / "STORM V2 RAW DATA.xlsx"


def _synthetic_source(metric_name: str, value: float | None) -> dict:
    return {
        "snapshot_id": "synthetic",
        "period_label": "Test MTD",
        "period_start": None,
        "period_end": None,
        "data_through": None,
        "platform": "Test",
        "channel": "DS",
        "subchannel": None,
        "brand": None,
        "power_source": None,
        "sku": None,
        "analysis_level": "CHANNEL",
        "metric_name": metric_name,
        "metric_origin": "SOURCE_REPORTED",
        "source_value": value,
        "source_sign": "MISSING" if value is None else ("NEGATIVE" if value < 0 else "POSITIVE"),
        "cost_sign_convention": "NEGATIVE_COST",
        "normalized_display_value": None if value is None else (value if metric_name == "gmv" else abs(value)),
        "display_normalization": "DISPLAY_NORMALIZED" if value is not None and value < 0 else "NONE",
        "source_file": "synthetic.xlsx",
        "source_sha256": "TEST",
        "source_sheet": "over view",
        "source_section": "All Brand",
        "source_reference": f"A{len(metric_name)}",
        "mapping_status": "MAPPED",
        "raw_dimensions": {"source_dimension": "Test"},
    }


@unittest.skipUnless(WORKBOOK.exists(), "requires approved local production workbook")
class OperatingEfficiencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.business = read_business_performance(WORKBOOK, ROOT, date(2026, 8, 13))
        cls.phase2 = build_phase2_data(WORKBOOK, ROOT, date(2026, 8, 13))
        cls.review = build_phase4_review(cls.phase2, cls.business)

    def _operating(self, level: str, metric_name: str, **dimensions):
        matches = [
            row for row in self.business.operating_records
            if row["analysis_level"] == level
            and row["metric_name"] == metric_name
            and all(row[key] == value for key, value in dimensions.items())
        ]
        self.assertEqual(len(matches), 1)
        return matches[0]

    def test_source_reported_operating_metrics_are_exact_and_unmutated(self) -> None:
        expected = {
            "market_insight": (1535.54, "E191"),
            "fixed_cost": (849.5909399999999, "E190"),
            "return_warranty_cost": (443.07, "E194"),
            "funding": (0, "E196"),
        }
        for metric_name, pair in expected.items():
            row = self._operating("CHANNEL", metric_name, platform="THD", channel="DS")
            self.assertEqual((row["source_value"], row["source_reference"]), pair)
            self.assertEqual(row["metric_origin"], "SOURCE_REPORTED")
            self.assertEqual(row["metric_value"], row["source_value"])
            self.assertEqual(row["source_value"], row["raw_value"])

    def test_sign_convention_and_display_values_are_explicit(self) -> None:
        self.assertEqual(self.business.operating_source_audit["sign_convention"], "POSITIVE_COST")
        source_rows = [
            row for row in self.business.operating_records
            if row["metric_origin"] == "SOURCE_REPORTED" and row["metric_name"] != "gmv"
        ]
        self.assertTrue(all(row["source_sign"] in {"POSITIVE", "ZERO"} for row in source_rows))
        self.assertTrue(all(row["display_normalization"] == "NONE" for row in source_rows))
        self.assertTrue(all(row["normalized_display_value"] == row["source_value"] for row in source_rows))

    def test_approved_rates_and_known_burden_reconcile(self) -> None:
        tacos = self._operating("CHANNEL", "tacos", platform="Walmart", channel="MP")
        fixed = self._operating("CHANNEL", "fixed_cost_rate", platform="Walmart", channel="MP")
        rw = self._operating("CHANNEL", "return_warranty_cost_rate", platform="Walmart", channel="MP")
        funding = self._operating("CHANNEL", "funding_rate", platform="Walmart", channel="MP")
        burden = self._operating(
            "CHANNEL", "known_operating_cost_burden_rate", platform="Walmart", channel="MP"
        )
        self.assertAlmostEqual(tacos["metric_value"], 1081.19 / 5750.92)
        self.assertAlmostEqual(fixed["metric_value"], 3693.638 / 5750.92)
        self.assertAlmostEqual(rw["metric_value"], 1172 / 5750.92)
        self.assertEqual(funding["metric_value"], 0)
        self.assertAlmostEqual(burden["metric_value"], (1081.19 + 3693.638 + 1172) / 5750.92)
        self.assertEqual(self.business.operating_reconciliation["status"], "PASS")

    def test_zero_gmv_missing_source_and_negative_cost_handling(self) -> None:
        source = [
            _synthetic_source("gmv", 0),
            _synthetic_source("market_insight", -10),
            _synthetic_source("fixed_cost", -20),
            _synthetic_source("return_warranty_cost", None),
            _synthetic_source("funding", 0),
        ]
        before = deepcopy(source)
        derived = derive_operating_efficiency_metrics(source, components_non_overlapping=True)
        by_name = {row["metric_name"]: row for row in derived}
        self.assertEqual(by_name["tacos"]["derivation_status"], "NOT_DERIVED_ZERO_OR_NEGATIVE_GMV")
        self.assertEqual(by_name["fixed_cost_rate"]["derivation_status"], "NOT_DERIVED_ZERO_OR_NEGATIVE_GMV")
        self.assertEqual(by_name["return_warranty_cost_rate"]["derivation_status"], "NOT_DERIVED_MISSING_SOURCE")
        self.assertEqual(by_name["funding_present"]["metric_value"], "NO")
        self.assertEqual(by_name["known_operating_cost_burden"]["derivation_status"], "NOT_DERIVED_MISSING_SOURCE")
        self.assertEqual(source, before)

    def test_overlapping_components_prevent_known_burden(self) -> None:
        source = [
            _synthetic_source("gmv", 100),
            _synthetic_source("market_insight", 10),
            _synthetic_source("fixed_cost", 20),
            _synthetic_source("return_warranty_cost", 5),
            _synthetic_source("funding", 1),
        ]
        derived = derive_operating_efficiency_metrics(source, components_non_overlapping=False)
        burden = next(row for row in derived if row["metric_name"] == "known_operating_cost_burden")
        self.assertIsNone(burden["metric_value"])
        self.assertEqual(burden["derivation_status"], "NOT_DERIVED_DUE_TO_OVERLAPPING_COMPONENTS")

    def test_no_forced_lower_level_allocation(self) -> None:
        self.assertEqual(self.business.operating_coverage["sku_operating_metrics"], 0)
        self.assertTrue(all(row["analysis_level"] != "SKU" for row in self.business.operating_records))
        self.assertTrue(all(row["sku"] is None for row in self.business.operating_records))
        for row in self.review["sku_sales_performance"]:
            self.assertEqual(row["operating_status"], "NOT_AVAILABLE_AT_THIS_LEVEL")
            self.assertIsNone(row["market_insight"])

    def test_phase4_review_and_five_outputs_are_stable(self) -> None:
        self.assertEqual(self.review["status"], "STORM_V2_PHASE_4_OPERATING_INSIGHT_COMPLETE")
        self.assertEqual(self.review["phase1_4_review"]["status"], "DATA_ANALYSIS_LAYER_COMPLETE")
        self.assertEqual(self.review["phase5_readiness"], "READY_FOR_PHASE_5_DASHBOARD")
        with tempfile.TemporaryDirectory() as temp:
            report_dir = Path(temp)
            generate_phase4(WORKBOOK, ROOT, snapshot_date=date(2026, 8, 13), report_dir=report_dir)
            expected = {
                "weekly_business_review.md", "weekly_business_review.json",
                "integrated_business_metrics.csv", "operating_efficiency_metrics.csv",
                "phase1_4_data_review.md",
            }
            self.assertEqual({path.name for path in report_dir.iterdir()}, expected)
            first = (report_dir / "weekly_business_review.json").read_bytes()
            generate_phase4(WORKBOOK, ROOT, snapshot_date=date(2026, 8, 13), report_dir=report_dir)
            self.assertEqual(first, (report_dir / "weekly_business_review.json").read_bytes())
            payload = json.loads(first)
            self.assertEqual(payload["schema_version"], "4.0.0-operating-insight")


if __name__ == "__main__":
    unittest.main()
