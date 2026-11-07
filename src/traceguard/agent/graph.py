"""Fixed LangGraph workflow for offline payment investigations."""

from collections.abc import Callable
from typing import cast

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from traceguard.agent.explain import explain_result
from traceguard.agent.intent import Intent, classify_intent
from traceguard.agent.state import GraphState
from traceguard.config import faults_from_environment
from traceguard.core.index import EventIndex
from traceguard.core.notes import process_notes
from traceguard.core.reconcile import reconcile_order
from traceguard.models import (
    ConfidenceLevel,
    Event,
    EventType,
    OrderStatus,
    ReconResult,
    ToolMeta,
    ToolResponse,
)
from traceguard.tools.faults import FaultInjector
from traceguard.tools.resilience import call_tool
from traceguard.tools.tools import (
    configure_tools,
    get_order,
    get_payment_events,
    get_support_notes,
)

_TOOL_PLAN: dict[Intent, tuple[str, ...]] = {
    intent: ("get_order", "get_payment_events", "get_support_notes")
    for intent in Intent
}


def _load(state: GraphState) -> GraphState:
    index, quarantined, _ = EventIndex.from_file(state["events_path"])
    configure_tools(index, quarantined)
    return {"index": index, "quarantined": quarantined}


def _interpret(state: GraphState) -> GraphState:
    return {"intent": classify_intent(state["question"])}


def _plan(state: GraphState) -> GraphState:
    return {"tool_plan": _TOOL_PLAN[state["intent"]]}


def _fetch_response(
    tool_name: str,
    operation: Callable[[], ToolResponse],
    faults: FaultInjector | None,
    tenant_id: str,
    order_id: str,
    allowed_types: set[EventType],
) -> ToolResponse:
    if faults is not None:
        operation = faults.wrap(tool_name, operation)
    response = call_tool(tool_name, operation)
    if not isinstance(response, ToolResponse):
        raise TypeError(f"{tool_name} returned an invalid response type")
    if any(
        not isinstance(record, Event)
        or record.tenant_id != tenant_id
        or record.order_id != order_id
        or record.type not in allowed_types
        for record in response.records
    ) or any(
        not record.is_attributable(tenant_id, order_id)
        for record in response.quarantined
    ):
        return _controlled_fallback(tool_name, response.meta.attempts)
    return response


def _controlled_fallback(tool_name: str, attempts: int = 1) -> ToolResponse:
    if tool_name == "get_support_notes":
        anomaly = "NOTES_UNAVAILABLE"
        cap = ConfidenceLevel.MEDIUM
    else:
        anomaly = f"TOOL_FAILURE:{tool_name}"
        cap = ConfidenceLevel.LOW
    return ToolResponse(
        records=[],
        quarantined=[],
        meta=ToolMeta(attempts=attempts, latency_ms=0.0, outcome="unavailable"),
        anomalies=[anomaly],
        confidence_cap=cap,
        unavailable=True,
    )


def _fetch_order(state: GraphState, faults: FaultInjector | None) -> GraphState:
    return {
        "order_response": _fetch_response(
            "get_order",
            lambda: get_order(state["tenant_id"], state["order_id"]),
            faults,
            state["tenant_id"],
            state["order_id"],
            {EventType.ORDER_CREATED},
        )
    }


def _fetch_payments(state: GraphState, faults: FaultInjector | None) -> GraphState:
    return {
        "payment_response": _fetch_response(
            "get_payment_events",
            lambda: get_payment_events(state["tenant_id"], state["order_id"]),
            faults,
            state["tenant_id"],
            state["order_id"],
            {
                EventType.PAYMENT_FAILED,
                EventType.PAYMENT_CAPTURED,
                EventType.REFUND_ISSUED,
                EventType.CHARGEBACK_OPENED,
            },
        )
    }


def _fetch_notes(state: GraphState, faults: FaultInjector | None) -> GraphState:
    return {
        "notes_response": _fetch_response(
            "get_support_notes",
            lambda: get_support_notes(state["tenant_id"], state["order_id"]),
            faults,
            state["tenant_id"],
            state["order_id"],
            {EventType.NOTE},
        )
    }


