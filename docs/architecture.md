# STORM v0.1 architecture

## Decision boundary

STORM v0.1 builds the business control layer, not a complete data platform. Feishu Bitable is the live operational ledger. The local repository owns stable contracts and integration boundaries; it does not mirror live Feishu records.

```text
Platform facts / manual evidence
              ↓
     Feishu Bitable ledger
              ↓
 Weekly review and human decision
```

## Dependency direction

```text
domain ← services ← adapters
```

The domain layer contains stable management concepts only. It must not import Feishu, Hermes, Walmart, THD, or Lowe's SDKs. External implementations translate their native payloads at the adapter boundary.

## Active v0.1 components

1. A new Feishu Base named `STORM | Business Control` with exactly four operational tables.
2. This repository's schema manifest, dimensions, rules, documentation, and port definitions.
3. A human-owned weekly review workflow.

## Reserved boundaries

- `src/storm/adapters/feishu/`: ledger port and future implementation.
- `src/storm/adapters/walmart/`, `thd/`, `lowes/`: future source adapters.
- `src/storm/adapters/hermes/`: advisory agent boundary only.
- `apps/dashboard/`: future Streamlit presentation boundary.

## Non-goals

No Streamlit application, full platform API integration, warehouse, scheduler, real-time notifications, autonomous write-back, forecasting engine, full catalog history, or multi-agent orchestration is part of v0.1.

## Authority and failure policy

AI suggestions never finalize operating status. Missing or stale evidence remains blank or `UNKNOWN`. External adapter failure cannot fabricate a current value or a green status. Human review is the final authority.
