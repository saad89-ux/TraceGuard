"""Golden tests and unit tests for the core reconciliation engine (Milestone M2).

Covers all scenarios from DataFlow Section 17 (O-201 to O-221, T2/O-201)
and traceability rules from DataFlow Section 18 / PRD Section 4.
"""


from traceguard.core.index import EventIndex
from traceguard.core.ingest import parse_line
from traceguard.core.reconcile import reconcile_order
from traceguard.models import (
    ConfidenceLevel,
    Event,
    OrderStatus,
    QuarantinedRecord,
)


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


# -----------------------------------------------------------------------------
# Golden Test Scenarios (DataFlow Section 17)
# -----------------------------------------------------------------------------

def test_o201_normal_paid_with_failure_and_duplicate() -> None:
    """O-201: Normal, failed attempt A1, capture on A2, duplicate capture -> PAID (12900/0/12900), HIGH."""
    lines = [
        '{"tenant_id": "T1", "order_id": "O-201", "event_id": "order-1", "source": "checkout", "type": "ORDER_CREATED", "occurred_at": "2026-11-01T10:00:00Z", "ingested_at": "2026-11-01T10:00:05Z", "amount_cents": 12900, "currency": "USD"}',
        '{"tenant_id": "T1", "order_id": "O-201", "event_id": "pay-1", "source": "payments", "type": "PAYMENT_FAILED", "occurred_at": "2026-11-01T10:02:00Z", "ingested_at": "2026-11-01T10:02:05Z", "attempt_id": "A1"}',
        '{"tenant_id": "T1", "order_id": "O-201", "event_id": "pay-2", "source": "payments", "type": "PAYMENT_CAPTURED", "occurred_at": "2026-11-01T10:05:00Z", "ingested_at": "2026-11-01T10:05:02Z", "attempt_id": "A2", "capture_id": "cap-1", "amount_cents": 12900, "currency": "USD"}',
        '{"tenant_id": "T1", "order_id": "O-201", "event_id": "pay-2", "source": "payments", "type": "PAYMENT_CAPTURED", "occurred_at": "2026-11-01T10:05:00Z", "ingested_at": "2026-11-01T10:06:00Z", "attempt_id": "A2", "capture_id": "cap-1", "amount_cents": 12900, "currency": "USD"}',
    ]
    index, quar = _build_index(lines)
    result = reconcile_order(index=index, tenant_id="T1", order_id="O-201", quarantined=quar)

    assert result.status == OrderStatus.PAID
    assert result.captured_cents == 12900
    assert result.refunded_cents == 0
    assert result.net_paid_cents == 12900
    assert result.anomalies == []
    assert result.evidence_event_ids == ["order-1", "pay-1", "pay-2"]
    assert result.confidence == ConfidenceLevel.HIGH
    assert result.duplicate_count == 1


def test_o202_only_failures_no_capture() -> None:
    """O-202: Only failures, no capture -> UNPAID (0/0/0)."""
    lines = [
        '{"tenant_id": "T1", "order_id": "O-202", "event_id": "ord-1", "source": "checkout", "type": "ORDER_CREATED", "occurred_at": "2026-11-01T10:00:00Z", "ingested_at": "2026-11-01T10:00:01Z", "amount_cents": 5000, "currency": "USD"}',
        '{"tenant_id": "T1", "order_id": "O-202", "event_id": "fail-1", "source": "payments", "type": "PAYMENT_FAILED", "occurred_at": "2026-11-01T10:01:00Z", "ingested_at": "2026-11-01T10:01:01Z", "attempt_id": "A1"}',
        '{"tenant_id": "T1", "order_id": "O-202", "event_id": "fail-2", "source": "payments", "type": "PAYMENT_FAILED", "occurred_at": "2026-11-01T10:02:00Z", "ingested_at": "2026-11-01T10:02:01Z", "attempt_id": "A2"}',
    ]
    index, quar = _build_index(lines)
    result = reconcile_order(index=index, tenant_id="T1", order_id="O-202", quarantined=quar)

    assert result.status == OrderStatus.UNPAID
    assert result.captured_cents == 0
    assert result.refunded_cents == 0
    assert result.net_paid_cents == 0
    assert result.confidence == ConfidenceLevel.HIGH


