# STORM V2 Phase 1 Data Contract

## Canonical hierarchy

`Platform → Channel/Subchannel → Brand → Power Source → SKU`

Every dimension is nullable. Missing facts remain `UNKNOWN`/`UNMAPPED`; no inferred fallback or zero-fill is allowed.

## Canonical record

Each candidate contains metric domain/name/value/unit/scenario/date; all five hierarchy dimensions; mapping status; raw value/dimensions; and exact source file hash, sheet, semantic section, header, and row/cell reference.

## Metric domains

| Domain | Approved use | Isolation rule |
| --- | --- | --- |
| `SALES` | Core actual order revenue and units | Consumer DFC data cannot enter |
| `ADS` | Approved core advertising metrics | Phase 1 contract only; no engine |
| `CM_BUSINESS_PERFORMANCE` | Approved BP/CM reconciliation | Phase 1 contract only; no engine |
| `THD_DFC_SELLOUT` | THD consumer sell-out, traffic, conversion, current inventory | Only `THD- robot Sell out` may populate |

## KPI Rawdata baseline

- Status: `REFERENCE_BASELINE / NOT_WEEKLY_ACTUAL_INPUT`
- Phase 1: no refresh, no recalculation, no Weekly Actual use.
- Permitted reference use: BP, CM, SKU mapping and related baseline context, subject to approved core scope.
- Future update: permitted through version, SHA-256, approval, and replacement record. This is not a permanent immutability assumption.

## Time semantics

- `actual order`: exact normalized dates, 2026-08-01 through 2026-08-10.
- `THD- robot Sell out`: exact normalized dates, 2026-01-01 through 2026-08-10.
- `over view` and `2026 acutal cost`: monthly/MTD context only; exact day-level data-through is `UNKNOWN`.
- `KPI Rawdata`: 2026 planning/reference horizon; not a Weekly Actual date source.
- `SKU MAP`: timeless mapping baseline.
