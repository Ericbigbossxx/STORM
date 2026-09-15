from __future__ import annotations

import unittest
from pathlib import Path

from storm_v2.sku_bp import (
    aggregate_bp,
    extract_sku_bp,
    gap_rankings,
    join_actual_bp,
    load_actual_sku_sales,
    reconcile_bp,
)


ROOT = Path(__file__).resolve().parents[1]
BP_WORKBOOK = (
    ROOT.parent / "STORM" / "data" / "inbox"
    / "US E-commerce Actual CM for 2026_vs. BP.xlsx"
)
SALES_FACTS = (
    ROOT / "data" / "snapshots" / "2026-08-13_b05ff566b9de"
    / "sales_facts.csv"
)


@unittest.skipUnless(BP_WORKBOOK.exists() and SALES_FACTS.exists(), "requires approved local production inputs")
class SkuBpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.extraction = extract_sku_bp(BP_WORKBOOK, year=2026, month=8)
        cls.joined = join_actual_bp(
            load_actual_sku_sales(SALES_FACTS), cls.extraction["rows"]
        )

    def test_sku_bp_extraction(self) -> None:
        extraction = self.extraction
        self.assertEqual(extraction["source"]["sheet"], "KPI Rawdata")
        self.assertEqual(extraction["source"]["promotion_header"], "Promition Type")
        self.assertEqual(extraction["source"]["workbook_mutation"], "NONE")
        self.assertTrue(extraction["rows"])
        self.assertTrue(all(row["source_rows"] for row in extraction["rows"]))
        self.assertTrue(
            any(len(row["promotion_types"]) > 1 for row in extraction["rows"])
        )

    def test_sku_bp_grouping(self) -> None:
        channel_rows = aggregate_bp(
            self.extraction["rows"], ("platform", "channel")
        )
        brand_power_rows = aggregate_bp(
            self.extraction["rows"],
            ("platform", "channel", "brand", "power_source"),
        )
        self.assertEqual(len(channel_rows), 4)
        self.assertAlmostEqual(
            sum(row["bp_sales"] for row in channel_rows),
            sum(row["bp_sales"] for row in brand_power_rows),
        )
        self.assertEqual(reconcile_bp(self.extraction)["status"], "PASS")

    def test_sku_actual_bp_join(self) -> None:
        keys = {
            (row["platform"], row["channel"], row["sku"]) for row in self.joined
        }
        self.assertEqual(len(keys), len(self.joined))
        self.assertTrue(
            any(row["actual_present"] and row["bp_present"] for row in self.joined)
        )
        self.assertTrue(
            any(
                not row["actual_present"] and row["bp_present"]
                for row in self.joined
            )
        )
        self.assertTrue(any(row["bp_sales"] == 0 for row in self.joined))
        for row in self.joined:
            if row["bp_sales"] and row["bp_sales"] > 0:
                self.assertAlmostEqual(
                    row["attainment"],
                    row["actual_sales"] / row["bp_sales"],
                )

    def test_sku_gap_ranking(self) -> None:
        rankings = gap_rankings(self.joined, limit=5)
        detractors = rankings["top_detractors"]
        overperformers = rankings["top_overperformers"]
        self.assertEqual(len(detractors), 5)
        self.assertTrue(overperformers)
        self.assertTrue(all(row["bp_sales"] > 0 for row in overperformers))
        self.assertTrue(all(row["actual_sales"] > row["bp_sales"] for row in overperformers))
        self.assertEqual(
            [row["sales_gap"] for row in detractors],
            sorted(row["sales_gap"] for row in detractors),
        )
        self.assertEqual(
            [row["sales_gap"] for row in overperformers],
            sorted(
                (row["sales_gap"] for row in overperformers), reverse=True
            ),
        )

    def test_walmart_badger_gas_bp_control_and_scope_exclusion(self) -> None:
        control = self.extraction["walmart_badger_gas_control"]
        self.assertEqual(control["expected"], 11112.40)
        self.assertAlmostEqual(control["actual"], 11112.40)
        self.assertEqual(control["status"], "PASS")
        excluded = self.extraction["excluded_source_rows"]
        positive = [row for row in excluded if row["bp_sales"] > 0]
        self.assertAlmostEqual(self.extraction["excluded_bp_sales"], 127035.0)
        self.assertEqual({row["source_row"] for row in positive}, {3322, 3348, 3349, 3350, 3384, 3385, 3386})
        self.assertEqual({row["sku"] for row in positive}, {"ORIONX7", "SKRMV3", "SKRMX3PLUS"})
        self.assertTrue(all(row["scope_source_sheet"] == "Walmart Seller-WBP" for row in positive))
        reconciliation = reconcile_bp(self.extraction)
        self.assertEqual(reconciliation["scope_exclusion_control"]["status"], "PASS")
        self.assertAlmostEqual(reconciliation["level_5_platform_to_total"]["platform_rollup"], 963087.8451659728)


if __name__ == "__main__":
    unittest.main()
