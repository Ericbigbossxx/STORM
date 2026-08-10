# Feishu ledger design

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

## Field presentation and authority

Business Health defaults to showing `Overall Health`, `Sales Health`, `Ads Health`, `Inventory Health`, and `Buyability Health`. `Listing Health`, `Fulfillment Health`, `Review Health`, and `Project Health` remain available but default hidden; Project Health is not a core v0.1 health input.

AI fields are optional, default hidden, non-manual, advisory, and reserved for Hermes v0.2. Human Decision is final. Quantitative fields remain blank when evidence is unavailable, and no formula may promote blank or `UNKNOWN` evidence to `GREEN`.

`Snapshot Locked` appears only in Business Health and Core SKU Performance. Signal and Action use reciprocal Feishu record links to represent their many-to-many relationship.

## MCP capability note

`lark-mcp 0.5.1` does not support persistent View sorting. This is non-blocking for v0.1. Filters, hidden fields, view configuration, and runtime record sorting are allowed. Do not upgrade MCP or build a workaround for persistent sorting in this phase.

## Phase 2/3 boundary

Phase 2 may create only the separately approved STORM Base from the manifest. Phase 3 must compare its live tables, fields, options, reciprocal links, and views with this contract. Neither phase may modify another Base.