def test_o203_under_captured() -> None:
    """O-203: Under-captured -> PARTIALLY_PAID (4000/0/4000)."""
    lines = [
        '{"tenant_id": "T1", "order_id": "O-203", "event_id": "ord-1", "source": "checkout", "type": "ORDER_CREATED", "occurred_at": "2026-11-01T10:00:00Z", "ingested_at": "2026-11-01T10:00:01Z", "amount_cents": 10000, "currency": "USD"}',
        '{"tenant_id": "T1", "order_id": "O-203", "event_id": "cap-1", "source": "payments", "type": "PAYMENT_CAPTURED", "occurred_at": "2026-11-01T10:02:00Z", "ingested_at": "2026-11-01T10:02:01Z", "capture_id": "c-1", "amount_cents": 4000, "currency": "USD"}',
    ]
    index, quar = _build_index(lines)
    result = reconcile_order(index=index, tenant_id="T1", order_id="O-203", quarantined=quar)

    assert result.status == OrderStatus.PARTIALLY_PAID
    assert result.captured_cents == 4000
    assert result.refunded_cents == 0
    assert result.net_paid_cents == 4000


def test_o204_partial_refund() -> None:
    """O-204: Partial refund -> PARTIALLY_REFUNDED (8000/2000/6000)."""
    lines = [
        '{"tenant_id": "T1", "order_id": "O-204", "event_id": "ord-1", "source": "checkout", "type": "ORDER_CREATED", "occurred_at": "2026-11-01T10:00:00Z", "ingested_at": "2026-11-01T10:00:01Z", "amount_cents": 8000, "currency": "USD"}',
        '{"tenant_id": "T1", "order_id": "O-204", "event_id": "cap-1", "source": "payments", "type": "PAYMENT_CAPTURED", "occurred_at": "2026-11-01T10:01:00Z", "ingested_at": "2026-11-01T10:01:01Z", "capture_id": "c-1", "amount_cents": 8000, "currency": "USD"}',
        '{"tenant_id": "T1", "order_id": "O-204", "event_id": "ref-1", "source": "payments", "type": "REFUND_ISSUED", "occurred_at": "2026-11-01T10:05:00Z", "ingested_at": "2026-11-01T10:05:01Z", "capture_id": "c-1", "refund_id": "r-1", "amount_cents": 2000, "currency": "USD"}',
    ]
    index, quar = _build_index(lines)
    result = reconcile_order(index=index, tenant_id="T1", order_id="O-204", quarantined=quar)

    assert result.status == OrderStatus.PARTIALLY_REFUNDED
    assert result.captured_cents == 8000
    assert result.refunded_cents == 2000
    assert result.net_paid_cents == 6000


def test_o205_full_refund() -> None:
    """O-205: Full refund -> REFUNDED (6000/6000/0)."""
    lines = [
        '{"tenant_id": "T1", "order_id": "O-205", "event_id": "ord-1", "source": "checkout", "type": "ORDER_CREATED", "occurred_at": "2026-11-01T10:00:00Z", "ingested_at": "2026-11-01T10:00:01Z", "amount_cents": 6000, "currency": "USD"}',
        '{"tenant_id": "T1", "order_id": "O-205", "event_id": "cap-1", "source": "payments", "type": "PAYMENT_CAPTURED", "occurred_at": "2026-11-01T10:01:00Z", "ingested_at": "2026-11-01T10:01:01Z", "capture_id": "c-1", "amount_cents": 6000, "currency": "USD"}',
        '{"tenant_id": "T1", "order_id": "O-205", "event_id": "ref-1", "source": "payments", "type": "REFUND_ISSUED", "occurred_at": "2026-11-01T10:05:00Z", "ingested_at": "2026-11-01T10:05:01Z", "capture_id": "c-1", "refund_id": "r-1", "amount_cents": 6000, "currency": "USD"}',
    ]
    index, quar = _build_index(lines)
    result = reconcile_order(index=index, tenant_id="T1", order_id="O-205", quarantined=quar)

    assert result.status == OrderStatus.REFUNDED
    assert result.captured_cents == 6000
    assert result.refunded_cents == 6000
    assert result.net_paid_cents == 0


