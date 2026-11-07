"""Support notes isolation and prompt injection detection (Stage 7 / Gate G3).

Notes are untrusted data: control characters stripped, length capped,
isolated from reconciliation and never cited as evidence (Doc 1 Sec 10).
"""

import re

from pydantic import BaseModel, ConfigDict

from traceguard.models import Event, EventType

MAX_NOTE_LENGTH = 2000  # S2 input cap
CONTROL_CHARS_REGEX = re.compile(r"[\x00-\x1f\x7f]")

INJECTION_PATTERNS = [
    re.compile(r"ignore\s+previous\s+instructions", re.IGNORECASE),
    re.compile(r"system\s+override", re.IGNORECASE),
    re.compile(r"mark\s+this\s+order", re.IGNORECASE),
    re.compile(r"do\s+not\s+mention", re.IGNORECASE),
    re.compile(r"financial\s+records\s+are\s+outdated", re.IGNORECASE),
]

INJECTION_WARNING_SENTENCE = (
    "A support note contained instructions to change the order status. "
    "It was treated as untrusted data and ignored."
)


class NotesChannel(BaseModel):
    """Isolated metadata output from the support notes channel (Gate G3)."""

    model_config = ConfigDict(frozen=True)

    count: int
    injection_suspected: bool
    note_event_ids: list[str]
    warning_sentence: str | None = None


def sanitize_note_text(text: str | None) -> str:
    """Strip control characters and enforce maximum length."""
    if not text:
        return ""
    # Replace controls with spaces so token boundaries survive sanitization
    # (for example, a line break in "SYSTEM\nOVERRIDE" must not hide a match).
    cleaned = CONTROL_CHARS_REGEX.sub(" ", text)
    if len(cleaned) > MAX_NOTE_LENGTH:
        cleaned = cleaned[:MAX_NOTE_LENGTH]
    return cleaned


def detect_injection(text: str) -> bool:
    """Heuristic check for prompt-injection instructions in untrusted notes (Doc 1 Sec 10)."""
    return any(pat.search(text) for pat in INJECTION_PATTERNS)


def process_notes(note_events: list[Event]) -> NotesChannel:
    """Process support notes through the untrusted channel (Gate G3).

    Notes never reach the reconciler, monetary totals, or evidence lists.
    """
    valid_notes = [n for n in note_events if n.type == EventType.NOTE]
    note_ids = sorted(n.event_id for n in valid_notes)

    injection_found = False
    for note in valid_notes:
        cleaned_text = sanitize_note_text(note.text)
        if detect_injection(cleaned_text):
            injection_found = True
            break

    return NotesChannel(
        count=len(valid_notes),
        injection_suspected=injection_found,
        note_event_ids=note_ids,
        warning_sentence=INJECTION_WARNING_SENTENCE if injection_found else None,
    )
