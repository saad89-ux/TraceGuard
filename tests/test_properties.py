"""Property-based and metamorphic tests using Hypothesis (Milestone M2)."""

import json

from hypothesis import given
from hypothesis import strategies as st

from traceguard.core.index import EventIndex
from traceguard.core.ingest import parse_line
from traceguard.core.reconcile import reconcile_order
from traceguard.models import Event, QuarantinedRecord


def _build_index(lines: list[str]) -> tuple[EventIndex, list[QuarantinedRecord]]:
    valid_events: list[Event] = []
    quarantined: list[QuarantinedRecord] = []
    for i, line in enumerate(lines, start=1):
        rec = parse_line(line, line_number=i)
        if isinstance(rec, Event):
            valid_events.append(rec)
        else:
            quarantined.append(rec)
    index = EventIndex.from_events(valid_events)
    return index, quarantined


# Standard valid event lines for order O-201
BASE_EVENTS = [
    json.dumps({
        "tenant_id": "T1",
        "order_id": "O-201",
        "event_id": "order-1",
        "source": "checkout",
        "type": "ORDER_CREATED",
        "occurred_at": "2026-11-01T10:00:00Z",
        "ingested_at": "2026-11-01T10:00:05Z",
        "amount_cents": 12900,
        "currency": "USD",
    }),
    json.dumps({
        "tenant_id": "T1",
        "order_id": "O-201",
        "event_id": "pay-1",
        "source": "payments",
        "type": "PAYMENT_FAILED",
        "occurred_at": "2026-11-01T10:02:00Z",
        "ingested_at": "2026-11-01T10:02:05Z",
        "attempt_id": "A1",
    }),
    json.dumps({
        "tenant_id": "T1",
        "order_id": "O-201",
        "event_id": "pay-2",
        "source": "payments",
        "type": "PAYMENT_CAPTURED",
        "occurred_at": "2026-11-01T10:05:00Z",
        "ingested_at": "2026-11-01T10:05:02Z",
        "attempt_id": "A2",
        "capture_id": "cap-1",
        "amount_cents": 12900,
        "currency": "USD",
    }),
]


@given(st.permutations(BASE_EVENTS))
def test_property_shuffle_invariance(shuffled_lines: list[str]) -> None:
    """Metamorphic test: Any permutation of input events yields identical financial results."""
    idx_base, quar_base = _build_index(BASE_EVENTS)
    res_base = reconcile_order(idx_base, "T1", "O-201", quar_base)

    idx_shuffled, quar_shuffled = _build_index(shuffled_lines)
    res_shuffled = reconcile_order(idx_shuffled, "T1", "O-201", quar_shuffled)

    assert res_shuffled.status == res_base.status
    assert res_shuffled.captured_cents == res_base.captured_cents
    assert res_shuffled.refunded_cents == res_base.refunded_cents
    assert res_shuffled.net_paid_cents == res_base.net_paid_cents
    assert res_shuffled.anomalies == res_base.anomalies
    assert res_shuffled.evidence_event_ids == res_base.evidence_event_ids
    assert res_shuffled.confidence == res_base.confidence


@given(st.integers(min_value=1, max_value=5))
def test_property_duplicate_injection(dup_count: int) -> None:
    """Property test: Inserting identical duplicates does not change totals or status."""
    dup_lines = list(BASE_EVENTS)
    for i in range(dup_count):
        # Create identical duplicate with varying ingested_at
        dup = json.loads(BASE_EVENTS[2])
        dup["ingested_at"] = f"2026-11-01T10:06:{i:02d}Z"
        dup_lines.append(json.dumps(dup))

    idx_base, quar_base = _build_index(BASE_EVENTS)
    res_base = reconcile_order(idx_base, "T1", "O-201", quar_base)

    idx_dups, quar_dups = _build_index(dup_lines)
    res_dups = reconcile_order(idx_dups, "T1", "O-201", quar_dups)

    assert res_dups.status == res_base.status
    assert res_dups.captured_cents == res_base.captured_cents
    assert res_dups.refunded_cents == res_base.refunded_cents
    assert res_dups.net_paid_cents == res_base.net_paid_cents
    assert res_dups.anomalies == res_base.anomalies
    assert res_dups.evidence_event_ids == res_base.evidence_event_ids
    assert res_dups.confidence == res_base.confidence


@given(st.integers(min_value=100, max_value=99999))
def test_property_tenant_isolation(other_amount: int) -> None:
    """Property test: Adding other-tenant events with the same order ID does not alter the result."""
    other_tenant_event = json.dumps({
        "tenant_id": "T2",
        "order_id": "O-201",
        "event_id": "order-t2",
        "source": "checkout",
        "type": "ORDER_CREATED",
        "occurred_at": "2026-11-01T10:00:00Z",
        "ingested_at": "2026-11-01T10:00:05Z",
        "amount_cents": other_amount,
        "currency": "EUR",
    })
    combined_lines = list(BASE_EVENTS) + [other_tenant_event]

    idx_base, quar_base = _build_index(BASE_EVENTS)
    res_base = reconcile_order(idx_base, "T1", "O-201", quar_base)

    idx_combined, quar_combined = _build_index(combined_lines)
    res_combined = reconcile_order(idx_combined, "T1", "O-201", quar_combined)

    assert res_combined.status == res_base.status
    assert res_combined.captured_cents == res_base.captured_cents
    assert res_combined.refunded_cents == res_base.refunded_cents
    assert res_combined.net_paid_cents == res_base.net_paid_cents
    assert res_combined.anomalies == res_base.anomalies
    assert res_combined.evidence_event_ids == res_base.evidence_event_ids
    assert res_combined.confidence == res_base.confidence


@given(st.text(min_size=1, max_size=200))
def test_property_note_mutation(note_content: str) -> None:
    """Property test: Adding, mutating, or editing a support note never alters financial state.

    (status, captured_cents, refunded_cents, net_paid_cents, evidence_event_ids remain identical).
    """
    note_event = json.dumps({
        "tenant_id": "T1",
        "order_id": "O-201",
        "event_id": "note-mutated",
        "source": "support",
        "type": "NOTE",
        "occurred_at": "2026-11-01T10:00:00Z",
        "ingested_at": "2026-11-01T10:00:05Z",
        "text": note_content,
    })
    lines_with_note = list(BASE_EVENTS) + [note_event]

    idx_base, quar_base = _build_index(BASE_EVENTS)
    res_base = reconcile_order(idx_base, "T1", "O-201", quar_base)

    idx_note, quar_note = _build_index(lines_with_note)
    res_note = reconcile_order(idx_note, "T1", "O-201", quar_note)

    # Financial results MUST remain identical
    assert res_note.status == res_base.status
    assert res_note.captured_cents == res_base.captured_cents
    assert res_note.refunded_cents == res_base.refunded_cents
    assert res_note.net_paid_cents == res_base.net_paid_cents
    assert res_note.evidence_event_ids == res_base.evidence_event_ids
    assert "note-mutated" not in res_note.evidence_event_ids
