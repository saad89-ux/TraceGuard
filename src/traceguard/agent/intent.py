"""Closed intent labels and deterministic keyword classification."""

from traceguard.adapters.llm_base import LLMError, LLMProvider
from traceguard.agent.prompts import build_prompt
from traceguard.models import Intent, IntentOutput

__all__ = ["Intent", "classify_intent", "classify_intent_with_provider"]


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


def classify_intent_with_provider(question: str, provider: LLMProvider) -> Intent:
    """Use an optional provider for a closed intent label, falling back to keywords."""
    fallback = classify_intent(question)
    payload: dict[str, object] = {
        "question": question,
        "keyword_intent": fallback.value,
    }
    payload["structured_prompt"] = build_prompt("intent", payload)
    try:
        response = provider.complete("intent", payload, IntentOutput)
    except LLMError:
        return fallback
    if not isinstance(response, IntentOutput):
        return fallback
    return response.intent
