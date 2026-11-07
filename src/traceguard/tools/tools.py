"""Tenant-scoped, in-memory tools over the validated event index."""

from time import perf_counter

from traceguard.core.index import EventIndex
from traceguard.models import (
    EventType,
    QuarantinedRecord,
    ToolMeta,
    ToolResponse,
)

_index = EventIndex.from_events([])
_quarantined: list[QuarantinedRecord] = []


def configure_tools(
    index: EventIndex, quarantined: list[QuarantinedRecord] | None = None
) -> None:
    """Bind the run's already-ingested dataset for subsequent tool calls."""
    global _index, _quarantined
    _index = index
    _quarantined = list(quarantined or [])


def _response(
    tenant_id: str, order_id: str, types: set[EventType] | None
) -> ToolResponse:
    started = perf_counter()
    records = _index.get_order_events(tenant_id, order_id)
    if types is not None:
        records = [event for event in records if event.type in types]
    quarantine = [
        record
        for record in _quarantined
        if record.is_attributable(tenant_id, order_id)
    ]
    return ToolResponse(
        records=records,
        quarantined=quarantine,
        meta=ToolMeta(
            attempts=1,
            latency_ms=(perf_counter() - started) * 1000,
            outcome="ok",
        ),
    )


def get_order(tenant_id: str, order_id: str) -> ToolResponse:
    """Return ORDER_CREATED records for exactly the requested tenant/order."""
    return _response(tenant_id, order_id, {EventType.ORDER_CREATED})


def get_payment_events(tenant_id: str, order_id: str) -> ToolResponse:
    """Return payment lifecycle records for exactly the requested tenant/order."""
    return _response(
        tenant_id,
        order_id,
        {
            EventType.PAYMENT_FAILED,
            EventType.PAYMENT_CAPTURED,
            EventType.REFUND_ISSUED,
            EventType.CHARGEBACK_OPENED,
        },
    )


def get_support_notes(tenant_id: str, order_id: str) -> ToolResponse:
    """Return untrusted NOTE records separately from financial tool records."""
    return _response(tenant_id, order_id, {EventType.NOTE})
