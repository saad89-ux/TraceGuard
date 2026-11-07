"""Small deterministic fault scripts for tests and offline demos."""

from collections.abc import Callable
from typing import TypeVar

from traceguard.tools.resilience import ToolError, ToolTimeout

T = TypeVar("T")
_ALLOWED = {"fail", "timeout", "ok"}


class FaultInjector:
    """Consume per-tool fail/timeout/ok outcomes in order."""

    def __init__(self, scripts: dict[str, list[str]]) -> None:
        if any(outcome not in _ALLOWED for script in scripts.values() for outcome in script):
            raise ValueError("fault outcomes must be fail, timeout, or ok")
        self._scripts = {name: list(script) for name, script in scripts.items()}

    def remaining(self, tool_name: str) -> list[str]:
        """Return a copy of the unconsumed script."""
        return list(self._scripts.get(tool_name, []))

    def wrap(self, tool_name: str, operation: Callable[[], T]) -> Callable[[], T]:
        """Return an operation that applies the next scripted fault, if any."""

        def injected() -> T:
            script = self._scripts.get(tool_name, [])
            outcome = script.pop(0) if script else "ok"
            if outcome == "fail":
                raise ToolError(f"injected failure in {tool_name}")
            if outcome == "timeout":
                raise ToolTimeout(f"injected timeout in {tool_name}")
            return operation()

        return injected