def test_o206_chargeback() -> None:
    """O-206: Chargeback -> DISPUTED (5000/0/5000)."""
    lines = [
        '{"tenant_id": "T1", "order_id": "O-206", "event_id": "ord-1", "source": "checkout", "type": "ORDER_CREATED", "occurred_at": "2026-11-01T10:00:00Z", "ingested_at": "2026-11-01T10:00:01Z", "amount_cents": 5000, "currency": "USD"}',
        '{"tenant_id": "T1", "order_id": "O-206", "event_id": "cap-1", "source": "payments", "type": "PAYMENT_CAPTURED", "occurred_at": "2026-11-01T10:01:00Z", "ingested_at": "2026-11-01T10:01:01Z", "capture_id": "c-1", "amount_cents": 5000, "currency": "USD"}',
        '{"tenant_id": "T1", "order_id": "O-206", "event_id": "cb-1", "source": "payments", "type": "CHARGEBACK_OPENED", "occurred_at": "2026-11-01T10:05:00Z", "ingested_at": "2026-11-01T10:05:01Z", "capture_id": "c-1"}',
    ]
    index, quar = _build_index(lines)
    result = reconcile_order(index=index, tenant_id="T1", order_id="O-206", quarantined=quar)

    assert result.status == OrderStatus.DISPUTED
    assert result.captured_cents == 5000
    assert result.refunded_cents == 0
    assert result.net_paid_cents == 5000


def test_o207_over_capture() -> None:
    """O-207: Over-capture -> UNKNOWN (null totals, OVER_CAPTURE anomaly)."""
    lines = [
        '{"tenant_id": "T1", "order_id": "O-207", "event_id": "ord-1", "source": "checkout", "type": "ORDER_CREATED", "occurred_at": "2026-11-01T10:00:00Z", "ingested_at": "2026-11-01T10:00:01Z", "amount_cents": 5000, "currency": "USD"}',
        '{"tenant_id": "T1", "order_id": "O-207", "event_id": "cap-1", "source": "payments", "type": "PAYMENT_CAPTURED", "occurred_at": "2026-11-01T10:01:00Z", "ingested_at": "2026-11-01T10:01:01Z", "capture_id": "c-1", "amount_cents": 3000, "currency": "USD"}',
        '{"tenant_id": "T1", "order_id": "O-207", "event_id": "cap-2", "source": "payments", "type": "PAYMENT_CAPTURED", "occurred_at": "2026-11-01T10:02:00Z", "ingested_at": "2026-11-01T10:02:01Z", "capture_id": "c-2", "amount_cents": 3000, "currency": "USD"}',
    ]
    index, quar = _build_index(lines)
    result = reconcile_order(index=index, tenant_id="T1", order_id="O-207", quarantined=quar)

    assert result.status == OrderStatus.UNKNOWN
    assert result.captured_cents is None
    assert result.refunded_cents is None
    assert result.net_paid_cents is None
    assert any("OVER_CAPTURE" in a for a in result.anomalies)
    assert result.confidence == ConfidenceLevel.LOW


def test_o208_refund_references_missing_capture() -> None:
    """O-208: Refund points to cap-999 -> UNKNOWN (INVALID_REFUND_REFERENCE)."""
    lines = [
        '{"tenant_id": "T1", "order_id": "O-208", "event_id": "ord-1", "source": "checkout", "type": "ORDER_CREATED", "occurred_at": "2026-11-01T10:00:00Z", "ingested_at": "2026-11-01T10:00:01Z", "amount_cents": 5000, "currency": "USD"}',
        '{"tenant_id": "T1", "order_id": "O-208", "event_id": "ref-1", "source": "payments", "type": "REFUND_ISSUED", "occurred_at": "2026-11-01T10:05:00Z", "ingested_at": "2026-11-01T10:05:01Z", "capture_id": "cap-999", "refund_id": "r-1", "amount_cents": 2000, "currency": "USD"}',
    ]
    index, quar = _build_index(lines)
    result = reconcile_order(index=index, tenant_id="T1", order_id="O-208", quarantined=quar)

    assert result.status == OrderStatus.UNKNOWN
    assert result.captured_cents is None
    assert any("INVALID_REFUND_REFERENCE" in a for a in result.anomalies)