def _reconcile(state: GraphState) -> GraphState:
    order_response = state["order_response"]
    payment_response = state["payment_response"]
    notes_response = state["notes_response"]
    notes_channel = process_notes(notes_response.records)
    if order_response.unavailable or payment_response.unavailable:
        failures = sorted(set(order_response.anomalies + payment_response.anomalies))
        result = ReconResult(
            status=OrderStatus.UNKNOWN,
            captured_cents=None,
            refunded_cents=None,
            net_paid_cents=None,
            anomalies=failures,
            evidence_event_ids=[],
            confidence=ConfidenceLevel.LOW,
        )
    else:
        events = order_response.records + payment_response.records
        index = EventIndex.from_events(events)
        result = reconcile_order(
            index,
            state["tenant_id"],
            state["order_id"],
            quarantined=order_response.quarantined,
            notes_tool_failed=notes_response.unavailable,
            any_tool_retried=any(
                response.meta.attempts > 1
                for response in (order_response, payment_response, notes_response)
            ),
            injection_suspected=notes_channel.injection_suspected,
        )
        if notes_response.unavailable:
            anomalies = sorted(set(result.anomalies + notes_response.anomalies))
            confidence = (
                ConfidenceLevel.LOW
                if result.status == OrderStatus.UNKNOWN
                else ConfidenceLevel.MEDIUM
            )
            result = result.model_copy(
                update={"anomalies": anomalies, "confidence": confidence}
            )

    return {"result": result, "notes_channel": notes_channel}


def _explain(state: GraphState) -> GraphState:
    result = state["result"]
    index = state["index"]
    relevant = index.get_order_events(state["tenant_id"], state["order_id"])
    event_ids = {event.event_id for event in index.events}
    allowed_numbers = {
        event.amount_cents for event in relevant if event.amount_cents is not None
    }
    order_amounts = {
        event.amount_cents
        for event in state["order_response"].records
        if event.amount_cents is not None
    }
    currencies = {
        event.currency
        for event in state["order_response"].records
        if event.currency is not None
    }
    expected_amount = next(iter(order_amounts)) if len(order_amounts) == 1 else None
    currency = next(iter(currencies)) if len(currencies) == 1 else None
    if expected_amount is not None:
        allowed_numbers.add(expected_amount)
    explanation = explain_result(
        result,
        state["notes_channel"],
        event_ids=event_ids,
        allowed_numbers=allowed_numbers,
        expected_amount=expected_amount if result.status != OrderStatus.UNKNOWN else None,
        currency=currency,
    )
    return {"explanation": explanation}


def _verify_and_finalize(state: GraphState) -> GraphState:
    result = state["result"]
    output: dict[str, object] = {
        "status": result.status.value,
        "captured_cents": result.captured_cents,
        "refunded_cents": result.refunded_cents,
        "net_paid_cents": result.net_paid_cents,
        "anomalies": result.anomalies,
        "evidence_event_ids": result.evidence_event_ids,
        "explanation": state["explanation"],
        "confidence": result.confidence.value,
    }
    return {"output": output}


def build_graph(
    faults: FaultInjector | None = None,
) -> CompiledStateGraph[GraphState, None, GraphState, GraphState]:
    """Compile the fixed, acyclic workflow (all intents fetch all three tools)."""
    graph = StateGraph(GraphState)
    graph.add_node("load_index", _load)
    graph.add_node("interpret_intent", _interpret)
    graph.add_node("plan_tools", _plan)
    graph.add_node("fetch_order", lambda state: _fetch_order(state, faults))
    graph.add_node("fetch_payment_events", lambda state: _fetch_payments(state, faults))
    graph.add_node("fetch_notes", lambda state: _fetch_notes(state, faults))
    graph.add_node("validate_and_reconcile", _reconcile)
    graph.add_node("explain", _explain)
    graph.add_node("verify_output", _verify_and_finalize)
    graph.add_edge(START, "load_index")
    graph.add_edge("load_index", "interpret_intent")
    graph.add_edge("interpret_intent", "plan_tools")
    graph.add_edge("plan_tools", "fetch_order")
    graph.add_edge("fetch_order", "fetch_payment_events")
    graph.add_edge("fetch_payment_events", "fetch_notes")
    graph.add_edge("fetch_notes", "validate_and_reconcile")
    graph.add_edge("validate_and_reconcile", "explain")
    graph.add_edge("explain", "verify_output")
    graph.add_edge("verify_output", END)
    return graph.compile()


def run_investigation(
    events_path: str,
    tenant_id: str,
    order_id: str,
    question: str,
) -> dict[str, object]:
    """Run the offline graph once and return the exact eight-field result object."""
    graph = build_graph(faults_from_environment())
    state = cast(
        GraphState,
        graph.invoke(
            {
                "events_path": str(events_path),
                "tenant_id": tenant_id,
                "order_id": order_id,
                "question": question,
            }
        ),
    )
    return state["output"]
