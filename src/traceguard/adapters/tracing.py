"""Local JSONL tracer with a strict, privacy-preserving attribute boundary."""

import json
import re
import sys
import uuid
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import Protocol

_SAFE_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
_BLOCKED_KEYS = {
    "text",
    "note",
    "note_text",
    "notes",
    "api_key",
    "key",
    "secret",
    "token",
    "inputs",
    "outputs",
    "input",
    "output",
    "prompt",
    "question",
    "raw_event",
    "raw_events",
}


class Span:
    """Context token for one recorded operation."""


class Tracer(Protocol):
    def span(self, name: str, **attrs: object) -> AbstractContextManager[Span]: ...

    def event(self, name: str, **attrs: object) -> None: ...


def _redact(attrs: dict[str, object]) -> dict[str, object]:
    safe: dict[str, object] = {}
    for key, value in attrs.items():
        lowered = key.lower()
        normalized = re.sub(r"[^a-z0-9]", "", lowered)
        sensitive_name = lowered in _BLOCKED_KEYS or any(
            fragment in normalized
            for fragment in ("note", "secret", "token", "apikey", "authorization")
        )
        if not _SAFE_KEY.fullmatch(key) or sensitive_name:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None or (
            isinstance(value, list)
            and all(isinstance(item, (str, int, float, bool)) or item is None for item in value)
        ):
            safe[key] = value
    return safe


class LocalJsonlTracer:
    """Append redacted span/event records to one file per run."""

    def __init__(self, directory: str | Path, run_id: str | None = None) -> None:
        self.directory = Path(directory)
        self.run_id = run_id or str(uuid.uuid4())

    def _write(self, record: dict[str, object]) -> None:
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            path = self.directory / f"{self.run_id}.jsonl"
            with path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        except OSError as exc:
            print(f"TraceGuard tracer error: {exc}", file=sys.stderr)

    @contextmanager
    def span(self, name: str, **attrs: object) -> Iterator[Span]:
        self._write({"kind": "span", "name": name, "run_id": self.run_id, **_redact(attrs)})
        try:
            yield Span()
        except Exception:
            self.event("span_error", span=name)
            raise

    def event(self, name: str, **attrs: object) -> None:
        self._write({"kind": "event", "name": name, "run_id": self.run_id, **_redact(attrs)})