def test_o209_refund_exceeds_capture() -> None:
    """O-209: Two refunds together exceed capture -> UNKNOWN (REFUND_EXCEEDS_CAPTURE)."""
    lines = [
        '{"tenant_id": "T1", "order_id": "O-209", "event_id": "ord-1", "source": "checkout", "type": "ORDER_CREATED", "occurred_at": "2026-11-01T10:00:00Z", "ingested_at": "2026-11-01T10:00:01Z", "amount_cents": 5000, "currency": "USD"}',
        '{"tenant_id": "T1", "order_id": "O-209", "event_id": "cap-1", "source": "payments", "type": "PAYMENT_CAPTURED", "occurred_at": "2026-11-01T10:01:00Z", "ingested_at": "2026-11-01T10:01:01Z", "capture_id": "c-1", "amount_cents": 5000, "currency": "USD"}',
        '{"tenant_id": "T1", "order_id": "O-209", "event_id": "ref-1", "source": "payments", "type": "REFUND_ISSUED", "occurred_at": "2026-11-01T10:02:00Z", "ingested_at": "2026-11-01T10:02:01Z", "capture_id": "c-1", "refund_id": "r-1", "amount_cents": 3000, "currency": "USD"}',
        '{"tenant_id": "T1", "order_id": "O-209", "event_id": "ref-2", "source": "payments", "type": "REFUND_ISSUED", "occurred_at": "2026-11-01T10:03:00Z", "ingested_at": "2026-11-01T10:03:01Z", "capture_id": "c-1", "refund_id": "r-2", "amount_cents": 3000, "currency": "USD"}',
    ]
    index, quar = _build_index(lines)
    result = reconcile_order(index=index, tenant_id="T1", order_id="O-209", quarantined=quar)

    assert result.status == OrderStatus.UNKNOWN
    assert result.captured_cents is None
    assert any("REFUND_EXCEEDS_CAPTURE" in a for a in result.anomalies)


def test_o210_capture_id_reused_with_different_amounts() -> None:
    """O-210: capture_id reused with different amounts -> UNKNOWN (TXN_ID_CONFLICT)."""
    lines = [
        '{"tenant_id": "T1", "order_id": "O-210", "event_id": "ord-1", "source": "checkout", "type": "ORDER_CREATED", "occurred_at": "2026-11-01T10:00:00Z", "ingested_at": "2026-11-01T10:00:01Z", "amount_cents": 12900, "currency": "USD"}',
        '{"tenant_id": "T1", "order_id": "O-210", "event_id": "cap-1", "source": "payments", "type": "PAYMENT_CAPTURED", "occurred_at": "2026-11-01T10:01:00Z", "ingested_at": "2026-11-01T10:01:01Z", "capture_id": "c-dup", "amount_cents": 12900, "currency": "USD"}',
        '{"tenant_id": "T1", "order_id": "O-210", "event_id": "cap-2", "source": "payments", "type": "PAYMENT_CAPTURED", "occurred_at": "2026-11-01T10:02:00Z", "ingested_at": "2026-11-01T10:02:01Z", "capture_id": "c-dup", "amount_cents": 9900, "currency": "USD"}',
    ]
    index, quar = _build_index(lines)
    result = reconcile_order(index=index, tenant_id="T1", order_id="O-210", quarantined=quar)

    assert result.status == OrderStatus.UNKNOWN
    assert result.captured_cents is None
    assert any("TXN_ID_CONFLICT:c-dup" in a for a in result.anomalies)
    assert result.evidence_event_ids == ["cap-1", "cap-2", "ord-1"]


