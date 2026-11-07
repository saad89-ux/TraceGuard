"""Record validation, parsing, and quarantine (Stage 1 / Ingest).

Strictly follows the 8 ordered checks from DataFlow Section 5.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, TypeGuard

from pydantic import BaseModel, ConfigDict

from traceguard.models import (
    Event,
    EventSource,
    EventType,
    QuarantinedRecord,
)

MAX_LINE_LENGTH = 64 * 1024  # 64 KB cap (Architecture Sec. 5 S2)
MAX_EVENTS_PER_FILE = 100_000  # Conservative default; callers may lower or raise it.
MAX_NOTE_LENGTH = 10_000  # Characters retained from an untrusted note.
CURRENCY_REGEX = re.compile(r"^[A-Z]{3}$")

REQUIRED_BASE_FIELDS = (
    "tenant_id",
    "order_id",
    "event_id",
    "source",
    "type",
    "occurred_at",
    "ingested_at",
)

ALLOWED_SOURCES_BY_TYPE = {
    EventType.ORDER_CREATED: {EventSource.CHECKOUT.value},
    EventType.PAYMENT_FAILED: {EventSource.PAYMENTS.value},
    EventType.PAYMENT_CAPTURED: {EventSource.PAYMENTS.value},
    EventType.REFUND_ISSUED: {EventSource.PAYMENTS.value},
    EventType.CHARGEBACK_OPENED: {EventSource.PAYMENTS.value},
    EventType.NOTE: {EventSource.SUPPORT.value},
}


class IngestResult(BaseModel):
    """Result of streaming a JSONL event file."""

    model_config = ConfigDict(frozen=True)

    valid_events: list[Event]
    quarantined: list[QuarantinedRecord]


def _is_valid_iso8601(ts_str: str, *, require_timezone: bool = False) -> bool:
    """Validate an ISO 8601 timestamp, optionally requiring a timezone."""
    if not isinstance(ts_str, str) or not ts_str.strip():
        return False
    try:
        # Python 3.11+ supports 'Z' and timezone offsets natively
        parsed = datetime.fromisoformat(ts_str)
        return not require_timezone or parsed.utcoffset() is not None
    except (ValueError, TypeError):
        return False


def _is_strict_int(val: Any) -> TypeGuard[int]:
    """True only if val is a real int (rejecting bool, float, str)."""
    if isinstance(val, bool):  # In Python, bool is a subclass of int
        return False
    return isinstance(val, int)


def parse_line(
    line: str,
    line_number: int,
    *,
    max_note_length: int = MAX_NOTE_LENGTH,
) -> Event | QuarantinedRecord:
    """Validate one JSONL line according to the 8 ordered checks in DataFlow Section 5."""
    if (
        isinstance(max_note_length, bool)
        or not isinstance(max_note_length, int)
        or max_note_length < 0
    ):
        raise ValueError("max_note_length must be a non-negative integer")

    # Check S2: line length cap
    if len(line.encode("utf-8")) > MAX_LINE_LENGTH:
        return QuarantinedRecord(
            line_number=line_number,
            raw_line=line[:200] + "... (truncated)",
            reason_code="INVALID_JSON",
        )

    # 1. Valid JSON object?
    try:
        raw_obj = json.loads(line)
        if not isinstance(raw_obj, dict):
            return QuarantinedRecord(
                line_number=line_number,
                raw_line=line,
                reason_code="INVALID_JSON",
            )
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return QuarantinedRecord(
            line_number=line_number,
            raw_line=line,
            reason_code="INVALID_JSON",
        )

    # Helper to extract partial metadata for attribution (Doc 1 Sec 2, Sec 5, A13)
    def _quarantine(reason: str) -> QuarantinedRecord:
        tenant_id = raw_obj.get("tenant_id") if isinstance(raw_obj.get("tenant_id"), str) else None
        order_id = raw_obj.get("order_id") if isinstance(raw_obj.get("order_id"), str) else None
        event_id = raw_obj.get("event_id") if isinstance(raw_obj.get("event_id"), str) else None
        source = raw_obj.get("source") if isinstance(raw_obj.get("source"), str) else None
        return QuarantinedRecord(
            line_number=line_number,
            raw_line=line,
            reason_code=reason,
            tenant_id=tenant_id,
            order_id=order_id,
            event_id=event_id,
            source=source,
        )

    # 2. Required fields present and non-empty?
    for field in REQUIRED_BASE_FIELDS:
        val = raw_obj.get(field)
        if not isinstance(val, str) or not val.strip():
            return _quarantine("MISSING_FIELD")

    # 3. type is one of the 6 supported types?
    raw_type = raw_obj["type"]
    try:
        event_type = EventType(raw_type)
    except ValueError:
        return _quarantine("UNSUPPORTED_TYPE")

    # 4. source allowed for this type?
    raw_source = raw_obj["source"]
    allowed_sources = ALLOWED_SOURCES_BY_TYPE[event_type]
    if raw_source not in allowed_sources:
        return _quarantine("SOURCE_NOT_ALLOWED")
    event_source = EventSource(raw_source)

    # 5. occurred_at and ingested_at valid ISO 8601?
    if not _is_valid_iso8601(raw_obj["occurred_at"], require_timezone=True) or not _is_valid_iso8601(raw_obj["ingested_at"]):
        return _quarantine("INVALID_TIMESTAMP")

    # 6. Type-specific IDs present?
    capture_id = raw_obj.get("capture_id")
    refund_id = raw_obj.get("refund_id")

    if event_type in (EventType.PAYMENT_CAPTURED, EventType.CHARGEBACK_OPENED):
        if not isinstance(capture_id, str) or not capture_id.strip():
            return _quarantine("MISSING_TXN_ID")
    elif event_type == EventType.REFUND_ISSUED and (
        not isinstance(capture_id, str)
        or not capture_id.strip()
        or not isinstance(refund_id, str)
        or not refund_id.strip()
    ):
        return _quarantine("MISSING_TXN_ID")

    # 7. amount_cents a real int and positive where required?
    amount_cents = raw_obj.get("amount_cents")
    if event_type in (EventType.ORDER_CREATED, EventType.PAYMENT_CAPTURED, EventType.REFUND_ISSUED):
        if not _is_strict_int(amount_cents) or amount_cents <= 0:
            return _quarantine("INVALID_AMOUNT")
    elif (
        event_type != EventType.NOTE
        and "amount_cents" in raw_obj
        and raw_obj["amount_cents"] is not None
        and not _is_strict_int(amount_cents)
    ):
        return _quarantine("INVALID_AMOUNT")

    # 8. currency is 3 uppercase letters where required?
    currency = raw_obj.get("currency")
    if (
        event_type in (EventType.ORDER_CREATED, EventType.PAYMENT_CAPTURED, EventType.REFUND_ISSUED)
        and (not isinstance(currency, str) or not CURRENCY_REGEX.match(currency))
    ):
        return _quarantine("INVALID_CURRENCY")

    # Note fields: per Doc 1 Sec 3.3, any financial fields on a note are ignored
    if event_type == EventType.NOTE:
        amount_cents = None
        currency = None
        capture_id = None
        refund_id = None

    note_text = raw_obj.get("text") if isinstance(raw_obj.get("text"), str) else None
    if event_type == EventType.NOTE and note_text is not None:
        note_text = note_text[:max_note_length]

    return Event(
        tenant_id=raw_obj["tenant_id"].strip(),
        order_id=raw_obj["order_id"].strip(),
        event_id=raw_obj["event_id"].strip(),
        source=event_source,
        type=event_type,
        occurred_at=raw_obj["occurred_at"].strip(),
        ingested_at=raw_obj["ingested_at"].strip(),
        attempt_id=raw_obj.get("attempt_id") if isinstance(raw_obj.get("attempt_id"), str) else None,
        capture_id=capture_id if isinstance(capture_id, str) else None,
        refund_id=refund_id if isinstance(refund_id, str) else None,
        amount_cents=amount_cents if isinstance(amount_cents, int) else None,
        currency=currency if isinstance(currency, str) else None,
        text=note_text,
    )


def ingest_events(
    path: Path | str,
    *,
    max_events: int = MAX_EVENTS_PER_FILE,
    max_note_length: int = MAX_NOTE_LENGTH,
) -> IngestResult:
    """Stream JSONL file line-by-line, validating each line (never crashes).

    Blank lines are skipped silently.
    """
    if isinstance(max_events, bool) or not isinstance(max_events, int) or max_events < 1:
        raise ValueError("max_events must be a positive integer")
    if (
        isinstance(max_note_length, bool)
        or not isinstance(max_note_length, int)
        or max_note_length < 0
    ):
        raise ValueError("max_note_length must be a non-negative integer")

    valid_events: list[Event] = []
    quarantined: list[QuarantinedRecord] = []
    record_count = 0

    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"Events file not found: {file_path}")

    with file_path.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped:
                continue  # Blank lines skipped silently (Doc 1 Sec 3.1)
            if record_count >= max_events:
                raise ValueError(
                    f"Events file exceeds maximum event count of {max_events}"
                )
            record_count += 1
            record = parse_line(
                line,
                line_number=line_num,
                max_note_length=max_note_length,
            )
            if isinstance(record, Event):
                valid_events.append(record)
            else:
                quarantined.append(record)

    return IngestResult(valid_events=valid_events, quarantined=quarantined)
