# STORM v0.1 — Weekly Business Control MVP
## Build Specification for Codex

**Project name:** STORM
**Expansion:** Strategic Tracking, Operations, Risks & Metrics
**Primary purpose:** North America Business Control System
**Phase 1 scope:** Solve weekly business review for Walmart, THD, and Lowe's using Feishu Bitable as the operational control ledger.
**Future direction:** Streamlit executive dashboard, automated data adapters, daily exception monitoring, Hermes agent workers, and later orchestration.

## 0. Operating principles

1. Build the control layer first, not a full data platform.
2. Feishu is the v0.1 live operational ledger; the local repository stores the schema contract, rules, documentation, and future adapters.
3. Do not force platform metrics into false uniformity. Unify management dimensions, while allowing platform-specific metrics to remain sparse.
4. Do not modify any existing project, global Codex config, Hermes installation, or existing Feishu Base.
5. Create everything under the new STORM project root and a new STORM Feishu Base.
6. Keep the runtime isolated. No global package installs.
7. Design extension points now, but do not implement future systems prematurely.
8. Current supported operating scope: US / Walmart / THD / Lowe's.
9. Future-ready dimensions must distinguish Market, Platform, Channel/Program, Product Line, and SKU.
10. Human decision remains authoritative. AI analysis is advisory and must preserve evidence/provenance.

## 1. Project root and environment

Create a new standalone project:

```text
C:\Users\admin\Documents\STORM
```

If that path already exists and is non-empty, do not overwrite it. Report the conflict.

Use an isolated Python environment owned by this project only. Prefer `uv` and a local `.venv`. Do not reuse the Hermes venv.

Minimum project tree:

```text
STORM/
├─ README.md
├─ AGENTS.md
├─ pyproject.toml
├─ uv.lock
├─ .gitignore
├─ .env.example
├─ config/
│  ├─ storm.yaml
│  ├─ dimensions.yaml
│  ├─ rules.yaml
│  └─ feishu_schema.yaml
├─ docs/
│  ├─ architecture.md
│  ├─ data_contract.md
│  ├─ feishu_design.md
│  ├─ weekly_workflow.md
│  ├─ hermes_contract.md
│  └─ decisions/
│     └─ 0001-feishu-first.md
├─ src/
│  └─ storm/
│     ├─ __init__.py
│     ├─ domain/
│     │  ├─ models.py
│     │  ├─ enums.py
│     │  └─ ids.py
│     ├─ adapters/
│     │  ├─ feishu/
│     │  ├─ walmart/
│     │  ├─ thd/
│     │  ├─ lowes/
│     │  └─ hermes/
│     ├─ services/
│     │  ├─ weekly/
│     │  ├─ validation/
│     │  └─ triage/
│     ├─ rules/
│     └─ cli.py
├─ apps/
│  └─ dashboard/
│     └─ README.md
├─ data/
│  ├─ inbox/
│  ├─ staging/
│  └─ snapshots/
├─ logs/
├─ scripts/
└─ tests/
```

Keep `data/`, `logs/`, secrets, caches, `.venv`, and local exports out of git.

## 2. Architecture boundary

STORM v0.1 has two active pieces:

```text
Feishu Bitable
    ↓
STORM Control Ledger
    ↓
Weekly Review / Human Decision
```

The local repository is the schema + rules + future integration contract, not a duplicate live database.

Reserve these future interfaces without implementing them now:

```text
Platform data adapters
  walmart/
  thd/
  lowes/

Agent adapter
  hermes/

Presentation
  apps/dashboard/   # future Streamlit

Automation
  daily watch / scheduled ingestion  # future
```

No Streamlit app, data warehouse, autonomous platform write-back, or multi-agent orchestration in v0.1.

## 3. Canonical dimensions

Never use `platform` as the only identity field.

Canonical dimensions:
- `market` — initial `US`; future CA/MX/etc.
- `platform` — Walmart / THD / Lowe's / Cross-platform
- `channel` — optional; examples: 3P, WFS, 1P, DSV, Drop Ship, Online
- `product_line` — Robot / OPE / Accessories / Other
- `sku`
- `week_id` — ISO-like `YYYY-Www`
- `data_as_of`
- `source_type`
- `source_ref`

Create `config/dimensions.yaml` as the registry. Do not hard-code future market/platform logic inside application code.

Initial registry should support:

```yaml
markets:
  - US

platforms:
  - id: walmart
    name: Walmart
  - id: thd
    name: THD
  - id: lowes
    name: Lowe's
  - id: cross_platform
    name: Cross-platform

channels:
  walmart:
    - 3P
    - WFS
    - 1P
    - DSV
  thd:
    - Online
  lowes:
    - Drop Ship
```

