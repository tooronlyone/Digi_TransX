"""Phase 1: Programmatic cross-matching of Frontend API calls vs Backend Routes.

Finds:
- Category C: Frontend API calls with no matching backend route or method mismatch.
- Category D: Backend routes with no frontend caller, or called only from dead/unreachable UI.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROUTES_FILE = ROOT / "inventory" / "backend_routes.json"
FRONTEND_CALLS_FILE = ROOT / "inventory" / "frontend_calls.json"
NAV_FILE = ROOT / "inventory" / "nav.json"

backend_data = json.loads(BACKEND_ROUTES_FILE.read_text(encoding="utf-8"))
frontend_data = json.loads(FRONTEND_CALLS_FILE.read_text(encoding="utf-8"))
nav_data = json.loads(NAV_FILE.read_text(encoding="utf-8"))

backend_routes = backend_data["routes"]
frontend_calls = frontend_data["calls"]
unimported_files = {p["file"] for p in nav_data["files_import_graph"] if not p["imported_by"]}

# Convert flask route rule to regex:
# e.g. /api/users/<int:user_id> -> ^/api/users/(?P<user_id>[^/]+)$
# also handle {param} from frontend normalize: /api/users/{param}
def flask_rule_to_regex(rule):
    pattern = re.sub(r"<(?:\w+:)?(\w+)>", r"[^/]+", rule)
    return f"^{pattern}$"

compiled_routes = []
for r in backend_routes:
    compiled_routes.append({
        **r,
        "regex": re.compile(flask_rule_to_regex(r["path"])),
        "normalized_path": re.sub(r"<(?:\w+:)?(\w+)>", r"{param}", r["path"]),
    })


def normalize_fe_path(p):
    # replace multiple {param} or url params
    p = p.split("?")[0].rstrip("/") or "/"
    p = re.sub(r"\{param\}", r"{param}", p)
    return p


# 1. Match Frontend calls -> Backend routes
matched_frontend = []
orphan_frontend = []
method_mismatch_frontend = []

for call in frontend_calls:
    if call["method"] == "REF":
        continue  # accessLock allowlist constants
    path = normalize_fe_path(call["path"])
    # test regex against raw path or converted path
    # replace {param} with a dummy id '123' for regex matching
    test_path = path.replace("{param}", "123").replace("${id}", "123")

    matched_by_path = []
    matched_exact = []

    for r in compiled_routes:
        if r["regex"].match(test_path) or r["normalized_path"] == path:
            matched_by_path.append(r)
            if r["method"] == call["method"]:
                matched_exact.append(r)

    is_unreachable_ui = call["file"] in unimported_files or any(call["file"].endswith(uf) for uf in unimported_files)

    if matched_exact:
        matched_frontend.append({
            "call": call,
            "matched_routes": matched_exact,
            "from_dead_page": is_unreachable_ui,
        })
    elif matched_by_path:
        method_mismatch_frontend.append({
            "call": call,
            "expected_method": call["method"],
            "backend_methods": [r["method"] for r in matched_by_path],
            "backend_routes": matched_by_path,
            "from_dead_page": is_unreachable_ui,
        })
    else:
        orphan_frontend.append({
            "call": call,
            "from_dead_page": is_unreachable_ui,
        })

# 2. Match Backend routes -> Frontend callers
called_backend = {}
for m in matched_frontend:
    for r in m["matched_routes"]:
        key = (r["method"], r["path"])
        called_backend.setdefault(key, []).append(m)

orphan_backend = []
called_only_by_dead_pages = []

for r in backend_routes:
    key = (r["method"], r["path"])
    callers = called_backend.get(key, [])
    if not callers:
        orphan_backend.append(r)
    elif all(c["from_dead_page"] for c in callers):
        called_only_by_dead_pages.append({
            "route": r,
            "callers": callers,
        })

print("=" * 80)
print(f"PHASE 1 - API CROSS MATCH RESULTS")
print(f"Total frontend calls evaluated: {len(frontend_calls)}")
print(f"Total backend routes evaluated: {len(backend_routes)}")
print(f"Orphan Frontend Calls (Category C - no backend endpoint): {len(orphan_frontend)}")
print(f"Method Mismatch Calls (Category C - path exists, method wrong): {len(method_mismatch_frontend)}")
print(f"Orphan Backend Routes (Category D - no frontend caller): {len(orphan_backend)}")
print(f"Backend Routes called ONLY by dead pages (Category D): {len(called_only_by_dead_pages)}")
print("=" * 80)

print("\n--- [CATEGORY C] ORPHAN FRONTEND CALLS ---")
for o in orphan_frontend:
    c = o["call"]
    dead_tag = " [IN UNIMPORTED/DEAD PAGE]" if o["from_dead_page"] else " [ACTIVE UI!]"
    print(f"{dead_tag} {c['method']} {c['path']} -> {c['file']}:{c['line']}")
    print(f"    Code snippet: {c['context']}")

print("\n--- [CATEGORY C] METHOD MISMATCH FRONTEND CALLS ---")
for mm in method_mismatch_frontend:
    c = mm["call"]
    dead_tag = " [IN UNIMPORTED/DEAD PAGE]" if mm["from_dead_page"] else " [ACTIVE UI!]"
    print(f"{dead_tag} {c['method']} {c['path']} -> backend has: {mm['backend_methods']} at {c['file']}:{c['line']}")

print("\n--- [CATEGORY D] ORPHAN BACKEND ROUTES ---")
# Group by prefix
by_prefix = {}
for r in orphan_backend:
    pfx = r["path"].split("/")[1] if len(r["path"].split("/")) > 1 else "root"
    if pfx == "api" and len(r["path"].split("/")) > 2:
        pfx = f"api/{r['path'].split('/')[2]}"
    by_prefix.setdefault(pfx, []).append(r)

for pfx, rlist in sorted(by_prefix.items()):
    print(f"\nPrefix: /{pfx} ({len(rlist)} routes)")
    for r in rlist:
        print(f"  {r['method']} {r['path']} ({r['handler']}) -> {r['file']}:{r['line']}")

print("\n--- [CATEGORY D] BACKEND ROUTES CALLED ONLY FROM DEAD PAGES ---")
for d in called_only_by_dead_pages:
    r = d["route"]
    callers = [f"{c['call']['file']}:{c['call']['line']}" for c in d["callers"]]
    print(f"  {r['method']} {r['path']} called only by: {', '.join(callers)}")
