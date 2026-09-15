"""Build Phase 2F Managed SKU candidates and portable cockpit inputs; no live write."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from storm.cockpit.weekly_cockpit import (
    build_dashboard_artifact,
    build_phase2f_package,
    render_weekly_preview,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--phase2e-package",
        default="data/cockpit/phase2e/walmart_weekly_driver_package.json",
    )
    parser.add_argument(
        "--business-health-snapshot",
        default="data/cockpit/phase2c/walmart_business_health_snapshot_v3.json",
    )
    parser.add_argument("--feishu-schema", default="config/feishu_schema.yaml")
    parser.add_argument("--live-record-count", type=int, required=True)
    parser.add_argument("--output-dir", default="data/cockpit/phase2f")
    args = parser.parse_args()
    if args.live_record_count < 0:
        parser.error("--live-record-count must be non-negative")

    phase2e = json.loads(Path(args.phase2e_package).read_text(encoding="utf-8"))
    health = json.loads(Path(args.business_health_snapshot).read_text(encoding="utf-8"))
    package = build_phase2f_package(
        phase2e,
        health,
        args.feishu_schema,
        live_record_count=args.live_record_count,
    )
    artifact = build_dashboard_artifact(package)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "walmart_phase2f_control_package.json").write_text(
        json.dumps(package, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "walmart_weekly_cockpit_artifact.json").write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "walmart_weekly_cockpit_preview.md").write_text(
        render_weekly_preview(package),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "PHASE_2F_LOCAL_CANDIDATE_BUILT",
                "managed_sku_count": len(package["selection"]["managed_skus"]),
                "cockpit_driver_count": len(package["selection"]["cockpit_driver_skus"]),
                "candidate_count": package["feishu_candidate_set"]["candidate_count"],
                "external_write_performed": False,
                "output_dir": str(output.resolve()),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
