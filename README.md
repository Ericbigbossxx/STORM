# STORM

**Strategic Tracking, Operations, Risks & Metrics** is the North America Business Control System.

STORM v0.1 is a Feishu-first Weekly Business Control MVP for US Walmart, THD, and Lowe's operations. Feishu is the live control ledger; this repository owns the schema contract, canonical dimensions, status rules, weekly workflow, and integration boundaries.

## v0.1 scope

- Four operational tables only: Business Health, Core SKU Performance, Action & Validation, and Signal Register.
- Management identity always separates market, platform, optional channel/program, product line, and SKU.
- Missing evidence remains blank or `UNKNOWN`; it is never inferred as `GREEN`.
- AI output is advisory. Human review and `Human Decision` remain authoritative.
- Platform, Feishu, and Hermes integrations are adapters outside the domain layer.

## Repository role

This repository is not a duplicate operational database. It does not contain Feishu credentials, live platform data, a Streamlit application, automated ingestion, or autonomous write-back.

## Development

The project uses a local `.venv` and project-owned `uv`. Focused validation:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

See `docs/architecture.md` and `docs/weekly_workflow.md` before extending the system.
