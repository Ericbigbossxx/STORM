from __future__ import annotations

import unittest

from storm_v2.sales_engine import (
    aggregate_sales,
    attach_baseline,
    performance_rankings,
    reconcile_common_sales,
    reconcile_hierarchy,
)


def fact(
    reference: str,
    metric: str,
    value: float | None,
    *,
    platform: str = "Walmart",
    channel: str = "MP",
    brand: str = "Sunseeker",
    power_source: str = "Robot",
    sku: str = "SKU-1",
    order: str = "ORDER-1",
    day: str = "2026-08-01",
) -> dict:
    return {
        "record_id": f"actual order:{reference}:{metric}",
        "record_role": "FACT",
        "scenario": "ACTUAL",
        "metric_domain": "SALES",
        "metric_name": metric,
        "metric_value": value,
        "raw_value": value,
        "platform": platform,
        "channel": channel,
        "brand": brand,
        "power_source": power_source,
        "sku": sku,
        "order_number": order,
        "period_start": day,
        "period_end": day,
        "source_reference": reference,
    }


def baseline(period_end: str = "2026-08-31", value: float = 200.0) -> dict:
    return {
        "record_role": "REFERENCE",
        "scenario": "BP",
        "metric_domain": "SALES",
        "metric_name": "revenue",
        "metric_value": value,
        "platform": "Walmart",
        "channel": "MP",
        "brand": "Sunseeker",
        "power_source": "Robot",
        "sku": "SKU-1",
        "period_start": "2026-08-01",
        "period_end": period_end,
    }


class SalesEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.records = [
            fact("2:2", "revenue", 100.0),
            fact("2:2", "units", 2.0),
            fact("3:3", "revenue", 50.0, sku="UNKNOWN", brand="UNKNOWN", order="ORDER-2"),
            fact("3:3", "units", 0.0, sku="UNKNOWN", brand="UNKNOWN", order="ORDER-2"),
        ]

    def test_revenue_units_orders_and_null_asp(self) -> None:
        total = aggregate_sales(self.records)[0]
        self.assertEqual(total["actual_sales"], 150.0)
        self.assertEqual(total["units"], 2.0)
        self.assertEqual(total["orders"], 2)
        self.assertEqual(total["asp"], 75.0)
        by_sku = {row["sku"]: row for row in aggregate_sales(self.records, ("sku",))}
        self.assertIsNone(by_sku["UNKNOWN"]["asp"])
        self.assertEqual(by_sku["UNKNOWN"]["units"], 0.0)

    def test_dfc_and_unapproved_channels_are_excluded(self) -> None:
        excluded = fact("4:4", "revenue", 999.0, platform="THD", channel="DFC")
        self.assertEqual(aggregate_sales(self.records + [excluded])[0]["actual_sales"], 150.0)

    def test_bp_requires_exact_period_and_zero_is_not_missing(self) -> None:
        actual = aggregate_sales(self.records[:2], ("sku",))
        actual[0]["period_start"] = "2026-08-01"
        actual[0]["period_end"] = "2026-08-10"
        unmatched, coverage = attach_baseline(actual, [baseline()], ("sku",))
        self.assertEqual(unmatched[0]["bp_status"], "BP_NOT_AVAILABLE")
        self.assertIsNone(unmatched[0]["bp"])
        self.assertEqual(coverage["matched_group_count"], 0)
        actual[0]["period_end"] = "2026-08-31"
        matched, _ = attach_baseline(actual, [baseline(value=0.0)], ("sku",))
        self.assertEqual(matched[0]["bp"], 0.0)
        self.assertIsNone(matched[0]["attainment"])
        self.assertIn("zero", matched[0]["bp_warning"])

    def test_reconciliation_and_hierarchy(self) -> None:
        self.assertEqual(reconcile_common_sales(self.records)["status"], "PASS")
        result = reconcile_hierarchy(self.records)
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(all(row["sales_difference"] == 0 for row in result["rows"]))

    def test_no_bp_uses_sales_contribution_rankings(self) -> None:
        rows = aggregate_sales(self.records, ("sku",))
        for row in rows:
            row["bp_status"] = "BP_NOT_AVAILABLE"
            row["gap"] = None
        rankings = performance_rankings(rows)
        self.assertTrue(rankings["top_sales_contributors"])
        self.assertTrue(rankings["lowest_sales_contributors"])
        self.assertEqual(rankings["top_negative_bp_gaps"], [])


if __name__ == "__main__":
    unittest.main()
