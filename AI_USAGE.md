# AI usage statement

OpenAI Codex and GitHub Copilot were used as coding assistants for this project. Codex helped implement the initial application, tests, and documentation. GitHub Copilot performed a readiness audit, added strict model validation, corrected conflict evidence and combined-tool-failure reporting, improved event-level explanations, and verified the changes with tests and quality checks. No other AI tools were used in the work recorded here.

## Suggestions and corrections

- **Useful approach:** Codex used a real subprocess test for the CLI. Pytest could not import the root-level `run.py` module directly, so invoking the documented CLI command in a subprocess tested argument handling and the stdout/stderr contract in the same way a user runs it. The M5 CLI tests passed after this change.
- **Correction:** An initial Codex-generated graph wiring imported concrete provider and tracer classes into the agent layer. The architecture import test exposed the boundary violation. The implementation was changed so the CLI composition root selects concrete adapters and the agent receives Protocol implementations. The focused architecture, agent, and adapter tests passed (23 tests).

## Authorship of this statement

Codex drafted this statement and the responses in `DECISIONS.md` from the repository and development log at the user's request. GitHub Copilot updated this statement to disclose its later implementation and verification work. The statement is intentionally explicit about that AI assistance; it does not claim that the candidate independently authored those drafts.
