"""Typed shared state for the fixed investigation graph."""

from typing import TypedDict

from traceguard.agent.intent import Intent
from traceguard.core.index import EventIndex
from traceguard.core.notes import NotesChannel
from traceguard.models import QuarantinedRecord, ReconResult, ToolResponse


class GraphState(TypedDict, total=False):
    events_path: str
    tenant_id: str
    order_id: str
    question: str
    intent: Intent
    index: EventIndex
    quarantined: list[QuarantinedRecord]
    tool_plan: tuple[str, ...]
    order_response: ToolResponse
    payment_response: ToolResponse
    notes_response: ToolResponse
    notes_channel: NotesChannel
    result: ReconResult
    explanation: str
    output: dict[str, object]
