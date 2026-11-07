"""Integrity checks, deduplication, and anomaly collection (Stage 5).

Strictly follows DataFlow Section 7. All checks execute on the whole set,
collecting all anomalies before sorting (C5 to C11).
"""

from collections import defaultdict
from typing import NamedTuple

from traceguard.core.index import EventIndex
from traceguard.models import (
    AnomalySeverity,
    Event,
    EventType,
)


class AnomalyItem(NamedTuple):
    code: str
    severity: AnomalySeverity
    ref: str | None = None

    def to_string(self) -> str:
        if self.ref and self.ref.strip():
            return f"{self.code}:{self.ref.strip()}"
        return self.code


class OrderDefinition(NamedTuple):
    amount_cents: int
    currency: str


class IntegrityResult(NamedTuple):
    clean_events: list[Event]
    captures: list[Event]  # collapsed to unique captures
    refunds: list[Event]   # collapsed to unique refunds
    failures: list[Event]
    chargebacks: list[Event]
    expected_order: OrderDefinition | None
    anomalies: list[AnomalyItem]
    duplicate_count: int
    agreeing_capture_events: list[Event]  # distinct events representing agreed captures


def check_integrity(
    index: EventIndex,
    tenant_id: str,
    order_id: str,
    raw_events: list[Event],
    extra_anomalies: list[AnomalyItem] | None = None,
) -> IntegrityResult:
    """Run all deduplication and integrity checks on the entire record set (Doc 1 Sec 7)."""
    anomalies: list[AnomalyItem] = list(extra_anomalies or [])

    # 1. Assert tenant & order scope (C11: defense in depth against tenant collision)
    scoped_records: list[Event] = []
    for ev in raw_events:
        if ev.tenant_id != tenant_id or ev.order_id != order_id:
            anomalies.append(
                AnomalyItem("TENANT_LEAK", AnomalySeverity.FATAL, ref=ev.event_id)
            )
        else:
            scoped_records.append(ev)

    # 2. Deduplicate and detect Event Identity Conflicts (C5, C6)
    # Check across tenant via identity_map to catch collisions across different orders
    seen_event_ids: set[str] = set()
    clean_events: list[Event] = []
    duplicate_count = 0

    for ev in scoped_records:
        if ev.event_id in seen_event_ids:
            continue
        seen_event_ids.add(ev.event_id)

        all_records_with_id = index.identity_map.get((tenant_id, ev.event_id), [])
        if len(all_records_with_id) > 1:
            # Compare all substantive fields against the first record
            first_substance = all_records_with_id[0].substantive_fields()
            has_conflict = False
            for other in all_records_with_id[1:]:
                if other.substantive_fields() != first_substance:
                    has_conflict = True
                    break

            if has_conflict:
                anomalies.append(
                    AnomalyItem("EVENT_ID_CONFLICT", AnomalySeverity.FATAL, ref=ev.event_id)
                )
            else:
                # Identical duplicates
                duplicate_count += len(all_records_with_id) - 1

        clean_events.append(ev)

    # Separate event types from clean events (excluding NOTE from financial evidence)
    order_records = [e for e in clean_events if e.type == EventType.ORDER_CREATED]
    capture_records = [e for e in clean_events if e.type == EventType.PAYMENT_CAPTURED]
    refund_records = [e for e in clean_events if e.type == EventType.REFUND_ISSUED]
    failure_records = [
        e for e in clean_events if e.type == EventType.PAYMENT_FAILED and e.source.value == "payments"
    ]
    chargeback_records = [e for e in clean_events if e.type == EventType.CHARGEBACK_OPENED]

    # 3. Transaction Identity for Captures (C7)
    # Group captures by capture_id
    captures_by_id: dict[str, list[Event]] = defaultdict(list)
    for cap in capture_records:
        if cap.capture_id:
            captures_by_id[cap.capture_id].append(cap)

    unique_captures: list[Event] = []
    agreeing_capture_events: list[Event] = []

    for cap_id, cap_list in captures_by_id.items():
        # Check tenant-level capture_map to detect cross-order reuse
        all_tenant_caps = index.capture_map.get((tenant_id, cap_id), [])
        # Transaction substance: (order_id, attempt_id, amount_cents, currency)
        substances = {
            (c.order_id, c.attempt_id, c.amount_cents, c.currency) for c in all_tenant_caps
        }
        if len(substances) > 1:
            anomalies.append(
                AnomalyItem("TXN_ID_CONFLICT", AnomalySeverity.FATAL, ref=cap_id)
            )
        else:
            # Agreeing capture group: treat as one capture, count amount once
            unique_captures.append(cap_list[0])
            agreeing_capture_events.extend(cap_list)

    # 4. Transaction Identity for Refunds (C7)
    refunds_by_id: dict[str, list[Event]] = defaultdict(list)
    for ref in refund_records:
        if ref.refund_id:
            refunds_by_id[ref.refund_id].append(ref)

    unique_refunds: list[Event] = []
    for ref_id, ref_list in refunds_by_id.items():
        all_tenant_refs = index.refund_map.get((tenant_id, ref_id), [])
        # Transaction substance for refunds: (order_id, capture_id, amount_cents, currency)
        substances = {
            (r.order_id, r.capture_id, r.amount_cents, r.currency) for r in all_tenant_refs
        }
        if len(substances) > 1:
            anomalies.append(
                AnomalyItem("TXN_ID_CONFLICT", AnomalySeverity.FATAL, ref=ref_id)
            )
        else:
            unique_refunds.append(ref_list[0])

    # 5. Order Definition (C10: ORDER_MISSING / ORDER_CONFLICT)
    expected_order: OrderDefinition | None = None
    if not order_records:
        anomalies.append(AnomalyItem("ORDER_MISSING", AnomalySeverity.FATAL))
    else:
        order_definitions = {
            (o.amount_cents, o.currency)
            for o in order_records
            if o.amount_cents is not None and o.currency is not None
        }
        if len(order_definitions) > 1:
            anomalies.append(AnomalyItem("ORDER_CONFLICT", AnomalySeverity.FATAL))
        elif len(order_definitions) == 1:
            amt, curr = next(iter(order_definitions))
            expected_order = OrderDefinition(amount_cents=amt, currency=curr)

    # 6. Currency Mismatch (C8)
    if expected_order:
        expected_curr = expected_order.currency
        for cap in unique_captures:
            if cap.currency and cap.currency != expected_curr:
                anomalies.append(
                    AnomalyItem("CURRENCY_MISMATCH", AnomalySeverity.FATAL, ref=cap.capture_id)
                )
        for ref in unique_refunds:
            if ref.currency and ref.currency != expected_curr:
                anomalies.append(
                    AnomalyItem("CURRENCY_MISMATCH", AnomalySeverity.FATAL, ref=ref.refund_id)
                )

    # 7. Refund References and Over-Refund Checks (C8)
    valid_capture_ids = {c.capture_id for c in unique_captures if c.capture_id}
    captures_dict = {c.capture_id: c for c in unique_captures if c.capture_id}
    refunds_per_capture: dict[str, list[Event]] = defaultdict(list)

    for ref in unique_refunds:
        if ref.capture_id not in valid_capture_ids:
            anomalies.append(
                AnomalyItem(
                    "INVALID_REFUND_REFERENCE",
                    AnomalySeverity.FATAL,
                    ref=ref.capture_id,
                )
            )
        else:
            refunds_per_capture[ref.capture_id].append(ref)

    # Sum of refunds on each capture must not exceed capture amount (whole set, C8)
    for cap_id, refs in refunds_per_capture.items():
        cap_obj = captures_dict.get(cap_id)
        if cap_obj and cap_obj.amount_cents is not None:
            total_refunded_for_cap = sum(r.amount_cents or 0 for r in refs)
            if total_refunded_for_cap > cap_obj.amount_cents:
                anomalies.append(
                    AnomalyItem(
                        "REFUND_EXCEEDS_CAPTURE",
                        AnomalySeverity.FATAL,
                        ref=cap_id,
                    )
                )

    # 8. Over-Capture (C9)
    total_captured = sum(c.amount_cents or 0 for c in unique_captures)
    if expected_order and total_captured > expected_order.amount_cents:
        anomalies.append(AnomalyItem("OVER_CAPTURE", AnomalySeverity.FATAL))

    # 9. Chargeback References (C8)
    for cb in chargeback_records:
        if cb.capture_id not in valid_capture_ids:
            anomalies.append(
                AnomalyItem(
                    "INVALID_CHARGEBACK_REFERENCE",
                    AnomalySeverity.FATAL,
                    ref=cb.capture_id,
                )
            )

    # 10. Attempt Contradiction (A11)
    captured_attempts = {c.attempt_id for c in unique_captures if c.attempt_id}
    failed_attempts = {f.attempt_id for f in failure_records if f.attempt_id}
    contradicting_attempts = captured_attempts.intersection(failed_attempts)
    for att in sorted(contradicting_attempts):
        anomalies.append(
            AnomalyItem("ATTEMPT_CONTRADICTION", AnomalySeverity.FATAL, ref=att)
        )

    return IntegrityResult(
        clean_events=clean_events,
        captures=unique_captures,
        refunds=unique_refunds,
        failures=failure_records,
        chargebacks=chargeback_records,
        expected_order=expected_order,
        anomalies=anomalies,
        duplicate_count=duplicate_count,
        agreeing_capture_events=agreeing_capture_events,
    )
