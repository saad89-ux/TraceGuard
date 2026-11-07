"""Enforce package boundaries from Architecture Section 10."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "traceguard"


def _import_modules(source: str) -> set[str]:
    tree = ast.parse(source)
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _violations(package: str, modules: set[str], source: str = "") -> set[str]:
    forbidden: set[str] = set()
    if package == "core":
        forbidden = {
            "traceguard.agent",
            "traceguard.tools",
            "traceguard.adapters",
            "langgraph",
            "litellm",
            "langsmith",
        }
    elif package == "tools":
        forbidden = {
            "traceguard.agent",
            "litellm",
            "langsmith",
        }
    elif package == "agent":
        forbidden = {"litellm", "langsmith"}
        allowed_internal = (
            "traceguard.agent",
            "traceguard.adapters",
            "traceguard.core",
            "traceguard.tools",
        )
        for module in modules:
            if module.startswith("traceguard.") and not (
                module == "traceguard.models"
                or any(module == prefix or module.startswith(f"{prefix}.") for prefix in allowed_internal)
                or module in {"traceguard.adapters.llm_base", "traceguard.adapters.tracing"}
            ):
                forbidden.add(module)
    elif package == "adapters":
        forbidden = {"traceguard.agent"}
    violations = {
        module
        for module in modules
        if any(module == blocked or module.startswith(f"{blocked}.") for blocked in forbidden)
    }
    if package == "agent":
        allowed_adapter_symbols = {
            "traceguard.adapters.llm_base": {"LLMError", "LLMProvider"},
            "traceguard.adapters.tracing": {"Tracer"},
        }
        for node in ast.walk(ast.parse(source)):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.startswith("traceguard.adapters.")
            ):
                allowed = allowed_adapter_symbols.get(node.module, set())
                imported = {alias.name for alias in node.names}
                if not imported <= allowed:
                    violations.add(f"{node.module}: concrete adapter import")
    return violations


def test_import_checker_detects_forbidden_adapter_to_agent_import() -> None:
    imports = _import_modules("from traceguard.agent import graph\n")
    assert _violations("adapters", imports) == {"traceguard.agent"}


def test_import_checker_detects_agent_import_of_concrete_adapter() -> None:
    source = "from traceguard.adapters.llm_mock import MockProvider\n"
    assert _violations("agent", _import_modules(source), source) == {
        "traceguard.adapters.llm_mock: concrete adapter import"
    }


def test_source_imports_follow_architecture_boundaries() -> None:
    for package in ("core", "tools", "agent", "adapters"):
        for path in (SOURCE / package).rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            modules = _import_modules(source)
            assert not _violations(package, modules, source), f"forbidden imports in {path}: {modules}"
