"""Phase 0: extract every frontend HTTP call (method + path + file:line).

Strategy: find every string/template literal whose value starts with /api/,
/auth/ or /uploads/ in frontend-react/src, then infer the HTTP method from the
wrapper it is passed to (apiGet/apiSend/adminRequest/fetch/requestJson/...).
Literals that are not directly passed to a known wrapper are kept with
method "?" plus a context snippet so they can be resolved manually; nothing
is silently dropped.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "frontend-react" / "src"
OUT = ROOT / "inventory" / "frontend_calls.json"

LIT = re.compile(r"""(['"`])(/(?:api|auth|uploads)/[^'"`]*?|/(?:api|auth))\1""", re.S)
CALLER = re.compile(r"([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\s*\(\s*$")

GET_WRAPPERS = {"apiGet", "get", "api.get", "fetchJson", "window.open", "useSWR", "loadJson"}
POST_WRAPPERS = {"post", "api.post", "apiPost", "send", "postAction", "postJson"}
PUT_WRAPPERS = {"put", "api.put"}
DEL_WRAPPERS = {"del", "api.del"}
OPTION_WRAPPERS = {
    "fetch", "adminRequest", "requestJson", "protectedFetch", "fetchForOwner",
    "fetcher", "fetchImpl", "request", "api.request", "window.fetch", "globalThis.fetch",
}


def line_of(text, idx):
    return text.count("\n", 0, idx) + 1


def normalize(raw, after):
    path = re.sub(r"\$\{[^}]*\}", "{param}", raw)
    # string concatenation: '/api/x/' + id
    if raw.endswith("/") and re.match(r"\s*\+\s*[\w.$\[\]()]+", after):
        path += "{param}"
    path = path.split("?")[0]
    # trailing {param} that is a query-string builder (e.g. ${qs(...)})
    if re.search(r"\$\{\s*(qs|query|params|search|buildQuery|toQuery)\b[^}]*\}$", raw):
        path = re.sub(r"\{param\}$", "", path)
    return path


def call_span(text, start):
    """Return text from start up to the matching close paren (best effort)."""
    depth = 1
    i = start
    while i < len(text) and depth and i - start < 1500:
        c = text[i]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        i += 1
    return text[start:i]


def infer(text, m):
    before = text[max(0, m.start() - 200): m.start()]
    cm = CALLER.search(before)
    after_span = call_span(text, m.end())
    if not cm:
        mm = re.search(r"method\s*:\s*['\"](\w+)['\"]", text[m.end(): m.end() + 500])
        return "?", None, (mm.group(1).upper() if mm else None)
    caller = cm.group(1)
    if caller in GET_WRAPPERS:
        return "GET", caller, None
    if caller in POST_WRAPPERS:
        return "POST", caller, None
    if caller in PUT_WRAPPERS:
        return "PUT", caller, None
    if caller in DEL_WRAPPERS:
        return "DELETE", caller, None
    if caller == "apiSend":
        mm = re.search(r"['\"](POST|PUT|PATCH|DELETE)['\"]", after_span)
        return (mm.group(1) if mm else "POST"), caller, None
    if caller in OPTION_WRAPPERS or caller.endswith("Fetch") or caller.endswith("fetch"):
        mm = re.search(r"method\s*:\s*['\"](\w+)['\"]", after_span)
        if mm:
            return mm.group(1).upper(), caller, None
        if re.search(r"method\s*:", after_span) or re.search(r"\.\.\.\s*\w+", after_span):
            return "?", caller, "dynamic-method"
        return "GET", caller, None
    return "?", caller, None


calls = []
files = [
    f for f in sorted(SRC.rglob("*"))
    if f.suffix in {".js", ".jsx", ".ts", ".tsx"} and ".test." not in f.name
]

# Pass 1: module-level URL constants, e.g. export const AI_API_BASE = '/api/ai-assistant'
CONST = re.compile(r"""(?:export\s+)?const\s+([A-Z_][A-Z0-9_]*)\s*=\s*(['"`])(/(?:api|auth)[^'"`]*)\2""")
url_constants = {}
for f in files:
    for cm in CONST.finditer(f.read_text(encoding="utf-8", errors="replace")):
        url_constants[cm.group(1)] = cm.group(3)

# Manual resolutions, each verified by reading the file (see AUDIT_LEDGER Phase 0 notes).
MANUAL = {
    ("frontend-react/src/auth/accessLock.js", None): ("REF", "allow-list constant, not a request"),
    ("frontend-react/src/lib/aiAssistant.js", 1): ("REF", "AI_API_BASE constant; expanded at use sites"),
    ("frontend-react/src/auth/genuineActivity.js", 1): ("POST", "fetchImpl(GENUINE_ACTIVITY_ENDPOINT,{method:'POST'}) line 16"),
    ("frontend-react/src/components/security/MpinManagement.jsx", 39): ("GET", "requestJson('/auth/mpin/status') default GET"),
    ("frontend-react/src/components/security/MpinManagement.jsx", 95): ("POST", "mutate('enrollment') line 95"),
    ("frontend-react/src/components/security/MpinManagement.jsx", 105): ("POST", "mutate('change') line 105"),
    ("frontend-react/src/components/security/MpinManagement.jsx", 115): ("POST", "mutate('disable') line 115"),
    ("frontend-react/src/components/security/MpinManagement.jsx", 125): ("POST", "mutate('reset') line 125"),
    ("frontend-react/src/pages/transporter/PartsMarketplace.jsx", 75): ("GET", "fetch(url,{credentials}) line 79"),
}
INVENTORY_PUT_POST = ("frontend-react/src/pages/shopkeeper/InventoryPage.jsx", 79)

for f in files:
    text = f.read_text(encoding="utf-8", errors="replace")
    rel = str(f.relative_to(ROOT)).replace("\\", "/")
    lines = text.splitlines()
    matches = list(LIT.finditer(text))
    # constant-prefixed templates: `${AI_API_BASE}/interpret`
    for name, value in url_constants.items():
        for tm in re.finditer(r"`\$\{\s*" + name + r"\s*\}([^`]*)`", text):
            matches.append(("CONST", tm, value + tm.group(1)))
    for m in matches:
        if isinstance(m, tuple):
            _, m, raw = m
        else:
            raw = m.group(2)
        method, caller, hint = infer(text, m)
        ln = line_of(text, m.start())
        key_line = (rel, ln)
        key_file = (rel, None)
        if key_line in MANUAL:
            method, hint = MANUAL[key_line]
        elif key_file in MANUAL:
            method, hint = MANUAL[key_file]
        elif key_line == INVENTORY_PUT_POST:
            method = "PUT" if "${" in raw else "POST"
            hint = "isEdit ? PUT : POST (line 80)"
        calls.append({
            "method": method,
            "path": normalize(raw, text[m.end(): m.end() + 40]),
            "raw": raw,
            "caller": caller,
            "hint": hint,
            "file": rel,
            "line": ln,
            "context": lines[ln - 1].strip()[:220],
        })

OUT.write_text(json.dumps({"count": len(calls), "calls": calls}, indent=2), encoding="utf-8")
unk = [c for c in calls if c["method"] == "?"]
print(f"calls={len(calls)} unresolved_method={len(unk)}")
for c in unk:
    print(f"? {c['path']}  caller={c['caller']} hint={c['hint']}  {c['file']}:{c['line']}  | {c['context'][:140]}")