def test_cross_order_transaction_conflict_cites_in_scope_event() -> None:
    lines = [
        '{"tenant_id":"T1","order_id":"O-A","event_id":"ord-a","source":"checkout","type":"ORDER_CREATED","occurred_at":"2026-11-01T10:00:00Z","ingested_at":"2026-11-01T10:00:01Z","amount_cents":5000,"currency":"USD"}',
        '{"tenant_id":"T1","order_id":"O-A","event_id":"pay-a","source":"payments","type":"PAYMENT_CAPTURED","occurred_at":"2026-11-01T10:01:00Z","ingested_at":"2026-11-01T10:01:01Z","capture_id":"shared","amount_cents":5000,"currency":"USD"}',
        '{"tenant_id":"T1","order_id":"O-B","event_id":"ord-b","source":"checkout","type":"ORDER_CREATED","occurred_at":"2026-11-01T10:00:00Z","ingested_at":"2026-11-01T10:00:01Z","amount_cents":4000,"currency":"USD"}',
        '{"tenant_id":"T1","order_id":"O-B","event_id":"pay-b","source":"payments","type":"PAYMENT_CAPTURED","occurred_at":"2026-11-01T10:01:00Z","ingested_at":"2026-11-01T10:01:01Z","capture_id":"shared","amount_cents":4000,"currency":"USD"}',
    ]
    index, quarantined = _build_index(lines)

    result = reconcile_order(index, "T1", "O-A", quarantined)

    assert result.status == OrderStatus.UNKNOWN
    assert result.anomalies == ["TXN_ID_CONFLICT:shared"]
    assert result.evidence_event_ids == ["ord-a", "pay-a"]


def test_o211_same_event_id_different_amount() -> None:
    """O-211: Same event_id, different amount -> UNKNOWN (EVENT_ID_CONFLICT)."""
    lines = [
        '{"tenant_id": "T1", "order_id": "O-211", "event_id": "ord-1", "source": "checkout", "type": "ORDER_CREATED", "occurred_at": "2026-11-01T10:00:00Z", "ingested_at": "2026-11-01T10:00:01Z", "amount_cents": 5000, "currency": "USD"}',
        '{"tenant_id": "T1", "order_id": "O-211", "event_id": "pay-x", "source": "payments", "type": "PAYMENT_CAPTURED", "occurred_at": "2026-11-01T10:01:00Z", "ingested_at": "2026-11-01T10:01:01Z", "capture_id": "c-1", "amount_cents": 5000, "currency": "USD"}',
        '{"tenant_id": "T1", "order_id": "O-211", "event_id": "pay-x", "source": "payments", "type": "PAYMENT_CAPTURED", "occurred_at": "2026-11-01T10:01:00Z", "ingested_at": "2026-11-01T10:01:01Z", "capture_id": "c-1", "amount_cents": 4000, "currency": "USD"}',
    ]
    index, quar = _build_index(lines)
    result = reconcile_order(index=index, tenant_id="T1", order_id="O-211", quarantined=quar)

    assert result.status == OrderStatus.UNKNOWN
    assert any("EVENT_ID_CONFLICT:pay-x" in a for a in result.anomalies)


def test_o212_currency_mismatch() -> None:
    """O-212: Currency mismatch (order USD, capture EUR) -> UNKNOWN (CURRENCY_MISMATCH)."""
    lines = [
        '{"tenant_id": "T1", "order_id": "O-212", "event_id": "ord-1", "source": "checkout", "type": "ORDER_CREATED", "occurred_at": "2026-11-01T10:00:00Z", "ingested_at": "2026-11-01T10:00:01Z", "amount_cents": 5000, "currency": "USD"}',
        '{"tenant_id": "T1", "order_id": "O-212", "event_id": "cap-1", "source": "payments", "type": "PAYMENT_CAPTURED", "occurred_at": "2026-11-01T10:01:00Z", "ingested_at": "2026-11-01T10:01:01Z", "capture_id": "c-1", "amount_cents": 5000, "currency": "EUR"}',
    ]
    index, quar = _build_index(lines)
    result = reconcile_order(index=index, tenant_id="T1", order_id="O-212", quarantined=quar)

    assert result.status == OrderStatus.UNKNOWN
    assert any("CURRENCY_MISMATCH" in a for a in result.anomalies)


