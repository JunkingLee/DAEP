import ast
from pathlib import Path


def _main_module():
    return ast.parse(
        (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text(
            encoding="utf-8"
        )
    )


def test_main_has_no_duplicate_top_level_function_definitions():
    tree = _main_module()
    names = [
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    assert len(names) == len(set(names)), "duplicate top-level function definitions remain"


def test_main_has_no_duplicate_fastapi_routes():
    tree = _main_module()
    routes = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            if not isinstance(decorator.func, ast.Attribute):
                continue
            if decorator.func.attr not in {"get", "post", "put", "patch", "delete", "websocket"}:
                continue
            if not decorator.args or not isinstance(decorator.args[0], ast.Constant):
                continue
            routes.append((decorator.func.attr, decorator.args[0].value))
    assert len(routes) == len(set(routes)), "duplicate FastAPI method/path registrations remain"

# Keep structural-duplication guard explicit for future refactors.
