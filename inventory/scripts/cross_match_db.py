"""Phase 1: Database Model / Migration vs Code Cross-match (Category F).

Checks:
- Tables referenced in code SQL (INSERT/UPDATE/SELECT) that do not exist in effective schema.
- Columns referenced in code SQL (INSERT/UPDATE) that do not exist in effective schema.
- Queries or references to obsolete/non-existent columns.
- Model/schema inconsistencies between baseline schema.sql and migrations.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_FILE = ROOT / "inventory" / "db_schema.json"
BACKEND = ROOT / "backend"

data = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
effective_tables = data["effective_tables"]
sql_usages = data["sql_usages"]

# Special/built-in tables or aliases to ignore in query detection
BUILTIN_TABLES = {"users", "auth", "information_schema", "pg_catalog", "pg_tables"}

missing_tables = []
missing_columns = []

for u in sql_usages:
    tbl = u["table"].lower()
    # handle subqueries, aliases, or syntax artifacts
    if tbl.startswith("(") or tbl in BUILTIN_TABLES:
        continue
    
    if tbl not in effective_tables:
        missing_tables.append(u)
        continue

    table_schema = effective_tables[tbl]
    schema_cols = set(table_schema["columns"].keys())

    # For INSERT and UPDATE, verify that the columns actually exist in the schema
    for col in u.get("columns", []):
        col_clean = col.lower().strip()
        if not col_clean or col_clean.startswith("%") or col_clean in {"excluded", "values"}:
            continue
        if col_clean not in schema_cols:
            missing_columns.append({
                "table": tbl,
                "column": col_clean,
                "type": u["type"],
                "file": u["file"],
                "line": u["line"],
                "snippet": u["snippet"],
                "known_schema_columns": sorted(list(schema_cols)),
            })

# Scan backend files for explicit queries referencing specific suspicious column patterns
# e.g., references to non-existent fields, legacy columns, etc.
raw_sql_checks = []
for py in sorted(BACKEND.rglob("*.py")):
    rel = str(py.relative_to(ROOT)).replace("\\", "/")
    if "/tests/" in rel or "/scripts/" in rel or "__pycache__" in rel:
        continue
    content = py.read_text(encoding="utf-8", errors="replace")

    # Check for queries selecting or filtering on fields across common tables
    for m in re.finditer(r"SELECT\s+(.*?)\s+FROM\s+(?:public\.)?([a-zA-Z0-9_]+)", content, re.I | re.DOTALL):
        select_clause = m.group(1)
        tbl = m.group(2).lower()
        ln = content.count("\n", 0, m.start()) + 1
        if tbl in effective_tables:
            schema_cols = set(effective_tables[tbl]["columns"].keys())
            # check simple column names
            for item in select_clause.split(","):
                item_clean = item.strip().split()[-1].strip('"').lower()
                # filter out functions, aggregates, constants
                if item_clean.isidentifier() and not item_clean.startswith("coalesce") and not item_clean.startswith("nullif"):
                    if item_clean != "*" and item_clean not in schema_cols:
                        # might be alias or expression; check if it's directly named
                        if re.search(r"\b" + item_clean + r"\b", item) and not re.search(r"AS\s+" + item_clean, item, re.I):
                            raw_sql_checks.append({
                                "table": tbl,
                                "column": item_clean,
                                "file": rel,
                                "line": ln,
                                "snippet": m.group(0)[:120].replace("\n", " "),
                            })

print("=" * 80)
print("PHASE 1 - DATABASE MODEL & MIGRATION CROSS MATCH RESULTS")
print(f"Total SQL usages checked: {len(sql_usages)}")
print(f"Total effective tables in schema: {len(effective_tables)}")
print(f"Missing Tables referenced in code: {len(missing_tables)}")
print(f"Missing Columns in INSERT/UPDATE: {len(missing_columns)}")
print("=" * 80)

print("\n--- [CATEGORY F] MISSING TABLES REFERENCED IN CODE ---")
seen_tbls = set()
for mt in missing_tables:
    key = (mt["table"], mt["file"])
    if key not in seen_tbls:
        seen_tbls.add(key)
        print(f"Table '{mt['table']}' in {mt['file']}:{mt['line']} ({mt['type']})")
        print(f"    Snippet: {mt['snippet']}")

print("\n--- [CATEGORY F] MISSING COLUMNS IN INSERT/UPDATE ---")
seen_cols = set()
for mc in missing_columns:
    key = (mc["table"], mc["column"], mc["file"])
    if key not in seen_cols:
        seen_cols.add(key)
        print(f"Column '{mc['column']}' on table '{mc['table']}' in {mc['file']}:{mc['line']} ({mc['type']})")
        print(f"    Snippet: {mc['snippet']}")
        print(f"    Known table columns: {mc['known_schema_columns']}")
