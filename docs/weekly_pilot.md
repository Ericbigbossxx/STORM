# STORM v0.1.1 Weekly Pilot entry contract

## Baseline and scope

The Weekly Pilot uses the hardened `STORM v0.1.1 Weekly Pilot Baseline` in the separately approved Feishu Base `STORM | Business Control`. The first round covers only Market `US` and Platforms `Walmart`, `THD`, and `Lowe's`.

The pilot is `MANUAL / ASSISTED INPUT`. It does not authorize automated ingestion, scheduling, notifications, autonomous write-back, Hermes, or Streamlit. Schema changes require a separate reviewed phase; pilot input must not add fields, tables, views, or select options.

## Input controls

- Reconcile by immutable STORM ID before creating a record. Do not create duplicates after a timeout or interrupted response.
- Record source provenance using the applicable `Source Type`, `Source Ref`, `Data As Of`, and `Evidence` fields.
- Enter structured metrics only when an actual source supports the value. Unknown values remain blank; status fields use `UNKNOWN` when evidence is insufficient. Never estimate, zero-fill, or convert unknown evidence to `GREEN`.
- Operational facts may be manually entered or AI-assisted, but a human reviews the final wording and status. AI fields remain advisory and default hidden; `Human Decision` is authoritative.
- `Human Reviewed` defaults to `false` on every table. Only the human review workflow may set it to `true`; AI-assisted input cannot approve a record.
- Do not backfill history merely for completeness. Include only records that remain relevant to the current operating cycle.
- Do not enter credentials, tokens, secrets, raw exports, or unrelated business data into the repository.

## Structured metrics

Structured metrics include Sales, Units, Orders, WoW Sales %, Target, Traffic, Conversion Rate, Ad Spend, ROAS, Inventory, DOS, and other approved numeric fields. A value is permitted only when its source, coverage period, grain, and as-of date are known. Missing or incompatible metrics remain blank.

## Operational facts

Operational facts include what happened, the action taken, the current blocker, risks, opportunities, evidence, owner, next step, and validation outcome. Manual or AI-assisted summarization is allowed, but it must preserve the source meaning and may not invent facts or final decisions.

## Table-specific first-round rules

### 01 Business Health

Create exactly one `Level=PLATFORM` record for each approved platform: Walmart, THD, and Lowe's. Use Market `US`, leave `Channel` blank, and use the current approved week. The two pilot views enforce `Level=PLATFORM`. Do not create CHANNEL-level records in v0.1.

### 02 Core SKU Performance

Enter only Core SKUs, Exception SKUs, and Current Focus SKUs. Do not import the full catalog. Preserve the platform and optional channel grain, and leave unsupported platform metrics blank.

### 03 Action & Validation

Enter only recent Actions that still have business relevance, Actions waiting for outcome validation, and Actions that must continue next week. Do not import every historical task. Execution without result evidence remains `EXECUTED_WAITING_VALIDATION`; only human-reviewed validation is final.

### 04 Signal Register

Enter only currently open Issues, current Risks, and current Opportunities. Do not import closed historical items with no remaining review value. Link Signals and Actions through the approved reciprocal many-to-many fields when the relationship is supported by evidence.

## Pilot close

Before weekly close, complete human review, confirm missing metrics remain blank or `UNKNOWN`, and verify every record has an appropriate source reference. Lock the Business Health and Core SKU snapshots only after review, then export all four tables under the governed weekly snapshot process.
