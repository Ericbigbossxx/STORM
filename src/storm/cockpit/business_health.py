"""Assemble one US x WALMART_MP Business Health snapshot without persistence."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from pathlib import Path
import re
import sqlite3
from typing import Any, Iterable, Mapping

from storm.adapters.walmart_official import WalmartOfficialEvidence

from .models import (
    AvailabilityState,
    BusinessHealthSnapshot,
    DataStatus,
    DerivedMetric,
    FreshnessState,
    MetricFact,
)


class AssemblyError(RuntimeError):
    """Raised when accepted Phase 1 evidence is absent or internally inconsistent."""


def _iso_date(value: Any) -> str:
    return str(value)[:10]


def _parse_date(value: Any) -> date:
    return date.fromisoformat(_iso_date(value))


def _period_days(record: Mapping[str, Any]) -> int:
    return (_parse_date(record["coverage_end_date"]) - _parse_date(record["coverage_start_date"])).days + 1


def _nullable_sum(values: Iterable[Any]) -> float | None:
    collected = list(values)
    if not collected or any(value is None for value in collected):
        return None
    return float(sum(float(value) for value in collected))


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def compare_equal_weekly(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Compare only consecutive equal-length WEEKLY_OPERATING snapshots."""

    ordered = sorted(records, key=lambda item: _parse_date(item["business_as_of_date"]))
    if len(ordered) < 2:
        return {"availability": "NOT_COMPARABLE", "reason": "INSUFFICIENT_WEEKLY_HISTORY"}
    previous, current = ordered[-2:]
    if previous.get("period_scope") != "WEEKLY_OPERATING" or current.get("period_scope") != "WEEKLY_OPERATING":
        return {"availability": "NOT_COMPARABLE", "reason": "MTD_RESET_OR_NON_WEEKLY_PERIOD"}
    if _period_days(previous) != _period_days(current):
        return {"availability": "NOT_COMPARABLE", "reason": "UNEQUAL_COVERAGE_LENGTH"}
    previous_end = _parse_date(previous["coverage_end_date"])
    current_start = _parse_date(current["coverage_start_date"])
    if previous_end + timedelta(days=1) != current_start:
        return {"availability": "NOT_COMPARABLE", "reason": "NON_CONSECUTIVE_WINDOWS"}
    current_value = current.get("net_sales")
    previous_value = previous.get("net_sales")
    if current_value is None or previous_value is None:
        return {"availability": "NOT_COMPARABLE", "reason": "NET_SALES_NOT_AVAILABLE"}
    absolute = float(current_value) - float(previous_value)
    percent = None if float(previous_value) == 0 else absolute / abs(float(previous_value))
    return {
        "availability": "AVAILABLE",
        "current_value": float(current_value),
        "previous_value": float(previous_value),
        "absolute_change": absolute,
        "percent_change": percent,
        "current_period_start": _iso_date(current["coverage_start_date"]),
        "current_period_end": _iso_date(current["coverage_end_date"]),
        "previous_period_start": _iso_date(previous["coverage_start_date"]),
        "previous_period_end": _iso_date(previous["coverage_end_date"]),
        "coverage_days": _period_days(current),
    }


def _month_bounds(year: int, month: int) -> tuple[str, str]:
    return date(year, month, 1).isoformat(), date(year, month, monthrange(year, month)[1]).isoformat()


def _week_id(day: date) -> str:
    iso = day.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


