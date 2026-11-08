# Decisions and tradeoffs

These responses were prepared with OpenAI Codex from the implementation and development record, then reviewed during a GitHub Copilot readiness pass. The accompanying [AI usage statement](AI_USAGE.md) describes both tools' contributions.

## 1. Most dangerous assumption

The most dangerous assumption is A9: a malformed input line without a usable tenant ID and order ID cannot be attributed and therefore cannot affect an order result. If that line represents a real capture, refund, or dispute, omitting it could make the reconstructed state wrong while leaving no safe way to associate the record with the requested order. The implementation quarantines it instead of guessing its tenant or order. At a larger deployment, I would surface quarantine counts and require the source system to repair or resend unattributable records.

## 2. What must never depend on an LLM

Financial status, captured/refunded/net totals, anomaly codes, and evidence event IDs must come only from validated records and deterministic reconciliation. The system computes that result before any LLM call. A provider may help choose a closed-set intent or word an explanation, but the explanation is checked against the result and falls back to a deterministic template if it fails verification. This keeps invented text from changing the financial answer.

## 3. When `UNKNOWN` is correct

`UNKNOWN` is correct when the available valid records cannot establish a reliable state. For example, O-217 contains a payment record with an invalid timestamp: it is quarantined and cannot be used as evidence. Returning `PAID` or `UNPAID` by guessing from incomplete history would claim more than the records support. The result preserves the fatal validation anomaly and uses null totals for `UNKNOWN`.

## 4. Hardest bug and verification

The evidence verifier was difficult because it had to reject several kinds of unsupported claims without rejecting valid explanations. Early tests found that arbitrary numeric counts such as `0` or `1` could pass and that malformed bracketed citations could be skipped. The fix allowed only numbers supported by result fields or verified counts, and checked every bracketed citation span. One revised test initially used the word “One” even though the rule checks digit-form integers; I corrected it to use `1`. The verifier suite then passed all 12 tests, including the hallucinated-ID, amount, status, count, and malformed-citation cases.

## 5. AI suggestion corrected

An initial Codex-generated workflow wired the concrete `MockProvider` and `LocalJsonlTracer` classes directly into the agent graph. The architecture import test caught that boundary violation: the agent layer should depend on adapter Protocols, while concrete implementations belong at the composition root. I moved provider and tracer selection to `run.py` and injected them into the graph. The architecture-import, agent, and adapter tests passed together (23 tests).

## 6. First bottleneck at one million events per day

The current default ingest limit is 100,000 nonblank events per input file, so a single daily file containing one million events would be rejected before throughput became the main concern. One million events per day averages about 11.6 events per second, but bursts, record size, and keeping validated events plus several in-memory indexes will affect capacity. I would first benchmark parsing and index construction with representative event sizes and burst patterns, recording throughput, peak memory, and quarantine counts. The measurements would show whether to raise the cap, partition files, or change the in-memory index design.

## 7. One more day of work

I would add a reproducible ingestion and memory benchmark at 100,000 and one million representative events, then use it to guide a streaming-to-index path that avoids retaining unnecessary intermediate collections. The tradeoff is added ingestion and cache complexity, especially around quarantine handling; I would keep the current deterministic reconciliation contract and avoid adding a database until measurements show it is needed.
