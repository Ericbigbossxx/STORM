"""Build the Phase 2C Walmart control-plane snapshot and write candidate; never write records."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from storm.adapters.walmart_official import WalmartOfficialAdapter
from storm.cockpit.business_health import BusinessHealthAssembler
from storm.cockpit.feishu_dry_run import build_feishu_write_candidate, render_preview_v3
from storm.cockpit.rules import activate_rules_v1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--control-week", required=True)
    parser.add_argument("--source-config", default="config/walmart_official_source.yaml")
    parser.add_argument("--database", default="data/structured_metrics/storm_metrics.sqlite3")
    parser.add_argument("--feishu-schema", default="config/feishu_schema.yaml")
    parser.add_argument("--output-dir", default="data/cockpit/phase2c")
    parser.add_argument("--live-schema-validated", action="store_true")
    parser.add_argument("--live-record-lookup-performed", action="store_true")
    args = parser.parse_args()

    walmart = WalmartOfficialAdapter(args.source_config).load()
    base_snapshot = BusinessHealthAssembler(args.database).assemble(
        walmart,
        control_week=args.control_week,
    )
    snapshot = activate_rules_v1(base_snapshot)
    candidate = build_feishu_write_candidate(
        snapshot,
        args.feishu_schema,
        live_schema_validated=args.live_schema_validated,
        live_record_lookup_performed=args.live_record_lookup_performed,
    )
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "walmart_business_health_snapshot_v3.json").write_text(
        json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "walmart_feishu_live_write_candidate.json").write_text(
        json.dumps(candidate.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "walmart_feishu_mapping_review.json").write_text(
        json.dumps(candidate.mapping_review, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "walmart_cockpit_preview_v3.md").write_text(
        render_preview_v3(snapshot, candidate),
        encoding="utf-8",
    )
    print(json.dumps({
        "status": "PHASE_2C_CANDIDATE_BUILT",
        "control_week": snapshot.control_week,
        "overall_health": snapshot.interpretation["overall_status"],
        "data_confidence": snapshot.interpretation["data_confidence"],
        "schema_validation_basis": candidate.validation["schema_validation_basis"],
        "record_api_invoked": False,
        "external_record_write_performed": False,
        "output_dir": str(output.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