Do not assume every record has a channel.

## 4. Feishu Base

Create a new Feishu Bitable/Base:

**`STORM | Business Control`**

Do not modify any existing Base.

Create exactly four operational tables in v0.1:
1. `01 Business Health`
2. `02 Core SKU Performance`
3. `03 Action & Validation`
4. `04 Signal Register`

Do not create a fifth Project table yet. Reserve project support in local domain/config for a later version.

Every table must have:
- immutable STORM ID
- week
- market
- platform
- optional channel
- data/evidence provenance where applicable
- created/updated timestamps if Feishu supports them

Use English field names for machine stability and short Chinese view names if useful for presentation.

## 5. Table 01 — Business Health

**Grain:** one record per `week × market × platform × optional channel aggregate`.

Fields:
- `Health ID`
- `Week`
- `Market`
- `Platform`
- `Channel`
- `Overall Health`
- `Sales Health`
- `Ads Health`
- `Inventory Health`
- `Buyability Health`
- `Listing Health`
- `Fulfillment Health`
- `Review Health`
- `Project Health`
- `Weekly Summary`
- `Top Change`
- `Top Risk`
- `Top Opportunity`
- `Next Priority`
- `Data Completeness` — `COMPLETE / PARTIAL / MINIMAL / UNKNOWN`
- `Data As Of`
- `Source Type` — `MANUAL / EXPORT / SYSTEM / AGENT / MIXED`
- `Source Ref`
- `Human Reviewed`
- `Last Reviewed At`

Health options: `GREEN / YELLOW / RED / UNKNOWN`.

Rules:
- Blank metrics must not silently become GREEN.
- When evidence is incomplete, use `UNKNOWN` or `Data Completeness=PARTIAL`.
- `Overall Health` is not auto-calculated in v0.1 unless a simple explicit rule is documented.

Views:
- `本周总览`
- `按平台`
- `红黄灯`
- `历史周`

## 6. Table 02 — Core SKU Performance

**Grain:** one record per `week × market × platform × channel(optional) × SKU`.

This table is for core SKUs, exception SKUs, and active focus SKUs only, not the full catalog in v0.1.

Fields:
- `SKU Perf ID`
- `Week`
- `Market`
- `Platform`
- `Channel`
- `Product Line`
- `SKU`
- `Model / Product`
- `SKU Role` — `HERO / GROWTH / PROFIT / TRAFFIC / CLEARANCE / NEW / WATCH / OTHER`
- `Sales`
- `Orders`
- `Units`
- `WoW Sales %`
- `Target`
- `Target Gap %`
- `Traffic`
- `Conversion Rate`
- `Ad Spend`
- `ROAS`
- `Inventory`
- `DOS`
- `Buyability` — `YES / NO / UNKNOWN`
- `Listing Status` — `HEALTHY / ISSUE / DOWN / UNKNOWN`
- `Status` — `GREEN / YELLOW / RED / UNKNOWN`
- `Main Change`
- `Diagnosis`
- `Recommended Action`
- `Data As Of`
- `Source Type`
- `Source Ref`
- `Evidence`
- `Human Reviewed`

Important:
- Do not invent a metric because another platform has it.
- Missing data stays blank/UNKNOWN.
- Platform-specific raw metrics belong in future adapters/raw snapshots, not by endlessly expanding this table.

Views:
- `本周核心SKU`
- `异常SKU`
- `Walmart`
- `THD`
- `Lowe's`
- `历史`

## 7. Table 03 — Action & Validation

Each record represents a business action with an expected outcome, not merely a to-do.

Fields:
- `Action ID`
- `Week Created`
- `Market`
- `Platform`
- `Channel`
- `Product Line`
- `SKU`
- `Action Title`
- `Objective`
- `Why / Problem`
- `Action Taken`
- `Expected Result`
- `Baseline`
- `Success Criteria`
- `Owner`
- `Priority` — `P0 / P1 / P2 / P3`
- `Status`:
  - `PLANNED`
  - `IN_PROGRESS`
  - `EXECUTED_WAITING_VALIDATION`
  - `VALIDATED_EFFECTIVE`
  - `VALIDATED_INEFFECTIVE`
  - `INCONCLUSIVE`
  - `BLOCKED`
  - `CANCELLED`
