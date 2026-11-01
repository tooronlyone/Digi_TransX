"""Deep audit of database queries in backend against effective schema.

Extracts table.column patterns like:
SELECT <col> FROM <table>
WHERE <col> = ...
ORDER BY <col>
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_FILE = ROOT / "inventory" / "db_schema.json"
BACKEND = ROOT / "backend"

data = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
effective_tables = data["effective_tables"]

# Known system tables/views
IGNORE_TABLES = {"users", "auth", "information_schema", "pg_catalog", "pg_tables"}

queries = []
for py in sorted(BACKEND.rglob("*.py")):
    rel = str(py.relative_to(ROOT)).replace("\\", "/")
    if "/tests/" in rel or "/scripts/" in rel or "__pycache__" in rel:
        continue
    content = py.read_text(encoding="utf-8", errors="replace")

    # Match db.execute("...") strings
    for m in re.finditer(r'db\.execute\s*\(\s*("""|\'\'\'|["\'])(.*?)\1', content, re.DOTALL):
        sql = m.group(2)
        ln = content.count("\n", 0, m.start()) + 1
        queries.append({"sql": sql, "file": rel, "line": ln})

print(f"Total db.execute calls: {len(queries)}")

# Analyze each query
column_errors = []

for q in queries:
    sql = q["sql"]
    file = q["file"]
    line = q["line"]

    # Match simple single-table queries: SELECT ... FROM <table_name> [WHERE ...]
    # e.g., SELECT a, b, c FROM shipment_trips WHERE status = %s
    m = re.search(r"\bFROM\s+(?:public\.)?([a-zA-Z0-9_]+)(?:\s+WHERE\s+(.*?))?(?:\s+ORDER\s+BY\s+(.*?))?(?:\s+LIMIT|\s+GROUP|\s*;|\s*$)", sql, re.I | re.DOTALL)
    if m:
        tbl = m.group(1).lower()
        where_clause = m.group(2) or ""
        order_clause = m.group(3) or ""
        if tbl in effective_tables and tbl not in IGNORE_TABLES:
            schema_cols = set(effective_tables[tbl]["columns"].keys())
            
            # Check WHERE clause column references: <col> (=|IN|LIKE|IS|<|>)
            for wm in re.finditer(r"\b([a-zA-Z0-9_]+)\s*(?:=|!=|<>|<|>|<=|>=|\bIN\b|\bIS\b|\bLIKE\b|\bILIKE\b)", where_clause, re.I):
                col = wm.group(1).lower()
                if col not in {"and", "or", "not", "null", "true", "false", "case", "when", "coalesce", "lower", "upper", "trim"}:
                    if col not in schema_cols:
                        column_errors.append({
                            "type": "WHERE_NON_EXISTENT_COLUMN",
                            "table": tbl,
                            "column": col,
                            "file": file,
                            "line": line,
                            "sql": sql[:140].replace("\n", " "),
                        })

            # Check ORDER BY column references
            for om in re.finditer(r"\b([a-zA-Z0-9_]+)(?:\s+ASC|\s+DESC)?", order_clause, re.I):
                col = om.group(1).lower()
                if col not in {"nulls", "first", "last", "asc", "desc", "case", "when"}:
                    if col not in schema_cols:
                        column_errors.append({
                            "type": "ORDER_BY_NON_EXISTENT_COLUMN",
                            "table": tbl,
                            "column": col,
                            "file": file,
                            "line": line,
                            "sql": sql[:140].replace("\n", " "),
                        })

print(f"Total potential column errors found: {len(column_errors)}")
seen = set()
for err in column_errors:
    key = (err["table"], err["column"], err["file"], err["line"])
    if key not in seen:
        seen.add(key)
        print(f"[{err['type']}] Table '{err['table']}', Column '{err['column']}' at {err['file']}:{err['line']}")
        print(f"    SQL: {err['sql']}")
