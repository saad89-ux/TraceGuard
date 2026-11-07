"""Data models for TraceGuard."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EventType(str, Enum):
    ORDER_CREATED = "ORDER_CREATED"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    PAYMENT_CAPTURED = "PAYMENT_CAPTURED"
    REFUND_ISSUED = "REFUND_ISSUED"
    CHARGEBACK_OPENED = "CHARGEBACK_OPENED"
    NOTE = "NOTE"


class EventSource(str, Enum):
    CHECKOUT = "checkout"
    PAYMENTS = "payments"
    SUPPORT = "support"


class AnomalySeverity(str, Enum):
    FATAL = "FATAL"
    INFO = "INFO"


class OrderStatus(str, Enum):
    PAID = "PAID"
    UNPAID = "UNPAID"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"
    REFUNDED = "REFUNDED"
    DISPUTED = "DISPUTED"
    UNKNOWN = "UNKNOWN"


class ConfidenceLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class Event(BaseModel):
    """A fully validated event record."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    tenant_id: str
    order_id: str
    event_id: str
    source: EventSource
    type: EventType
    occurred_at: str
    ingested_at: str
    attempt_id: str | None = None
    capture_id: str | None = None
    refund_id: str | None = None
    amount_cents: int | None = None
    currency: str | None = None
    text: str | None = None

    def substantive_fields(self) -> dict[str, Any]:
        """All fields except ingested_at for duplicate comparison (Doc 1 Sec 2, A3).

        Absent fields and null values are treated as equal.
        """
        return {
            "tenant_id": self.tenant_id,
            "order_id": self.order_id,
            "event_id": self.event_id,
            "source": self.source.value,
            "type": self.type.value,
            "occurred_at": self.occurred_at,
            "attempt_id": self.attempt_id,
            "capture_id": self.capture_id,
            "refund_id": self.refund_id,
            "amount_cents": self.amount_cents,
            "currency": self.currency,
            "text": self.text,
        }


class QuarantinedRecord(BaseModel):
    """A raw record that failed validation and is held in quarantine."""

    model_config = ConfigDict(frozen=True)

    line_number: int
    raw_line: str
    reason_code: str
    tenant_id: str | None = None
    order_id: str | None = None
    event_id: str | None = None
    source: str | None = None

    def is_attributable(self, tenant_id: str, order_id: str) -> bool:
        """True if tenant_id and order_id parse as strings and match requested values."""
        return (
            isinstance(self.tenant_id, str)
            and isinstance(self.order_id, str)
            and self.tenant_id == tenant_id
            and self.order_id == order_id
        )

    def anomaly_severity(self) -> AnomalySeverity:
        """Determine severity if attributable (Doc 1 Sec 5, Sec 13).

        source == payments and reason != SOURCE_NOT_ALLOWED is FATAL, else INFO.
        """
        if self.source == EventSource.PAYMENTS.value and self.reason_code != "SOURCE_NOT_ALLOWED":
            return AnomalySeverity.FATAL
        return AnomalySeverity.INFO

    def to_anomaly_string(self) -> str:
        """Format anomaly string with ref per PRD Assumption A13.

        Ref is event_id if non-empty string, else line-<N>.
        """
        ref = (
            self.event_id
            if (self.event_id and self.event_id.strip())
            else f"line-{self.line_number}"
        )
        return f"{self.reason_code}:{ref}"

    def to_anomaly_for_order(
        self, tenant_id: str, order_id: str
    ) -> tuple[str, AnomalySeverity] | None:
        """Return (anomaly_string, severity) if attributable, else None."""
        if not self.is_attributable(tenant_id, order_id):
            return None
        return (self.to_anomaly_string(), self.anomaly_severity())


class ReconResult(BaseModel):
    """Deterministic financial reconciliation result produced by core only (Doc 1 Sec 8)."""

    model_config = ConfigDict(frozen=True)

    status: OrderStatus
    captured_cents: int | None
    refunded_cents: int | None
    net_paid_cents: int | None
    anomalies: list[str]
    evidence_event_ids: list[str]
    confidence: ConfidenceLevel
    duplicate_count: int = 0


class ToolMeta(BaseModel):
    """Metadata describing a bounded tool invocation."""

    model_config = ConfigDict(frozen=True)

    attempts: int
    latency_ms: float
    outcome: str


class ToolResponse(BaseModel):
    """Records and attributable quarantine returned by a tool."""

    model_config = ConfigDict(frozen=True)

    records: list[Event]
    quarantined: list[QuarantinedRecord]
    meta: ToolMeta
    anomalies: list[str] = Field(default_factory=list)
    confidence_cap: ConfidenceLevel | None = None
    unavailable: bool = False