- `Execution Date`
- `Validation Date`
- `Validation Window`
- `Actual Result`
- `Conclusion`
- `AI Analysis`
- `AI Suggested Status`
- `AI Confidence` — `HIGH / MEDIUM / LOW`
- `Human Decision`
- `Evidence`
- `Last Reviewed At`

Rules:
- `EXECUTED` is not success.
- A completed execution with no result proof must be `EXECUTED_WAITING_VALIDATION`.
- Only a human-reviewed validation may be treated as final in v0.1.

Views:
- `本周动作`
- `等待验证`
- `逾期`
- `P0-P1`
- `已验证有效`
- `无效或不确定`
- `按平台`

## 8. Table 04 — Signal Register

One table for issues, risks, and opportunities.

Fields:
- `Signal ID`
- `Week Opened`
- `Market`
- `Platform`
- `Channel`
- `Product Line`
- `SKU`
- `Signal Type` — `ISSUE / RISK / OPPORTUNITY`
- `Category` — `SALES / TRAFFIC / CONVERSION / ADS / INVENTORY / BUYABILITY / LISTING / FULFILLMENT / REVIEW / ACCOUNT / PROMOTION / ONBOARDING / SYSTEM / OTHER`
- `Title`
- `Description`
- `Business Impact`
- `Priority` — `P0 / P1 / P2 / P3`
- `Confidence` — `HIGH / MEDIUM / LOW`
- `Root Cause`
- `Current Status` — `OPEN / INVESTIGATING / ACTION_REQUIRED / WAITING_EXTERNAL / MONITORING / RESOLVED / CLOSED`
- `Owner`
- `Next Step`
- `DDL`
- `Related Action ID`
- `Evidence`
- `Source Type`
- `Source Ref`
- `AI Analysis`
- `Human Decision`
- `Resolved At`

Views:
- `P0-P1 Open`
- `风险`
- `机会`
- `等待外部`
- `本周关闭`
- `按平台`

## 9. Status semantics

Priority:
- `P0` — current direct revenue/compliance/fulfillment block; immediate intervention
- `P1` — meaningful near-term business impact; must be actively managed this week
- `P2` — normal optimization or project work
- `P3` — backlog / low urgency

Health:
- `GREEN` — operating within expectation; no material active issue
- `YELLOW` — deviation/risk requiring attention
- `RED` — material business interruption or severe deviation
- `UNKNOWN` — insufficient evidence

Never convert UNKNOWN to GREEN.

## 10. Initial rules contract

Create `config/rules.yaml`, starter examples only:

```yaml
rules:
  - id: BUYABILITY_NO
    when: buyability == "NO"
    health: RED
    category: BUYABILITY

  - id: SALES_WOW_WARN
    when: wow_sales_pct <= -20
    health: YELLOW
    category: SALES

  - id: SALES_WOW_CRITICAL
    when: wow_sales_pct <= -35
    health: RED
    category: SALES

  - id: DOS_WARN
    when: dos < 14
    health: YELLOW
    category: INVENTORY

  - id: DOS_CRITICAL
    when: dos < 7
    health: RED
    category: INVENTORY
```

Do not build a large rules engine yet.

## 11. Weekly workflow

Each weekly cycle:

```text
1. Gather / update platform facts
2. Update Business Health
3. Update core/focus SKU records
4. Review open Signals
5. Review previous Actions
6. Validate actions whose validation date arrived
7. Record actual result / conclusion
8. Identify top risks and opportunities
9. Set one Next Priority per platform and one overall weekly priority
10. Human review
11. Freeze/mark weekly snapshot
```

The weekly meeting must answer:
1. What is the current status of Walmart / THD / Lowe's?
2. What materially changed?
3. What did we do?
4. What did those actions achieve?
5. What remains unvalidated or ineffective?
6. What are the main risks/opportunities?
7. What is next week's priority?

## 12. Hermes integration contract

Do not make Hermes a hard dependency of STORM v0.1.

Reserve three task types:

### `weekly_analyze`
Input:
- business health snapshot
- core SKU records
- open signals
- actions

Output:
- summary
- top_changes
- risks
- opportunities
- recommended_priorities
- evidence_refs
- confidence

### `action_validate`
Input:
- action
- baseline
- expected_result
- success_criteria
- current_metrics/evidence

Output:
- suggested_status
- actual_result_summary
- conclusion
- evidence_refs
- confidence

### `signal_triage`
Input:
- raw issue/risk/opportunity text
- platform context
- available evidence

Output:
- signal_type
- category
- priority
- business_impact
- next_step
- confidence

Create these contracts in `docs/hermes_contract.md`.

