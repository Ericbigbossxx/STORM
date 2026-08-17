import unittest
from pathlib import Path

from storm_v2.phase5r import build_phase5r_package
from storm_v2.sku_bp import PHASE5R_DATA_STATUS


ROOT = Path(__file__).resolve().parents[1]
BP_WORKBOOK = ROOT.parent / "STORM" / "data" / "inbox" / "US E-commerce Actual CM for 2026_vs. BP.xlsx"
SNAPSHOT = ROOT / "data" / "snapshots" / "2026-08-13_b05ff566b9de"


@unittest.skipUnless(BP_WORKBOOK.exists() and SNAPSHOT.exists() and (ROOT / "reports" / "phase4" / "weekly_business_review.json").exists(), "requires approved local production inputs")
class Phase5RPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = build_phase5r_package(
            bp_workbook=BP_WORKBOOK,
            actual_snapshot_csv=SNAPSHOT / "sales_facts.csv",
            snapshot_manifest=SNAPSHOT / "manifest.json",
            phase4_json=ROOT / "reports" / "phase4" / "weekly_business_review.json",
        )

    def test_phase5r_data_status(self):
        self.assertEqual(self.package["status"], PHASE5R_DATA_STATUS)

    def test_phase5r_three_level_reconciliation(self):
        self.assertEqual(self.package["reconciliation"]["status"], "PASS")

    def test_phase5r_executive_actual_reconciles(self):
        self.assertAlmostEqual(self.package["executive"]["actual_sales"], 84090.87, places=2)

    def test_phase5r_channel_rollups(self):
        self.assertEqual(len(self.package["channel_health"]), 4)
        self.assertAlmostEqual(
            sum(row["actual_sales"] for row in self.package["channel_health"]),
            self.package["executive"]["actual_sales"],
            places=2,
        )
        self.assertAlmostEqual(
            sum(row["bp_sales"] for row in self.package["channel_health"]),
            self.package["executive"]["bp_sales"],
            places=2,
        )

    def test_phase5r_source_mutation_none(self):
        self.assertEqual(self.package["source_mutation"]["status"], "NONE")


if __name__ == "__main__":
    unittest.main()
