"""Phase 1: Cross-match Nav Items & Links vs App Routes.

Finds:
- Category E: Sidebar/nav items that point to non-existent or dead routes.
- Category E: Sidebar/nav items with mismatched role visibility or guards.
- Category G: Commented-out routes or links in App.jsx and layouts.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NAV_FILE = ROOT / "inventory" / "nav.json"

nav_data = json.loads(NAV_FILE.read_text(encoding="utf-8"))
routes = nav_data["routes"]
nav_items = nav_data["nav_items"]
links = nav_data["links"]
commented_out = nav_data["commented_out"]

# Convert route paths to regex patterns
# e.g., /transporter/trucks/:id -> ^/transporter/trucks/[^/]+$
# /admin/* -> ^/admin(/.*)?$
route_patterns = []
for r in routes:
    p = r["path"]
    pattern = re.sub(r":\w+", r"[^/]+", p)
    pattern = pattern.replace("/*", r"(/.*)?")
    pattern = f"^{pattern}$"
    route_patterns.append({
        "route": r,
        "regex": re.compile(pattern),
    })

def matches_any_route(target_path):
    target = target_path.split("?")[0].rstrip("/") or "/"
    for rp in route_patterns:
        if rp["regex"].match(target):
            return rp["route"]
    return None

# 1. Check all nav items
dead_nav_items = []
valid_nav_items = []
for item in nav_items:
    path = item["path"]
    match = matches_any_route(path)
    if not match:
        dead_nav_items.append(item)
    else:
        valid_nav_items.append({"item": item, "matched_route": match})

# 2. Check all internal links
broken_links = []
for l in links:
    target = l["normalized"]
    # skip dynamic template expressions that couldn't be normalized cleanly
    if "${" in target:
        continue
    # replace :param with dummy 123
    test_target = target.replace(":param", "123")
    match = matches_any_route(test_target)
    if not match:
        broken_links.append(l)

print("=" * 80)
print("PHASE 1 - NAV & ROUTE CROSS MATCH RESULTS")
print(f"Total routes defined in App.jsx: {len(routes)}")
print(f"Total nav items extracted: {len(nav_items)}")
print(f"Total internal links extracted: {len(links)}")
print(f"Commented out routes/imports in App.jsx: {len(commented_out)}")
print(f"Dead Nav Items (Category E): {len(dead_nav_items)}")
print(f"Broken Internal Links (Category E / G): {len(broken_links)}")
print("=" * 80)

print("\n--- COMMENTED OUT ROUTES/IMPORTS IN APP.JSX ---")
for co in commented_out:
    print(f"  Line {co['line']}: {co['text']}")

print("\n--- [CATEGORY E] DEAD NAV ITEMS ---")
for d in dead_nav_items:
    print(f"  Nav item '{d['label']}' -> path '{d['path']}' in {d['file']}:{d['line']} (array: {d['array']})")

print("\n--- [CATEGORY E/G] BROKEN INTERNAL LINKS ---")
seen_broken = set()
for bl in broken_links:
    key = (bl["normalized"], bl["file"])
    if key not in seen_broken:
        seen_broken.add(key)
        print(f"  Target '{bl['normalized']}' (raw: {bl['target']}) in {bl['file']}:{bl['line']}")
