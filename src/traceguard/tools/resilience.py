"""One bounded retry policy for all tool calls."""

import logging
import queue
import threading
import time
from collections.abc import Callable
from typing import TypeVar

from traceguard.models import ConfidenceLevel, ToolMeta, ToolResponse

T = TypeVar("T")
logger = logging.getLogger(__name__)


class ToolError(Exception):
    """Transient tool failure eligible for retry."""


class ToolTimeout(ToolError):
    """A tool attempt exceeded its per-attempt timeout."""


class ToolValidationError(Exception):
    """Invalid tool response; deliberately not eligible for retry."""


def _run_with_timeout(operation: Callable[[], T], timeout_s: float) -> T:
    result: queue.Queue[tuple[bool, object]] = queue.Queue(maxsize=1)

    def target() -> None:
        try:
            result.put((True, operation()))
        except Exception as exc:  # noqa: BLE001 - re-raise worker errors in the caller
            result.put((False, exc))

    worker = threading.Thread(target=target, daemon=True)
    worker.start()
    worker.join(timeout_s)
    if worker.is_alive():
        raise ToolTimeout(f"tool exceeded {timeout_s:g}s timeout")
    succeeded, value = result.get_nowait()
    if not succeeded:
        if isinstance(value, BaseException):
            raise value
        raise ToolError("tool worker failed")
    return value  # type: ignore[return-value]


def _fallback(tool_name: str, attempts: int, elapsed_ms: float) -> ToolResponse:
    if tool_name == "get_support_notes":
        anomaly = "NOTES_UNAVAILABLE"
        cap = ConfidenceLevel.MEDIUM
    else:
        anomaly = f"TOOL_FAILURE:{tool_name}"
        cap = ConfidenceLevel.LOW
    return ToolResponse(
        records=[],
        quarantined=[],
        meta=ToolMeta(attempts=attempts, latency_ms=elapsed_ms, outcome="unavailable"),
        anomalies=[anomaly],
        confidence_cap=cap,
        unavailable=True,
    )


def call_tool(
    tool_name: str,
    operation: Callable[[], T],
    *,
    timeout_s: float = 2.0,
    backoff_s: float = 0.1,
    max_attempts: int = 3,
) -> T | ToolResponse:
    """Run one tool with a timeout and no more than three transient-error attempts."""
    if not tool_name.strip():
        raise ValueError("tool_name must not be empty")
    if timeout_s <= 0 or backoff_s < 0:
        raise ValueError("timeout_s must be positive and backoff_s non-negative")
    if not 1 <= max_attempts <= 3:
        raise ValueError("max_attempts must be between 1 and 3")

    started = time.perf_counter()
    for attempt in range(1, max_attempts + 1):
        try:
            value = _run_with_timeout(operation, timeout_s)
            elapsed_ms = (time.perf_counter() - started) * 1000
            if isinstance(value, ToolResponse):
                return value.model_copy(
                    update={
                        "meta": ToolMeta(
                            attempts=attempt,
                            latency_ms=elapsed_ms,
                            outcome="ok",
                        )
                    }
                )
            return value
        except (ToolTimeout, ToolError) as exc:
            if attempt >= max_attempts:
                logger.error("%s unavailable after %d attempts: %s", tool_name, attempt, exc)
                return _fallback(
                    tool_name,
                    attempt,
                    (time.perf_counter() - started) * 1000,
                )
            logger.warning(
                "%s failed on attempt %d/%d; retrying",
                tool_name,
                attempt,
                max_attempts,
            )
            time.sleep(backoff_s * (2 ** (attempt - 1)))
    raise AssertionError("bounded retry loop exited unexpectedly")
