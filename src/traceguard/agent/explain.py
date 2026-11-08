"""Deterministic explanation generation and evidence verification."""

from traceguard.adapters.llm_base import LLMError, LLMProvider
from traceguard.agent.prompts import build_prompt
from traceguard.core.evidence_verifier import (
    build_template_explanation,
    verify_explanation,
)
from traceguard.core.notes import NotesChannel
from traceguard.models import Event, ExplainOutput, ReconResult


def llm_explanation_is_valid(
    response: ExplainOutput,
    result: ReconResult,
    *,
    allowed_event_ids: set[str],
    allowed_numbers: set[int],
) -> bool:
    """Apply G5 to the provider's structured status, evidence, and explanation."""
    if response.status != result.status:
        return False
    if response.evidence_event_ids != result.evidence_event_ids:
        return False
    verification = verify_explanation(
        response.text,
        result,
        allowed_evidence_ids=allowed_event_ids,
        allowed_numbers=allowed_numbers,
    )
    return verification.is_valid


def explain_result(
    result: ReconResult,
    notes: NotesChannel,
    *,
    event_ids: set[str],
    allowed_numbers: set[int],
    expected_amount: int | None,
    currency: str | None,
    events: list[Event] | None = None,
) -> str:
    """Build the template explanation and apply the G5 verifier before returning it."""
    text = build_template_explanation(
        result,
        notes_channel=notes,
        expected_amount=expected_amount,
        currency=currency,
        events=events,
    )
    verification = verify_explanation(
        text,
        result,
        allowed_evidence_ids=event_ids,
        allowed_numbers=allowed_numbers,
    )
    if verification.is_valid:
        return text

    safe_text = f"Order status: {result.status.value}."
    if notes.injection_suspected and notes.warning_sentence:
        safe_text = f"{safe_text} {notes.warning_sentence}"
    safe_verification = verify_explanation(
        safe_text,
        result,
        allowed_evidence_ids=event_ids,
    )
    if not safe_verification.is_valid:
        raise ValueError("Unable to construct a verified explanation")
    return safe_text


def explain_with_provider(
    result: ReconResult,
    notes: NotesChannel,
    *,
    event_ids: set[str],
    allowed_numbers: set[int],
    expected_amount: int | None,
    currency: str | None,
    events: list[Event] | None,
    provider: LLMProvider,
) -> tuple[str, bool]:
    """Use provider wording only after G5; return template text and rejection flag otherwise."""
    template = explain_result(
        result,
        notes,
        event_ids=event_ids,
        allowed_numbers=allowed_numbers,
        expected_amount=expected_amount,
        currency=currency,
        events=events,
    )
    payload: dict[str, object] = {
        "status": result.status.value,
        "totals": {
            "captured_cents": result.captured_cents,
            "refunded_cents": result.refunded_cents,
            "net_paid_cents": result.net_paid_cents,
        },
        "evidence_event_ids": result.evidence_event_ids,
        "anomaly_codes": sorted({item.split(":", 1)[0] for item in result.anomalies}),
        "counts": {"duplicates": result.duplicate_count},
        "template_explanation": template,
    }
    payload["structured_prompt"] = build_prompt("explain", payload)
    try:
        response = provider.complete("explain", payload, ExplainOutput)
    except LLMError:
        return template, True
    if not isinstance(response, ExplainOutput) or not llm_explanation_is_valid(
        response,
        result,
        allowed_event_ids=event_ids,
        allowed_numbers=allowed_numbers,
    ):
        return template, True
    return response.text, False
