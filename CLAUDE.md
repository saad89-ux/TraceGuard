# TraceGuard

TraceGuard is an offline-capable payment-dispute investigation service for e-commerce orders with inconsistent event histories. It deterministically reconstructs financial state (`PAID`, `UNPAID`, `PARTIALLY_PAID`, `PARTIALLY_REFUNDED`, `REFUNDED`, `DISPUTED`, `UNKNOWN`) from validated records, flags anomalies, cites real event IDs, and reports confidence. Golden principle: an LLM is never the source of financial truth; the system runs fully offline with no credentials or external services.

## RESUME PROTOCOL (do this first in every session)
1. Read the "Progress tracker" below.
2. Run: `git status`, `git log --oneline -15`, test command, and read tails of `docs/DEV_LOG.md` and `docs/OPEN_QUESTIONS.md`.
3. If tests are red, fix them BEFORE doing anything else.
4. Read ONLY the spec sections listed for the current milestone in the table below, never whole files.
5. State in 3 lines: current milestone, what is done, what you will do now. Then begin work.
6. Before ending ANY session or when context gets long: update Progress tracker and "Last session / Next action", then commit.

## Spec files and authority
- Brief: `docs/spec/SharkStack AI Internship Assessment.pdf` (wins over everything).
- Business rules: `docs/spec/TraceGuard_DataFlow.md` (wins on business rules).
- Architecture: `docs/spec/TraceGuard_Architecture.md` (wins on structure and tooling).
- Scope & Priorities: `docs/spec/TraceGuard_PRD.md` (adds no business rules/structure; adds decisions D1-D3, gap resolutions A13-A17).
- Specs are read-only; never edit them. Log any ambiguity or conflict in `docs/OPEN_QUESTIONS.md`.

## Non-negotiable invariants
- LLM, memory, and notes can NEVER set status, totals, anomalies or evidence_event_ids. Financial result is computed before any LLM call.
- Key is `(tenant_id, order_id)`. Never combine tenants. Tools filter and reconciler re-asserts.
- No decision uses timestamps or "first/last seen". Output independent of arrival order, duplicates, notes, other tenants, and question wording (all 4 intents produce byte-identical output in default mode).
- `amount_cents` must be a real int: reject bool, float, str. Absent key == null when comparing duplicates. Dedup ignores only `ingested_at`.
- Run ALL integrity checks, collect ALL anomalies, then sort. Never stop at the first.
- `UNKNOWN` => captured/refunded/net all `null`. `UNPAID` => `0 / 0 / 0`.
- Evidence IDs must exist in input, are sorted, and are never note IDs. Quarantined records are never evidence (A13).
- Notes are untrusted data: separate channel, never reach reconciler, never raw into LLM prompt, warning sentence + `MEDIUM` cap only. Notes fetched for every intent (D1).
- stdout = exactly the 8-field JSON. Logs and `run_id` go to stderr. Exit 0 for any produced result; non-zero only for unusable invocation (e.g. missing file), no stack trace.
- Bounded retries only: max 3 attempts, no loops, at most 2 optional LLM calls per run.
- `core/` imports no `agent`, `tools`, `adapters`, `langgraph`, `litellm`, or `langsmith`.
- Tests never use the network (enforced via socket-block fixture).

## Tiers and decisions
- P0 (brief-mandatory): core engine, tools + resilience, keyword intent, template explainer, fixed graph, CLI, tests, dataset.
- P1 (design-required): LLMProvider Protocol, MockProvider with misbehaving mode, prompts, G5 output validation, local tracer with redaction, import tests.
- P2 (optional extras): LiteLLM, LangSmith, session memory, trace_summary.py.
- Decisions: P2 is NOT built (D2); no `litellm` dependency (D3); notes fetched for every intent (D1). Assumptions A13-A17 are in PRD Sec. 10 and listed in README.

## Commands
- Setup: `uv sync --extra dev` (verified)
- Run tests: `uv run pytest` (verified)
- Coverage: `uv run pytest --cov=traceguard` (verified)
- Lint: `uv run ruff check .` (verified)
- Type check: `uv run mypy src tests run.py` (verified)
- Security audit: `uv run pip-audit` (verified)
- CLI example: verified against `data/events.jsonl`. Command: `uv run python run.py --events data/events.jsonl --tenant T1 --order O-201 --question "Was this order paid?"`

