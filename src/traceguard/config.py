"""Configuration parsers for the optional offline demo settings."""

import os
from collections.abc import Mapping

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
