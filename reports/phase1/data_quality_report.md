# Data Quality Report

## Gate result

- Blocking issues: `0`
- Non-blocking warnings: `7`
- Workbook hash unchanged: `PASS`
- Traceability complete: `PASS`
- DFC isolated: `PASS`

## Findings

| Severity | Code | Sheet | Affected | Reference | Finding |
| --- | --- | --- | --- | --- | --- |
| WARNING | OVERVIEW_CACHED_ERROR_VALUES | over view | 166 | Q20, C21, K77, Q77, H83, K83, Q83, H87, K87, Q87 | Management summary contains 166 cached/literal Excel error cells |
| WARNING | SKU_NORMALIZED_DUPLICATE_EQUIVALENT | SKU MAP | 2 | A105, A106 | Normalized SKU SK-L-WIRE appears 2 times; values are equivalent |
| WARNING | ACTUAL_ORDER_UNMAPPED_SKU | actual order | 1 | SKU column | Unmapped SKU rows retained with UNKNOWN dimensions: KB2618STR (1) |
| WARNING | ACTUAL_ORDER_MIXED_DATE_TYPES | actual order | 486 | C2:C487 | Mixed source date representations normalized to ISO dates: int=440, str=46 |
| WARNING | THD_DFC_POSITIVE_UNITS_ZERO_GMV | THD- robot Sell out | 6 | A:G consumer daily block | Positive sell-out units with zero GMV require business review; records remain in the DFC consumer domain |
| WARNING | EXACT_DATA_THROUGH_UNKNOWN | over view | 1 | period labels | Exact day-level data-through is not explicit; monthly/MTD labels are not converted into a guessed date |
| WARNING | EXACT_DATA_THROUGH_UNKNOWN | 2026 acutal cost | 1 | period labels | Exact day-level data-through is not explicit; monthly/MTD labels are not converted into a guessed date |

Warnings are explicit and non-blocking. No unknown fact is inferred or converted to zero. Inventory-only businesses are intentionally not quality-scored here.
