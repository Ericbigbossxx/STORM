# Workbook Inventory

## Source integrity

- File: `STORM V2 RAW DATA.xlsx`
- Size: `1,120,274` bytes
- SHA-256 before: `B05FF566B9DECC2852460E8FEC12AF8026B0C8D72148F52F974C32F27F1A8833`
- SHA-256 after: `B05FF566B9DECC2852460E8FEC12AF8026B0C8D72148F52F974C32F27F1A8833`
- Read-only integrity: `PASS`
- Visible sheet count: `6`

## Sheet inventory

| Sheet | Used range | Rows after row 1 | Visibility | Header contract |
| --- | --- | --- | --- | --- |
| over view | A1:AG349 | 348 | visible | PASS |
| 2026 acutal cost | A1:AR111 | 110 | visible | PASS |
| actual order | A1:I487 | 486 | visible | PASS |
| THD- robot Sell out | A1:W1136 | 1135 | visible | PASS |
| KPI Rawdata | A1:AJ5189 | 5188 | visible | PASS |
| SKU MAP | A1:E323 | 322 | visible | PASS |

`over view` is a formatted management-summary grid, so its row count is a layout-row count rather than a transaction count. All other counts above are physical rows after the header; semantic valid-row counts are stated in the source mapping report.

## Overview semantic sections

| Section label | Occurrences | Observed references |
| --- | --- | --- |
| By Brand | 1 | B5 |
| By Power Source | 1 | B42 |
| By Channel | 1 | B78 |
| Actual CM vs. BP CM | 5 | P5, P42, B137, B226, B324 |
| All Brand | 1 | B168 |
| BI Channel Name | 2 | B258, B296 |

Coordinates are validation hints only. Section labels, header sequence, and business keys define the contract.

## Inventory-only business data

The following data is present in the authoritative workbook and is monitored for structural/count drift. It is inventory evidence only: it is not registered as a V2 source, mapped, converted to canonical candidates, quality-scored, or admitted to later engines.

| Business | Sheet | Section | Records | Count basis | Status | Reason |
| --- | --- | --- | --- | --- | --- | --- |
| Amazon | over view | repeated By Channel / brand-power summary labels | 64 | summary label occurrences | OUT_OF_SCOPE_FOR_STORM_V2 | Not part of the approved STORM V2 core channel contract |
| Costco | over view | repeated By Channel / brand-power summary labels | 13 | summary label occurrences | OUT_OF_SCOPE_FOR_STORM_V2 | Not part of the approved STORM V2 core channel contract |
| DTC | over view | repeated By Channel / brand-power summary labels | 16 | summary label occurrences | OUT_OF_SCOPE_FOR_STORM_V2 | Not part of the approved STORM V2 core channel contract |
| Amazon | 2026 acutal cost | Channel data rows | 24 | source rows | OUT_OF_SCOPE_FOR_STORM_V2 | Not part of the approved STORM V2 core channel contract |
| Costco | 2026 acutal cost | Channel data rows | 8 | source rows | OUT_OF_SCOPE_FOR_STORM_V2 | Not part of the approved STORM V2 core channel contract |
| DTC | 2026 acutal cost | Channel data rows | 8 | source rows | OUT_OF_SCOPE_FOR_STORM_V2 | Not part of the approved STORM V2 core channel contract |
| Amazon | KPI Rawdata | Customer data rows | 1695 | source rows | OUT_OF_SCOPE_FOR_STORM_V2 | Not part of the approved STORM V2 core channel contract |
| DTC | KPI Rawdata | Customer data rows | 211 | source rows | OUT_OF_SCOPE_FOR_STORM_V2 | Not part of the approved STORM V2 core channel contract |