If a local Hermes CLI/gateway is available and can be called safely, run one non-blocking read-only probe using synthetic/static STORM JSON. Store the result only under `data/snapshots/hermes_probe/`.

The probe must not:
- write to Feishu
- change STORM statuses
- touch platform accounts
- block v0.1 completion if it fails

## 13. AGENTS.md rules

Create project-scoped `AGENTS.md` with at least:
1. Default to one main agent.
2. Read/inspect before editing.
3. Make the minimum sufficient change.
4. Do not scan unrelated directories or other Codex projects.
5. Never edit global Codex/Hermes configuration unless explicitly instructed.
6. Do not touch existing Feishu Bases.
7. Do not make platform-side business changes.
8. Treat STORM IDs and schema names as contracts.
9. Preserve evidence/provenance.
10. UNKNOWN is valid; never fabricate missing metrics.
11. Human-reviewed status overrides AI suggestions.
12. Future integrations go through adapters; do not add platform-specific logic to domain models.
13. Run focused tests only.
14. Stop and report if a required external permission is missing.

## 14. Feishu schema manifest

`config/feishu_schema.yaml` must be machine-readable and mirror the actual Base:
- base name
- table names
- field names
- field types
- select options
- required/optional flags
- view names

After Feishu creation, compare the live schema with the manifest and report mismatches.

## 15. Seed data

Do not invent sales or performance metrics.

After schema creation, it is acceptable to create minimal current-week seed records containing only known, evidence-backed facts.

If source context is insufficient, use clearly marked placeholders:
- `Source Type = MANUAL`
- `Data Completeness = MINIMAL`
- `Human Reviewed = false`

Prefer empty quantitative fields over guesses.

## 16. v0.1 non-goals

Do not build:
- Streamlit dashboard
- full platform APIs
- live Walmart/THD/Lowe's ingestion
- data warehouse
- autonomous ad/listing/price changes
- automated Feishu write-back from Hermes
- multi-agent task scheduler
- real-time notifications
- complex forecasting
- full catalog SKU history
- cross-project shared runtime

## 17. Acceptance criteria

STORM v0.1 is complete only when:
1. A clean standalone STORM project exists.
2. Project has isolated environment and no global changes.
3. A new `STORM | Business Control` Feishu Base exists.
4. Exactly four v0.1 tables exist with the required schemas.
5. Required views exist.
6. `config/feishu_schema.yaml` matches the live Base.
7. Canonical dimensions support market/platform/channel separation.
8. Architecture, data contract, weekly workflow, and Hermes contract docs exist.
9. Walmart/THD/Lowe's/Hermes adapter boundaries are reserved but not over-implemented.
10. No existing Feishu Base/project/platform account was modified.
11. Missing metrics remain blank/UNKNOWN.
12. Final implementation report includes:
    - local project path
    - git status
    - environment status
    - Feishu Base link/identifier
    - tables/views created
    - schema validation result
    - Hermes probe result if attempted
    - blockers
    - next recommended step

## 18. Execution sequence

### Phase 0 — Safety / discovery
- Confirm project root is safe.
- Confirm Feishu connector capability.
- Do not touch existing Bases.
- Inspect only what is needed.

### Phase 1 — Local scaffold
- Create repository structure.
- Create isolated environment.
- Write config/docs/contracts.
- Initialize git if appropriate.

### Phase 2 — Feishu build
- Create the new Base.
- Create four tables.
- Create fields/options.
- Create views.
- Record live identifiers locally if appropriate.

### Phase 3 — Schema verification
- Compare live schema to `feishu_schema.yaml`.
- Fix only STORM's new Base if needed.

### Phase 4 — Minimal seed / usability check
- Add only minimal safe seed records.
- Verify weekly meeting views are usable.

### Phase 5 — Hermes boundary
- Create adapter contract.
- Optional non-blocking static probe only.

### Phase 6 — Final report
Return:
- `READY_FOR_WEEKLY_PILOT` if all core criteria pass.
- `READY_WITH_LIMITATIONS` if Feishu works but a non-core item such as Hermes probe is unavailable.
- `BLOCKED` only for a core blocker.

Do not start Streamlit or automated ingestion after completion.

## 19. Product direction

```text
v0.1  Feishu Control Ledger + Weekly
v0.2  Hermes weekly analysis / validation (human-approved)
v0.5  selective automated data ingestion
v1.0  Streamlit executive dashboard
v1.5  daily exception watch
v2.0  task orchestration / agent execution
```

The v0.1 schema must be stable enough that future versions consume it rather than replace it.
