# Open Questions and Conservative Decisions

Log of ambiguities found in the specifications or during development, along with the conservative choice made (fail-closed, `UNKNOWN` with anomaly, etc.).

| Date | Question | Where in spec | Conservative choice made |
|---|---|---|---|
| 2026-11-07 | What thresholds and overflow behavior should apply to the event-count and note-length caps? | Architecture Section 5, S2 | Use configurable limits: 100,000 nonblank records by default (reject the whole file with a controlled `ValueError` when exceeded) and 10,000 characters per note by default (truncate longer note text). Callers may override the limits. |
| 2026-11-07 | What maximum length should the notes sanitizer use? | DataFlow Section 10; Architecture Section 5, S2 | The notes channel uses a 2,000-character cap after the 10,000-character ingest cap. Review whether the stricter second cap is intended; only sanitized text reaches the injection detector. |
| 2026-11-07 | How should `TRACEGUARD_FAULTS` separate scripts for multiple tools? | PRD A14 gives a single-tool example (`tool=fail,timeout,ok`) without a multi-tool separator | Use semicolons between tool assignments and commas between outcomes, e.g. `get_order=fail,ok;get_support_notes=timeout`; reject unknown tools, duplicate assignments, and invalid outcomes. |
| 2026-11-07 | How can the README reproduce every assumption when its authoritative sections are excluded from the M6 read allowlist? | PRD Section 9 requires assumptions from DataFlow Section 15 and PRD Section 10; CLAUDE M6 permits only DataFlow 17, PRD 9/11/12, and Architecture 11. User directed keeping that allowlist. | Keep the source-section boundary. Include a clearly marked candidate completion note linking the omitted sections by name, and do not claim the README assumption inventory is complete until those sections are explicitly allowed. |

## Questions & Resolutions

No additional open questions are recorded.
