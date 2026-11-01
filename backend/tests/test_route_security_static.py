"""Static route-security regression for accidental public API handlers.

This test intentionally avoids a live database. It inspects Flask blueprint
route decorators and requires protected-looking API handlers to either carry a
known auth decorator or be listed as intentionally public.

Limitations: this is decorator-level static analysis. It cannot prove runtime
auth for routes protected inside helper wrappers unless those wrappers are
listed as protected decorators below.
"""

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

PROTECTED_DECORATORS = {"login_required", "admin_required"}

PUBLIC_ROUTES = {
    ("GET", "/auth/csrf-token"),
    ("POST", "/auth/signup"),
    ("GET", "/auth/signup-terms"),
    ("POST", "/auth/login"),
    ("POST", "/auth/forgot-password"),
    ("POST", "/auth/password-reset/verify-otp"),
    ("POST", "/auth/reset-password"),
    # Public compatibility endpoints: they do not expose account data and the
    # MPIN variant currently returns a full-login-required 401.
    ("GET", "/auth/fast-login/options"),
    ("POST", "/auth/fast-login/mpin"),
    # Public read-only catalog used before/while creating truck listings.
    ("GET", "/api/catalog/truck-types"),
    ("GET", "/api/catalog/truck-types/<string:type_key>/fields"),
}

PUBLIC_PREFIXES = (
    "/uploads/",
)


def _decorator_name(node):
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _literal_arg(call, index=0):
    if len(call.args) <= index:
        return ""
    value = call.args[index]
    return value.value if isinstance(value, ast.Constant) and isinstance(value.value, str) else ""


def _blueprint_prefixes(tree):
    prefixes = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        call = node.value
        if _decorator_name(call.func) != "Blueprint" or not node.targets:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        prefix = ""
        for keyword in call.keywords:
            if keyword.arg == "url_prefix" and isinstance(keyword.value, ast.Constant):
                prefix = keyword.value.value or ""
        prefixes[target.id] = prefix
    return prefixes


def _routes(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    prefixes = _blueprint_prefixes(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        protected = any(_decorator_name(decorator) in PROTECTED_DECORATORS for decorator in node.decorator_list)
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                continue
            method = decorator.func.attr.upper()
            if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                continue
            owner = decorator.func.value
            if not isinstance(owner, ast.Name):
                continue
            route_path = _literal_arg(decorator)
            if not route_path:
                continue
            prefix = prefixes.get(owner.id, "")
            yield {
                "method": method,
                "path": f"{prefix}{route_path}",
                "protected": protected,
                "source": f"{path.relative_to(ROOT)}:{node.lineno}:{node.name}",
            }


def test_protected_api_routes_are_decorated_or_allowlisted():
    unknown = []
    for path in sorted(ROOT.rglob("*.py")):
        if "tests" in path.parts:
            continue
        for route in _routes(path):
            route_path = route["path"]
            if not (route_path.startswith("/api/") or route_path.startswith("/auth/")):
                continue
            if route["protected"]:
                continue
            if (route["method"], route_path) in PUBLIC_ROUTES:
                continue
            if any(route_path.startswith(prefix) for prefix in PUBLIC_PREFIXES):
                continue
            unknown.append(route)

    assert unknown == []
