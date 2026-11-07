"""Tests for record validation, parsing, and quarantine (Milestone M1)."""

import json
from pathlib import Path

import pytest

from traceguard.core.ingest import ingest_events, parse_line
from traceguard.models import (
    AnomalySeverity,
    EventType,
    QuarantinedRecord,
)


def _valid_order_line() -> str:
    return json.dumps({
        "tenant_id": "T1",
        "order_id": "O-201",
        "event_id": "order-1",
        "source": "checkout",
        "type": "ORDER_CREATED",
        "occurred_at": "2026-11-01T10:00:00Z",
        "ingested_at": "2026-11-01T10:00:05Z",
        "amount_cents": 12900,
        "currency": "USD",
    })


def _valid_capture_line() -> str:
    return json.dumps({
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
    })


# -------------------------------------------------------------------------
# Test Check 1: INVALID_JSON
# -------------------------------------------------------------------------
def test_check_1_invalid_json() -> None:
    line = "{malformed-json"
    res = parse_line(line, line_number=1)
    assert isinstance(res, QuarantinedRecord)
    assert res.reason_code == "INVALID_JSON"
    assert res.line_number == 1
    assert res.tenant_id is None
    assert res.order_id is None


def test_check_1_non_object_json() -> None:
    for non_obj in ["123", '["array"]', '"string"']:
        res = parse_line(non_obj, line_number=2)
        assert isinstance(res, QuarantinedRecord)
        assert res.reason_code == "INVALID_JSON"


# -------------------------------------------------------------------------
# Test Check 2: MISSING_FIELD
# -------------------------------------------------------------------------
@pytest.mark.parametrize(
    "missing_field",
    [
        "tenant_id",
        "order_id",
        "event_id",
        "source",
        "type",
        "occurred_at",
        "ingested_at",
    ],
)
def test_check_2_missing_required_fields(missing_field: str) -> None:
    data = json.loads(_valid_order_line())
    del data[missing_field]
    res = parse_line(json.dumps(data), line_number=3)
    assert isinstance(res, QuarantinedRecord)
    assert res.reason_code == "MISSING_FIELD"


def test_check_2_empty_string_required_fields() -> None:
    data = json.loads(_valid_order_line())
    data["tenant_id"] = "   "
    res = parse_line(json.dumps(data), line_number=4)
    assert isinstance(res, QuarantinedRecord)
    assert res.reason_code == "MISSING_FIELD"


# -------------------------------------------------------------------------
# Test Check 3: UNSUPPORTED_TYPE
# -------------------------------------------------------------------------
def test_check_3_unsupported_type() -> None:
    data = json.loads(_valid_order_line())
    data["type"] = "PAYMENT_PENDING"
    res = parse_line(json.dumps(data), line_number=5)
    assert isinstance(res, QuarantinedRecord)
    assert res.reason_code == "UNSUPPORTED_TYPE"


# -------------------------------------------------------------------------
# Test Check 4: SOURCE_NOT_ALLOWED
# -------------------------------------------------------------------------
def test_check_4_source_not_allowed_checkout_for_captured() -> None:
    data = json.loads(_valid_capture_line())
    data["source"] = "checkout"  # must be payments
    res = parse_line(json.dumps(data), line_number=6)
    assert isinstance(res, QuarantinedRecord)
    assert res.reason_code == "SOURCE_NOT_ALLOWED"


def test_check_4_source_not_allowed_support_for_capture() -> None:
    data = json.loads(_valid_capture_line())
    data["source"] = "support"  # rule 02: capture from support ignored
    res = parse_line(json.dumps(data), line_number=7)
    assert isinstance(res, QuarantinedRecord)
    assert res.reason_code == "SOURCE_NOT_ALLOWED"


# -------------------------------------------------------------------------
# Test Check 5: INVALID_TIMESTAMP (e.g. golden O-217)
# -------------------------------------------------------------------------
def test_check_5_invalid_occurred_at() -> None:
    data = json.loads(_valid_capture_line())
    data["occurred_at"] = "not-a-timestamp"
    res = parse_line(json.dumps(data), line_number=8)
    assert isinstance(res, QuarantinedRecord)
    assert res.reason_code == "INVALID_TIMESTAMP"