## Module map
```
src/traceguard/
├── config.py
├── models.py
├── core/
│   ├── ingest.py
│   ├── index.py
│   ├── integrity.py
│   ├── reconcile.py
│   ├── notes.py
│   ├── confidence.py
│   └── evidence_verifier.py
├── tools/
│   ├── tools.py
│   ├── resilience.py
│   └── faults.py
├── agent/
│   ├── graph.py
│   ├── state.py
│   ├── intent.py
│   ├── explain.py
│   └── prompts.py
└── adapters/
    ├── llm_base.py
    ├── llm_mock.py
    └── tracing.py
tests/
├── conftest.py
├── test_core_*.py
├── test_tools_resilience.py
├── test_graph_*.py
├── test_adapters_*.py
├── test_architecture_imports.py
└── test_properties.py
```

## Milestones and spec sections to read
| Milestone | Scope | Read these sections only | Exit criterion |
|---|---|---|---|
| M1 | Models & ingest validation | DataFlow 3, 5; Architecture 5 (S1, S2); PRD 7.3, A13 | Ingest & quarantine tests green |
| M2 | Index, integrity, reconciler, confidence | DataFlow 6, 7, 8, 12, 13, 17; PRD 4.1, 4.2 | All Doc 1 Sec. 17 golden cases & properties green |
| M3 | Notes isolation & evidence verifier | DataFlow 10, 11; Architecture 5 (S5, G3, G5); PRD 7.2 | Notes injection & verifier tests green |
| M4 | Tool layer with resilience & faults | DataFlow 9; Architecture 1, 10; PRD A14 | Retry, fallback, timeout tests green |
| M5 | Keyword intent, template explainer, graph, CLI | Architecture 4, 10, 13; PRD 7.1, 7.2, A16 | CLI end-to-end green offline; four-intents test green |
| M6 | Dataset (100+ events), README, draft docs | DataFlow 17; PRD 9, 11, 12; Architecture 11 | Complete dataset & delivery items verified |
| M7 | LLM protocols, MockProvider, prompts, local tracer | Architecture 5, 6, 7; PRD 8, M7 | Misbehaving mock, tracer, G1-G6 & import tests green |
| M8 | Quality gates | Architecture 2, 16; PRD 6 (NFR-8) | ruff, mypy, pytest-cov, pip-audit all clean |
| M9 | P2 optional extras (skipped by D2) | PRD 8, 10 (D2, D3); Architecture 16 | Document omission in README |

## Progress tracker
- [x] M1: Ingest & validation (including configurable caps and timezone-required `occurred_at`)
- [x] M2: Core reconcile & golden tests
- [x] M3: Notes isolation & evidence verifier
- [x] M4: Tools & resilience
- [x] M5: LangGraph & CLI
- [x] M6: Dataset & documentation scaffolding (complete A1-A17 README inventory; candidate drafts retained)
- [ ] M7: LLM mock & local tracer
- [ ] M8: Quality gates
- [ ] M9: P2 review (skipped per D2)
- Current milestone: M7 (LLM protocols, mock provider, prompts, and local tracer; awaiting user approval).
- Last session: 2026-11-07, revalidated M1 and fixed ingestion accepting timezone-naive `occurred_at` values. Focused ingest tests: 38 passed; full suite: 122 passed; `ruff` and `mypy` clean. The suite reports 13 third-party LangSmith deprecation warnings.
- Next action: Wait for the user's instruction before starting another milestone.
- Decisions made and open questions: see `docs/DEV_LOG.md` and `docs/OPEN_QUESTIONS.md`.

## Working rules
- Test first: write failing test, observe failure, implement, confirm pass. Keep suite green. Never move on while red.
- One milestone at a time. Do not start next until exit criterion met and user approves.
- Commit after each milestone (and meaningful green step) with clear message (e.g. "M2: reconcile engine + golden tests").
- Honest logging: every failing test, root cause, fix, and wrong AI suggestion goes into `docs/DEV_LOG.md` immediately. Never invent entries.
- Ambiguity: do not guess. Choose most conservative option + record in `docs/OPEN_QUESTIONS.md`.
- No extra dependencies beyond Architecture Sec. 2. No `litellm`. No network in runtime or tests. No credentials anywhere; `.env` git-ignored.
- Never write final text for `DECISIONS.md` or `AI_USAGE.md`. Leave only clearly marked DRAFT files with bullet notes for candidate.
- Keep modules small, clean, and readable for live review explanation.

## Definition of done
Refer to PRD Section 9, Section 15, and Architecture Section 16.
