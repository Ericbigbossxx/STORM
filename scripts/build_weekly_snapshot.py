"""Single entry point for a contract-gated STORM weekly production run."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from storm_v2.weekly_production import run_weekly_production


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week", required=True, help="ISO week, for example 2026-W34")
    parser.add_argument("--inbox", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    result = run_weekly_production(args.project_root, args.week, args.inbox)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result["status"] != "FAILED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
