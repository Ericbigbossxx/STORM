from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from storm.adapters.walmart_official.adapter import (
    SourceValidationError,
    WalmartOfficialAdapter,
    dataframe_content_hash,
)


def _write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _source_fixture(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "wos"
    history = root / "data" / "history" / "marketplace"
    history.mkdir(parents=True)
    run = "RUN-OFFICIAL"
    frames = {
        "business_current_state": pd.DataFrame([
            {"period_scope": "MTD_OPERATING", "business_as_of_date": pd.Timestamp("2026-08-02"),
             "metric_scope": "BUSINESS_MTD", "net_sales": 10.0, "nullable_metric": None,
             "source_run_id": run}
        ]),
        "business_weekly_current_state": pd.DataFrame([
            {"period_scope": "WEEKLY_OPERATING", "business_as_of_date": pd.Timestamp("2026-07-26"),
             "metric_scope": "BUSINESS_WEEKLY", "net_sales": 8.0, "source_run_id": "RUN-PREV"},
            {"period_scope": "WEEKLY_OPERATING", "business_as_of_date": pd.Timestamp("2026-08-02"),
             "metric_scope": "BUSINESS_WEEKLY", "net_sales": 10.0, "source_run_id": run},
        ]),
        "sku_current_performance": pd.DataFrame([
            {"period_scope": "MTD_OPERATING", "business_as_of_date": pd.Timestamp("2026-08-02"),
             "sku": "A", "metric_scope": "SKU_MTD", "inventory_status": "In Stock",
             "source_run_id": run}
        ]),
        "snapshot_manifest": pd.DataFrame([
            {"snapshot_id": f"S-{index}", "snapshot_type": kind, "period_scope": "MTD_OPERATING",
             "business_as_of_date": pd.Timestamp("2026-08-02"), "snapshot_version": 1,
             "record_count": 1, "content_hash": "x", "source_run_id": run,
             "run_status": "SUCCESS", "official_result": "YES", "published_to_history": "YES",
             "superseded_flag": "NO"}
            for index, kind in enumerate(("BUSINESS_MTD", "BUSINESS_WEEKLY", "SKU_MTD"), start=1)
        ] + [
            {"snapshot_id": "S-PREV-WEEKLY", "snapshot_type": "BUSINESS_WEEKLY", "period_scope": "WEEKLY_OPERATING",
             "business_as_of_date": pd.Timestamp("2026-07-26"), "snapshot_version": 1,
             "record_count": 1, "content_hash": "previous", "source_run_id": "RUN-PREV",
             "run_status": "SUCCESS", "official_result": "YES", "published_to_history": "YES",
             "superseded_flag": "NO"}
        ]),
    }
    filenames = {
        "business_current_state": "business.parquet",
        "business_weekly_current_state": "weekly.parquet",
        "sku_current_performance": "sku.parquet",
        "snapshot_manifest": "manifest.parquet",
    }
    primary_keys = {
        "business_current_state": ["period_scope", "business_as_of_date", "metric_scope"],
        "business_weekly_current_state": ["period_scope", "business_as_of_date", "metric_scope"],
        "sku_current_performance": ["period_scope", "business_as_of_date", "sku", "metric_scope"],
        "snapshot_manifest": ["snapshot_id"],
    }
    schema_names = {
        "business_current_state": "business_snapshot",
        "business_weekly_current_state": "business_snapshot",
        "sku_current_performance": "sku_performance_snapshot",
        "snapshot_manifest": "snapshot_manifest",
    }
    returned_fields = {
        "business_current_state": ["period_scope", "business_as_of_date", "metric_scope", "net_sales", "nullable_metric", "source_run_id"],
        "business_weekly_current_state": ["period_scope", "business_as_of_date", "metric_scope", "net_sales", "source_run_id"],
        "sku_current_performance": ["period_scope", "business_as_of_date", "sku", "metric_scope", "inventory_status", "source_run_id"],
        "snapshot_manifest": list(frames["snapshot_manifest"].columns),
    }
    contract_datasets = []
    manifest_datasets = []
    for name, frame in frames.items():
        relative = f"data/history/marketplace/{filenames[name]}"
        frame.to_parquet(root / relative, index=False)
        latest = frame.loc[pd.to_datetime(frame["business_as_of_date"]).eq(pd.to_datetime(frame["business_as_of_date"]).max())].reset_index(drop=True)
        digest = dataframe_content_hash(latest, sort_by=primary_keys[name])
        contract_datasets.append({
            "dataset_name": name, "canonical_source": relative, "primary_key": primary_keys[name],
            "business_date_field": "business_as_of_date", "schema_version": "1.0.0",
        })
        manifest_datasets.append({
            "dataset_name": name, "canonical_source": relative, "schema_version": "1.0.0",
            "record_count": len(latest), "business_date": "2026-08-02", "readiness_status": "READY",
            "content_hash": digest,
        })
    _write_yaml(root / "config" / "backend_data_contract.yaml", {
        "contract_version": "1.1.0", "business_scope": "WALMART_MARKETPLACE_3P",
        "consumer_boundary": {"write_policy": "READ_ONLY"}, "datasets": contract_datasets,
    })
    _write_yaml(root / "config" / "backend_schema_versions.yaml", {"datasets": {
        "business_snapshot": {"schema_version": "1.0.0", "required_fields": ["business_as_of_date", "net_sales", "source_run_id"], "field_types": {"business_as_of_date": "date", "net_sales": "currency", "source_run_id": "text"}},
        "sku_performance_snapshot": {"schema_version": "1.0.0", "required_fields": ["business_as_of_date", "sku", "source_run_id"], "field_types": {"business_as_of_date": "date", "sku": "identifier_text"}},
        "snapshot_manifest": {"schema_version": "1.0.0", "required_fields": ["snapshot_id", "snapshot_type", "business_as_of_date", "run_status", "official_result", "published_to_history", "superseded_flag"], "field_types": {"business_as_of_date": "date", "snapshot_id": "identifier_text"}, "enum_fields": {"run_status": ["SUCCESS"], "official_result": ["YES"], "published_to_history": ["YES"], "superseded_flag": ["YES", "NO"]}},
    }})
    release = {
        "release_version": "1.1.1", "release_status": "READY_FOR_PHASE_3",
        "backend_contract_version": "1.1.0", "business_as_of_date": "2026-08-02",
        "official_run_id": run, "pipeline_status": "SUCCESS",
        "created_at_utc": "2026-08-04T00:00:00+00:00", "canonical_datasets": manifest_datasets,
    }
    release_path = root / "outputs" / "latest" / "backend_release_manifest.json"
    release_path.parent.mkdir(parents=True)
    release_path.write_text(json.dumps(release), encoding="utf-8")
    config = {
        "source_system": "Walmart Operation System", "business_scope": "WALMART_MARKETPLACE_3P",
        "root_path": str(root), "release_manifest": "outputs/latest/backend_release_manifest.json",
        "data_contract": "config/backend_data_contract.yaml", "schema_registry": "config/backend_schema_versions.yaml",
        "read_policy": "READ_ONLY", "expected_contract_version": "1.1.0",
        "expected_release_status": "READY_FOR_PHASE_3", "expected_pipeline_status": "SUCCESS",
        "allowed_dataset_roots": ["data/history/marketplace"],
        "forbidden_source_prefixes": ["data/raw", "data/processed", "tests/fixtures"],
        "platform_mapping": {"Marketplace 3P": "WALMART_MP"},
        "datasets": {
            name: {"schema_name": schema_names[name], "returned_fields": returned_fields[name],
                   **({"retain_official_history": True} if name in {"business_weekly_current_state", "snapshot_manifest"} else {})}
            for name in frames
        },
        "required_snapshot_types": ["BUSINESS_MTD", "BUSINESS_WEEKLY", "SKU_MTD"],
    }
    config_path = tmp_path / "source.yaml"
    _write_yaml(config_path, config)
    return config_path, release_path


def _mutate_release(path: Path, mutation) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutation(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_official_ingestion_mapping_null_and_lineage(tmp_path: Path) -> None:
    config_path, _ = _source_fixture(tmp_path)
    evidence = WalmartOfficialAdapter(config_path).load()
    assert evidence.platform == "WALMART_MP"
    assert evidence.official_run_id == "RUN-OFFICIAL"
    assert evidence.datasets["business_current_state"].records[0]["nullable_metric"] is None
    assert len(evidence.datasets["business_weekly_current_state"].history_records) == 2
    assert evidence.datasets["business_current_state"].source_release == "RUN-OFFICIAL"


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        (lambda release: release.update(release_status="NOT_READY"), "BACKEND_RELEASE_NOT_READY"),
        (lambda release: release["canonical_datasets"][0].update(readiness_status="BLOCKED"), "DATASET_NOT_READY"),
        (lambda release: release["canonical_datasets"][0].update(schema_version="2.0.0"), "SCHEMA_VERSION_MISMATCH"),
        (lambda release: release["canonical_datasets"][0].update(record_count=2), "RECORD_COUNT_MISMATCH"),
        (lambda release: release["canonical_datasets"][0].update(content_hash="bad"), "CONTENT_HASH_MISMATCH"),
    ],
)
def test_release_readiness_schema_and_hash_fail_safely(tmp_path: Path, mutation, error: str) -> None:
    config_path, release_path = _source_fixture(tmp_path)
    _mutate_release(release_path, mutation)
    with pytest.raises(SourceValidationError, match=error):
        WalmartOfficialAdapter(config_path).load()


