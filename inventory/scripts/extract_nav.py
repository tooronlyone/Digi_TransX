"""Phase 0: extract React routes, sidebar/nav items, and in-app links.

Outputs inventory/nav.json with:
  routes     - every <Route path> in App.jsx, fully prefixed per portal
  nav_items  - every {path,label} entry in layout/nav files (array name kept)
  links      - every <Link to>, navigate(), href, window.location target in src
  page_files - every page file and whether App.jsx imports it
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "frontend-react" / "src"
OUT = ROOT / "inventory" / "nav.json"
app = (SRC / "App.jsx").read_text(encoding="utf-8")
app_lines = app.splitlines()

# --- routes ---------------------------------------------------------------
portal_prefix = {}
for m in re.finditer(r'<Route\s+path="([^"]+)\*"\s+element=\{<(\w+)\s*/>\}', app):
    portal_prefix[m.group(2)] = m.group(1).rstrip("/")

routes = []
func_spans = [(m.group(1), m.start()) for m in re.finditer(r"^function (\w+)\(", app, re.M)]
func_spans.append(("__END__", len(app)))
export_start = app.find("export default function App")


def owner(idx):
    name = None
    for fname, start in func_spans:
        if start <= idx:
            name = fname
    return name


for m in re.finditer(r'<Route\s+(?:path="([^"]*)"|index)\s*(?:element=\{(.*?)\})?\s*/?>', app, re.S):
    idx = m.start()
    line = app.count("\n", 0, idx) + 1
    if app_lines[line - 1].strip().startswith("{/*"):
        continue
    path = m.group(1)
    element = (m.group(2) or "").strip()
    fn = owner(idx) if idx < export_start else "App"
    prefix = portal_prefix.get(fn, "")
    if path is None:
        full = prefix or "/"
        kind = "index"
    elif path.startswith("/"):
        full = path
        kind = "absolute"
    else:
        full = f"{prefix}/{path}" if prefix else f"/{path}"
        kind = "relative"
    # signup nested children
    if fn == "App" and path and not path.startswith("/") :
        full = f"/signup/{path}"
    redirect = re.search(r'<Navigate\s+to="([^"]+)"', element)
    comp = re.search(r"<(\w+)", element)
    routes.append({
        "path": full,
        "portal": fn,
        "element": comp.group(1) if comp else None,
        "redirect_to": redirect.group(1) if redirect else None,
        "line": line,
        "kind": kind,
    })

commented_routes = [
    {"line": i + 1, "text": l.strip()} for i, l in enumerate(app_lines)
    if re.search(r"^\s*(\{/\*|//).*<?Route|^\s*//\s*import", l)
]

# --- nav items -----------------------------------------------------------
NAV_FILES = list((SRC / "components").rglob("*Layout*.jsx")) + [
    SRC / "components/transporter/navItems.js",
    SRC / "components/client/OrderWorkspaceNavigation.jsx",
]
nav_items = []
for f in NAV_FILES:
    text = f.read_text(encoding="utf-8")
    rel = str(f.relative_to(ROOT)).replace("\\", "/")
    arrays = [(m.group(1), m.start()) for m in re.finditer(r"const\s+(\w+)\s*=\s*\[", text)]
    for m in re.finditer(r"\{[^{}]*\bpath:\s*'([^']+)'[^{}]*\}", text):
        label = re.search(r"label:\s*'([^']+)'", m.group(0))
        arr = None
        for name, start in arrays:
            if start < m.start():
                arr = name
        nav_items.append({
            "file": rel,
            "array": arr,
            "path": m.group(1),
            "label": label.group(1) if label else None,
            "match": re.findall(r"'(/[^']+)'", (re.search(r"match:\s*\[([^\]]*)\]", m.group(0)) or [None, ""])[1] if re.search(r"match:\s*\[", m.group(0)) else ""),
            "line": text.count("\n", 0, m.start()) + 1,
        })
    for m in re.finditer(r'<(?:Nav)?Link\s+to="([^"]+)"', text):
        nav_items.append({
            "file": rel, "array": "<Link>", "path": m.group(1), "label": None, "match": [],
            "line": text.count("\n", 0, m.start()) + 1,
        })

# --- links ---------------------------------------------------------------
LINK_PATTERNS = [
    r'\bto=\{?\s*["\'`]([^"\'`]+)["\'`]',
    r'navigate\(\s*["\'`]([^"\'`]+)["\'`]',
    r'href=\{?\s*["\'`](/[^"\'`]*)["\'`]',
    r'window\.location(?:\.href)?\s*=\s*["\'`]([^"\'`]+)["\'`]',
    r'window\.location\.(?:assign|replace)\(\s*["\'`]([^"\'`]+)["\'`]',
    r'<Navigate\s+to=\{?\s*["\'`]([^"\'`]+)["\'`]',
]
links = []
for f in sorted(SRC.rglob("*")):
    if f.suffix not in {".js", ".jsx", ".mjs"} or ".test." in f.name:
        continue
    text = f.read_text(encoding="utf-8", errors="replace")
    rel = str(f.relative_to(ROOT)).replace("\\", "/")
    for pat in LINK_PATTERNS:
        for m in re.finditer(pat, text):
            target = m.group(1)
            if not target.startswith("/") and not target.startswith("${"):
                continue
            links.append({
                "target": target,
                "normalized": re.sub(r"\$\{[^}]*\}", ":param", target).split("?")[0].split("#")[0],
                "file": rel,
                "line": text.count("\n", 0, m.start()) + 1,
            })

# --- page files & imports ------------------------------------------------
all_text = {
    str(f.relative_to(SRC)).replace("\\", "/"): f.read_text(encoding="utf-8", errors="replace")
    for f in SRC.rglob("*") if f.suffix in {".js", ".jsx", ".mjs"}
}
page_files = []
for rel in sorted(all_text):
    if not (rel.startswith("pages/") or rel.startswith("components/")):
        continue
    stem = rel.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    importers = [
        other for other, t in all_text.items()
        if other != rel and re.search(r"""from\s+['"][^'"]*/""" + re.escape(stem) + r"""(\.\w+)?['"]""", t)
    ]
    page_files.append({"file": rel, "imported_by": importers})

OUT.write_text(json.dumps({
    "routes": routes,
    "commented_out": commented_routes,
    "nav_items": nav_items,
    "links": links,
    "files_import_graph": page_files,
}, indent=2), encoding="utf-8")
print(f"routes={len(routes)} nav_items={len(nav_items)} links={len(links)} files={len(page_files)}")
print("UNIMPORTED FILES:")
for p in page_files:
    if not p["imported_by"]:
        print("  ", p["file"])
