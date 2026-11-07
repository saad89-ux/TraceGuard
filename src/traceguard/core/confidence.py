"""Confidence calculation based exclusively on DataFlow Section 12.

Confidence is computed deterministically from the reconciliation result and run metadata.
"""

from traceguard.models import AnomalySeverity, ConfidenceLevel, OrderStatus


def calculate_confidence(
    status: OrderStatus,
    anomalies: list[tuple[str, AnomalySeverity]],
    order_or_payment_tool_failed: bool = False,
    notes_tool_failed: bool = False,
    any_tool_retried: bool = False,
    injection_suspected: bool = False,
) -> ConfidenceLevel:
    """Calculate confidence level (Doc 1 Sec 12).

    LOW:
      Status is UNKNOWN, or any FATAL anomaly exists, or get_order/get_payment_events failed.
    MEDIUM:
      Status is established but: a tool needed a retry, or get_support_notes failed,
      or injection note suspected, or any INFO anomaly exists.
    HIGH:
      Status established, no anomalies of any severity, no retries, no injection note.
    """
    has_fatal = any(sev == AnomalySeverity.FATAL for _, sev in anomalies)

    # 1. LOW condition
    if status == OrderStatus.UNKNOWN or has_fatal or order_or_payment_tool_failed:
        return ConfidenceLevel.LOW

    # 2. MEDIUM condition
    has_info = any(sev == AnomalySeverity.INFO for _, sev in anomalies)
    if (
        any_tool_retried
        or notes_tool_failed
        or injection_suspected
        or has_info
    ):
        return ConfidenceLevel.MEDIUM

    # 3. HIGH condition
    return ConfidenceLevel.HIGH
