# Decisions and tradeoffs

These are AI-assisted discussion answers prepared with OpenAI Codex and GitHub Copilot from the project specifications, code, tests, and development record. They are not represented as the candidate's independently written words. Review the reasoning and examples before using them in a technical discussion.

## 1. Most dangerous assumption

The riskiest assumption is A9: a malformed record without a usable tenant ID and order ID cannot safely be assigned to an order. If it was a real payment, ignoring it could make the reconstructed result incomplete; guessing its owner could contaminate another tenant's result. TraceGuard quarantines the record and does not attribute it. In production, I would monitor quarantines and require the source system to repair and resend unattributable records.

## 2. What must never depend on an LLM

The financial status, totals, anomalies, and evidence IDs must come only from validated records and deterministic reconciliation. TraceGuard computes them before any provider is called. A language model may help classify a question or phrase an explanation, but its output is validated against the computed result and rejected in favor of a template if it is unsupported. That boundary prevents generated text from changing a financial decision.

## 3. When `UNKNOWN` is correct

`UNKNOWN` is correct when the available valid evidence cannot establish a reliable state, such as a fatal integrity error, missing essential order data, or exhausted essential tools. For example, O-217's payment record has an invalid timestamp, so it is quarantined rather than treated as proof of a capture. Claiming `PAID` or `UNPAID` would go beyond the usable evidence. For `UNKNOWN`, all three totals are `null`, and the relevant anomaly explains why.

## 4. Hardest bug and verification

The hardest issue was making explanation verification strict enough to reject unsupported amounts, statuses, and citations without rejecting valid evidence-backed explanations. The verifier now checks every bracketed citation and only permits numbers supported by the result or verified event data. Tests cover invented event IDs, unsupported amounts and counts, conflicting status claims, and malformed citations. The full verifier test module passed after those checks were added.

## 5. AI suggestion corrected

An initial AI-generated workflow imported concrete `MockProvider` and `LocalJsonlTracer` classes directly into the agent layer. That broke the architecture boundary: the agent should depend on Protocols, while concrete adapters belong at the composition root. The import test caught it. The implementation was changed to inject the Protocols and select concrete adapters outside the agent; the architecture, agent, and adapter tests then passed together.

## 6. First bottleneck at one million events per day

The current default cap is 100,000 nonblank events per input file, so a one-million-event daily file would be rejected before throughput became the first problem. At an even rate, one million events per day is about 11.6 events per second, but bursts and the in-memory event indexes could make memory and index-build time the practical limits. I would benchmark representative event sizes and burst rates, measuring throughput and peak memory, before raising the cap or changing the storage design.

## 7. One more day of work

I would build a reproducible ingestion and peak-memory benchmark at the current 100,000-event cap and at one million events. I would use those measurements to decide whether to optimize index construction, partition input files, or adopt a disk-backed index. I would not add a database preemptively: it adds complexity, and the current deterministic result and evidence behavior must remain unchanged.
