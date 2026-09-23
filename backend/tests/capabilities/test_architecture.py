"""Architecture test: verify tools delegate to capabilities, not services.

Step 04 of CAPABILITY-002 requires that all migrated agent tools avoid
direct imports from domain services, using only capability calls instead.
"""

import ast
import importlib
import pkgutil


def _tool_modules():
    """Yield (module_name, module_source) for every public tool module."""
    import app.agents.tools as tools_pkg

    for _, module_name, _ in pkgutil.iter_modules(tools_pkg.__path__):
        if module_name.startswith("_"):
            continue  # skip __init__
        module = importlib.import_module(f"app.agents.tools.{module_name}")
        try:
            import inspect

            source = inspect.getsource(module)
        except (TypeError, OSError):
            continue
        yield module_name, source


def test_tools_do_not_import_services_directly():
    """No agent tool module may import from ``app.services``.

    Tools must delegate to capabilities (``app.capabilities.*``) instead.
    """
    violations = []
    for module_name, source in _tool_modules():
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module and node.module.startswith("app.services"):
                    violations.append(f"{module_name}.py imports {node.module}")

    assert not violations, (
        "Tools must use capabilities, not import services directly.\n"
        + "\n".join(violations)
    )
