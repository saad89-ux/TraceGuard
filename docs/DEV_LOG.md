# Development Log

Honest running log of test failures, root causes, fixes, and corrected AI suggestions during TraceGuard development. Never invent or retroactively modify entries.

| Date | What failed | Root cause | Fix | How verified |
|---|---|---|---|---|
| 2026-11-07 | `uv sync --extra dev` build failure | Hatchling could not detect package directory because `src/traceguard` did not yet exist | Configured `[tool.hatch.build.targets.wheel] packages = ["src/traceguard"]` in `pyproject.toml` and created `src/traceguard/__init__.py` | Ran `uv sync --extra dev` successfully |
| 2026-11-07 | `pytest` collection error (`ModuleNotFoundError: traceguard.models`) | Test-first failure: wrote unit tests before implementing data models | Implemented `src/traceguard/models.py` and `src/traceguard/core/ingest.py` | Ran `uv run pytest` (35 tests passed) |
| 2026-11-07 | `mypy` type check error: `Unsupported operand types for >= ("int" and "None")` | `_is_strict_int` returned plain `bool` so mypy could not narrow `amount_cents` from `Any \| None` to `int` | Annotated `_is_strict_int` return type with `typing.TypeGuard[int]` | Ran `uv run mypy src tests` (0 issues in 5 source files) |
| 2026-11-07 | `pytest` collection error (`ModuleNotFoundError: traceguard.core.index`) | Test-first failure: wrote golden & property tests for M2 before implementing core index & reconciler | Implemented `index.py`, `integrity.py`, `confidence.py`, and `reconcile.py` | Ran `uv run pytest` (61 tests passed, 98% coverage) |
| 2026-11-07 | Two new M1 cap tests failed (`ingest_events` rejected `max_events` and `max_note_length` parameters) | M1 ingest enforced the line cap but omitted Architecture S2's configurable event-count and maximum note-length caps | Added configurable caps, reject the entire file when the nonblank record count exceeds the event limit, and truncate note text at its configured limit | `uv run pytest tests/test_core_ingest.py -q` (37 passed after fix) |
| 2026-11-07 | Ruff reported FLY002 in the new event-count test | The test built two lines with a one-element `str.join` expression that the configured lint rules reject | Replaced the join expression with a direct f-string | `uv run ruff check .` (all checks passed) |

## Log Entries

*(Entries logged above as they occurred during M1 and M2)*
