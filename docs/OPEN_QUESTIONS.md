# Open Questions and Conservative Decisions

Log of ambiguities found in the specifications or during development, along with the conservative choice made (fail-closed, `UNKNOWN` with anomaly, etc.).

| Date | Question | Where in spec | Conservative choice made |
|---|---|---|---|
| 2026-11-07 | What thresholds and overflow behavior should apply to the event-count and note-length caps? | Architecture Section 5, S2 | Use configurable limits: 100,000 nonblank records by default (reject the whole file with a controlled `ValueError` when exceeded) and 10,000 characters per note by default (truncate longer note text). Callers may override the limits. |
| 2026-11-07 | What maximum length should the notes sanitizer use? | DataFlow Section 10; Architecture Section 5, S2 | The notes channel uses a 2,000-character cap after the 10,000-character ingest cap. Review whether the stricter second cap is intended; only sanitized text reaches the injection detector. |
| 2026-11-07 | How should `TRACEGUARD_FAULTS` separate scripts for multiple tools? | PRD A14 gives a single-tool example (`tool=fail,timeout,ok`) without a multi-tool separator | Use semicolons between tool assignments and commas between outcomes, e.g. `get_order=fail,ok;get_support_notes=timeout`; reject unknown tools, duplicate assignments, and invalid outcomes. |
| 2026-11-07 | How can the README reproduce every assumption when its authoritative sections are excluded from the M6 read allowlist? | PRD Section 9 requires assumptions from DataFlow Section 15 and PRD Section 10; these were initially outside the M6 allowlist. | Resolved 2026-11-07: the user explicitly authorized reading both sections. README now lists A1-A12 from DataFlow Section 15 and A13-A17 from PRD Section 10. |
| 2026-11-07 | May M7 read PRD Section 10's MUST-get-right list? | M7's CLAUDE allowlist is Architecture 5-7 and PRD 8/M7, while the user's general rule asks to follow PRD Section 10. | Resolved by the user's explicit instruction to follow PRD Section 10 and previous authorization to read it; reread the section before checking M7's LLM isolation behavior. |
| 2026-11-07 | Does the G5 rejection marker conflict with the rule that an LLM must not set anomalies? | Architecture Section 6 says invalid LLM output falls back to the template and adds `LLM_OUTPUT_REJECTED`; PRD Section 10 says nothing from an LLM may set anomalies. | Keep the marker as a deterministic G5 validation diagnostic (the provider cannot return or set anomaly fields). Tests assert rejection preserves status, totals, and evidence. This follows the explicit Architecture Section 6 fallback while isolating it from financial truth. |

## Questions & Resolutions

No additional open questions are recorded.
