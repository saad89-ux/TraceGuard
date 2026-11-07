"""Configuration parsers for the optional offline demo settings."""

import os
import sys
from collections.abc import Mapping

from traceguard.adapters.llm_base import LLMProvider
from traceguard.adapters.llm_mock import MockProvider
from traceguard.adapters.tracing import LocalJsonlTracer, Tracer
from traceguard.tools.faults import FaultInjector

_TOOL_NAMES = {"get_order", "get_payment_events", "get_support_notes"}


def faults_from_environment(
    environ: Mapping[str, str] | None = None,
) -> FaultInjector | None:
    """Parse A14's ``tool=outcome,outcome;tool=...`` fault-script format."""
    values = os.environ if environ is None else environ
    raw = values.get("TRACEGUARD_FAULTS", "").strip()
    if not raw:
        return None

    scripts: dict[str, list[str]] = {}
    for entry in raw.split(";"):
        tool_name, separator, outcomes = entry.partition("=")
        tool_name = tool_name.strip()
        if not separator or tool_name not in _TOOL_NAMES or tool_name in scripts:
            raise ValueError(f"invalid TRACEGUARD_FAULTS entry: {entry!r}")
        script = [outcome.strip() for outcome in outcomes.split(",")]
        if not script or any(not outcome for outcome in script):
            raise ValueError(f"empty TRACEGUARD_FAULTS outcome in {entry!r}")
        scripts[tool_name] = script
    return FaultInjector(scripts)


def provider_from_environment(
    environ: Mapping[str, str] | None = None,
) -> LLMProvider:
    """Select the offline mock; unavailable optional providers fall back with a warning."""
    values = os.environ if environ is None else environ
    selected = values.get("TRACEGUARD_LLM_PROVIDER", "mock").strip().lower()
    if selected != "mock":
        print(
            f"TraceGuard: provider {selected!r} is unavailable in this build; falling back to mock.",
            file=sys.stderr,
        )
    return MockProvider()


def tracer_for_run(run_id: str) -> Tracer:
    """Build the local redacted tracer selected for the current P1 run."""
    return LocalJsonlTracer("traces", run_id)
