"""Index construction and in-process caching (Stage 2 / Scope and index).

Maintains tenant-level maps to detect collisions and identity conflicts across orders (Doc 1 Sec 6).
"""

import hashlib
from collections import defaultdict
from pathlib import Path
from typing import ClassVar

from traceguard.core.ingest import ingest_events
from traceguard.models import Event, EventType, QuarantinedRecord


class EventIndex:
    """In-memory index supporting O(1) order lookups and tenant-level integrity checks."""

    _file_cache: ClassVar[dict[str, tuple["EventIndex", list[QuarantinedRecord]]]] = {}

    def __init__(self, events: list[Event]) -> None:
        self.events = events
        self.by_order: dict[tuple[str, str], list[Event]] = defaultdict(list)
        self.identity_map: dict[tuple[str, str], list[Event]] = defaultdict(list)
        self.capture_map: dict[tuple[str, str], list[Event]] = defaultdict(list)
        self.refund_map: dict[tuple[str, str], list[Event]] = defaultdict(list)

        # Build in one streaming pass (Doc 1 Sec 6)
        for ev in events:
            self.by_order[(ev.tenant_id, ev.order_id)].append(ev)
            self.identity_map[(ev.tenant_id, ev.event_id)].append(ev)

            if ev.type == EventType.PAYMENT_CAPTURED and ev.capture_id:
                self.capture_map[(ev.tenant_id, ev.capture_id)].append(ev)
            elif ev.type == EventType.REFUND_ISSUED and ev.refund_id:
                self.refund_map[(ev.tenant_id, ev.refund_id)].append(ev)

    @classmethod
    def from_events(cls, events: list[Event]) -> "EventIndex":
        """Build index from pre-validated events."""
        return cls(events)

    @classmethod
    def from_file(
        cls, file_path: Path | str
    ) -> tuple["EventIndex", list[QuarantinedRecord], str]:
        """Stream and index a file, cached by file SHA-256 (Architecture Sec 8).

        Returns (index, quarantined_records, file_sha256).
        """
        path = Path(file_path)
        sha256_hash = hashlib.sha256()
        with path.open("rb") as f:
            while chunk := f.read(65536):
                sha256_hash.update(chunk)
        file_hash = sha256_hash.hexdigest()

        if file_hash in cls._file_cache:
            cached_index, cached_quar = cls._file_cache[file_hash]
            return cached_index, cached_quar, file_hash

        ingest_res = ingest_events(path)
        index = cls(ingest_res.valid_events)
        cls._file_cache[file_hash] = (index, ingest_res.quarantined)
        return index, ingest_res.quarantined, file_hash

    def get_order_events(self, tenant_id: str, order_id: str) -> list[Event]:
        """Retrieve all valid events for exactly that (tenant_id, order_id)."""
        return list(self.by_order.get((tenant_id, order_id), []))