def test_check_5_invalid_ingested_at() -> None:
    data = json.loads(_valid_capture_line())
    data["ingested_at"] = "2026-99-99T99:99:99"
    res = parse_line(json.dumps(data), line_number=9)
    assert isinstance(res, QuarantinedRecord)
    assert res.reason_code == "INVALID_TIMESTAMP"


# -------------------------------------------------------------------------
# Test Check 6: MISSING_TXN_ID
# -------------------------------------------------------------------------
def test_check_6_missing_capture_id_on_payment_captured() -> None:
    data = json.loads(_valid_capture_line())
    del data["capture_id"]
    res = parse_line(json.dumps(data), line_number=10)
    assert isinstance(res, QuarantinedRecord)
    assert res.reason_code == "MISSING_TXN_ID"


def test_check_6_missing_refund_id_on_refund_issued() -> None:
    data = {
        "tenant_id": "T1",
        "order_id": "O-201",
        "event_id": "ref-1",
        "source": "payments",
        "type": "REFUND_ISSUED",
        "occurred_at": "2026-11-01T11:00:00Z",
        "ingested_at": "2026-11-01T11:00:02Z",
        "capture_id": "cap-1",
        # missing refund_id
        "amount_cents": 2000,
        "currency": "USD",
    }
    res = parse_line(json.dumps(data), line_number=11)
    assert isinstance(res, QuarantinedRecord)
    assert res.reason_code == "MISSING_TXN_ID"


# -------------------------------------------------------------------------
# Test Check 7: INVALID_AMOUNT (strict int, rejection of bool/float/str)
# -------------------------------------------------------------------------
@pytest.mark.parametrize(
    "bad_amount",
    [
        True,       # bool is subclass of int in Python, MUST be rejected
        False,
        129.50,     # float rejected
        "12900",    # str rejected
        0,          # captures and orders must have amount > 0
        -500,       # negative rejected
    ],
)
def test_check_7_invalid_amounts(bad_amount: object) -> None:
    data = json.loads(_valid_order_line())
    data["amount_cents"] = bad_amount
    res = parse_line(json.dumps(data), line_number=12)
    assert isinstance(res, QuarantinedRecord)
    assert res.reason_code == "INVALID_AMOUNT"


# -------------------------------------------------------------------------
# Test Check 8: INVALID_CURRENCY
# -------------------------------------------------------------------------
@pytest.mark.parametrize("bad_curr", ["usd", "US", "USDD", "123", "U$D"])
def test_check_8_invalid_currency(bad_curr: str) -> None:
    data = json.loads(_valid_order_line())
    data["currency"] = bad_curr
    res = parse_line(json.dumps(data), line_number=13)
    assert isinstance(res, QuarantinedRecord)
    assert res.reason_code == "INVALID_CURRENCY"


# -------------------------------------------------------------------------
# Test Check Order & Priority (First failing check determines reason)
# -------------------------------------------------------------------------
def test_validation_check_order_precedence() -> None:
    # Line has both unsupported type AND invalid timestamp AND invalid amount
    data = {
        "tenant_id": "T1",
        "order_id": "O-201",
        "event_id": "e-1",
        "source": "payments",
        "type": "UNKNOWN_CUSTOM_TYPE",
        "occurred_at": "bad-date",
        "ingested_at": "bad-date",
        "amount_cents": "not-int",
    }
    # Check 3 (UNSUPPORTED_TYPE) runs before Check 5 (INVALID_TIMESTAMP) or Check 7
    res = parse_line(json.dumps(data), line_number=14)
    assert isinstance(res, QuarantinedRecord)
    assert res.reason_code == "UNSUPPORTED_TYPE"


# -------------------------------------------------------------------------
# Test Attribution, Severity, and Anomaly formatting (Assumption A13)
# -------------------------------------------------------------------------
def test_attribution_and_severity_payments_fatal() -> None:
    # Golden O-217 case: payments record with bad timestamp
    data = json.loads(_valid_capture_line())
    data["occurred_at"] = "invalid-ts"
    rec = parse_line(json.dumps(data), line_number=42)
    assert isinstance(rec, QuarantinedRecord)
    assert rec.is_attributable("T1", "O-201")
    assert rec.anomaly_severity() == AnomalySeverity.FATAL
    assert rec.to_anomaly_string() == "INVALID_TIMESTAMP:pay-2"


