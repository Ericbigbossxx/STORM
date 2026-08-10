# Weekly business control workflow

## Weekly cycle

1. Gather or update evidence-backed platform facts.
2. Update the single PLATFORM-level Business Health row for each Week × Market × Platform; leave Channel blank.
3. Update core, exception, and focus SKU records without filling unavailable quantitative metrics.
4. Review open Signals and their many-to-many related Actions.
5. Review prior Actions and validate those whose validation date has arrived.
6. Record actual result and conclusion; execution without outcome evidence stays `EXECUTED_WAITING_VALIDATION`.
7. Identify top risks and opportunities.
8. Set one next priority per platform and one overall weekly priority.
9. Complete human review. Human Decision is authoritative; AI fields remain advisory and optional.

## Weekly close and audit snapshot

Close the week in this order:

1. Mark `Snapshot Locked` on `01 Business Health` and `02 Core SKU Performance` after human review.
2. Export all four operational tables as one weekly snapshot.
3. Store the export under `data/snapshots/{week_id}/`.

`Snapshot Locked` is workflow control and must not exist on Action & Validation or Signal Register. The local four-table export is the historical audit record. Locking does not erase or replace Action/Signal lifecycle history.

## Meeting questions

The ledger must answer the current Walmart, THD, and Lowe's status; material changes; actions taken; validated outcomes; unvalidated or ineffective work; main risks/opportunities; and next-week priorities.
