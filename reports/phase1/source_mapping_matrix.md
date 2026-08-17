# Source Mapping Matrix

## Registered sources and roles

| Sheet | Approved role | Weekly actual | Canonical output in Phase 1 profiler |
| --- | --- | --- | --- |
| `over view` | Management reconciliation reference | No | No |
| `2026 acutal cost` | Core cost/CM reconciliation reference | No | No |
| `actual order` | Core weekly actual orders | Yes | `SALES` revenue and units |
| `THD- robot Sell out` | THD consumer DFC actual | Yes | `THD_DFC_SELLOUT` units, GMV, traffic, conversion, inventory |
| `KPI Rawdata` | `REFERENCE_BASELINE / NOT_WEEKLY_ACTUAL_INPUT` | No | No |
| `SKU MAP` | SKU/Brand/Power reference | No | Dimension enrichment only |

## Core channel mappings

| Raw label | Platform | Channel/Subchannel | Status |
| --- | --- | --- | --- |
| Walmart Seller / Walmart MP | Walmart | MP | MAPPED |
| Walmart DSV | Walmart | DSV | MAPPED |
| Lowe's / Lowes | Lowe's | DS | MAPPED |
| The Home Depot Inc / THD / HomeDepot | THD | DS | MAPPED |
| Walmart (without approved context) | UNKNOWN | UNKNOWN | AMBIGUOUS |

Prior V1 channel taxonomy is not inherited. `3P`, `WFS`, `1P`, and `THD Online` are not canonical V2 channel values.

## DFC isolation

DFC financial rows in overview/cost contexts are `EXCLUDED_CONTRACT_CONFLICT`. They cannot enter ordinary `SALES` and cannot populate the DFC consumer domain. The consumer domain is populated only by the dedicated sell-out sheet.

## Observed coverage

- SKU mapping: `321` normalized keys.
- Core actual rows accepted: `486`.
- Core canonical metric candidates: `5513`.
- Actual-order unmapped SKU rows: `1`; retained as `UNMAPPED` with raw values.
- DFC daily consumer rows accepted: `1134`.
- Traceability completeness: `PASS`.
- DFC domain isolation: `PASS`.