def test_o213_conflicting_order_definitions() -> None:
    """O-213: Conflicting order definitions -> UNKNOWN (ORDER_CONFLICT)."""
    lines = [
        '{"tenant_id": "T1", "order_id": "O-213", "event_id": "ord-1", "source": "checkout", "type": "ORDER_CREATED", "occurred_at": "2026-11-01T10:00:00Z", "ingested_at": "2026-11-01T10:00:01Z", "amount_cents": 5000, "currency": "USD"}',
        '{"tenant_id": "T1", "order_id": "O-213", "event_id": "ord-2", "source": "checkout", "type": "ORDER_CREATED", "occurred_at": "2026-11-01T10:01:00Z", "ingested_at": "2026-11-01T10:01:01Z", "amount_cents": 7000, "currency": "USD"}',
    ]
    index, quar = _build_index(lines)
    result = reconcile_order(index=index, tenant_id="T1", order_id="O-213", quarantined=quar)

    assert result.status == OrderStatus.UNKNOWN
    assert any("ORDER_CONFLICT" in a for a in result.anomalies)


def test_o214_payments_but_no_order_record() -> None:
    """O-214: Payments but no order record -> UNKNOWN (ORDER_MISSING)."""
    lines = [
        '{"tenant_id": "T1", "order_id": "O-214", "event_id": "cap-1", "source": "payments", "type": "PAYMENT_CAPTURED", "occurred_at": "2026-11-01T10:01:00Z", "ingested_at": "2026-11-01T10:01:01Z", "capture_id": "c-1", "amount_cents": 5000, "currency": "USD"}',
    ]
    index, quar = _build_index(lines)
    result = reconcile_order(index=index, tenant_id="T1", order_id="O-214", quarantined=quar)

    assert result.status == OrderStatus.UNKNOWN
    assert any("ORDER_MISSING" in a for a in result.anomalies)


def test_o215_order_only_no_payment_events() -> None:
    """O-215: Order only, no payment events -> UNKNOWN (rule 8 fallback, null totals)."""
    lines = [
        '{"tenant_id": "T1", "order_id": "O-215", "event_id": "ord-1", "source": "checkout", "type": "ORDER_CREATED", "occurred_at": "2026-11-01T10:00:00Z", "ingested_at": "2026-11-01T10:00:01Z", "amount_cents": 5000, "currency": "USD"}',
    ]
    index, quar = _build_index(lines)
    result = reconcile_order(index=index, tenant_id="T1", order_id="O-215", quarantined=quar)

    assert result.status == OrderStatus.UNKNOWN
    assert result.captured_cents is None
    assert result.refunded_cents is None
    assert result.net_paid_cents is None


def test_o217_capture_with_invalid_timestamp() -> None:
    """O-217: Capture with invalid timestamp -> UNKNOWN (INVALID_TIMESTAMP FATAL)."""
    lines = [
        '{"tenant_id": "T1", "order_id": "O-217", "event_id": "ord-1", "source": "checkout", "type": "ORDER_CREATED", "occurred_at": "2026-11-01T10:00:00Z", "ingested_at": "2026-11-01T10:00:01Z", "amount_cents": 5000, "currency": "USD"}',
        '{"tenant_id": "T1", "order_id": "O-217", "event_id": "cap-1", "source": "payments", "type": "PAYMENT_CAPTURED", "occurred_at": "bad-timestamp", "ingested_at": "2026-11-01T10:01:01Z", "capture_id": "c-1", "amount_cents": 5000, "currency": "USD"}',
    ]
    index, quar = _build_index(lines)
    result = reconcile_order(index=index, tenant_id="T1", order_id="O-217", quarantined=quar)

    assert result.status == OrderStatus.UNKNOWN
    assert result.captured_cents is None
    assert any("INVALID_TIMESTAMP:cap-1" in a for a in result.anomalies)


def test_o218_out_of_order_arrival() -> None:
    """O-218: Capture appears before order line -> PAID (5000/0/5000)."""
    lines = [
        '{"tenant_id": "T1", "order_id": "O-218", "event_id": "cap-1", "source": "payments", "type": "PAYMENT_CAPTURED", "occurred_at": "2026-11-01T10:05:00Z", "ingested_at": "2026-11-01T10:05:01Z", "capture_id": "c-1", "amount_cents": 5000, "currency": "USD"}',
        '{"tenant_id": "T1", "order_id": "O-218", "event_id": "ord-1", "source": "checkout", "type": "ORDER_CREATED", "occurred_at": "2026-11-01T10:00:00Z", "ingested_at": "2026-11-01T10:06:01Z", "amount_cents": 5000, "currency": "USD"}',
    ]
    index, quar = _build_index(lines)
    result = reconcile_order(index=index, tenant_id="T1", order_id="O-218", quarantined=quar)

    assert result.status == OrderStatus.PAID
    assert result.captured_cents == 5000
    assert result.refunded_cents == 0
    assert result.net_paid_cents == 5000


