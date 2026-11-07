"""Unit tests for EventIndex and file caching (Milestone M2)."""

import json
from pathlib import Path

from traceguard.core.index import EventIndex


def test_event_index_from_file_and_cache(tmp_path: Path) -> None:
    events_file = tmp_path / "events.jsonl"
    line = json.dumps({
        "tenant_id": "T1",
        "order_id": "O-999",
        "event_id": "ord-1",
        "source": "checkout",
        "type": "ORDER_CREATED",
        "occurred_at": "2026-11-01T10:00:00Z",
        "ingested_at": "2026-11-01T10:00:01Z",
        "amount_cents": 5000,
        "currency": "USD",
    })
    events_file.write_text(line + "\n", encoding="utf-8")

    idx1, quar1, hash1 = EventIndex.from_file(events_file)
    assert len(idx1.events) == 1
    assert len(quar1) == 0
    assert len(hash1) == 64

    # Second call should hit in-process cache with identical hash
    idx2, quar2, hash2 = EventIndex.from_file(events_file)
    assert hash2 == hash1
    assert idx2 is idx1
