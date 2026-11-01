"""Inspect all active UI orphan frontend calls in detail.
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
    p = p.split("?")[0].rstrip("/") or "/"
    return p

active_orphans = []
for call in frontend_calls:
    if call["method"] == "REF":
        continue
    is_unreachable_ui = call["file"] in unimported_files or any(call["file"].endswith(uf) for uf in unimported_files)
    if is_unreachable_ui:
        continue
    path = normalize_fe_path(call["path"])
    test_path = path.replace("{param}", "123").replace("${id}", "123").replace("${orderId}", "123").replace("${action}", "approve")
    
    matched = False
    for r in compiled_routes:
        if r["regex"].match(test_path) or r["normalized_path"] == path:
            matched = True
            break
    if not matched:
        active_orphans.append(call)

print(f"Total active orphans: {len(active_orphans)}")
for o in active_orphans:
    print(f"{o['method']} {o['path']} in {o['file']}:{o['line']}")
    print(f"    Raw: {o['raw']}")
    print(f"    Context: {o['context']}")