class BusinessHealthAssembler:
    """Join verified Walmart operating evidence to the accepted Phase 1 metrics batch."""

    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path).resolve()

    def _connect_read_only(self) -> sqlite3.Connection:
        if not self.database_path.is_file():
            raise AssemblyError(f"STRUCTURED_METRICS_DATABASE_MISSING: {self.database_path}")
        connection = sqlite3.connect(f"file:{self.database_path.as_posix()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _current_batch(connection: sqlite3.Connection) -> sqlite3.Row:
        batch = connection.execute(
            """SELECT * FROM IMPORT_BATCH
               WHERE report_type = 'OFFICIAL_CM_WORKBOOK' AND status = 'COMMITTED'
                 AND source_period LIKE '%|MTD'
               ORDER BY imported_at DESC LIMIT 1"""
        ).fetchone()
        if batch is None:
            raise AssemblyError("ACCEPTED_MTD_IMPORT_BATCH_NOT_AVAILABLE")
        return batch

    @staticmethod
    def _phase1_facts(connection: sqlite3.Connection, batch: sqlite3.Row) -> dict[str, Any]:
        period_month, period_type = str(batch["source_period"]).split("|", maxsplit=1)
        if period_type != "MTD":
            raise AssemblyError("PHASE1_PERIOD_NOT_MTD")
        year, month = map(int, period_month.split("-"))
        bp_rows = connection.execute(
            """SELECT bp_units, bp_sales, bp_cm FROM FACT_BP_TARGET_MONTHLY
               WHERE import_batch_id = ? AND year = ? AND month = ? AND platform = 'WALMART_MP'""",
            (batch["import_batch_id"], year, month),
        ).fetchall()
        cm_rows = connection.execute(
            """SELECT actual_units, actual_sales, actual_cm, cm_basis, primary_sales_basis,
                      snapshot_date, data_through_date
               FROM FACT_CM_SNAPSHOT
               WHERE import_batch_id = ? AND period_type = 'MTD' AND platform = 'WALMART_MP'""",
            (batch["import_batch_id"],),
        ).fetchall()
        if not bp_rows or not cm_rows:
            raise AssemblyError("WALMART_PHASE1_FACTS_NOT_AVAILABLE")
        if {str(row["data_through_date"]) for row in cm_rows} != {str(batch["data_through_date"])}:
            raise AssemblyError("CM_BATCH_LINEAGE_MISMATCH")
        return {
            "year": year,
            "month": month,
            "bp_units": _nullable_sum(row["bp_units"] for row in bp_rows),
            "bp_sales": _nullable_sum(row["bp_sales"] for row in bp_rows),
            "bp_cm": _nullable_sum(row["bp_cm"] for row in bp_rows),
            "cm_units": _nullable_sum(row["actual_units"] for row in cm_rows),
            "cm_basis_sales": _nullable_sum(row["actual_sales"] for row in cm_rows),
            "actual_cm": _nullable_sum(row["actual_cm"] for row in cm_rows),
            "cm_basis": sorted({str(row["cm_basis"]) for row in cm_rows}),
            "primary_sales_basis": sorted({str(row["primary_sales_basis"]) for row in cm_rows}),
        }

    def assemble(
        self,
        walmart: WalmartOfficialEvidence,
        *,
        control_week: str | None = None,
    ) -> BusinessHealthSnapshot:
        if walmart.platform != "WALMART_MP" or walmart.source_scope != "WALMART_MARKETPLACE_3P":
            raise AssemblyError("WALMART_PLATFORM_SCOPE_INVALID")
        with self._connect_read_only() as connection:
            batch = self._current_batch(connection)
            phase1 = self._phase1_facts(connection, batch)
        mtd_dataset = walmart.datasets["business_current_state"]
        weekly_dataset = walmart.datasets["business_weekly_current_state"]
        sku_dataset = walmart.datasets["sku_current_performance"]
        if len(mtd_dataset.records) != 1:
            raise AssemblyError("WALMART_MTD_SINGLE_ROW_REQUIRED")
        mtd = mtd_dataset.records[0]
        wos_start = _iso_date(mtd["coverage_start_date"])
        wos_end = _iso_date(mtd["coverage_end_date"])
        cm_end = str(batch["data_through_date"])
        cm_snapshot = str(batch["snapshot_date"])
        month_start, month_end = _month_bounds(phase1["year"], phase1["month"])
        review_day = max(_parse_date(cm_snapshot), _parse_date(walmart.business_as_of_date))
        resolved_control_week = control_week or _week_id(review_day)
        if re.fullmatch(r"\d{4}-W(?:0[1-9]|[1-4]\d|5[0-3])", resolved_control_week) is None:
            raise AssemblyError("CONTROL_WEEK_INVALID")
        inventory_distribution: dict[str, int] = {}
        for row in sku_dataset.records:
            status = str(row["inventory_status"]) if row["inventory_status"] is not None else "SOURCE_NOT_AVAILABLE"
            inventory_distribution[status] = inventory_distribution.get(status, 0) + 1
        actual_sales = None if mtd["net_sales"] is None else float(mtd["net_sales"])
        bp_sales = phase1["bp_sales"]
        actual_cm = phase1["actual_cm"]
        bp_cm = phase1["bp_cm"]
        cm_basis_sales = phase1["cm_basis_sales"]
        trend = compare_equal_weekly(weekly_dataset.history_records)
        batch_id = str(batch["import_batch_id"])
        phase1_artifact = str(batch["source_filename"])
        phase1_release = str(batch["file_hash"])

        def wos_fact(name: str, value: Any, unit: str, notes: tuple[str, ...] = ()) -> MetricFact:
            return MetricFact(
                name, value, unit, str(mtd["period_scope"]), wos_start, wos_end,
                _iso_date(mtd["business_as_of_date"]), wos_end,
                AvailabilityState.AVAILABLE if value is not None else AvailabilityState.SOURCE_NOT_AVAILABLE,
                FreshnessState.CURRENT, walmart.source_system, mtd_dataset.source_artifact,
                walmart.official_run_id, walmart.official_run_id, walmart.generated_at_utc, "UTC",
                notes + ("Latest official release; no day-based freshness threshold is defined.",),
            )

        def phase1_fact(name: str, value: Any, unit: str, period_type: str, period_start: str,
                        period_end: str, data_through: str | None, notes: tuple[str, ...] = ()) -> MetricFact:
            return MetricFact(
                name, value, unit, period_type, period_start, period_end, cm_snapshot, data_through,
                AvailabilityState.AVAILABLE if value is not None else AvailabilityState.SOURCE_NOT_AVAILABLE,
                FreshnessState.CURRENT, "STORM Structured Metrics", phase1_artifact, phase1_release,
                batch_id, str(batch["imported_at"]), "UTC", notes,
            )

        facts: dict[str, MetricFact] = {
            "actual_sales": wos_fact("actual_sales", actual_sales, "USD", ("Walmart net_sales; not CM-basis sales.",)),
            "bp_sales": phase1_fact("bp_sales", bp_sales, "USD", "MONTHLY_TARGET", month_start, month_end, None, ("Full-month target; not plan-to-date.",)),
            "actual_cm": phase1_fact("actual_cm", actual_cm, "USD", "MTD", month_start, cm_end, cm_end, (f"CM basis: {', '.join(phase1['cm_basis'])}",)),
            "bp_cm": phase1_fact("bp_cm", bp_cm, "USD", "MONTHLY_TARGET", month_start, month_end, None, ("Full-month target; not plan-to-date.",)),
            "cm_basis_sales": phase1_fact("cm_basis_sales", cm_basis_sales, "USD", "MTD", month_start, cm_end, cm_end, (f"Primary sales basis: {', '.join(phase1['primary_sales_basis'])}",)),
            "ad_spend": wos_fact("ad_spend", None if mtd["ad_spend"] is None else float(mtd["ad_spend"]), "USD"),
            "attributed_ad_sales": wos_fact("attributed_ad_sales", None if mtd["ad_sales"] is None else float(mtd["ad_sales"]), "USD"),
            "roas": wos_fact("roas", None if mtd["calculated_roas"] is None else float(mtd["calculated_roas"]), "RATIO"),
            "inventory_units": wos_fact("inventory_units", None if mtd["inventory_units"] is None else int(mtd["inventory_units"]), "UNITS"),
            "inventory_condition": MetricFact(
                "inventory_condition", inventory_distribution, "STATUS_DISTRIBUTION", "SNAPSHOT",
                wos_start, wos_end, sku_dataset.business_date, sku_dataset.business_date,
                AvailabilityState.AVAILABLE, FreshnessState.CURRENT, walmart.source_system,
                sku_dataset.source_artifact, walmart.official_run_id, walmart.official_run_id,
                walmart.generated_at_utc, "UTC",
                ("No approved platform health rollup; source SKU statuses only.",
                 "Latest official release; no day-based freshness threshold is defined."),
            ),
            "ytd_actual_cm": MetricFact(
                "ytd_actual_cm", None, "USD", "YTD", None, None, cm_snapshot, None,
                AvailabilityState.SOURCE_NOT_AVAILABLE, FreshnessState.SOURCE_NOT_AVAILABLE,
                "STORM Structured Metrics", phase1_artifact, phase1_release, batch_id,
                str(batch["imported_at"]), "UTC", ("Phase 1 workbook is MTD; YTD was not reconstructed.",),
            ),
        }
        sales_attainment = _ratio(actual_sales, bp_sales)
        cm_attainment = _ratio(actual_cm, bp_cm)
        actual_cm_pct = _ratio(actual_cm, cm_basis_sales)
        derived: dict[str, DerivedMetric] = {
            "sales_attainment_pct": DerivedMetric("sales_attainment_pct", sales_attainment, "RATIO", AvailabilityState.AVAILABLE if sales_attainment is not None else AvailabilityState.SOURCE_NOT_AVAILABLE, "actual_sales / full_month_bp_sales", ("actual_sales", "bp_sales"), wos_end, ("MTD progress-to-monthly-plan; not plan-to-date pacing.",)),
            "cm_attainment_pct": DerivedMetric("cm_attainment_pct", cm_attainment, "RATIO", AvailabilityState.AVAILABLE if cm_attainment is not None else AvailabilityState.SOURCE_NOT_AVAILABLE, "actual_cm / full_month_bp_cm", ("actual_cm", "bp_cm"), cm_end, ("MTD progress-to-monthly-plan; not plan-to-date pacing.",)),
            "actual_cm_pct": DerivedMetric("actual_cm_pct", actual_cm_pct, "RATIO", AvailabilityState.AVAILABLE if actual_cm_pct is not None else AvailabilityState.SOURCE_NOT_AVAILABLE, "actual_cm / cm_basis_sales", ("actual_cm", "cm_basis_sales"), cm_end, ("Uses two facts from the same accepted CM batch; does not use Walmart net_sales.",)),
            "weekly_sales_change": DerivedMetric("weekly_sales_change", trend if trend["availability"] == "AVAILABLE" else None, "USD_AND_RATIO", AvailabilityState.AVAILABLE if trend["availability"] == "AVAILABLE" else AvailabilityState.NOT_COMPARABLE, "latest_equal_week_net_sales - prior_equal_week_net_sales" if trend["availability"] == "AVAILABLE" else None, ("business_weekly_current_state.latest", "business_weekly_current_state.previous"), trend.get("current_period_end"), (() if trend["availability"] == "AVAILABLE" else (str(trend["reason"]),))),
            "sales_cm_common_cutoff_metric": DerivedMetric("sales_cm_common_cutoff_metric", None, "NOT_APPLICABLE", AvailabilityState.NOT_COMPARABLE, None, ("actual_sales", "actual_cm"), None, (f"Native cutoffs differ ({wos_end} vs {cm_end}); neither aggregate can be safely re-sliced.",)),
        }
        data_status = {
            "sales": DataStatus("sales", walmart.source_system, mtd_dataset.source_artifact, walmart.official_run_id, _iso_date(mtd["business_as_of_date"]), wos_end, wos_start, wos_end, str(mtd["period_scope"]), FreshnessState.CURRENT, AvailabilityState.AVAILABLE, (walmart.release_manifest, mtd_dataset.content_hash), ("Latest official source; cadence age not scored.",)),
            "advertising": DataStatus("advertising", walmart.source_system, mtd_dataset.source_artifact, walmart.official_run_id, _iso_date(mtd["business_as_of_date"]), wos_end, wos_start, wos_end, str(mtd["period_scope"]), FreshnessState.CURRENT, AvailabilityState.AVAILABLE, (walmart.release_manifest, mtd_dataset.content_hash)),
            "inventory": DataStatus("inventory", walmart.source_system, sku_dataset.source_artifact, walmart.official_run_id, sku_dataset.business_date, sku_dataset.business_date, wos_start, wos_end, "SNAPSHOT", FreshnessState.CURRENT, AvailabilityState.UNRESOLVED, (walmart.release_manifest, sku_dataset.content_hash), ("Units and SKU statuses are available; platform health rollup is not approved.",)),
            "weekly_trend": DataStatus("weekly_trend", walmart.source_system, weekly_dataset.source_artifact, walmart.official_run_id, weekly_dataset.business_date, trend.get("current_period_end"), trend.get("current_period_start"), trend.get("current_period_end"), "WEEKLY_OPERATING", FreshnessState.CURRENT, AvailabilityState.AVAILABLE if trend["availability"] == "AVAILABLE" else AvailabilityState.NOT_COMPARABLE, (walmart.release_manifest, weekly_dataset.content_hash), weekly_dataset.warnings + (() if trend["availability"] == "AVAILABLE" else (str(trend["reason"]),))),
            "bp_plan": DataStatus("bp_plan", "STORM Structured Metrics", phase1_artifact, phase1_release, cm_snapshot, None, month_start, month_end, "MONTHLY_TARGET", FreshnessState.CURRENT, AvailabilityState.AVAILABLE, (batch_id, str(batch["file_hash"]))),
            "cm_actual": DataStatus("cm_actual", "STORM Structured Metrics", phase1_artifact, phase1_release, cm_snapshot, cm_end, month_start, cm_end, "MTD", FreshnessState.CURRENT, AvailabilityState.AVAILABLE, (batch_id, str(batch["file_hash"]))),
            "ytd_cm": DataStatus("ytd_cm", "STORM Structured Metrics", phase1_artifact, phase1_release, cm_snapshot, None, None, None, "YTD", FreshnessState.SOURCE_NOT_AVAILABLE, AvailabilityState.SOURCE_NOT_AVAILABLE, (batch_id,), ("No accepted YTD CM evidence.",)),
            "cross_domain_comparison": DataStatus("cross_domain_comparison", "MIXED", None, None, cm_snapshot, None, None, None, "NATIVE_SOURCE_PERIODS", FreshnessState.NOT_APPLICABLE, AvailabilityState.NOT_COMPARABLE, (walmart.official_run_id, batch_id), (f"Sales through {wos_end}; CM through {cm_end}; no false common cutoff.",)),
        }
        return BusinessHealthSnapshot(
            schema_version=2, control_week=resolved_control_week, market="US", platform="WALMART_MP",
            level="PLATFORM", snapshot_date=review_day.isoformat(), facts=facts,
            data_status=data_status, derived_control_metrics=derived,
            interpretation={
                "overall_status": "UNRESOLVED", "sales_status": "UNRESOLVED",
                "ads_status": "UNRESOLVED", "inventory_status": "UNRESOLVED",
                "primary_driver": "UNRESOLVED", "key_risk": "UNRESOLVED",
                "key_opportunity": "UNRESOLVED", "required_action": "UNRESOLVED",
            },
            warnings=weekly_dataset.warnings + (
                f"MIXED_NATIVE_CUTOFFS: sales/ads/inventory through {wos_end}; CM through {cm_end}.",
                "NO_HEALTH_THRESHOLDS: all Feishu health fields remain UNKNOWN.",
                "YTD_CM_SOURCE_NOT_AVAILABLE.",
            ),
        )
