# Development Log

Honest running log of test failures, root causes, fixes, and corrected AI suggestions during TraceGuard development. Never invent or retroactively modify entries.

| Date | What failed | Root cause | Fix | How verified |
|---|---|---|---|---|
| 2026-11-07 | `uv sync --extra dev` build failure | Hatchling could not detect package directory because `src/traceguard` did not yet exist | Configured `[tool.hatch.build.targets.wheel] packages = ["src/traceguard"]` in `pyproject.toml` and created `src/traceguard/__init__.py` | Ran `uv sync --extra dev` successfully |
| 2026-11-07 | `pytest` collection error (`ModuleNotFoundError: traceguard.models`) | Test-first failure: wrote unit tests before implementing data models | Implemented `src/traceguard/models.py` and `src/traceguard/core/ingest.py` | Ran `uv run pytest` (35 tests passed) |
| 2026-11-07 | `mypy` type check error: `Unsupported operand types for >= ("int" and "None")` | `_is_strict_int` returned plain `bool` so mypy could not narrow `amount_cents` from `Any \| None` to `int` | Annotated `_is_strict_int` return type with `typing.TypeGuard[int]` | Ran `uv run mypy src tests` (0 issues in 5 source files) |

## Log Entries

*(Entries logged above as they occurred during M1)*
