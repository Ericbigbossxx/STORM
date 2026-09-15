from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from storm_v2.comparison import previous_valid_snapshot
from storm_v2.weekly_production import (
    CM_SOURCE,
    RAW_SOURCE,
    WeeklyProductionBlocked,
    discover_sources,
    run_weekly_production,
    validate_sources,
    _all_reconciliation_statuses_pass,
)
from storm_v2.ytd import extract_ytd_metrics
from app.data import load_snapshot, metric_context


ROOT = Path(__file__).resolve().parents[1]
INBOX = ROOT / "data" / "inbox" / "2026-W34"


@unittest.skipUnless(INBOX.exists() and (ROOT / "data" / "snapshots" / "2026-08-17_r6").exists(), "requires approved local weekly production data")
class WeeklyProductionTests(unittest.TestCase):
    def test_discovery_and_compatibility_ignore_sha_baseline(self):
        sources = discover_sources(INBOX)
        self.assertEqual(set(sources), {RAW_SOURCE, CM_SOURCE})
        self.assertNotEqual(sources[RAW_SOURCE].sha256, "B05FF566B9DECC2852460E8FEC12AF8026B0C8D72148F52F974C32F27F1A8833")
        validation = validate_sources(sources, ROOT)
        self.assertEqual(validation["status"], "PASS")
        self.assertTrue(all(validation["source_compatibility"].values()))
        self.assertEqual(validation["bp_reconciliation"]["scope_exclusion_control"]["status"], "PASS")

    def test_authoritative_ytd_is_not_snapshot_sum(self):
        ytd = extract_ytd_metrics(INBOX / "weekly_cm_bp.xlsx", year=2026, through_month=8)
        self.assertEqual(ytd["source"], "AUTHORITATIVE_CM_BP_WORKBOOK")
        self.assertAlmostEqual(ytd["actual_sales"], 10151868.035637656)
        self.assertGreater(ytd["bp_sales"], 0)
        self.assertEqual(ytd["availability"]["actual_cm"]["status"], "N/A")

    def test_bad_source_blocks_without_snapshot(self):
        temporary = Path(tempfile.mkdtemp())
        try:
            inbox = temporary / "inbox"
            inbox.mkdir()
            book = Workbook()
            book.active.title = "Broken"
            book.save(inbox / "bad.xlsx")
            result = run_weekly_production(temporary, "2026-W52", inbox)
            self.assertEqual(result["status"], "FAILED")
            self.assertTrue(Path(result["failed_report"]).exists())
            self.assertFalse((temporary / "data" / "snapshots").exists())
        finally:
            shutil.rmtree(temporary)

    def test_reconciliation_gate_rejects_nested_failure(self):
        self.assertTrue(_all_reconciliation_statuses_pass({"phase2": {"common_sales": {"status": "PASS"}}}))
        self.assertFalse(_all_reconciliation_statuses_pass({"phase2": {"common_sales": {"status": "FAIL"}}}))

    def test_previous_valid_snapshot_excludes_current_week(self):
        previous = previous_valid_snapshot(ROOT, exclude_week_key="2026-W34")
        self.assertIsNotNone(previous)
        self.assertEqual(previous["snapshot_id"], "2026-08-14_r3")

    def test_latest_weekly_snapshot_exposes_authoritative_ytd_and_wow(self):
        data = load_snapshot("2026-08-17_r6")
        filters = {"platform": "All", "channel": "All", "brand": "All", "power_source": "All", "sku": "All"}
        ytd = metric_context(data, filters, "YTD")
        self.assertEqual(ytd["availability"], "AVAILABLE")
        self.assertAlmostEqual(ytd["actual_sales"], 10151868.035637656)
        self.assertEqual(data["manifest"]["wow"]["previous_snapshot_id"], "2026-08-14_r3")


if __name__ == "__main__":
    unittest.main()
