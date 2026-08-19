# STORM structured metrics data contract — Phase 0.5 / Phase 1

## Gate result

This contract is based on a read-only inspection of `data/inbox/US E-commerce Actual CM for 2026_vs. BP.xlsx`.
The current inspected file SHA-256 is `89B8BF3EAD9D940833582CA01FC0065C4099E335C30EC9FEAC0D5CB2CBBC1168`
(15,015,701 bytes; modified 2026-08-11 17:08:11 Asia/Shanghai). This supersedes the
earlier Phase 0.5 hash; the file changed externally and was revalidated before closeout.
The workbook was saved with the `Overview` selector at `Aug` / `MTD`; scoped `Actual Orders`
rows run through 2026-08-10. No workbook cell or live Feishu asset was modified.

Phase 0.5 inspection, the Phase 1 code build, and the authoritative MTD import are complete.
`PHASE_1_MTD = ACCEPTED`. The committed import batch is
`5a7ee7c5-4895-4243-b771-39143bc42011` with status `PASS_WITH_WARNINGS` and zero blocking
reconciliation failures. `YTD = SOURCE_NOT_AVAILABLE`; this is a source-coverage state and
does not block the cockpit MVP.

The implementation consumes Excel's cached results using `openpyxl.load_workbook(...,
data_only=True, read_only=True)`. Raw OOXML inspection found 546,583 formula cells and no
formula cell without a cached `<v>` element. Formula-error cells exist in presentation areas
(including `Overview` ratio cells); the adapter reads only the verified numeric output cells
and converts an invalid targeted cache into `DATA_EXCEPTION` rather than zero.

## Observed workbook structure

| # | Sheet | State | Used range | Formula cells |
|---:|---|---|---|---:|
| 1 | Overview-SH EC All Channel | visible | A1:AQ264 | 7,333 |
| 2 | Overview | visible | A1:AG349 | 4,361 |
| 3 | 2026 Actual Cost | visible | A1:AR111 | 3,019 |
| 4 | KPI Trend | visible | A1:Q465 | 4,797 |
| 5 | 透视1 | hidden | A2:P38 | 29 |
| 6 | Actual Orders | visible | A1:X22549 | 345,428 |
| 7 | Walmart DDP | visible | A1:D212 | 1 |
| 8 | Amazon DI | visible | A1:E7 | 0 |
| 9 | HD&Lowes Cost Deatils | visible | A1:L5922 | 17,310 |
| 10 | EU Trend | visible | A1:S53 | 0 |
| 11 | KPI Rawdata | visible | A1:AJ5189 | 126,765 |
| 12 | BP Funding | visible | A1:H92 | 362 |
| 13 | Config | visible | A1:M59 | 40 |
| 14 | Handling Fee | visible | A1:AA3472 | 6,942 |
| 15 | 2026 BP Cost | visible | A1:AA97 | 1,804 |
| 16 | AMZ Vendor-WBP | visible | A1:Y103 | 1,553 |
| 17 | AMZ Vendor-SK | visible | A1:Y49 | 257 |
| 18 | AMZ Seller-SK | visible | A1:Y48 | 239 |
| 19 | COSTCO | visible | A1:Y48 | 239 |
| 20 | DTC-SK | visible | A1:Y60 | 521 |
| 21 | The Home Depot-SK | visible | A1:Y46 | 191 |
| 22 | The Home Depot DFC-SK | visible | A1:Y46 | 190 |
| 23 | Lowes-SK | visible | A1:Y48 | 238 |
| 24 | Walmart-SK | visible | A1:Y46 | 185 |
| 25 | The Home Depot-WBP | visible | A1:Y101 | 1,511 |
| 26 | Lowes-WBP | visible | A1:Y102 | 1,535 |
| 27 | Walmart Seller-WBP | visible | A1:Y101 | 1,505 |
| 28 | Walmart DSV-WBP | visible | A1:Y101 | 1,505 |
| 29 | 3PL Shipped Qty | visible | A3:D2761 | 0 |
| 30 | 3PL Shipments | visible | A1:U16181 | 16,180 |
| 31 | 12.31Inv&DDP FCST | hidden | A1:R163 | 846 |
| 32 | DDP Summary - FOR Actual Orders | visible | A1:AE169 | 1,683 |
| 33 | SKU Mapping | visible | A1:E325 | 14 |

Relevant structural conditions:

- `Overview` hides rows 97, 257, 258, 295, 296, 310, and 317. It contains 14 merged
  presentation ranges; none intersects the fixed Brand×Power values read by the adapter.
- `Actual Orders` hides rows 2–22503; `KPI Rawdata` and `SKU Mapping` have no hidden rows,
  hidden columns, or merged cells.
- `The Home Depot-SK`, `The Home Depot DFC-SK`, `Lowes-SK`, and `Walmart-SK` use merged
  label cells around rows 18–23. They are evidence of separate channel models, not Phase 1
  fact inputs.
- `SKU Mapping` headers are exactly `SKU`, `ASIN`, `Pource Source`, `Brand`, `Category`.
  The source typo `Pource Source` is a contract and is mapped explicitly to `power_source`.
- `KPI Rawdata` has 36 fields. Its verified target grain is source line item by SKU,
  Customer, Year, `Month-INT`, promotion/price. Multiple rows are therefore aggregated to
  `(year, month, platform, canonical_sku)`; 5,188 input rows produce 1,110 target facts.

## Observed source-of-truth rules

### Platform and business model

| Contract enum | Accepted source display values | Model | Primary sales basis |
|---|---|---|---|
| `WALMART_MP` | `Walmart Seller`, `Walmart` | marketplace | sell-out |
| `THD` | `The Home Depot Inc`, `HomeDepot`, `HomeDepot*` | first party | sell-in |
| `LOWES` | `Lowe's`, `Lowes` | first party | sell-in |

