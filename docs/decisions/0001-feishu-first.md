# ADR 0001: Feishu-first control ledger

- Status: Accepted
- Date: 2026-08-07

## Context

STORM must support a real weekly operating review before a full data platform or executive dashboard is justified.

## Decision

Use a new Feishu Base as the v0.1 live Business Control Ledger. Keep schema, dimensions, status semantics, rules, documentation, and adapter contracts in this standalone repository.

## Consequences

- Weekly collaboration and human decisions can begin without live platform integrations.
- The repository does not become a second live database.
- Feishu implementation details remain behind `src/storm/adapters/feishu/`.
- Future APIs, Hermes workers, and dashboards consume the stable contract instead of replacing it.
- Existing Bases, projects, and platform accounts remain untouched.
