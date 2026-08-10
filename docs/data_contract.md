# STORM v0.1 data contract

## Canonical identity

`platform` is never sufficient by itself. The canonical management dimensions are `market`, `platform`, optional `channel`, `product_line`, `sku`, and `week_id`. Registries live in `config/dimensions.yaml`; adapters resolve source-specific values before domain use.

STORM v0.1 operates only in Market `US` and Currency `USD`. Currency is not an active ledger input field in v0.1. Before CA, MX, or another non-USD market is activated, Currency must become an explicit dimension and all affected metric contracts must declare their currency.

## Table grains

- Business Health: exactly one row per `Week × Market × Platform × Level=PLATFORM`. For a given Week, Market, and Platform, only one PLATFORM row is permitted. `Channel` must be blank. `CHANNEL` is a reserved Level value and is inactive in v0.1.
- Core SKU Performance: one row per `Week × Market × Platform × optional Channel × SKU` for core, exception, or focus SKUs only.
- Action & Validation: one business action and its expected, observed, and human-validated outcome.
- Signal Register: one issue, risk, or opportunity across its lifecycle.

## STORM IDs

Every row receives an immutable, machine-minted, human-read-only domain ID. A Feishu `record_id` is adapter metadata and never substitutes for a STORM ID.

- Business Health: `HLT-{YYYYWww}-{MARKET}-{PLATFORM_CODE}`
- Core SKU: `SKU-{YYYYWww}-{MARKET}-{PLATFORM_CODE}-{NORMALIZED_SKU}`
- Action: `ACT-{YYYYWww}-{sequence}`
- Signal: `SIG-{YYYYWww}-{sequence}`

Platform codes are Walmart=`WMT`, THD=`THD`, and Lowe's=`LOWES`. `YYYYWww` is derived from ledger `Week` (`YYYY-Www`) by removing the hyphen. Normalized SKU values are uppercase, with non-alphanumeric runs replaced by `-`. Action and Signal sequences are positive integers allocated by a STORM service; users never enter or maintain them.

## Signal and Action relation

Signal ↔ Action is many-to-many. `03 Action & Validation.Related Signals` links to `04 Signal Register`; the reciprocal field is `04 Signal Register.Related Actions`. Text copies of related IDs are not the relationship contract.

## Required inputs

Action operator-required fields are exactly: `Action ID`, `Week Created`, `Market`, `Platform`, `Action Title`, `Objective`, `Owner`, `Priority`, `Status`, and `Success Criteria`. The ID is system minted and read-only. Channel, Product Line, SKU, Why / Problem, Action Taken, Expected Result, Baseline, dates/windows, Actual Result, Conclusion, Evidence, and AI fields are optional. Feishu system timestamps are not operator input.

`Diagnosis` and `Recommended Action` are optional for Core SKU records.

## Provenance and missing evidence

Facts record `Data As Of`, `Source Type`, `Source Ref`, and evidence where applicable. Missing quantitative values stay blank; insufficient status evidence is `UNKNOWN`; `UNKNOWN` never becomes `GREEN` by default. Platform metrics may remain sparse and must never be invented for cross-platform uniformity.

## AI and human authority

`AI Analysis`, `AI Suggested Status`, and `AI Confidence` are optional, default-hidden, non-manual fields reserved for Hermes v0.2. AI output is advisory only. `Human Decision` and human-reviewed status remain final. Execution alone is not validation; an unproven action remains `EXECUTED_WAITING_VALIDATION`.