Known non-scope sources such as Amazon, DTC, Walmart DSV, and THD DFC are not coerced into
one of these enums. An unexpected value presented to the scoped mapping is an
`INVALID_PLATFORM` exception.

### SKU and BP targets

`SKU Mapping` is the authoritative source for canonical SKU, Brand, Power Source, and
Category. `KPI Rawdata` formulas confirm Brand and Power Source are looked up from this
mapping. Leading/trailing whitespace is normalized. The inspected workbook contains two
visually identical `SK-L-WIRE` rows after normalization (one begins with a line break); the
second is retained as a `DUPLICATE_SKU_MAPPING` warning, not silently dropped.

Phase 1 imports BP only for `The Home Depot Inc`, `Lowe's`, and `Walmart Seller`. BP CM is
the workbook's verified line calculation:

```text
TTL amount
- DDP/ALL (COGS)
- Fixed cost/ALL
- MKT-Insite/ALL
- MKT-Offsite(种草)/ALL
- MKT-Offsite(Channel MKT)/ALL
- Return+Warranty/ALL
- Funding/ALL
```

If a required source component is unavailable, `bp_cm` and its ratio remain `NULL`.
Zero sales produces a `NULL` ratio; no missing value is converted to zero.

### Official CM snapshot and THD DFC exclusion

The current official Brand×Power cache is the hidden detail area in `Overview`:

- Actual dimensions: rows 259–261; metrics: rows 262–291.
- BP dimensions: rows 297–299; metrics: rows 300–320.
- THD Main columns: J, K, T, U, V.
- THD DFC columns: L, M — explicitly excluded.
- Lowe's columns: N, O, W, X, Y.
- Walmart MP columns: P, Q, Z, AA, AB.

`Overview!I82` is `=G82+H82`, proving the displayed THD Sunseeker summary combines Main and
DFC. Current DFC sales are zero but DFC CM is -612.5, so using the combined THD cell would
materially understate primary THD CM. Phase 1 uses Main sell-in only. The independent
platform reconciliation therefore uses G+M for THD, J+N for Lowe's, and K+O for Walmart MP.

Current inspected MTD primary totals are:

| Platform | Actual units | Actual sales | Actual CM | BP units | BP sales | BP CM |
|---|---:|---:|---:|---:|---:|---:|
| THD, Main only | 251 | 38,617.77 | 15,104.261940 | 1,641.173279 | 524,757.561901 | 35,597.784210 |
| Lowe's | 166 | 23,376.48 | 3,463.575303 | 1,557.891955 | 324,983.463265 | 13,070.946595 |
| Walmart MP | 34 | 5,750.92 | -3,273.324693 | 388 | 80,476.70 | 3,307.767377 |

