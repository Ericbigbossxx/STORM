"""Build Phase 2E Walmart Core SKU facts and candidates; never write Feishu records."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from storm.adapters.walmart_official import WalmartOfficialAdapter
from storm.cockpit.core_sku import build_walmart_core_sku_package, render_core_sku_preview


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--control-week", required=True)
    parser.add_argument("--source-config", default="config/walmart_official_source.yaml")
    parser.add_argument("--database", default="data/structured_metrics/storm_metrics.sqlite3")
    parser.add_argument("--feishu-schema", default="config/feishu_schema.yaml")
    parser.add_argument(
        "--business-health-snapshot",
        default="data/cockpit/phase2c/walmart_business_health_snapshot_v3.json",
    )
    parser.add_argument("--output-dir", default="data/cockpit/phase2e")
    parser.add_argument("--live-schema-validated", action="store_true")
    parser.add_argument("--live-record-count", type=int)
    args = parser.parse_args()
    if not args.live_schema_validated:
        parser.error("--live-schema-validated is required for a supervised-write candidate")
    if args.live_record_count is None or args.live_record_count < 0:
        parser.error("--live-record-count must be a non-negative result of the live read lookup")

    evidence = WalmartOfficialAdapter(args.source_config).load()
    platform_health_snapshot = json.loads(
        Path(args.business_health_snapshot).read_text(encoding="utf-8")
    )
    package = build_walmart_core_sku_package(
        evidence,
        args.database,
        args.feishu_schema,
        control_week=args.control_week,
        live_record_count=args.live_record_count,
        platform_health_snapshot=platform_health_snapshot,
    )
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "walmart_weekly_driver_package.json").write_text(
        json.dumps(package, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "walmart_weekly_driver_preview.md").write_text(
        render_core_sku_preview(package),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "PHASE_2E_PACKAGE_BUILT",
                "control_week": package["control_week"],
                "eligible_sku_fact_count": package["eligible_sku_fact_count"],
                "candidate_count": package["feishu_candidate_set"]["candidate_count"],
                "candidate_validation": package["feishu_candidate_set"]["validation_status"],
                "external_write_performed": False,
                "output_dir": str(output.resolve()),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
