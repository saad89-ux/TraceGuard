# TraceGuard

TraceGuard is an offline payment-dispute investigation service. It validates event records, reconstructs order payment state deterministically, flags inconsistencies, cites evidence IDs, and reports confidence. The CLI and tests need no credentials or external services.

## Setup and run

```bash
uv sync --extra dev
uv run pytest
uv run python run.py --events data/events.jsonl --tenant T1 --order O-201 --question "Was this order paid?"
```

Without uv:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python run.py --events data/events.jsonl --tenant T1 --order O-201 --question "Was this order paid?"
```

The CLI takes exactly four required options: `--events`, `--tenant`, `--order`, and `--question`. It writes one JSON object with eight fields to stdout. Diagnostics go to stderr. Missing or unusable input returns a nonzero code without a traceback.

To demonstrate bounded retries locally, set (for example) `TRACEGUARD_FAULTS=get_payment_events=fail,timeout,ok`. This only scripts offline tool outcomes; retry messages are written to stderr.

## Included data

`data/events.jsonl` contains 147 valid records, six malformed noise lines, and filler orders. It includes the Section 17 cases O-201 through O-221 and T2/O-201. O-218 and selected filler orders deliberately place a capture before the order event. The tests assert the expected status, totals, and anomaly codes for every listed scenario.

## Status and confidence

The deterministic core sets financial status and totals. Notes and question wording cannot change them.

- `LOW`: status is `UNKNOWN`, a fatal anomaly exists, or an essential order/payment tool failed.
- `MEDIUM`: status is established but a tool retried, the notes tool failed, an injection-like note was detected, or an informational anomaly exists.
- `HIGH`: status is established without anomalies, retries, or an injection-like note.

`UNKNOWN` always has null captured, refunded, and net totals. `UNPAID` has zero for all three. Notes are processed separately, never become evidence, and cannot set financial state.

## Assumptions

**Candidate completion required.** PRD Section 9 asks this README to enumerate assumptions A1–A12 from DataFlow Section 15 and A13–A17 from PRD Section 10. The M6 instruction allowlist permits DataFlow Section 17 and PRD Sections 9, 11, and 12, but excludes those two assumption sections; the user directed keeping that allowlist. This assumption inventory is **not complete**. Before submission, the candidate should review the cited sections, write each assumption here in their own words, and resolve the open note in `docs/OPEN_QUESTIONS.md`.

Other tracked implementation choices are recorded in `docs/OPEN_QUESTIONS.md`, including configurable ingest caps and the semicolon separator used when fault scripts name multiple tools.

## Build status

- P0: ingest and validation, deterministic reconciliation, notes isolation, tools and resilience, keyword intent, fixed workflow, offline CLI, and the Section 17 dataset are implemented.
- P1: LLM adapter, local tracer, and related gates are not part of this build yet.
- P2: optional provider integrations and session memory are omitted.

## Test record

Example of a real failure and fix from development:

- **Failing test:** M5 CLI test collection, `ModuleNotFoundError: run`.
- **Root cause:** pytest's import path contained `src` but not the repository root, so it could not import the root-level CLI module.
- **Fix:** run the real `run.py` entry point in a subprocess from its explicit repository path. The end-to-end CLI tests then passed.

Run the complete suite with `uv run pytest`. Tests block network connections.
