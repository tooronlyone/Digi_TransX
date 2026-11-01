"""Audit row dictionary key accesses against table schema.

Finds queries like:
row = db.execute("SELECT * FROM <table> WHERE ...").fetchone()
... row["some_column"] or row.get("some_column")
where some_column does not exist on <table>!
"""
import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_FILE = ROOT / "inventory" / "db_schema.json"
BACKEND = ROOT / "backend"

data = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
effective_tables = data["effective_tables"]

# Patterns where a query selects * from a single table into a variable:
# e.g.:
# row = db.execute("SELECT * FROM <table> ...").fetchone()
# user = db.execute("... FROM users ...").fetchone()
# and then accesses row["col"] or row.get("col")

KEY_ACCESS = re.compile(r"""\b([a-zA-Z0-9_]+)(?:\[['"]([a-zA-Z0-9_]+)['"]\]|\.get\(['"]([a-zA-Z0-9_]+)['"]\))""")

# Let's inspect function by function in Python AST:
mismatches = []

for py in sorted(BACKEND.rglob("*.py")):
    rel = str(py.relative_to(ROOT)).replace("\\", "/")
    if "/tests/" in rel or "/scripts/" in rel or "__pycache__" in rel:
        continue
    content = py.read_text(encoding="utf-8", errors="replace")

    # Look for functions where a query assigns to var = db.execute("SELECT * FROM <table> ...")
    pattern = re.compile(
        r"""([a-zA-Z0-9_]+)\s*=\s*db\.execute\s*\(\s*(?:f?["']|f?\"\"\")\s*SELECT\s+(?:\*|[^;]+)\s+FROM\s+(?:public\.)?([a-zA-Z0-9_]+).*?\.(fetchone|fetchall)\(\)""",
        re.I | re.DOTALL,
    )

    for m in pattern.finditer(content):
        var_name = m.group(1)
        tbl_name = m.group(2).lower()
        call_type = m.group(3)
        start_idx = m.end()
        # Look ahead up to 100 lines for accesses to var_name['...']
        span_text = content[start_idx: start_idx + 3000]
        
        if tbl_name in effective_tables:
            schema_cols = set(effective_tables[tbl_name]["columns"].keys())
            
            # Find var_name['col'] or var_name.get('col')
            for km in KEY_ACCESS.finditer(span_text):
                if km.group(1) == var_name or (call_type == "fetchall" and km.group(1) in {"row", "item", "r", "t"}):
                    col = km.group(2) or km.group(3)
                    if col and col not in schema_cols:
                        ln = content.count("\n", 0, start_idx + km.start()) + 1
                        mismatches.append({
                            "file": rel,
                            "line": ln,
                            "table": tbl_name,
                            "column": col,
                            "var": var_name,
                            "known_columns": sorted(list(schema_cols)),
                        })

print(f"Total row access mismatches found: {len(mismatches)}")
seen = set()
for mm in mismatches:
    key = (mm["file"], mm["line"], mm["table"], mm["column"])
    if key not in seen:
        seen.add(key)
        print(f"File {mm['file']}:{mm['line']} accesses '{mm['column']}' on table '{mm['table']}' (var: {mm['var']})")
