# STORM project instructions

1. Default to one main agent.
2. Read and inspect before editing.
3. Make the minimum sufficient change.
4. Do not scan unrelated directories or other Codex projects.
5. Never edit global Codex or Hermes configuration unless explicitly instructed.
6. Do not touch existing Feishu Bases; STORM may only use its separately approved Base.
7. Do not make platform-side business changes.
8. Treat STORM IDs, table names, field names, and schema names as contracts.
9. Preserve source evidence and provenance.
10. `UNKNOWN` is valid; never fabricate missing metrics or convert unknown data to `GREEN`.
11. Human-reviewed status overrides AI suggestions. AI output is advisory only.
12. Future integrations go through adapters; never add platform-specific logic to domain models.
13. Run focused tests first. Run broader validation only for phase acceptance or explicit requests.
14. Stop and report if required external permission is missing.
15. Do not place secrets, credentials, tokens, webhook URLs, live exports, or business data in this repository.
16. Do not implement Streamlit, live ingestion, scheduling, notifications, or autonomous write-back in v0.1.
17. Do not advance to a later build phase without explicit authorization.
