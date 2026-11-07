"""M4 tool scope, resilience, and fault injection tests."""

import time

import pytest

from traceguard.config import faults_from_environment
from traceguard.core.index import EventIndex
from traceguard.models import Event, EventSource, EventType, ToolResponse
from traceguard.tools.faults import FaultInjector
from traceguard.tools.resilience import call_tool
from traceguard.tools.tools import (
    configure_tools,
    get_order,
    get_payment_events,
    get_support_notes,
)


def _event(
    event_id: str, tenant: str, order: str, kind: EventType, source: EventSource
) -> Event:
    return Event(
        tenant_id=tenant,
        order_id=order,
        event_id=event_id,
        source=source,
        type=kind,
        occurred_at="2026-01-01T00:00:00Z",
        ingested_at="2026-01-01T00:00:01Z",
    )


def test_tools_return_only_records_for_requested_scope() -> None:
    events = [
        _event("order", "T1", "O1", EventType.ORDER_CREATED, EventSource.CHECKOUT),
        _event("capture", "T1", "O1", EventType.PAYMENT_CAPTURED, EventSource.PAYMENTS),
        _event("note", "T1", "O1", EventType.NOTE, EventSource.SUPPORT),
        _event("other", "T2", "O1", EventType.ORDER_CREATED, EventSource.CHECKOUT),
    ]
    configure_tools(EventIndex.from_events(events))

    assert [e.event_id for e in get_order("T1", "O1").records] == ["order"]
    assert [e.event_id for e in get_payment_events("T1", "O1").records] == ["capture"]
    assert [e.event_id for e in get_support_notes("T1", "O1").records] == ["note"]


def test_retry_succeeds_with_attempt_metadata_and_bounded_backoff() -> None:
    calls = 0

    def flaky() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            from traceguard.tools.resilience import ToolError

            raise ToolError("temporary")
        return "ok"

    result = call_tool("get_order", flaky, timeout_s=1, backoff_s=0)
    assert result == "ok"
    assert calls == 3


def test_exhausted_order_tool_returns_fatal_unknown_fallback() -> None:
    from traceguard.tools.resilience import ToolError

    def broken() -> None:
        raise ToolError("down")

    response = call_tool("get_order", broken, timeout_s=1, backoff_s=0)
    assert isinstance(response, ToolResponse)
    assert response.unavailable is True
    assert response.anomalies == ["TOOL_FAILURE:get_order"]
    assert response.confidence_cap is not None
    assert response.confidence_cap.value == "LOW"
    assert response.meta.attempts == 3


def test_exhausted_notes_tool_returns_info_medium_fallback() -> None:
    from traceguard.tools.resilience import ToolError

    def broken() -> None:
        raise ToolError("down")

    response = call_tool("get_support_notes", broken, timeout_s=1, backoff_s=0)
    assert isinstance(response, ToolResponse)
    assert response.unavailable is True
    assert response.anomalies == ["NOTES_UNAVAILABLE"]
    assert response.confidence_cap is not None
    assert response.confidence_cap.value == "MEDIUM"
    assert response.records == []


def test_timeout_counts_as_failed_attempt_and_eventually_falls_back() -> None:
    def too_slow() -> None:
        time.sleep(0.05)

    response = call_tool(
        "get_payment_events", too_slow, timeout_s=0.001, backoff_s=0
    )
    assert isinstance(response, ToolResponse)
    assert response.unavailable is True
    assert response.meta.attempts == 3


def test_fault_injector_consumes_scripted_fail_timeout_ok_sequence() -> None:
    injector = FaultInjector({"get_payment_events": ["fail", "timeout", "ok"]})
    calls = 0

    def operation() -> str:
        nonlocal calls
        calls += 1
        return "ok"

    result = call_tool(
        "get_payment_events",
        injector.wrap("get_payment_events", operation),
        timeout_s=1,
        backoff_s=0,
    )
    assert result == "ok"
    assert calls == 1
    assert injector.remaining("get_payment_events") == []


def test_validation_errors_are_not_retried() -> None:
    from traceguard.tools.resilience import ToolValidationError

    calls = 0

    def invalid() -> None:
        nonlocal calls
        calls += 1
        raise ToolValidationError("bad response")

    with pytest.raises(ToolValidationError):
        call_tool("get_order", invalid, timeout_s=1, backoff_s=0)
    assert calls == 1


def test_a14_fault_script_configuration_is_optional_and_parsed_in_config() -> None:
    assert faults_from_environment({}) is None
    injector = faults_from_environment(
        {"TRACEGUARD_FAULTS": "get_payment_events=fail,timeout,ok"}
    )
    assert injector is not None
    assert injector.remaining("get_payment_events") == ["fail", "timeout", "ok"]
