## STATUS

`STORM_V2_PHASE_5R_WEEKLY_COCKPIT_READY`

## SKU BP REPAIR

SKU BP: AVAILABLE

SKU Gap: AVAILABLE

SKU Attainment: AVAILABLE

Promotion header alias accepted: `Promition Type`.

## BP RECONCILIATION

Walmart Aug Badger Gas BP:

Expected = 11112.40

Actual = 11112.40

Reconciliation = PASS

Three-level reconciliation = PASS

## SKU ACTUAL VS BP RESULT

117 Channel × SKU rows; matched 48, BP-only 52, Actual-only 17.

## TOP SKU DETRACTORS

- THD / DS | SKRMX5 | Sunseeker / Robot | Actual $0.00 | BP $330,512.34 | Gap $-330,512.34 | 0.0%
- Lowe's / DS | ORIONX7 | Sunseeker / Robot | Actual $3,890.00 | BP $117,600.42 | Gap $-113,710.42 | 3.3%
- Walmart / MP | ORIONX7 | Sunseeker / Robot | Actual $0.00 | BP $79,017.00 | Gap $-79,017.00 | 0.0%
- THD / DS | SKRMX3PLUS | Sunseeker / Robot | Actual $0.00 | BP $49,522.10 | Gap $-49,522.10 | 0.0%
- Walmart / MP | SKRMX3PLUS | Sunseeker / Robot | Actual $0.00 | BP $43,173.00 | Gap $-43,173.00 | 0.0%

## TOP SKU OVERPERFORMERS

- Lowe's / DS | WB40VSNBL2 | Badger / Lithium | Actual $7,945.44 | BP $2,691.65 | Gap $5,253.79 | 295.2%
- THD / DS | WB31CCED | Badger / Gas | Actual $3,870.30 | BP $1,388.95 | Gap $2,481.35 | 278.6%
- Walmart / MP | WB40VTRED | Badger / Lithium | Actual $689.95 | BP $0.00 | Gap $689.95 | N/A
- Walmart / MP | WB20VTRSBL | Badger / Lithium | Actual $473.94 | BP $0.00 | Gap $473.94 | N/A
- Walmart / MP | WB52CCEA | Badger / Gas | Actual $279.00 | BP $0.00 | Gap $279.00 | N/A

## EXECUTIVE VIEW

Live KPI cards: Actual $84,091; BP $1,090,123; Attainment 7.71%; Gap $-1,006,032; overall Actual CM / CM Gap shown as N/A.

## CHANNEL HEALTH VIEW

Live four-channel matrix bound to `01 Business Performance` / `Channel Health`.

## BUSINESS DRIVER VIEW

Live Brand × Power gap ranking bound to the filtered `Business Drivers` view.

## THD DFC VIEW

Phase 4 DFC data reused unchanged; live `Daily Trend` line chart uses Date × GMV.

## KEY FINDINGS VIEW

Four current-data findings generated dynamically: MAIN RISK, WHY, WATCH, and STRENGTH.

## DATA FRESHNESS

Sales through 8/10 | DFC through 8/10 | CM Aug MTD | Operating Cost Aug MTD | CM exact cutoff unknown

## VISUAL CHANGES

Replaced the prior layout with KPI cards, Channel Health, dynamic What Matters cards, Brand × Power ranking, Top 5 detractors/overperformers, five filter dimensions, DFC trend, and freshness card.

## 3-MINUTE WEEKLY REVIEW TEST

PASS — reopened the Dashboard link, verified STATUS → PROBLEM → DRIVER → SKU → OPPORTUNITY, five filter dimensions, and DFC trend without navigating through Base tables or doing manual calculations.

## TESTS

Targeted Phase 5R/SKU BP tests: 10/10 PASS. Full suite: 60/65 PASS; five pre-existing failures are caused by current Actual raw-workbook hash drift versus the frozen B05F snapshot and are outside this write scope.

## SOURCE MUTATION

Workbook mutation = NONE

## FILES MODIFIED

`src/storm_v2/sku_bp.py`; `src/storm_v2/phase5r.py`; `tests/test_sku_bp.py`; `tests/test_phase5r.py`; `reports/phase5r/phase5r_package.json`; `reports/phase5r/phase5r_completion_report.md`.

## FEISHU COMPONENTS CREATED / REMOVED / REPLACED

Created/replaced in new Base only: 4 governed tables, 117-row SKU chain, 21-row business layer, 17-row DFC layer, 11-row findings layer, filtered views, KPI cards, Channel Health table, dynamic text cards, Brand × Power ranking, Top 5 tables, Date × GMV line chart, and five slicers. Old Dashboard components were removed/replaced; old Base was not modified.

## KNOWN LIMITATIONS

Overall Actual CM and CM Gap remain N/A because no compatible overall source exists; driver-level CM is not allocated.
