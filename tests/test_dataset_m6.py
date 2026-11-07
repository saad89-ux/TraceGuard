"""M6 dataset and candidate-facing documentation acceptance tests."""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from traceguard.core.index import EventIndex
from traceguard.core.ingest import IngestResult, ingest_events
from traceguard.core.reconcile import reconcile_order
from traceguard.models import OrderStatus

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "events.jsonl"
DatasetResult = tuple[EventIndex, IngestResult]

GOLDEN = [
    ("T1", "O-201", OrderStatus.PAID, (12900, 0, 12900), ()),
    ("T1", "O-202", OrderStatus.UNPAID, (0, 0, 0), ()),
    ("T1", "O-203", OrderStatus.PARTIALLY_PAID, (4000, 0, 4000), ()),
    ("T1", "O-204", OrderStatus.PARTIALLY_REFUNDED, (8000, 2000, 6000), ()),
    ("T1", "O-205", OrderStatus.REFUNDED, (6000, 6000, 0), ()),
    ("T1", "O-206", OrderStatus.DISPUTED, (5000, 0, 5000), ()),
    ("T1", "O-207", OrderStatus.UNKNOWN, (None, None, None), ("OVER_CAPTURE",)),
    ("T1", "O-208", OrderStatus.UNKNOWN, (None, None, None), ("INVALID_REFUND_REFERENCE",)),
    ("T1", "O-209", OrderStatus.UNKNOWN, (None, None, None), ("REFUND_EXCEEDS_CAPTURE",)),
    ("T1", "O-210", OrderStatus.UNKNOWN, (None, None, None), ("TXN_ID_CONFLICT",)),
    ("T1", "O-211", OrderStatus.UNKNOWN, (None, None, None), ("EVENT_ID_CONFLICT",)),
    ("T1", "O-212", OrderStatus.UNKNOWN, (None, None, None), ("CURRENCY_MISMATCH",)),
    ("T1", "O-213", OrderStatus.UNKNOWN, (None, None, None), ("ORDER_CONFLICT",)),
    ("T1", "O-214", OrderStatus.UNKNOWN, (None, None, None), ("ORDER_MISSING",)),
    ("T1", "O-215", OrderStatus.UNKNOWN, (None, None, None), ()),
    ("T1", "O-216", OrderStatus.PAID, (12900, 0, 12900), ()),
    ("T1", "O-217", OrderStatus.UNKNOWN, (None, None, None), ("INVALID_TIMESTAMP",)),
    ("T1", "O-218", OrderStatus.PAID, (12900, 0, 12900), ()),
    ("T1", "O-219", OrderStatus.UNKNOWN, (None, None, None), ()),
    ("T1", "O-220", OrderStatus.UNKNOWN, (None, None, None), ("ATTEMPT_CONTRADICTION",)),
    ("T1", "O-221", OrderStatus.UNKNOWN, (None, None, None), ("OVER_CAPTURE",)),
    ("T2", "O-201", OrderStatus.UNPAID, (0, 0, 0), ()),
]


@pytest.fixture(scope="module")
def dataset() -> DatasetResult:
    assert DATASET.is_file()
    parsed = ingest_events(DATASET)
    return EventIndex.from_events(parsed.valid_events), parsed


def test_dataset_has_at_least_100_valid_events_and_all_scenarios(
    dataset: DatasetResult,
) -> None:
    _, parsed = dataset
    assert len(parsed.valid_events) >= 100
    ids = {event.order_id for event in parsed.valid_events}
    assert {order for _, order, *_ in GOLDEN} <= ids


@pytest.mark.parametrize(
    ("tenant", "order", "status", "totals", "anomaly_codes"),
    GOLDEN,
)
def test_dataset_all_section_17_golden_results(
    dataset: DatasetResult,
    tenant: str,
    order: str,
    status: OrderStatus,
    totals: tuple[int | None, int | None, int | None],
    anomaly_codes: tuple[str, ...],
) -> None:
    index, parsed = dataset
    result = reconcile_order(index, tenant, order, parsed.quarantined)
    assert result.status == status
    assert (
        result.captured_cents,
        result.refunded_cents,
        result.net_paid_cents,
    ) == totals
    assert tuple(sorted({code.split(":", 1)[0] for code in result.anomalies})) == anomaly_codes


def test_dataset_contains_each_required_noise_type(dataset: DatasetResult) -> None:
    _, parsed = dataset
    reason_codes = {record.reason_code for record in parsed.quarantined}
    assert {
        "INVALID_JSON",
        "MISSING_FIELD",
        "UNSUPPORTED_TYPE",
        "INVALID_AMOUNT",
        "INVALID_CURRENCY",
        "SOURCE_NOT_ALLOWED",
    } <= reason_codes


def test_documented_dataset_cli_command_is_json_only() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "run.py"),
            "--events",
            str(DATASET),
            "--tenant",
            "T1",
            "--order",
            "O-201",
            "--question",
            "Was this order paid?",
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert completed.returncode == 0
    output = json.loads(completed.stdout)
    assert output["status"] == "PAID"
    assert output["confidence"] == "HIGH"
    assert len(output) == 8
    assert completed.stdout.strip() == json.dumps(output, separators=(",", ":"))
    assert re.search(r"run_id=[0-9a-f-]{36}", completed.stderr)


def test_readme_has_required_commands_confidence_and_failure_record() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for required in (
        "uv sync --extra dev",
        "uv run pytest",
        "uv run python run.py --events data/events.jsonl",
        "HIGH",
        "MEDIUM",
        "LOW",
        "Failing test",
        "Root cause",
        "Fix",
        "P0",
        "P1",
        "P2",
        "Assumptions",
        "A1",
        "A17",
        "checkout",
        "ingested_at",
        "ATTEMPT_CONTRADICTION",
        "line-<N>",
        "TRACEGUARD_FAULTS",
        "Notes are fetched for every intent",
        "Tier P2 is not built by default",
    ):
        assert required in readme


def test_candidate_owned_documents_are_clearly_marked_drafts() -> None:
    decisions = (ROOT / "DECISIONS.md").read_text(encoding="utf-8")
    ai_usage = (ROOT / "AI_USAGE.md").read_text(encoding="utf-8")
    assert "DRAFT" in decisions
    assert "DRAFT" in ai_usage
    assert decisions.count("\n- ") >= 7
    assert "candidate" in decisions.lower()
    assert "AI tools used" in ai_usage
    assert "corrected" in ai_usage.lower()
