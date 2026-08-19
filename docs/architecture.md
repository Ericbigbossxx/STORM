# STORM v0.1.1 architecture

## Product goal

STORM is the North America E-commerce Business Cockpit / Weekly Business Control System.
Structured Metrics is only its measurement foundation. STORM does not replace platform-owned
pipelines, become a general finance warehouse, or recalculate every source report.

## Decision boundary

STORM v0.1.1 builds the business control layer, not a complete data platform. Feishu Bitable is the live operational ledger. The local repository owns stable contracts and integration boundaries; it does not mirror live Feishu records.

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

## Active v0.1.1 components

1. A new Feishu Base named `STORM | Business Control` with exactly four operational tables.
2. This repository's schema manifest, dimensions, rules, documentation, and port definitions.
3. A human-owned weekly review workflow.

## Phase 1 structured-metrics boundary

The approved local metrics path is additive and does not change the Feishu ledger:

```text
official CM workbook (read-only, cached values)
                    ↓
        CM workbook adapter
                    ↓ validate + reconcile
        local SQLite fact layer
                    ↓ future read-only use
        aggregation / review / presentation
```

`src/storm/structured_metrics/` owns the local schema, immutable import batches,
exceptions, validation, and transactional persistence. `src/storm/adapters/cm_workbook/`
owns workbook-specific sheet, row, column, and display-value translation. Domain models
remain free of workbook and platform-specific logic. Phase 1 does not write to Feishu,
schedule imports, notify users, or implement a dashboard.

## Reserved boundaries

- `src/storm/adapters/feishu/`: ledger port and future implementation.
- `src/storm/adapters/walmart/`, `thd/`, `lowes/`: future source adapters.
- `src/storm/adapters/hermes/`: advisory agent boundary only.
- `apps/dashboard/`: future Streamlit presentation boundary.

## Non-goals

No Streamlit application, full platform API integration, warehouse, scheduler, real-time notifications, autonomous write-back, forecasting engine, full catalog history, or multi-agent orchestration is part of v0.1.1.

## Authority and failure policy

AI suggestions never finalize operating status. Missing or stale evidence remains blank or `UNKNOWN`. External adapter failure cannot fabricate a current value or a green status. Human review is the final authority.
