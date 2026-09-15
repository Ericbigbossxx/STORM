"""Build the Phase 2B calibrated Walmart preview; no rules or writes are activated."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from storm.adapters.walmart_official import WalmartOfficialAdapter
from storm.cockpit.business_health import BusinessHealthAssembler
from storm.cockpit.feishu_dry_run import build_feishu_dry_run, render_preview_v2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--control-week", required=True)
    parser.add_argument("--source-config", default="config/walmart_official_source.yaml")
    parser.add_argument("--database", default="data/structured_metrics/storm_metrics.sqlite3")
    parser.add_argument("--feishu-schema", default="config/feishu_schema.yaml")
    parser.add_argument("--output-dir", default="data/cockpit/phase2b")
    args = parser.parse_args()

    walmart = WalmartOfficialAdapter(args.source_config).load()
    snapshot = BusinessHealthAssembler(args.database).assemble(
        walmart,
        control_week=args.control_week,
    )
    dry_run = build_feishu_dry_run(snapshot, args.feishu_schema)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "walmart_business_health_snapshot_v2.json").write_text(
        json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "walmart_cockpit_preview_v2.md").write_text(
        render_preview_v2(snapshot, dry_run),
        encoding="utf-8",
    )
    print(json.dumps({
        "status": "PHASE_2B_PREVIEW_BUILT",
        "control_week": snapshot.control_week,
        "rules_activated": False,
        "external_write_performed": False,
        "output_dir": str(output.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