def test_o219_note_claims_paid_but_no_capture() -> None:
    """O-219: Note claims paid but no capture exists -> UNKNOWN (rule 8, notes are not evidence)."""
    lines = [
        '{"tenant_id": "T1", "order_id": "O-219", "event_id": "ord-1", "source": "checkout", "type": "ORDER_CREATED", "occurred_at": "2026-11-01T10:00:00Z", "ingested_at": "2026-11-01T10:00:01Z", "amount_cents": 5000, "currency": "USD"}',
        '{"tenant_id": "T1", "order_id": "O-219", "event_id": "note-1", "source": "support", "type": "NOTE", "occurred_at": "2026-11-01T10:05:00Z", "ingested_at": "2026-11-01T10:05:01Z", "text": "Customer confirmed order was paid in full."}',
    ]
    index, quar = _build_index(lines)
    result = reconcile_order(index=index, tenant_id="T1", order_id="O-219", quarantined=quar)

    assert result.status == OrderStatus.UNKNOWN
    assert result.captured_cents is None
    assert "note-1" not in result.evidence_event_ids


def test_o220_same_attempt_has_failure_and_capture() -> None:
    """O-220: Same attempt_id has failure and capture -> UNKNOWN (ATTEMPT_CONTRADICTION)."""
    lines = [
        '{"tenant_id": "T1", "order_id": "O-220", "event_id": "ord-1", "source": "checkout", "type": "ORDER_CREATED", "occurred_at": "2026-11-01T10:00:00Z", "ingested_at": "2026-11-01T10:00:01Z", "amount_cents": 5000, "currency": "USD"}',
        '{"tenant_id": "T1", "order_id": "O-220", "event_id": "fail-1", "source": "payments", "type": "PAYMENT_FAILED", "occurred_at": "2026-11-01T10:01:00Z", "ingested_at": "2026-11-01T10:01:01Z", "attempt_id": "A9"}',
        '{"tenant_id": "T1", "order_id": "O-220", "event_id": "cap-1", "source": "payments", "type": "PAYMENT_CAPTURED", "occurred_at": "2026-11-01T10:02:00Z", "ingested_at": "2026-11-01T10:02:01Z", "attempt_id": "A9", "capture_id": "c-1", "amount_cents": 5000, "currency": "USD"}',
    ]
    index, quar = _build_index(lines)
    result = reconcile_order(index=index, tenant_id="T1", order_id="O-220", quarantined=quar)

    assert result.status == OrderStatus.UNKNOWN
    assert any("ATTEMPT_CONTRADICTION" in a for a in result.anomalies)


def test_o221_dispute_plus_over_capture_step_1_beats_step_2() -> None:
    """O-221: Dispute plus over-capture -> UNKNOWN (step 1 beats step 2)."""
    lines = [
        '{"tenant_id": "T1", "order_id": "O-221", "event_id": "ord-1", "source": "checkout", "type": "ORDER_CREATED", "occurred_at": "2026-11-01T10:00:00Z", "ingested_at": "2026-11-01T10:00:01Z", "amount_cents": 5000, "currency": "USD"}',
        '{"tenant_id": "T1", "order_id": "O-221", "event_id": "cap-1", "source": "payments", "type": "PAYMENT_CAPTURED", "occurred_at": "2026-11-01T10:01:00Z", "ingested_at": "2026-11-01T10:01:01Z", "capture_id": "c-1", "amount_cents": 3000, "currency": "USD"}',
        '{"tenant_id": "T1", "order_id": "O-221", "event_id": "cap-2", "source": "payments", "type": "PAYMENT_CAPTURED", "occurred_at": "2026-11-01T10:02:00Z", "ingested_at": "2026-11-01T10:02:01Z", "capture_id": "c-2", "amount_cents": 3000, "currency": "USD"}',
        '{"tenant_id": "T1", "order_id": "O-221", "event_id": "cb-1", "source": "payments", "type": "CHARGEBACK_OPENED", "occurred_at": "2026-11-01T10:05:00Z", "ingested_at": "2026-11-01T10:05:01Z", "capture_id": "c-1"}',
    ]
    index, quar = _build_index(lines)
    result = reconcile_order(index=index, tenant_id="T1", order_id="O-221", quarantined=quar)

    assert result.status == OrderStatus.UNKNOWN
    assert result.captured_cents is None
    assert any("OVER_CAPTURE" in a for a in result.anomalies)


