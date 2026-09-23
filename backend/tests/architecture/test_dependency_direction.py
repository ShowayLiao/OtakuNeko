"""Static dependency-boundary tests for the V3 architecture.

The scanner reads source files directly.  It does not import application
modules, so coverage is recursive, deterministic, and independent of runtime
configuration or optional dependencies.
"""

from __future__ import annotations

import ast
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = BACKEND_ROOT / "app"

# These imports predate the V3 boundary guard.  They are explicit migration
# debt: removal is allowed, but adding a new direct API dependency is not.
LEGACY_API_SERVICE_IMPORTS = {
    ("app.api.v1.agent", "app.services.collection_service"),
    ("app.api.v1.auth", "app.services.user_service"),
    ("app.api.v1.bangumi", "app.services.bangumi_service"),
    ("app.api.v1.collections", "app.services.bangumi_service"),
    ("app.api.v1.collections", "app.services.collection_service"),
    ("app.api.v1.collections", "app.services.douban_service"),
    ("app.api.v1.dashboard", "app.services.stats_service"),
    ("app.api.v1.endpoints.schedules", "app.services.schedule_service"),
    ("app.api.v1.rss", "app.services.qb_service"),
    ("app.api.v1.subjects", "app.services.subject_service"),
    ("app.api.v1.users", "app.services.user_service"),
}

LEGACY_API_AGENT_IMPORTS = {
    ("app.api.v1.agent", "app.agents.agent_registry"),
    ("app.api.v1.agent", "app.agents.provider_endpoint"),
    ("app.api.v1.agent", "app.agents.recommendation_agent"),
    ("app.api.v1.agent", "app.agents.router"),
    ("app.api.v1.agent", "app.agents.thread_scope"),
}


def _walk_modules(
    package_dir: Path,
    package_name: str,
):
    """Yield module metadata for every Python file recursively."""
    for path in sorted(package_dir.rglob("*.py")):
        relative = path.relative_to(package_dir).with_suffix("")
        parts = list(relative.parts)
        is_package = parts[-1] == "__init__"
        if is_package:
            parts.pop()
        module_name = ".".join((package_name, *parts)).rstrip(".")
        yield module_name, path.read_text(encoding="utf-8"), is_package


def _imported_modules(
    source: str,
    *,
    filename: str,
    is_package: bool = False,
) -> set[str]:
    """Return absolute import targets, failing loudly on invalid source."""
    tree = ast.parse(source, filename=filename)
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                package_parts = filename.split(".")
                if not is_package:
                    package_parts.pop()
                parents_to_remove = node.level - 1
                if parents_to_remove > len(package_parts):
                    raise ValueError(
                        f"Invalid relative import in {filename}: level={node.level}"
                    )
                if parents_to_remove:
                    package_parts = package_parts[:-parents_to_remove]
                module_parts = node.module.split(".") if node.module else []
                base = ".".join((*package_parts, *module_parts))
            else:
                base = node.module or ""
            if base:
                imports.add(base)
                imports.update(
                    f"{base}.{alias.name}"
                    for alias in node.names
                    if alias.name != "*"
                )
        elif isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
    return imports


def _dependencies(package_dir: Path, package_name: str, prefix: str):
    dependencies: set[tuple[str, str]] = set()
    for module_name, source, is_package in _walk_modules(
        package_dir,
        package_name,
    ):
        imports = _imported_modules(
            source,
            filename=module_name,
            is_package=is_package,
        )
        matching = {
            imported
            for imported in imports
            if imported == prefix or imported.startswith(f"{prefix}.")
        }
        canonical = {
            imported
            for imported in matching
            if not any(
                imported.startswith(f"{other}.")
                for other in matching
                if other != imported
            )
        }
        dependencies.update((module_name, imported) for imported in canonical)
    return dependencies


def test_module_walker_includes_nested_modules(tmp_path):
    """The scanner covers nested packages such as app.api.v1."""
    package = tmp_path / "sample_package"
    nested = package / "nested"
    nested.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (nested / "__init__.py").write_text("", encoding="utf-8")
    (nested / "router.py").write_text(
        "from app.services.example import service\n",
        encoding="utf-8",
    )

    modules = {
        module_name
        for module_name, _, _ in _walk_modules(package, "sample_package")
    }

    assert "sample_package.nested.router" in modules


def test_import_parser_normalizes_relative_and_aliased_modules():
    """Equivalent import spellings cannot bypass dependency checks."""
    source = "\n".join(
        (
            "from ...services.catalog import CatalogService",
            "from app import services",
        )
    )

    imports = _imported_modules(source, filename="app.api.v1.router")

    assert "app.services.catalog" in imports
    assert "app.services" in imports


def test_api_service_dependencies_do_not_exceed_legacy_baseline():
    """New API-to-service imports must go through the intended boundary."""
    actual = _dependencies(APP_ROOT / "api", "app.api", "app.services")
    unexpected = actual - LEGACY_API_SERVICE_IMPORTS
    assert not unexpected, (
        "New direct API-to-service dependencies are not allowed: "
        f"{sorted(unexpected)}"
    )


def test_api_agent_dependencies_do_not_exceed_legacy_baseline():
    """Only the existing agent endpoint may directly assemble agents."""
    actual = _dependencies(APP_ROOT / "api", "app.api", "app.agents")
    unexpected = actual - LEGACY_API_AGENT_IMPORTS
    assert not unexpected, (
        "New direct API-to-agent dependencies are not allowed: "
        f"{sorted(unexpected)}"
    )


def test_agents_do_not_import_services_directly():
    """Agents depend on capability and memory interfaces, not services."""
    violations = _dependencies(
        APP_ROOT / "agents",
        "app.agents",
        "app.services",
    )
    assert not violations, (
        f"Agent modules must not import services directly: {sorted(violations)}"
    )


def test_capabilities_do_not_import_api():
    """Capabilities must not depend on the API delivery layer."""
    violations = _dependencies(
        APP_ROOT / "capabilities",
        "app.capabilities",
        "app.api",
    )
    assert not violations, (
        f"Capability modules must not import API: {sorted(violations)}"
    )


def test_harness_does_not_import_api():
    """Harness orchestration must not depend on the API delivery layer."""
    violations = _dependencies(
        APP_ROOT / "harness",
        "app.harness",
        "app.api",
    )
    assert not violations, (
        f"Harness modules must not import API: {sorted(violations)}"
    )
