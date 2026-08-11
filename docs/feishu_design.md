# Feishu ledger design — STORM v0.1.1

## Base boundary

STORM v0.1 uses a separately approved Base named `STORM | Business Control`. Existing Bases remain outside scope. `config/feishu_schema.yaml` is the machine-readable contract; credentials and live business exports never enter this repository.

Exactly four operational tables are permitted:

1. `01 Business Health`
2. `02 Core SKU Performance`
3. `03 Action & Validation`
4. `04 Signal Register`

## Weekly Pilot views

Launch exactly these 13 views:

- 01 Business Health: `本周总览`, `红黄灯`
- 02 Core SKU Performance: `本周核心SKU`, `异常SKU`
- 03 Action & Validation: `本周动作`, `等待验证`, `逾期`, `P0-P1`, `无效或不确定`
- 04 Signal Register: `未决Signal`, `P0-P1`, `风险`, `机会`

Do not launch platform-specific, history, generic `按平台`, or other non-pilot views. Users switch Walmart, THD, and Lowe's through view filters.

The v0.1.1 specialized filter contract is:

- `红黄灯`: `Level=PLATFORM` and `Overall Health != GREEN`.
- `异常SKU`: `Status in {YELLOW, RED}` or `Buyability=NO` or `Listing Status in {ISSUE, DOWN}`. `UNKNOWN` is not automatically an anomaly.
- `等待验证`: `Status=EXECUTED_WAITING_VALIDATION`.
- Action `P0-P1`: `Priority in {P0, P1}`.
- `无效或不确定`: `Status in {VALIDATED_INEFFECTIVE, INCONCLUSIVE}`.
- Signal `未决Signal`: `Current Status not in {RESOLVED, CLOSED}`.
- Signal `P0-P1`: `Priority in {P0, P1}`.
- `风险`: `Signal Type=RISK`.
- `机会`: `Signal Type=OPPORTUNITY`.

`逾期` is `DEFERRED_NOT_RELIABLY_FILTERABLE`. Action has no general due-date field, and `Validation Date` is not a valid substitute. Do not infer a due date or populate one without human confirmation. Current affected actions are `REQUIRES_HUMAN_DATE_CONFIRMATION`.

## Field presentation and authority

Business Health defaults to showing `Overall Health`, `Sales Health`, `Ads Health`, `Inventory Health`, and `Buyability Health`. `Listing Health`, `Fulfillment Health`, `Review Health`, and `Project Health` remain available but default hidden; Project Health is not a core v0.1.1 health input.

AI fields are optional, default hidden, non-manual, advisory, and reserved for Hermes v0.2. Human Decision is final. `Human Reviewed` exists on all four tables, defaults to `false`, and may be set to `true` only by the human review workflow. Quantitative fields remain blank when evidence is unavailable, and no formula may promote blank or `UNKNOWN` evidence to `GREEN`.

`Snapshot Locked` appears only in Business Health and Core SKU Performance. Signal and Action use reciprocal Feishu record links to represent their many-to-many relationship.

## MCP capability note

`lark-mcp 0.5.1` does not support persistent View sorting. This is non-blocking for v0.1.1. Filters, hidden fields, view configuration, and runtime record sorting are allowed. Do not upgrade MCP or build a workaround for persistent sorting in this phase.

## Phase 2/3 boundary

Phase 2 may create only the separately approved STORM Base from the manifest. Phase 3 must compare its live tables, fields, options, reciprocal links, and views with this contract. Neither phase may modify another Base.

## Pilot hardening backlog

The following items are observation-only until 2–4 weeks of real use provide enough evidence. They are not v0.1.1 schema cleanup authorization:

- low usage of `Review Health` and `Project Health`;
- duplicated narratives across Business Health, Core SKU, Signal, and Action;
- weekly Core SKU records with no change;
- long audit fields that may be hidden from meeting views.
