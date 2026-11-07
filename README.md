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

The following implementation assumptions and gap resolutions define how TraceGuard interprets the brief:

| ID | Assumption |
|---|---|
| A1 | `checkout` emits `ORDER_CREATED`, `payments` emits financial events, and `support` emits notes. |
| A2 | Every valid `CHARGEBACK_OPENED` is considered open because no close event exists in the input. |
| A3 | Duplicate comparison uses every field except `ingested_at`. |
| A4 | Repeated `capture_id`s with identical transaction substance are one capture; any substance difference raises `TXN_ID_CONFLICT`. |
| A5 | A verified payment failure is a valid `PAYMENT_FAILED` event from `payments`; checkout failures and note text do not count. |
| A6 | `UNKNOWN` always has null totals, including when there are no captures or failure evidence, because incomplete history cannot prove that nothing was captured. |
| A7 | Timestamps are validated but never determine ordering or results. |
| A8 | Amounts must be integers (not booleans, floats, or strings); capture, refund, and expected amounts must be positive. |
| A9 | A malformed line without a usable string `tenant_id` or `order_id` cannot be attributed and cannot affect a result; this risk is accepted and documented. |
| A10 | An injection-suspected note caps confidence at `MEDIUM`. |
| A11 | A capture and failure with the same `attempt_id` are contradictory and produce fatal `ATTEMPT_CONTRADICTION`. |
| A12 | A refund or chargeback that references a capture belonging to another order in the same tenant is an invalid reference. |
| A13 | When an attributable quarantined `payments` record raises a fatal anomaly, its reference uses its non-empty `event_id`, or `line-<N>` (the one-based input line number) if unavailable. Quarantined records never appear in `evidence_event_ids`. |
| A14 | Optional `TRACEGUARD_FAULTS` scripts can demonstrate bounded retries (for example, `get_payment_events=fail,timeout,ok`). The setting is read only by config, does not change CLI options or stdout, and retry messages go to stderr. |
| A15 | When distinct event IDs agree on capture substance, all of those IDs are cited as evidence; the amount is stated once. |
| A16 | Notes are fetched for every intent, so the injection warning and `MEDIUM` confidence cap do not depend on question wording. |
| A17 | Tier P2 is not built by default. If a provider switch is requested without a built provider, it falls back to the mock provider with a stderr warning. |

These are candidate assumptions to review and explain in your own words before submission. Other tracked implementation choices are recorded in `docs/OPEN_QUESTIONS.md`, including configurable ingest caps and the semicolon separator used when fault scripts name multiple tools.

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
