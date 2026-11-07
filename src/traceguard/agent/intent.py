"""Closed intent labels and deterministic keyword classification."""

from enum import Enum


class Intent(str, Enum):
    IS_PAID = "IS_PAID"
    WHY_FAILURE = "WHY_FAILURE"
    EVIDENCE_SUPPORT = "EVIDENCE_SUPPORT"
    GENERAL_STATUS = "GENERAL_STATUS"


def classify_intent(question: str) -> Intent:
    """Classify using the fixed keyword precedence from Architecture Section 4.2."""
    normalized = question.lower()
    if any(word in normalized for word in ("evidence", "support", "proof", "cite")):
        return Intent.EVIDENCE_SUPPORT
    if "fail" in normalized or normalized.startswith("why"):
        return Intent.WHY_FAILURE
    if any(word in normalized for word in ("paid", "payment", "pay", "refund", "status")):
        return Intent.IS_PAID
    return Intent.GENERAL_STATUS
