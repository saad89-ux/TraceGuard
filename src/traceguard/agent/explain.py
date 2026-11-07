"""Deterministic explanation generation and evidence verification."""

from traceguard.core.evidence_verifier import (
    build_template_explanation,
    verify_explanation,
)
from traceguard.core.notes import NotesChannel
from traceguard.models import ReconResult


def explain_result(
    result: ReconResult,
    notes: NotesChannel,
    *,
    event_ids: set[str],
    allowed_numbers: set[int],
    expected_amount: int | None,
    currency: str | None,
) -> str:
    """Build the template explanation and apply the G5 verifier before returning it."""
    text = build_template_explanation(
        result,
        notes_channel=notes,
        expected_amount=expected_amount,
        currency=currency,
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