## Phase 1 persistence contract

The runtime database is `data/structured_metrics/storm_metrics.sqlite3`; `data/**` is ignored.
The database contains:

- `DIM_SKU`: one reviewed platform/canonical-SKU mapping. Existing dimension history is not
  overwritten; a changed contract fails the new batch.
- `IMPORT_BATCH`: immutable source identity, SHA-256, period, snapshot and cutoff dates, row
  counts, source totals, reconciliation evidence, and status. Duplicate identity is
  `(file_hash, report_type, source_period)` because identical bytes cannot contain a newer
  cached result for the same report/period.
- `DATA_EXCEPTION`: invalid, duplicate, unmapped, and unavailable-source evidence with source
  sheet/row/range. Exceptions are never converted to facts or silently deleted.
- `FACT_BP_TARGET_MONTHLY`: verified monthly SKU grain with batch and source-row lineage.
- `FACT_CM_SNAPSHOT`: immutable `(snapshot_date, period_type, platform, brand, power_source,
  cm_basis)` facts with batch and cell-range lineage.

All validation and reconciliation complete before commit. SQLite foreign keys and one
transaction cover the batch, dimensions, facts, and exceptions; any mid-import error rolls
back the entire batch. Reconciliation stores official value, imported value, variance,
tolerance, and result in `IMPORT_BATCH.reconciliation_json`.

Tolerances are explicit: USD 0.01, units 0.000001, ratios 0.000000001. A failed authoritative
comparison blocks the commit. Overview Actual CM detail-to-summary platform and Brand×Power
comparisons pass, including THD Main-only reconciliation. `KPI Rawdata` is authoritative for
monthly SKU BP; `Overview` BP is a secondary derived-view check. The secondary check reports
the following warning for Walmart MP / Sunseeker / Robot:

| Metric | KPI Rawdata authority | Overview derived cache | Variance | Result |
|---|---:|---:|---:|---|
| BP units | 71 | 0 | 71 | WARNING |
| BP sales | 127,035.00 | 0 | 127,035.00 | WARNING |
| BP CM | 12,210.706542 | 0 | 12,210.706542 | WARNING |

Formula inspection classifies the cause as `BROKEN_DERIVED_FORMULA`, not stale cache:
`Overview!P300` queries `KPI Rawdata` with customer criterion `P296`; `P296` references
`P258 = Walmart`, while the authoritative rows use `Customer = Walmart Seller`. The parallel
Badger formula uses `Z258 = Walmart Seller` and returns 44 units. The six Brand×Power/platform
differences are stored as non-blocking `BROKEN_DERIVED_FORMULA` warnings. The official workbook
was not edited.

## Observed, inferred, unresolved

Observed:

- Current saved selector is `Aug` / `MTD`; scoped source cutoff is 2026-08-10.
- Main and DFC have separate sheets, rows, detail columns, and channel names.
- `Overview` combines Main and DFC in its displayed THD roll-up.
- BP monthly targets and the fixed Brand×Power CM region expose sufficient stable keys.

Inferred and encoded:

- The file modification date 2026-08-11 is used as this import's explicit snapshot date.
- The same fixed `Overview` detail range can support YTD only when an official workbook is
  saved with the selector at `YTD` and its formula caches are refreshed.

Coverage gaps and deliberately unavailable values:

- This file does not simultaneously contain a saved official YTD Brand×Power cache; it is
  saved at MTD. Phase 1 therefore imports only the evidenced MTD snapshot. A future YTD import
  requires a separately saved/recalculated official workbook and the same reconciliation gate.
- `ASIN` is absent for 167 mapping rows and is not substituted as a platform SKU.
- The adapter does not reconstruct YTD from `Actual Orders` or `2026 Actual Cost`; doing so
  would create a competing finance engine outside Phase 1.
- `KPI Rawdata` contains seven Aug 2026 Walmart Seller / Sunseeker / Robot BP rows totaling
  71 units and $127,035 sales. They remain authoritative; the broken secondary Overview formula
  provides no valid rule for discarding them.
