from __future__ import annotations

import unittest
from datetime import date, timedelta

from storm_v2.thd_dfc_engine import aggregate_dfc, build_dfc_review, reconcile_dfc


def dfc_fact(day: date, reference: str, metric: str, value: float, sku: str = "SKU-1") -> dict:
    return {
        "record_id": f"THD- robot Sell out:{reference}:{metric}",
        "record_role": "FACT",
        "scenario": "ACTUAL",
        "metric_domain": "THD_DFC_SELLOUT",
        "metric_name": metric,
        "metric_value": value,
        "raw_value": value,
        "platform": "THD",
        "channel": "DFC",
        "brand": "Sunseeker",
        "power_source": "Robot",
        "sku": sku,
        "period_start": day.isoformat(),
        "period_end": day.isoformat(),
        "source_reference": reference,
    }


class ThdDfcEngineTests(unittest.TestCase):
    def test_positive_units_zero_gmv_is_retained_and_asp_suppressed(self) -> None:
        day = date(2026, 8, 10)
        records = [
            dfc_fact(day, "2:2", "units", 2.0),
            dfc_fact(day, "2:2", "gmv", 0.0),
            dfc_fact(day, "2:2", "traffic", 10.0),
        ]
        row = aggregate_dfc(records)[0]
        self.assertEqual(row["units"], 2.0)
        self.assertEqual(row["gmv"], 0.0)
        self.assertIsNone(row["asp"])
        self.assertEqual(row["positive_units_zero_gmv_count"], 1)
        self.assertEqual(reconcile_dfc(records)["status"], "PASS")

    def test_recent_windows_require_complete_equal_length_dates(self) -> None:
        records = []
        start = date(2026, 7, 28)
        for offset in range(14):
            day = start + timedelta(days=offset)
            ref = f"{offset + 2}:{offset + 2}"
            records.extend(
                [
                    dfc_fact(day, ref, "units", 1.0),
                    dfc_fact(day, ref, "gmv", 10.0),
                    dfc_fact(day, ref, "traffic", 20.0),
                ]
            )
        review = build_dfc_review(records)
        self.assertTrue(review["recent_window"]["available"])
        sku = review["mtd_by_sku"][0]
        self.assertEqual(sku["recent_7d_gmv"], 70.0)
        self.assertEqual(sku["previous_7d_gmv"], 70.0)
        self.assertEqual(sku["gmv_7d_change"], 0.0)
        incomplete = [row for row in records if row["period_start"] != "2026-08-03"]
        self.assertFalse(build_dfc_review(incomplete)["recent_window"]["available"])


if __name__ == "__main__":
    unittest.main()
