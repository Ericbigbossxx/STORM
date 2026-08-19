"""Validate-first orchestration for the official CM workbook import."""

from __future__ import annotations

from pathlib import Path

from storm.adapters.cm_workbook.adapter import CmWorkbookAdapter

from .store import StructuredMetricsStore


class StructuredMetricsImportService:
    def __init__(self, config_path: str | Path, database_path: str | Path | None = None):
        self.adapter = CmWorkbookAdapter(config_path)
        configured_path = self.adapter.config["database_path"]
        self.store = StructuredMetricsStore(database_path or configured_path)

    def import_workbook(
        self,
        workbook_path: str | Path,
        *,
        snapshot_date: str,
        data_through_date: str,
    ) -> dict[str, str | int]:
        plan = self.adapter.parse(workbook_path, snapshot_date=snapshot_date, data_through_date=data_through_date)
        return self.store.import_plan(plan)