def test_forbidden_source_is_rejected(tmp_path: Path) -> None:
    config_path, release_path = _source_fixture(tmp_path)
    contract_path = tmp_path / "wos" / "config" / "backend_data_contract.yaml"
    contract = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    contract["datasets"][0]["canonical_source"] = "data/raw/business.parquet"
    _write_yaml(contract_path, contract)
    _mutate_release(release_path, lambda release: release["canonical_datasets"][0].update(canonical_source="data/raw/business.parquet"))
    with pytest.raises(SourceValidationError, match="FORBIDDEN_SOURCE"):
        WalmartOfficialAdapter(config_path).load()


def test_duplicate_primary_key_is_rejected(tmp_path: Path) -> None:
    config_path, _ = _source_fixture(tmp_path)
    path = tmp_path / "wos" / "data" / "history" / "marketplace" / "business.parquet"
    frame = pd.read_parquet(path)
    pd.concat([frame, frame], ignore_index=True).to_parquet(path, index=False)
    with pytest.raises(SourceValidationError, match="DUPLICATE_PRIMARY_KEY"):
        WalmartOfficialAdapter(config_path).load()


def test_superseded_weekly_history_is_excluded_not_compared(tmp_path: Path) -> None:
    config_path, _ = _source_fixture(tmp_path)
    path = tmp_path / "wos" / "data" / "history" / "marketplace" / "manifest.parquet"
    frame = pd.read_parquet(path)
    frame.loc[frame["snapshot_id"].eq("S-PREV-WEEKLY"), "superseded_flag"] = "YES"
    frame.to_parquet(path, index=False)
    contract = yaml.safe_load((tmp_path / "wos" / "config" / "backend_data_contract.yaml").read_text(encoding="utf-8"))
    key = next(item["primary_key"] for item in contract["datasets"] if item["dataset_name"] == "snapshot_manifest")
    latest = frame.loc[pd.to_datetime(frame["business_as_of_date"]).eq(pd.Timestamp("2026-08-02"))].reset_index(drop=True)
    release_path = tmp_path / "wos" / "outputs" / "latest" / "backend_release_manifest.json"
    _mutate_release(
        release_path,
        lambda release: next(item for item in release["canonical_datasets"] if item["dataset_name"] == "snapshot_manifest").update(content_hash=dataframe_content_hash(latest, sort_by=key)),
    )
    evidence = WalmartOfficialAdapter(config_path).load()
    weekly = evidence.datasets["business_weekly_current_state"]
    assert len(weekly.history_records) == 1
    assert weekly.warnings[0].startswith("SUPERSEDED_OR_UNREGISTERED_WEEKLY_HISTORY_EXCLUDED")