def test_t2_o201_tenant_collision() -> None:
    """T2 / O-201: Same order ID, other tenant, different amount -> UNPAID for T2."""
    lines = [
        # T1 order
        '{"tenant_id": "T1", "order_id": "O-201", "event_id": "ord-t1", "source": "checkout", "type": "ORDER_CREATED", "occurred_at": "2026-11-01T10:00:00Z", "ingested_at": "2026-11-01T10:00:01Z", "amount_cents": 12900, "currency": "USD"}',
        '{"tenant_id": "T1", "order_id": "O-201", "event_id": "cap-t1", "source": "payments", "type": "PAYMENT_CAPTURED", "occurred_at": "2026-11-01T10:05:00Z", "ingested_at": "2026-11-01T10:05:02Z", "capture_id": "c-1", "amount_cents": 12900, "currency": "USD"}',
        # T2 order with same order_id O-201
        '{"tenant_id": "T2", "order_id": "O-201", "event_id": "ord-t2", "source": "checkout", "type": "ORDER_CREATED", "occurred_at": "2026-11-01T10:00:00Z", "ingested_at": "2026-11-01T10:00:01Z", "amount_cents": 3000, "currency": "USD"}',
        '{"tenant_id": "T2", "order_id": "O-201", "event_id": "fail-t2", "source": "payments", "type": "PAYMENT_FAILED", "occurred_at": "2026-11-01T10:02:00Z", "ingested_at": "2026-11-01T10:02:01Z", "attempt_id": "A1"}',
    ]
    index, quar = _build_index(lines)

    res_t1 = reconcile_order(index=index, tenant_id="T1", order_id="O-201", quarantined=quar)
    assert res_t1.status == OrderStatus.PAID
    assert res_t1.captured_cents == 12900

    res_t2 = reconcile_order(index=index, tenant_id="T2", order_id="O-201", quarantined=quar)
    assert res_t2.status == OrderStatus.UNPAID
    assert res_t2.captured_cents == 0
    assert res_t2.evidence_event_ids == ["fail-t2", "ord-t2"]


def test_agreeing_capture_reuse_both_event_ids_cited() -> None:
    """Assumption A4 / A15: Same capture_id on 2 event IDs with identical substance cites both IDs once."""
    lines = [
        '{"tenant_id": "T1", "order_id": "O-300", "event_id": "ord-1", "source": "checkout", "type": "ORDER_CREATED", "occurred_at": "2026-11-01T10:00:00Z", "ingested_at": "2026-11-01T10:00:01Z", "amount_cents": 5000, "currency": "USD"}',
        '{"tenant_id": "T1", "order_id": "O-300", "event_id": "pay-a", "source": "payments", "type": "PAYMENT_CAPTURED", "occurred_at": "2026-11-01T10:01:00Z", "ingested_at": "2026-11-01T10:01:01Z", "attempt_id": "A1", "capture_id": "cap-shared", "amount_cents": 5000, "currency": "USD"}',
        '{"tenant_id": "T1", "order_id": "O-300", "event_id": "pay-b", "source": "payments", "type": "PAYMENT_CAPTURED", "occurred_at": "2026-11-01T10:02:00Z", "ingested_at": "2026-11-01T10:02:01Z", "attempt_id": "A1", "capture_id": "cap-shared", "amount_cents": 5000, "currency": "USD"}',
    ]
    index, quar = _build_index(lines)
    result = reconcile_order(index=index, tenant_id="T1", order_id="O-300", quarantined=quar)

    assert result.status == OrderStatus.PAID
    assert result.captured_cents == 5000  # counted only once
    assert result.evidence_event_ids == ["ord-1", "pay-a", "pay-b"]
