"""Evidence verification and deterministic template explanation (Stage 8 / Gate G5 / C15).

Verifies that no explanation invents event IDs, monetary numbers, or conflicting status words.
"""

import re

from pydantic import BaseModel, ConfigDict

from traceguard.core.notes import NotesChannel
from traceguard.models import OrderStatus, ReconResult

BRACKETED_ID_REGEX = re.compile(r"\[([^\[\]]*)\]")
INTEGER_REGEX = re.compile(r"\b\d+\b")
ALL_STATUS_WORDS = [s.value for s in OrderStatus]


class VerificationResult(BaseModel):
    """Result of validating an explanation against the verified ReconResult."""

    model_config = ConfigDict(frozen=True)

    is_valid: bool
    violations: list[str]


def verify_explanation(
    text: str,
    result: ReconResult,
    allowed_evidence_ids: set[str],
    allowed_numbers: set[int] | None = None,
) -> VerificationResult:
    """Verify an explanation string against Gate G5 rules (Doc 1 Sec 11).

    1. Every bracketed ID exists in the input file and is in evidence_event_ids.
    2. Every integer outside bracketed IDs is an established total or count.
    3. No status word other than the result's actual status appears.
    """
    violations: list[str] = []

    # 1. Check bracketed IDs
    cited_ids = BRACKETED_ID_REGEX.findall(text)
    for cited in cited_ids:
        if cited not in allowed_evidence_ids or cited not in result.evidence_event_ids:
            violations.append(f"Cites unverified or non-evidence event ID: [{cited}]")

    # 2. Check standalone integers (outside bracketed IDs)
    text_without_brackets = BRACKETED_ID_REGEX.sub(" ", text)
    found_numbers = [int(n) for n in INTEGER_REGEX.findall(text_without_brackets)]

    permitted_numbers: set[int] = set(allowed_numbers or [])
    if result.captured_cents is not None:
        permitted_numbers.add(result.captured_cents)
    if result.refunded_cents is not None:
        permitted_numbers.add(result.refunded_cents)
    if result.net_paid_cents is not None:
        permitted_numbers.add(result.net_paid_cents)
    if result.duplicate_count is not None:
        permitted_numbers.add(result.duplicate_count)
    for num in found_numbers:
        if num not in permitted_numbers:
            violations.append(f"Contains unverified number: {num}")

    # 3. Check for conflicting status words
    for status_word in ALL_STATUS_WORDS:
        if status_word != result.status.value:
            # Look for whole word case-insensitive match
            pattern = rf"\b{re.escape(status_word)}\b"
            if re.search(pattern, text, re.IGNORECASE):
                violations.append(f"Mentions conflicting status word: {status_word}")

    return VerificationResult(
        is_valid=len(violations) == 0,
        violations=violations,
    )


def build_template_explanation(
    result: ReconResult,
    notes_channel: NotesChannel | None = None,
    expected_amount: int | None = None,
    currency: str | None = None,
) -> str:
    """Construct the canonical deterministic explanation template (Doc 1 Sec 11).

    Cites real bracketed IDs from evidence_event_ids and guaranteed to pass verification.
    """
    parts: list[str] = []

    curr_str = f" {currency}" if currency else ""
    if expected_amount is not None:
        parts.append(f"Order expected {expected_amount}{curr_str}.")

    # Status-specific description
    if result.status == OrderStatus.PAID:
        parts.append(f"Payment fully captured {result.captured_cents or 0}{curr_str}.")
    elif result.status == OrderStatus.PARTIALLY_PAID:
        parts.append(f"Payment partially captured {result.captured_cents or 0}{curr_str}.")
    elif result.status == OrderStatus.UNPAID:
        parts.append("No successful payment was captured.")
    elif result.status == OrderStatus.REFUNDED:
        parts.append(f"Payment was fully refunded {result.refunded_cents or 0}{curr_str}.")
    elif result.status == OrderStatus.PARTIALLY_REFUNDED:
        parts.append(f"Payment was partially refunded {result.refunded_cents or 0}{curr_str}.")
    elif result.status == OrderStatus.DISPUTED:
        parts.append("A chargeback was opened on this order.")
    else:  # UNKNOWN
        parts.append("Order status could not be established reliably.")

    # Cite evidence IDs
    if result.evidence_event_ids:
        cited_str = " ".join(f"[{eid}]" for eid in result.evidence_event_ids)
        parts.append(f"Evidence: {cited_str}.")

    # Duplicates ignored
    if result.duplicate_count > 0:
        plural = "s were" if result.duplicate_count > 1 else " was"
        parts.append(f"{result.duplicate_count} duplicate event{plural} ignored.")

    # Net paid
    if result.net_paid_cents is not None:
        parts.append(f"Net paid is {result.net_paid_cents}.")

    # Anomalies
    if result.anomalies:
        anomaly_codes = sorted({item.split(":", 1)[0] for item in result.anomalies})
        anom_str = ", ".join(anomaly_codes)
        parts.append(f"Anomalies: {anom_str}.")

    # Injection warning sentence if flagged
    if notes_channel and notes_channel.injection_suspected and notes_channel.warning_sentence:
        parts.append(notes_channel.warning_sentence)

    return " ".join(parts)
