"""Manifest-first, read-only access to a narrow Walmart official evidence slice."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd
import yaml


VOLATILE_CONTENT_FIELDS = {
    "generated_at_utc",
    "run_id",
    "run_time",
    "actual_start_time",
    "file_mtime",
    "temporary_path",
    "temp_path",
}


class SourceValidationError(RuntimeError):
    """Raised when official-source evidence fails a blocking contract gate."""


@dataclass(frozen=True, slots=True)
class DatasetEvidence:
    dataset_name: str
    source_artifact: str
    source_release: str
    schema_version: str
    business_date: str
    readiness_status: str
    record_count: int
    content_hash: str
    records: tuple[dict[str, Any], ...]
    history_records: tuple[dict[str, Any], ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class WalmartOfficialEvidence:
    source_system: str
    source_scope: str
    platform: str
    official_run_id: str
    release_version: str
    contract_version: str
    business_as_of_date: str
    generated_at_utc: str
    release_manifest: str
    datasets: Mapping[str, DatasetEvidence]


def dataframe_content_hash(
    frame: pd.DataFrame,
    *,
    exclude_fields: Iterable[str] = VOLATILE_CONTENT_FIELDS,
    sort_by: Iterable[str] | None = None,
) -> str:
    """Match the producing system's governed DataFrame content-hash algorithm."""

    excluded = set(exclude_fields)
    stable = frame.drop(
        columns=[column for column in frame.columns if column in excluded],
        errors="ignore",
    ).copy()
    if sort_by:
        keys = [key for key in sort_by if key in stable]
        if keys:
            stable = stable.sort_values(keys, kind="stable")
    else:
        stable = stable.sort_index(axis=1)
    for column in stable.columns:
        if pd.api.types.is_datetime64_any_dtype(stable[column]):
            stable[column] = pd.to_datetime(stable[column], errors="coerce").dt.strftime(
                "%Y-%m-%d"
            )
    payload = stable.reset_index(drop=True).to_json(
        orient="records",
        date_format="iso",
        default_handler=str,
        force_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SourceValidationError(f"YAML_OBJECT_REQUIRED: {path}")
    return payload


def _latest_official(frame: pd.DataFrame) -> pd.DataFrame:
    current = frame.copy()
    if "superseded_flag" in current:
        current = current.loc[current["superseded_flag"].astype(str).eq("NO")]
    if "business_as_of_date" in current and not current.empty:
        dates = pd.to_datetime(current["business_as_of_date"], errors="coerce").dt.normalize()
        if dates.isna().all():
            raise SourceValidationError("BUSINESS_DATE_INVALID")
        current = current.loc[dates.eq(dates.max())]
    return current.reset_index(drop=True)


def _normalize_scalar(value: Any) -> Any:
    if value is None or value is pd.NA:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return value


def _records(frame: pd.DataFrame, fields: list[str]) -> tuple[dict[str, Any], ...]:
    missing = [field for field in fields if field not in frame]
    if missing:
        raise SourceValidationError(f"RETURN_FIELD_MISSING: {', '.join(missing)}")
    return tuple(
        {field: _normalize_scalar(value) for field, value in row.items()}
        for row in frame[fields].to_dict(orient="records")
    )


def _validate_primary_key(frame: pd.DataFrame, fields: tuple[str, ...], dataset: str) -> None:
    missing = [field for field in fields if field not in frame]
    if missing:
        raise SourceValidationError(
            f"PRIMARY_KEY_FIELD_MISSING: {dataset}: {', '.join(missing)}"
        )
    if bool(frame[list(fields)].isna().any(axis=1).any()):
        raise SourceValidationError(f"BLANK_PRIMARY_KEY: {dataset}")
    if bool(frame.duplicated(list(fields)).any()):
        raise SourceValidationError(f"DUPLICATE_PRIMARY_KEY: {dataset}")


def _type_ok(series: pd.Series, expected: str) -> bool:
    values = series.dropna()
    if expected in {"text", "identifier_text"}:
        return bool(values.map(lambda value: isinstance(value, str)).all())
    if expected in {"currency", "ratio", "ratio_decimal", "number", "integer"}:
        numeric = pd.to_numeric(values, errors="coerce")
        if not bool(numeric.notna().all()):
            return False
        return expected != "integer" or bool(((numeric % 1) == 0).all())
    if expected in {"date", "datetime"}:
        return bool(pd.to_datetime(values, errors="coerce").notna().all())
    return True


def _validate_schema(frame: pd.DataFrame, schema: Mapping[str, Any], dataset: str) -> None:
    missing = [field for field in schema.get("required_fields", []) if field not in frame]
    if missing:
        raise SourceValidationError(
            f"SCHEMA_REQUIRED_FIELD_MISSING: {dataset}: {', '.join(missing)}"
        )
    for field, expected in schema.get("field_types", {}).items():
        if field in frame and not _type_ok(frame[field], str(expected)):
            raise SourceValidationError(f"SCHEMA_FIELD_TYPE_INVALID: {dataset}: {field}")
    for field, allowed in schema.get("enum_fields", {}).items():
        if field not in frame:
            continue
        invalid = set(frame[field].dropna().astype(str)) - {str(value) for value in allowed}
        if invalid:
            raise SourceValidationError(
                f"SCHEMA_ENUM_INVALID: {dataset}: {field}: {sorted(invalid)}"
            )


class WalmartOfficialAdapter:
    """Validate and return only the approved Walmart cockpit evidence."""

    def __init__(self, config_path: str | Path):
        self.config_path = Path(config_path).resolve()
        self.config = _load_yaml(self.config_path)
        if self.config.get("read_policy") != "READ_ONLY":
            raise SourceValidationError("READ_ONLY_POLICY_REQUIRED")
        self.root = Path(str(self.config["root_path"])).resolve()

    def _resolved(self, relative: str, *, dataset: bool = False) -> Path:
        path_value = Path(relative)
        if path_value.is_absolute():
            raise SourceValidationError(f"ABSOLUTE_SOURCE_FORBIDDEN: {relative}")
        candidate = (self.root / path_value).resolve()
        try:
            normalized = candidate.relative_to(self.root).as_posix()
        except ValueError as error:
            raise SourceValidationError(f"SOURCE_OUTSIDE_ROOT: {relative}") from error
        if dataset:
            forbidden = tuple(str(value).rstrip("/") for value in self.config["forbidden_source_prefixes"])
            if any(normalized == prefix or normalized.startswith(prefix + "/") for prefix in forbidden):
                raise SourceValidationError(f"FORBIDDEN_SOURCE: {normalized}")
            allowed = tuple(str(value).rstrip("/") for value in self.config["allowed_dataset_roots"])
            if not any(normalized == prefix or normalized.startswith(prefix + "/") for prefix in allowed):
                raise SourceValidationError(f"SOURCE_ROOT_NOT_ALLOWED: {normalized}")
        return candidate

    @staticmethod
    def _contract_datasets(contract: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
        return {str(item["dataset_name"]): item for item in contract.get("datasets", [])}

    def _load_dataset(
        self,
        name: str,
        manifest: Mapping[str, Any],
        contract: Mapping[str, Any],
        schema_registry: Mapping[str, Any],
    ) -> DatasetEvidence:
        requested = self.config["datasets"][name]
        manifest_matches = [
            item for item in manifest["canonical_datasets"] if item.get("dataset_name") == name
        ]
        if len(manifest_matches) != 1:
            raise SourceValidationError(f"BACKEND_MANIFEST_DATASET_INVALID: {name}")
        manifest_row = manifest_matches[0]
        contract_spec = self._contract_datasets(contract).get(name)
        if contract_spec is None:
            raise SourceValidationError(f"BACKEND_CONTRACT_DATASET_MISSING: {name}")
        if manifest_row.get("readiness_status") != "READY":
            raise SourceValidationError(f"DATASET_NOT_READY: {name}")
        expected_version = str(contract_spec["schema_version"])
        if str(manifest_row.get("schema_version")) != expected_version:
            raise SourceValidationError(f"SCHEMA_VERSION_MISMATCH: {name}")
        schema_name = str(requested["schema_name"])
        schema = schema_registry.get("datasets", {}).get(schema_name)
        if not isinstance(schema, dict) or str(schema.get("schema_version")) != expected_version:
            raise SourceValidationError(f"SCHEMA_REGISTRY_VERSION_MISMATCH: {name}")
        canonical = contract_spec.get("canonical_source")
        if not isinstance(canonical, str) or canonical != manifest_row.get("canonical_source"):
            raise SourceValidationError(f"CANONICAL_SOURCE_MISMATCH: {name}")
        path = self._resolved(canonical, dataset=True)
        if not path.is_file():
            raise SourceValidationError(f"CANONICAL_DATASET_MISSING: {canonical}")
        frame = pd.read_parquet(path)
        latest = _latest_official(frame)
        primary_key = tuple(str(value) for value in contract_spec["primary_key"])
        _validate_primary_key(latest, primary_key, name)
        _validate_schema(latest, schema, name)
        if len(latest) != int(manifest_row["record_count"]):
            raise SourceValidationError(f"RECORD_COUNT_MISMATCH: {name}")
        business_dates = pd.to_datetime(latest[contract_spec["business_date_field"]]).dt.strftime(
            "%Y-%m-%d"
        )
        if set(business_dates) != {str(manifest_row["business_date"])}:
            raise SourceValidationError(f"BUSINESS_DATE_MISMATCH: {name}")
        computed_hash = dataframe_content_hash(latest, sort_by=primary_key)
        if computed_hash.lower() != str(manifest_row["content_hash"]).lower():
            raise SourceValidationError(f"CONTENT_HASH_MISMATCH: {name}")
        run_id = str(manifest["official_run_id"])
        if "source_run_id" in latest and set(latest["source_run_id"].astype(str)) != {run_id}:
            raise SourceValidationError(f"OFFICIAL_RUN_LINEAGE_MISMATCH: {name}")
        fields = [str(value) for value in requested["returned_fields"]]
        history_records: tuple[dict[str, Any], ...] = ()
        if requested.get("retain_official_history"):
            official_history = frame.copy()
            if "superseded_flag" in official_history:
                official_history = official_history.loc[
                    official_history["superseded_flag"].astype(str).eq("NO")
                ]
            _validate_primary_key(official_history, primary_key, name + "_history")
            history_records = _records(
                official_history.sort_values(contract_spec["business_date_field"], kind="stable"),
                fields,
            )
        return DatasetEvidence(
            dataset_name=name,
            source_artifact=canonical,
            source_release=run_id,
            schema_version=expected_version,
            business_date=str(manifest_row["business_date"]),
            readiness_status=str(manifest_row["readiness_status"]),
            record_count=len(latest),
            content_hash=computed_hash,
            records=_records(latest, fields),
            history_records=history_records,
        )

    @staticmethod
    def _official_snapshot_match(
        snapshot_history: Iterable[Mapping[str, Any]],
        *,
        snapshot_type: str,
        business_date: str,
        source_run_id: str,
    ) -> list[Mapping[str, Any]]:
        return [
            row
            for row in snapshot_history
            if str(row["snapshot_type"]) == snapshot_type
            and str(row["business_as_of_date"])[:10] == business_date[:10]
            and str(row["source_run_id"]) == source_run_id
            and row["run_status"] == "SUCCESS"
            and row["official_result"] == "YES"
            and row["published_to_history"] == "YES"
            and row["superseded_flag"] == "NO"
        ]

    def _load_auxiliary_dataset(
        self,
        name: str,
        requested: Mapping[str, Any],
        snapshot_history: tuple[dict[str, Any], ...],
        official_run_id: str,
    ) -> DatasetEvidence:
        canonical = str(requested["canonical_source"])
        path = self._resolved(canonical, dataset=True)
        if not path.is_file():
            raise SourceValidationError(f"AUXILIARY_DATASET_MISSING: {name}")
        frame = pd.read_parquet(path)
        primary_key = tuple(str(value) for value in requested["primary_key"])
        required = set(primary_key) | {
            "source_run_id",
            "snapshot_content_hash",
            "business_as_of_date",
        }
        missing = sorted(required - set(frame.columns))
        if missing:
            raise SourceValidationError(
                f"AUXILIARY_FIELD_MISSING: {name}: {', '.join(missing)}"
            )
        verified_groups: list[pd.DataFrame] = []
        warnings: list[str] = []
        snapshot_type = str(requested["snapshot_type"])
        for (business_date, source_run_id), group in frame.groupby(
            ["business_as_of_date", "source_run_id"], dropna=False, sort=True
        ):
            date_text = pd.Timestamp(business_date).strftime("%Y-%m-%d")
            run_text = str(source_run_id)
            matches = self._official_snapshot_match(
                snapshot_history,
                snapshot_type=snapshot_type,
                business_date=date_text,
                source_run_id=run_text,
            )
            if len(matches) != 1:
                warnings.append(
                    f"SUPERSEDED_OR_UNREGISTERED_{snapshot_type}_HISTORY_EXCLUDED: "
                    f"{date_text}: {run_text}"
                )
                continue
            manifest_row = matches[0]
            if len(group) != int(manifest_row["record_count"]):
                raise SourceValidationError(
                    f"AUXILIARY_RECORD_COUNT_MISMATCH: {name}: {date_text}"
                )
            row_hashes = set(group["snapshot_content_hash"].dropna().astype(str))
            if row_hashes != {str(manifest_row["content_hash"])}:
                raise SourceValidationError(
                    f"AUXILIARY_SNAPSHOT_HASH_MISMATCH: {name}: {date_text}"
                )
            verified_groups.append(group.copy())
        if not verified_groups:
            raise SourceValidationError(f"NO_OFFICIAL_AUXILIARY_HISTORY: {name}")
        verified = pd.concat(verified_groups, ignore_index=True)
        _validate_primary_key(verified, primary_key, name + "_history")
        dates = pd.to_datetime(verified["business_as_of_date"], errors="coerce")
        latest = verified.loc[dates.eq(dates.max())].reset_index(drop=True)
        if set(latest["source_run_id"].astype(str)) != {official_run_id}:
            raise SourceValidationError(f"AUXILIARY_CURRENT_RUN_MISMATCH: {name}")
        fields = [str(value) for value in requested["returned_fields"]]
        latest_date = pd.Timestamp(latest["business_as_of_date"].iloc[0]).strftime(
            "%Y-%m-%d"
        )
        latest_manifest = self._official_snapshot_match(
            snapshot_history,
            snapshot_type=snapshot_type,
            business_date=latest_date,
            source_run_id=official_run_id,
        )[0]
        return DatasetEvidence(
            dataset_name=name,
            source_artifact=canonical,
            source_release=official_run_id,
            schema_version=str(requested["schema_version"]),
            business_date=latest_date,
            readiness_status="READY",
            record_count=len(latest),
            content_hash=str(latest_manifest["content_hash"]),
            records=_records(latest, fields),
            history_records=_records(
                verified.sort_values(["business_as_of_date", "sku"], kind="stable"),
                fields,
            ),
            warnings=tuple(warnings),
        )

    def _load_reference_dataset(
        self,
        name: str,
        requested: Mapping[str, Any],
        manifest: Mapping[str, Any],
    ) -> DatasetEvidence:
        canonical = str(requested["canonical_source"])
        path = self._resolved(canonical)
        if not path.is_file():
            raise SourceValidationError(f"REFERENCE_DATASET_MISSING: {name}")
        expected_hash = manifest.get("protected_files_hashes", {}).get(
            str(requested["manifest_hash_key"])
        )
        if not expected_hash:
            raise SourceValidationError(f"REFERENCE_HASH_MISSING: {name}")
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_hash.lower() != str(expected_hash).lower():
            raise SourceValidationError(f"REFERENCE_HASH_MISMATCH: {name}")
        frame = pd.read_excel(path, sheet_name=str(requested["sheet_name"]))
        for field, value in requested.get("filters", {}).items():
            if field not in frame:
                raise SourceValidationError(f"REFERENCE_FILTER_FIELD_MISSING: {name}: {field}")
            frame = frame.loc[frame[field].astype(str).eq(str(value))]
        frame = frame.reset_index(drop=True)
        primary_key = tuple(str(value) for value in requested["primary_key"])
        _validate_primary_key(frame, primary_key, name)
        fields = [str(value) for value in requested["returned_fields"]]
        records = _records(frame.sort_values(list(primary_key), kind="stable"), fields)
        return DatasetEvidence(
            dataset_name=name,
            source_artifact=canonical,
            source_release=str(manifest["official_run_id"]),
            schema_version=str(requested["schema_version"]),
            business_date=str(manifest["business_as_of_date"]),
            readiness_status="READY",
            record_count=len(frame),
            content_hash=actual_hash,
            records=records,
        )

    def load(self) -> WalmartOfficialEvidence:
        release_path = self._resolved(str(self.config["release_manifest"]))
        contract_path = self._resolved(str(self.config["data_contract"]))
        schema_path = self._resolved(str(self.config["schema_registry"]))
        if not release_path.is_file():
            raise SourceValidationError("BACKEND_RELEASE_MANIFEST_MISSING")
        manifest = json.loads(release_path.read_text(encoding="utf-8"))
        contract = _load_yaml(contract_path)
        schema_registry = _load_yaml(schema_path)
        if manifest.get("release_status") != self.config["expected_release_status"]:
            raise SourceValidationError("BACKEND_RELEASE_NOT_READY")
        if manifest.get("pipeline_status") != self.config["expected_pipeline_status"]:
            raise SourceValidationError("BACKEND_PIPELINE_NOT_SUCCESS")
        expected_contract = str(self.config["expected_contract_version"])
        if (
            str(manifest.get("backend_contract_version")) != expected_contract
            or str(contract.get("contract_version")) != expected_contract
        ):
            raise SourceValidationError("BACKEND_CONTRACT_VERSION_MISMATCH")
        if contract.get("business_scope") != self.config["business_scope"]:
            raise SourceValidationError("BACKEND_BUSINESS_SCOPE_MISMATCH")
        if contract.get("consumer_boundary", {}).get("write_policy") != "READ_ONLY":
            raise SourceValidationError("BACKEND_WRITE_POLICY_INVALID")
        mapping = self.config.get("platform_mapping", {})
        if mapping.get("Marketplace 3P") != "WALMART_MP":
            raise SourceValidationError("PLATFORM_MAPPING_INVALID")
        datasets = {
            name: self._load_dataset(name, manifest, contract, schema_registry)
            for name in self.config["datasets"]
        }
        snapshot_rows = datasets["snapshot_manifest"].records
        required_types = set(map(str, self.config["required_snapshot_types"]))
        available_types = {str(row["snapshot_type"]) for row in snapshot_rows}
        if not required_types.issubset(available_types):
            raise SourceValidationError("REQUIRED_OFFICIAL_SNAPSHOT_MISSING")
        for row in snapshot_rows:
            if (
                row["run_status"] != "SUCCESS"
                or row["official_result"] != "YES"
                or row["published_to_history"] != "YES"
                or row["superseded_flag"] != "NO"
            ):
                raise SourceValidationError("SNAPSHOT_MANIFEST_NOT_OFFICIAL")
        snapshot_history = datasets["snapshot_manifest"].history_records
        verified_weekly_history: list[dict[str, Any]] = []
        weekly_history_warnings: list[str] = []
        for weekly_row in datasets["business_weekly_current_state"].history_records:
            weekly_date = str(weekly_row["business_as_of_date"])[:10]
            weekly_run = str(weekly_row["source_run_id"])
            matches = self._official_snapshot_match(
                snapshot_history,
                snapshot_type="BUSINESS_WEEKLY",
                business_date=weekly_date,
                source_run_id=weekly_run,
            )
            if len(matches) == 1:
                verified_weekly_history.append(weekly_row)
            else:
                weekly_history_warnings.append(
                    f"SUPERSEDED_OR_UNREGISTERED_WEEKLY_HISTORY_EXCLUDED: {weekly_date}: {weekly_run}"
                )
        if not any(
            str(row["business_as_of_date"])[:10]
            == datasets["business_weekly_current_state"].business_date
            for row in verified_weekly_history
        ):
            raise SourceValidationError("CURRENT_WEEKLY_SNAPSHOT_NOT_OFFICIAL")
        datasets = dict(datasets)
        datasets["business_weekly_current_state"] = replace(
            datasets["business_weekly_current_state"],
            history_records=tuple(verified_weekly_history),
            warnings=tuple(weekly_history_warnings),
        )
        if self.config["datasets"]["sku_current_performance"].get(
            "retain_official_history"
        ):
            verified_sku_history: list[dict[str, Any]] = []
            sku_history_warnings: list[str] = []
            for sku_row in datasets["sku_current_performance"].history_records:
                sku_date = str(sku_row["business_as_of_date"])[:10]
                sku_run = str(sku_row["source_run_id"])
                if self._official_snapshot_match(
                    snapshot_history,
                    snapshot_type="SKU_MTD",
                    business_date=sku_date,
                    source_run_id=sku_run,
                ):
                    verified_sku_history.append(sku_row)
                else:
                    sku_history_warnings.append(
                        f"SUPERSEDED_OR_UNREGISTERED_SKU_MTD_HISTORY_EXCLUDED: "
                        f"{sku_date}: {sku_run}"
                    )
            if not any(
                str(row["business_as_of_date"])[:10]
                == datasets["sku_current_performance"].business_date
                for row in verified_sku_history
            ):
                raise SourceValidationError("CURRENT_SKU_MTD_SNAPSHOT_NOT_OFFICIAL")
            datasets["sku_current_performance"] = replace(
                datasets["sku_current_performance"],
                history_records=tuple(verified_sku_history),
                warnings=tuple(sku_history_warnings),
            )
        for name, requested in self.config.get("auxiliary_datasets", {}).items():
            datasets[str(name)] = self._load_auxiliary_dataset(
                str(name), requested, snapshot_history, str(manifest["official_run_id"])
            )
        for name, requested in self.config.get("reference_datasets", {}).items():
            datasets[str(name)] = self._load_reference_dataset(
                str(name), requested, manifest
            )
        return WalmartOfficialEvidence(
            source_system=str(self.config["source_system"]),
            source_scope=str(self.config["business_scope"]),
            platform="WALMART_MP",
            official_run_id=str(manifest["official_run_id"]),
            release_version=str(manifest["release_version"]),
            contract_version=expected_contract,
            business_as_of_date=str(manifest["business_as_of_date"]),
            generated_at_utc=str(manifest["created_at_utc"]),
            release_manifest=release_path.relative_to(self.root).as_posix(),
            datasets=datasets,
        )
