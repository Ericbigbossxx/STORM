from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

import duckdb

from app.components.layout import percent
from app.data import apply_filters, load_snapshot, metric_context, snapshot_options
from scripts.build_phase6_snapshot import build_snapshot


ROOT = Path(__file__).resolve().parents[1]
PHASE6_INPUTS = (
    ROOT / "reports" / "phase5r" / "phase5r_package.json",
    ROOT / "data" / "snapshots" / "2026-08-13_b05ff566b9de" / "manifest.json",
    ROOT / "data" / "snapshots" / "2026-08-13_b05ff566b9de" / "canonical_records.csv",
)


@unittest.skipUnless(all(path.exists() for path in PHASE6_INPUTS), "requires local production snapshot inputs")
class Phase6SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp())
        (self.temp / "reports" / "phase5r").mkdir(parents=True)
        (self.temp / "data" / "snapshots" / "2026-08-13_b05ff566b9de").mkdir(parents=True)
        shutil.copy2(ROOT / "reports" / "phase5r" / "phase5r_package.json", self.temp / "reports" / "phase5r" / "phase5r_package.json")
        shutil.copy2(ROOT / "data" / "snapshots" / "2026-08-13_b05ff566b9de" / "manifest.json", self.temp / "data" / "snapshots" / "2026-08-13_b05ff566b9de" / "manifest.json")
        shutil.copy2(ROOT / "data" / "snapshots" / "2026-08-13_b05ff566b9de" / "canonical_records.csv", self.temp / "data" / "snapshots" / "2026-08-13_b05ff566b9de" / "canonical_records.csv")
        package_path = self.temp / "reports" / "phase5r" / "phase5r_package.json"
        package = json.loads(package_path.read_text(encoding="utf-8"))
        package["source"]["bp"]["path"] = str(package_path)
        package_path.write_text(json.dumps(package), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.temp)

    def test_creation_manifest_and_reconciliation(self):
        manifest = build_snapshot(self.temp, "2026-08-14")
        self.assertEqual(manifest["week_key"], "2026-W33")
        self.assertEqual(manifest["reconciliation"]["status"], "PASS")
        self.assertEqual(manifest["reconciliation"]["sku_bp_control"]["status"], "PASS")
        self.assertTrue((self.temp / "data" / "snapshots" / manifest["snapshot_id"] / "sku_metrics.parquet").exists())
        with duckdb.connect(str(self.temp / "data" / "storm.duckdb")) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM snapshot_registry").fetchone()[0], 1)

    def test_snapshot_immutability_and_revision(self):
        first = build_snapshot(self.temp, "2026-08-14")
        with self.assertRaises(FileExistsError):
            build_snapshot(self.temp, "2026-08-14", revision=1)
        second = build_snapshot(self.temp, "2026-08-14")
        self.assertEqual(first["revision"], 1)
        self.assertEqual(second["revision"], 2)

    def test_published_snapshot_loads_and_matches_controls(self):
        data = load_snapshot("2026-08-14_r1")
        controls = data["manifest"]["reconciliation"]
        self.assertEqual(controls["status"], "PASS")
        self.assertAlmostEqual(controls["actual_sales"], 84090.87, places=2)
        self.assertAlmostEqual(controls["bp_sales"], 1090122.8451659728, places=6)
        self.assertAlmostEqual(controls["sales_gap"], -1006031.9751659728, places=6)
        self.assertAlmostEqual(controls["attainment"], 0.07713889344938646, places=8)
        self.assertEqual(controls["sku_bp_control"]["status"], "PASS")

    def test_r3_has_corrected_bp_hierarchy_and_supersedes_r2(self):
        data = load_snapshot("2026-08-14_r3")
        manifest = data["manifest"]
        self.assertEqual(manifest["supersedes"], "2026-08-14_r2")
        self.assertAlmostEqual(manifest["reconciliation"]["bp_sales"], 963087.8451659728)
        self.assertEqual(manifest["reconciliation"]["bp_hierarchy"]["status"], "PASS")
        self.assertEqual(manifest["reconciliation"]["bp_hierarchy"]["scope_exclusion_control"]["status"], "PASS")
        status_by_id = {item["snapshot_id"]: item["status"] for item in snapshot_options()}
        self.assertEqual(status_by_id["2026-08-14_r2"], "SUPERSEDED_DATA_RECONCILIATION_ERROR")

    def test_percentage_and_executive_filter_context(self):
        data = load_snapshot("2026-08-14_r3")
        row = data["sku_metrics"][(data["sku_metrics"]["platform"] == "THD") & (data["sku_metrics"]["sku"] == "WB31CCED")].iloc[0]
        self.assertAlmostEqual(float(row["attainment"]), 2.7864953017745298)
        self.assertEqual(percent(float(row["attainment"])), "278.65%")
        all_filters = {"platform": "All", "channel": "All", "brand": "All", "power_source": "All", "sku": "All"}
        thd_filters = {**all_filters, "platform": "THD"}
        overall = metric_context(data, all_filters, "MTD")
        thd = metric_context(data, thd_filters, "MTD")
        self.assertNotEqual(overall["actual_sales"], thd["actual_sales"])
        self.assertNotEqual(overall["sales_gap"], thd["sales_gap"])

    def test_mtd_ytd_are_distinct_and_ytd_is_not_snapshot_sum(self):
        data = load_snapshot("2026-08-14_r3")
        filters = {"platform": "All", "channel": "All", "brand": "All", "power_source": "All", "sku": "All"}
        mtd = metric_context(data, filters, "MTD")
        ytd = metric_context(data, filters, "YTD")
        self.assertEqual(mtd["availability"], "AVAILABLE")
        self.assertEqual(ytd["period_source"], "AUTHORITATIVE_CM_WORKBOOK")
        self.assertEqual(ytd["availability"], "N/A_NO_COMPATIBLE_YTD_SALES_BP_EXTRACT")
        self.assertIsNone(ytd["actual_sales"])

    def test_latest_snapshot_resolution_and_cascading_filter(self):
        snapshots = snapshot_options()
        latest = snapshots[0]
        self.assertEqual(latest["revision"], max(item["revision"] for item in snapshots if item["snapshot_date"] == latest["snapshot_date"]))
        data = load_snapshot(latest["snapshot_id"])
        thd = apply_filters(data["sku_metrics"], {"platform": "THD"})
        self.assertEqual(set(thd["channel"]), {"DS"})
        robot = apply_filters(data["sku_metrics"], {"platform": "THD", "channel": "DS", "brand": "Sunseeker", "power_source": "Robot"})
        self.assertEqual(set(robot["power_source"]), {"Robot"})

    def test_dfc_isolation(self):
        data = load_snapshot("2026-08-14_r1")
        dfc = data["thd_dfc_daily"]
        self.assertNotIn("actual_cm", dfc.columns)
        august = dfc[dfc["date"].astype(str).str.startswith("2026-08")]
        self.assertAlmostEqual(float(august["gmv"].sum()), 28504.78, places=2)


if __name__ == "__main__":
    unittest.main()