def test_superseded_sku_release_is_excluded_from_retained_history(tmp_path: Path) -> None:
    config_path, _ = _source_fixture(tmp_path)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["datasets"]["sku_current_performance"]["retain_official_history"] = True
    _write_yaml(config_path, config)
    sku_path = tmp_path / "wos" / "data" / "history" / "marketplace" / "sku.parquet"
    sku = pd.read_parquet(sku_path)
    previous = sku.copy()
    previous["business_as_of_date"] = pd.Timestamp("2026-07-26")
    previous["source_run_id"] = "RUN-SKU-SUPERSEDED"
    pd.concat([previous, sku], ignore_index=True).to_parquet(sku_path, index=False)
    manifest_path = tmp_path / "wos" / "data" / "history" / "marketplace" / "manifest.parquet"
    manifest = pd.read_parquet(manifest_path)
    manifest = pd.concat(
        [
            manifest,
            pd.DataFrame(
                [
                    {
                        "snapshot_id": "S-PREV-SKU",
                        "snapshot_type": "SKU_MTD",
                        "period_scope": "MTD_OPERATING",
                        "business_as_of_date": pd.Timestamp("2026-07-26"),
                        "snapshot_version": 1,
                        "record_count": 1,
                        "content_hash": "previous-sku",
                        "source_run_id": "RUN-SKU-SUPERSEDED",
                        "run_status": "SUCCESS",
                        "official_result": "YES",
                        "published_to_history": "YES",
                        "superseded_flag": "YES",
                    }
                ]
            ),
        ],
        ignore_index=True,
    )
    manifest.to_parquet(manifest_path, index=False)
    evidence = WalmartOfficialAdapter(config_path).load()
    retained = evidence.datasets["sku_current_performance"]
    assert len(retained.history_records) == 1
    assert retained.history_records[0]["source_run_id"] == "RUN-OFFICIAL"
    assert retained.warnings[0].startswith("SUPERSEDED_OR_UNREGISTERED_SKU_MTD_HISTORY_EXCLUDED")
