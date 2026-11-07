# Open Questions and Conservative Decisions

Log of ambiguities found in the specifications or during development, along with the conservative choice made (fail-closed, `UNKNOWN` with anomaly, etc.).

| Date | Question | Where in spec | Conservative choice made |
|---|---|---|---|
| 2026-11-07 | What thresholds and overflow behavior should apply to the event-count and note-length caps? | Architecture Section 5, S2 | Use configurable limits: 100,000 nonblank records by default (reject the whole file with a controlled `ValueError` when exceeded) and 10,000 characters per note by default (truncate longer note text). Callers may override the limits. |
| 2026-11-07 | What maximum length should the notes sanitizer use? | DataFlow Section 10; Architecture Section 5, S2 | The notes channel uses a 2,000-character cap after the 10,000-character ingest cap. Review whether the stricter second cap is intended; only sanitized text reaches the injection detector. |

## Questions & Resolutions

No additional open questions are recorded.