def test_attribution_and_severity_source_not_allowed_info() -> None:
    # SOURCE_NOT_ALLOWED is INFO severity
    data = json.loads(_valid_capture_line())
    data["source"] = "support"
    rec = parse_line(json.dumps(data), line_number=50)
    assert isinstance(rec, QuarantinedRecord)
    assert rec.is_attributable("T1", "O-201")
    assert rec.anomaly_severity() == AnomalySeverity.INFO
    assert rec.to_anomaly_string() == "SOURCE_NOT_ALLOWED:pay-2"


def test_attribution_ref_fallback_to_line_number() -> None:
    # Malformed line with missing event_id falls back to line-<N> (A13)
    data = {
        "tenant_id": "T1",
        "order_id": "O-201",
        "source": "payments",
        "type": "PAYMENT_CAPTURED",
        "occurred_at": "2026-11-01T10:00:00Z",
        "ingested_at": "2026-11-01T10:00:05Z",
        "capture_id": "cap-1",
        "amount_cents": 100,
        "currency": "USD",
        # event_id missing
    }
    rec = parse_line(json.dumps(data), line_number=77)
    assert isinstance(rec, QuarantinedRecord)
    assert rec.is_attributable("T1", "O-201")
    assert rec.to_anomaly_string() == "MISSING_FIELD:line-77"


def test_unattributable_record_not_raised_for_order() -> None:
    # Corrupt line with missing tenant_id/order_id
    rec = parse_line("{corrupt", line_number=99)
    assert isinstance(rec, QuarantinedRecord)
    assert not rec.is_attributable("T1", "O-201")
    assert rec.to_anomaly_for_order("T1", "O-201") is None


# -------------------------------------------------------------------------
# Test Size Caps (Architecture Section 5 S2)
# -------------------------------------------------------------------------
def test_line_length_cap() -> None:
    huge_line = " " * (70 * 1024)
    rec = parse_line(huge_line, line_number=1)
    assert isinstance(rec, QuarantinedRecord)
    assert rec.reason_code == "INVALID_JSON"


# -------------------------------------------------------------------------
# Test Streaming Ingestion & Blank Lines
# -------------------------------------------------------------------------
def test_ingest_events_streaming(tmp_path: Path) -> None:
    file_path = tmp_path / "events.jsonl"
    lines = [
        "",  # blank line skipped silently
        _valid_order_line(),
        "   ",  # whitespace line skipped silently
        _valid_capture_line(),
        "{bad-json",  # quarantined
    ]
    file_path.write_text("\n".join(lines), encoding="utf-8")

    result = ingest_events(file_path)
    assert len(result.valid_events) == 2
    assert len(result.quarantined) == 1
    assert result.quarantined[0].reason_code == "INVALID_JSON"
    assert result.valid_events[0].type == EventType.ORDER_CREATED
    assert result.valid_events[1].type == EventType.PAYMENT_CAPTURED
    assert result.valid_events[1].amount_cents == 12900


def test_ingest_enforces_configurable_maximum_event_count(tmp_path: Path) -> None:
    file_path = tmp_path / "events.jsonl"
    file_path.write_text(
        f"{_valid_order_line()}\n{_valid_capture_line()}",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="maximum event count"):
        ingest_events(file_path, max_events=1)


def test_ingest_caps_note_text_at_configured_length(tmp_path: Path) -> None:
    file_path = tmp_path / "events.jsonl"
    note = {
        "tenant_id": "T1",
        "order_id": "O-201",
        "event_id": "note-1",
        "source": "support",
        "type": "NOTE",
        "occurred_at": "2026-11-01T10:00:00Z",
        "ingested_at": "2026-11-01T10:00:05Z",
        "text": "x" * 20,
    }
    file_path.write_text(json.dumps(note), encoding="utf-8")

    result = ingest_events(file_path, max_note_length=8)

    assert len(result.valid_events) == 1
    assert result.valid_events[0].text == "x" * 8
