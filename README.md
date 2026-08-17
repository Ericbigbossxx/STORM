# STORM V2

Weekly Business Control / Review Dashboard for North America E-commerce.

STORM V2 analyzes the governed hierarchy:

`Platform → Channel/Subchannel → Brand → Power Source → SKU`

Supported operating channels are Walmart MP, Walmart DSV, THD DS, THD DFC, and Lowe's.

## Production-data policy

This repository contains code, contracts, configuration, and tests only. Real production Sales, CM, BP, DFC, inventory, weekly snapshots, workbooks, and credentials are intentionally excluded from GitHub. Keep approved production data in the local `data/` directories listed in `.gitignore`.

## Architecture

The local production workflow uses RAW Sales / DFC and CM / BP workbooks, weekly production intake, source-contract validation, immutable snapshot revisions, a latest pointer, reconciliation gates, WoW, and direct workbook-sourced YTD.

## Setup

Use Python 3.11+ and install the project plus web dependencies:

```bash
python -m pip install -e .
python -m pip install -r requirements-web.txt
```

Run the test suite:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

Tests that require approved local production workbooks or snapshots are explicitly skipped when those inputs are absent; pure logic and no-data bootstrap tests remain runnable from a fresh clone.

On Windows PowerShell:

```powershell
$env:PYTHONPATH = 'src;.'
```

## Dashboard

Launch the local dashboard with:

```bash
streamlit run app/app.py
```

Without a local published production snapshot, the dashboard intentionally shows `NO PRODUCTION DATA / DATA REQUIRED` instead of attempting to infer or generate data.

## Weekly production

Place exactly one compatible RAW Sales / DFC workbook and one compatible CM / BP workbook in `data/inbox/YYYY-WXX/`, then run:

```bash
python scripts/build_weekly_snapshot.py --week YYYY-WXX --inbox data/inbox/YYYY-WXX
```

The workflow validates source contracts and reconciliation gates before it publishes. Each successful rerun creates an immutable revision; only the local latest pointer changes. SHA-256 is recorded for traceability; compatibility and business controls decide publication.

Do not copy production data into this repository or commit it.
