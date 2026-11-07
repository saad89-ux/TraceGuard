"""Provider contract for optional LLM-backed tasks."""

from typing import Any, Protocol

from pydantic import BaseModel


class LLMError(Exception):
    """Controlled provider or response error; callers should use safe fallback output."""


class LLMProvider(Protocol):
    def complete(self, task: str, payload: dict[str, Any], schema: type[BaseModel]) -> BaseModel:
        """Return an instance of ``schema`` or raise ``LLMError``."""
