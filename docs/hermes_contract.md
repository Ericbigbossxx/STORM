# Hermes integration contract

Hermes is optional external infrastructure and is not a hard dependency of STORM v0.1. The adapter may exchange synthetic or evidence-backed JSON only; it may not write to Feishu, alter a final status, or touch platform accounts.

## `weekly_analyze`

Input:

- business health snapshot
- core SKU records
- open signals
- actions

Output:

- summary
- top changes
- risks
- opportunities
- recommended priorities
- evidence references
- confidence

## `action_validate`

Input:

- action
- baseline
- expected result
- success criteria
- current metrics and evidence

Output:

- suggested status
- actual result summary
- conclusion
- evidence references
- confidence

## `signal_triage`

Input:

- raw issue, risk, or opportunity text
- platform context
- available evidence

Output:

- signal type
- category
- priority
- business impact
- next step
- confidence

## Authority and probe policy

All outputs are advisory. The Feishu ledger stores human decisions separately. A future static probe may write its result only beneath ignored `data/snapshots/hermes_probe/`; probe failure must not block v0.1.
