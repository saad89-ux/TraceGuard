"""Deterministic financial reconciliation engine (Stage 6).

Implements the strict 8-step decision order from DataFlow Section 8.
Pure functions, no I/O, no LLM.
"""

from traceguard.core.confidence import calculate_confidence
from traceguard.core.index import EventIndex
from traceguard.core.integrity import (
    AnomalyItem,
    check_integrity,
)
from traceguard.models import (
    AnomalySeverity,
    ConfidenceLevel,
    OrderStatus,
    QuarantinedRecord,
    ReconResult,
)


def reconcile_order(
    index: EventIndex,
    tenant_id: str,
    order_id: str,
    quarantined: list[QuarantinedRecord] | None = None,
    order_or_payment_tool_failed: bool = False,
    notes_tool_failed: bool = False,
    any_tool_retried: bool = False,
    injection_suspected: bool = False,
) -> ReconResult:
    """Reconcile an order deterministically (DataFlow Section 8)."""
    # 1. Collect attributable quarantine anomalies (Doc 1 Sec 5, PRD A13)
    extra_anomalies: list[AnomalyItem] = []
    if quarantined:
        for q in quarantined:
            order_anom = q.to_anomaly_for_order(tenant_id, order_id)
            if order_anom:
                code_with_ref, severity = order_anom
                # Parse code and ref
                if ":" in code_with_ref:
                    code, ref = code_with_ref.split(":", 1)
                else:
                    code, ref = code_with_ref, None
                extra_anomalies.append(AnomalyItem(code=code, severity=severity, ref=ref))

    # 2. Retrieve valid events for this order and check integrity
    raw_events = index.get_order_events(tenant_id, order_id)
    integ = check_integrity(
        index=index,
        tenant_id=tenant_id,
        order_id=order_id,
        raw_events=raw_events,
        extra_anomalies=extra_anomalies,
    )

    all_anomalies = integ.anomalies

    # Gather evidence event IDs (excluding notes, sorted, Doc 1 Sec 8.3)
    # Agreeing capture group includes all distinct event IDs (Assumption A4, A15)
    evidence_events = (
        [e for e in integ.clean_events if e.type.value == "ORDER_CREATED"]
        + integ.agreeing_capture_events
        + integ.conflicting_events
        + integ.refunds
        + integ.failures
        + integ.chargebacks
    )
    # Deduplicate event IDs and sort lexicographically (rule 08)
    sorted_evidence_ids = sorted({e.event_id for e in evidence_events})

    # Prepare formatted anomaly strings and severity pairs
    anomaly_strings_with_severity: list[tuple[str, AnomalySeverity]] = [
        (a.to_string(), a.severity) for a in all_anomalies
    ]
    # Unique, sorted list of anomaly strings for output (Doc 1 Sec 8.4)
    formatted_anomalies = sorted({s for s, _ in anomaly_strings_with_severity})

    has_fatal_anomaly = any(sev == AnomalySeverity.FATAL for _, sev in anomaly_strings_with_severity)

    # Calculate preliminary sums
    captured = sum(c.amount_cents or 0 for c in integ.captures)
    refunded = sum(r.amount_cents or 0 for r in integ.refunds)

    # -------------------------------------------------------------------------
    # 8-step decision order (strict precedence: first matching row wins)
    # -------------------------------------------------------------------------

    # Step 1: Any FATAL anomaly, or missing essential order evidence
    if has_fatal_anomaly:
        status = OrderStatus.UNKNOWN
        captured_cents = None
        refunded_cents = None
        net_paid_cents = None
        confidence = ConfidenceLevel.LOW
        return ReconResult(
            status=status,
            captured_cents=captured_cents,
            refunded_cents=refunded_cents,
            net_paid_cents=net_paid_cents,
            anomalies=formatted_anomalies,
            evidence_event_ids=sorted_evidence_ids,
            confidence=confidence,
            duplicate_count=integ.duplicate_count,
        )

    # Step 2: At least one valid open chargeback
    if integ.chargebacks:
        status = OrderStatus.DISPUTED
        captured_cents = captured
        refunded_cents = refunded
        net_paid_cents = captured - refunded

    # Step 3: No captures AND at least one verified payment failure
    elif not integ.captures and integ.failures:
        status = OrderStatus.UNPAID
        captured_cents = 0
        refunded_cents = 0
        net_paid_cents = 0

    # Step 4: refunded == captured, both > 0
    elif refunded == captured and captured > 0:
        status = OrderStatus.REFUNDED
        captured_cents = captured
        refunded_cents = refunded
        net_paid_cents = 0

    # Step 5: 0 < refunded < captured
    elif 0 < refunded < captured:
        status = OrderStatus.PARTIALLY_REFUNDED
        captured_cents = captured
        refunded_cents = refunded
        net_paid_cents = captured - refunded

    # Step 6: captured == expected order amount
    elif integ.expected_order and captured == integ.expected_order.amount_cents:
        status = OrderStatus.PAID
        captured_cents = captured
        refunded_cents = refunded
        net_paid_cents = captured - refunded

    # Step 7: 0 < captured < expected order amount
    elif integ.expected_order and 0 < captured < integ.expected_order.amount_cents:
        status = OrderStatus.PARTIALLY_PAID
        captured_cents = captured
        refunded_cents = refunded
        net_paid_cents = captured - refunded

    # Step 8: Nothing established above -> UNKNOWN (all totals null)
    else:
        status = OrderStatus.UNKNOWN
        captured_cents = None
        refunded_cents = None
        net_paid_cents = None

    # Calculate confidence level (Doc 1 Sec 12)
    confidence = calculate_confidence(
        status=status,
        anomalies=anomaly_strings_with_severity,
        order_or_payment_tool_failed=order_or_payment_tool_failed,
        notes_tool_failed=notes_tool_failed,
        any_tool_retried=any_tool_retried,
        injection_suspected=injection_suspected,
    )

    return ReconResult(
        status=status,
        captured_cents=captured_cents,
        refunded_cents=refunded_cents,
        net_paid_cents=net_paid_cents,
        anomalies=formatted_anomalies,
        evidence_event_ids=sorted_evidence_ids,
        confidence=confidence,
        duplicate_count=integ.duplicate_count,
    )
