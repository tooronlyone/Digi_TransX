"""Phase 0: extract every Flask route via the runtime url_map.

Read-only. shared.db.check_connection is stubbed so importing app.py does not
touch the database; the scheduler is left OFF (its env gate default).
Also performs a static AST pass so we can attach file:line to each handler and
detect decorators that never get registered.
"""
import ast
import inspect
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
OUT = ROOT / "inventory" / "backend_routes.json"

sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DIGITRANSX_ENABLE_SCHEDULER", "false")

import shared.db as shared_db  # noqa: E402

shared_db.check_connection = lambda: None

import app as app_module  # noqa: E402

flask_app = app_module.app
routes = []
for rule in flask_app.url_map.iter_rules():
    if rule.endpoint == "static":
        continue
    view = flask_app.view_functions.get(rule.endpoint)
    target = inspect.unwrap(view) if view else None
    try:
        src_file = inspect.getsourcefile(target) if target else None
        src_line = inspect.getsourcelines(target)[1] if target else None
    except (TypeError, OSError):
        src_file, src_line = None, None
    for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
        routes.append(
            {
                "method": method,
                "path": rule.rule,
                "endpoint": rule.endpoint,
                "handler": getattr(target, "__name__", None),
                "file": str(Path(src_file).relative_to(ROOT)).replace("\\", "/") if src_file else None,
                "line": src_line,
            }
        )

# Static pass: every decorator that looks like a route, to spot unregistered ones.
static_decorators = []
for py in BACKEND.rglob("*.py"):
    rel = str(py.relative_to(ROOT)).replace("\\", "/")
    if "/tests/" in rel or "/scripts/" in rel or "__pycache__" in rel:
        continue
    try:
        tree = ast.parse(py.read_text(encoding="utf-8"))
    except SyntaxError as exc:
        static_decorators.append({"file": rel, "error": str(exc)})
        continue
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                if (
                    isinstance(dec, ast.Call)
                    and isinstance(dec.func, ast.Attribute)
                    and dec.func.attr in {"route", "get", "post", "put", "patch", "delete"}
                    and dec.args
                    and isinstance(dec.args[0], ast.Constant)
                    and isinstance(dec.args[0].value, str)
                ):
                    static_decorators.append(
                        {
                            "file": rel,
                            "line": dec.lineno,
                            "decorator": f"{ast.unparse(dec.func)}",
                            "path": dec.args[0].value,
                            "handler": node.name,
                        }
                    )

# Match static decorators to runtime rules by endpoint-name suffix + path suffix
# (some wrappers, e.g. admin_required, do not use functools.wraps so
# inspect.getsourcefile points at the wrapper; endpoint names are reliable).
def _norm(p):
    return p.rstrip("/")


unregistered = []
for d in static_decorators:
    if "handler" not in d:
        continue
    hits = [
        r for r in routes
        if r["endpoint"].split(".")[-1] == d["handler"] and _norm(r["path"]).endswith(_norm(d["path"]))
    ]
    if not hits:
        unregistered.append(d)
    else:
        for r in hits:
            if r["handler"] == "wrapped" or r["file"] != d["file"]:
                r["handler"] = d["handler"]
                r["file"] = d["file"]
                r["line"] = d["line"]

# Duplicate (method,path) registrations
seen = {}
dupes = []
for r in routes:
    key = (r["method"], r["path"])
    if key in seen:
        dupes.append({"first": seen[key], "second": r})
    else:
        seen[key] = r

# Duplicate handler names in the same file (shadowing = AI leftover risk)
by_file = {}
for d in static_decorators:
    if "handler" in d:
        by_file.setdefault(d["file"], []).append(d)
shadowed = []
for f, decs in by_file.items():
    names = {}
    for d in decs:
        names.setdefault(d["handler"], []).append(d["line"])
    for n, lines in names.items():
        if len(lines) > 1:
            shadowed.append({"file": f, "handler": n, "lines": lines})

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(
    json.dumps(
        {
            "count": len(routes),
            "routes": sorted(routes, key=lambda r: (r["path"], r["method"])),
            "static_decorator_count": len([d for d in static_decorators if "handler" in d]),
            "unregistered_static_decorators": unregistered,
            "duplicate_method_path": dupes,
            "same_name_handlers_in_file": shadowed,
        },
        indent=2,
    ),
    encoding="utf-8",
)
print(f"routes={len(routes)} static_decorators={len(static_decorators)}")
print(f"unregistered={len(unregistered)} dupes={len(dupes)} shadowed={len(shadowed)}")
for u in unregistered:
    print("UNREGISTERED", u)
for d in dupes:
    print("DUPE", d["first"]["method"], d["first"]["path"], d["first"]["file"], d["second"]["file"])
for s in shadowed:
    print("SHADOW", s)
