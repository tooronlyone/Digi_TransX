"""Phase 0: extract DB models, migrations, and effective schema into inventory/db_schema.json.

Also extracts all SQL table and column references across backend python files.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SUPABASE = ROOT / "supabase"
BACKEND = ROOT / "backend"
OUT = ROOT / "inventory" / "db_schema.json"

SCHEMA_FILE = SUPABASE / "schema.sql"
MIGRATIONS_DIR = SUPABASE / "migrations"


def parse_create_table(sql):
    tables = {}
    # Find CREATE TABLE [IF NOT EXISTS] (public.)?<name> ( ... );
    pattern = re.compile(
        r"CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+(?:public\.)?([a-zA-Z0-9_]+)\s*\((.*?)\);",
        re.DOTALL | re.IGNORECASE,
    )
    for m in pattern.finditer(sql):
        tbl = m.group(1).lower()
        body = m.group(2)
        columns = {}
        constraints = []
        for line in body.splitlines():
            line = line.strip().rstrip(",")
            if not line or line.startswith("--"):
                continue
            if re.match(r"^(CONSTRAINT|PRIMARY\s+KEY|FOREIGN\s+KEY|UNIQUE|CHECK)\b", line, re.I):
                constraints.append(line)
                continue
            parts = line.split()
            if len(parts) >= 2:
                col_name = parts[0].strip('"').lower()
                col_type = parts[1].upper()
                columns[col_name] = {
                    "type": col_type,
                    "definition": line,
                    "nullable": "NOT NULL" not in line.upper(),
                }
        tables[tbl] = {
            "columns": columns,
            "constraints": constraints,
        }
    return tables


# Parse schema.sql baseline
baseline_tables = {}
if SCHEMA_FILE.exists():
    baseline_tables = parse_create_table(SCHEMA_FILE.read_text(encoding="utf-8"))

# Parse migrations in chronological order
migrations = []
effective_tables = {t: {"columns": dict(data["columns"]), "constraints": list(data["constraints"])} for t, data in baseline_tables.items()}

mig_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
for mf in mig_files:
    sql = mf.read_text(encoding="utf-8")
    mig_info = {
        "file": mf.name,
        "creates": [],
        "adds": [],
        "drops": [],
        "drop_tables": [],
        "alters": [],
    }

    # CREATE TABLE
    new_tables = parse_create_table(sql)
    for tbl, data in new_tables.items():
        mig_info["creates"].append(tbl)
        if tbl not in effective_tables:
            effective_tables[tbl] = data
        else:
            effective_tables[tbl]["columns"].update(data["columns"])
            effective_tables[tbl]["constraints"].extend(data["constraints"])

    # DROP TABLE (the final Agreemental retirement migration intentionally
    # removes tables that older immutable migrations created).
    for drop_table in re.finditer(
        r"DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:public\.)?([a-zA-Z0-9_]+)",
        sql,
        re.I,
    ):
        tbl = drop_table.group(1).lower()
        mig_info["drop_tables"].append(tbl)
        effective_tables.pop(tbl, None)

    # ALTER TABLE ... (supports multi-column ADD COLUMN)
    for alter_block in re.finditer(r"ALTER\s+TABLE\s+(?:ONLY\s+)?(?:public\.)?([a-zA-Z0-9_]+)\s+(.*?);", sql, re.I | re.DOTALL):
        tbl = alter_block.group(1).lower()
        block_body = alter_block.group(2)
        if tbl not in effective_tables:
            effective_tables[tbl] = {"columns": {}, "constraints": []}
        
        for add_match in re.finditer(r"ADD\s+(?:COLUMN\s+)?(?:IF\s+NOT\s+EXISTS\s+)?([a-zA-Z0-9_]+)\s+([^;,\n]+)", block_body, re.I):
            col = add_match.group(1).lower()
            if col in {"constraint", "primary", "foreign", "unique", "check"}:
                continue
            col_type = add_match.group(2).strip().split()[0].upper()
            mig_info["adds"].append({"table": tbl, "column": col, "type": col_type})
            effective_tables[tbl]["columns"][col] = {
                "type": col_type,
                "definition": add_match.group(0),
                "nullable": "NOT NULL" not in add_match.group(2).upper(),
            }

        for drop_match in re.finditer(r"DROP\s+(?:COLUMN\s+)?(?:IF\s+EXISTS\s+)?([a-zA-Z0-9_]+)", block_body, re.I):
            col = drop_match.group(1).lower()
            if col in {"constraint"}:
                continue
            mig_info["drops"].append({"table": tbl, "column": col})
            if col in effective_tables[tbl]["columns"]:
                del effective_tables[tbl]["columns"][col]
            # PostgreSQL removes dependent CHECK/UNIQUE constraints when a
            # column is dropped with CASCADE. Keep the effective inventory in
            # sync instead of retaining a constraint for a retired column.
            effective_tables[tbl]["constraints"] = [
                constraint
                for constraint in effective_tables[tbl]["constraints"]
                if not re.search(rf"\b{re.escape(col)}\b", constraint, re.I)
            ]

        for drop_constraint in re.finditer(
            r"DROP\s+CONSTRAINT\s+(?:IF\s+EXISTS\s+)?([a-zA-Z0-9_]+)",
            block_body,
            re.I,
        ):
            name = drop_constraint.group(1).lower()
            # Baseline CREATE TABLE constraints are sometimes unnamed in the
            # source. In that case infer the checked column from PostgreSQL's
            # conventional <table>_<column>_check constraint name.
            inferred_column = name
            table_prefix = f"{tbl}_"
            if inferred_column.startswith(table_prefix):
                inferred_column = inferred_column[len(table_prefix):]
            if inferred_column.endswith("_check"):
                inferred_column = inferred_column[:-6]
            effective_tables[tbl]["constraints"] = [
                constraint
                for constraint in effective_tables[tbl]["constraints"]
                if name not in constraint.lower()
                and not re.search(
                    rf"\b{re.escape(inferred_column)}\b", constraint, re.I
                )
            ]

        for add_constraint in re.finditer(
            r"ADD\s+CONSTRAINT\s+([a-zA-Z0-9_]+)\s+(.+?)(?=,\s*(?:ADD|DROP|ALTER)\b|$)",
            block_body,
            re.I | re.DOTALL,
        ):
            definition = f"CONSTRAINT {add_constraint.group(1)} {add_constraint.group(2).strip()}"
            if definition not in effective_tables[tbl]["constraints"]:
                effective_tables[tbl]["constraints"].append(definition)

    migrations.append(mig_info)

# Scan backend python files for SQL table and column usages
sql_usages = []
for py in sorted(BACKEND.rglob("*.py")):
    rel = str(py.relative_to(ROOT)).replace("\\", "/")
    if "/tests/" in rel or "/scripts/" in rel or "__pycache__" in rel:
        continue
    content = py.read_text(encoding="utf-8", errors="replace")

    # String literals that contain SQL statements
    for m in re.finditer(r'("""|\'\'\'|["\'])(.*?\b(?:SELECT|INSERT\s+INTO|UPDATE|DELETE\s+FROM)\b.*?)\1', content, re.DOTALL | re.IGNORECASE):
        raw_sql = m.group(2)
        ln = content.count("\n", 0, m.start()) + 1

        # INSERT INTO <table> (<col1>, <col2>)
        for ins in re.finditer(r"INSERT\s+INTO\s+(?:public\.)?([a-zA-Z0-9_]+)\s*\(([^)]+)\)", raw_sql, re.I):
            tbl = ins.group(1).lower()
            cols = [c.strip().split()[-1].strip('"').lower() for c in ins.group(2).split(",")]
            sql_usages.append({
                "type": "INSERT",
                "table": tbl,
                "columns": cols,
                "file": rel,
                "line": ln,
                "snippet": ins.group(0)[:120],
            })

        # UPDATE <table> SET <col1> = ..., <col2> = ...
        for upd in re.finditer(r"UPDATE\s+(?:public\.)?([a-zA-Z0-9_]+)\s+SET\s+(.*?)(?:\s+WHERE|\s+RETURNING|\s*$)", raw_sql, re.I | re.DOTALL):
            tbl = upd.group(1).lower()
            set_clause = upd.group(2)
            cols = []
            for item in set_clause.split(","):
                before_eq = item.split("=")[0].strip()
                if not before_eq:
                    continue
                parts = before_eq.split()
                if parts:
                    part = parts[-1].strip('"').lower()
                    if part and part.isidentifier():
                        cols.append(part)
            sql_usages.append({
                "type": "UPDATE",
                "table": tbl,
                "columns": cols,
                "file": rel,
                "line": ln,
                "snippet": upd.group(0)[:120].replace("\n", " "),
            })

        # SELECT ... FROM <table>
        for sel in re.finditer(r"FROM\s+(?:public\.)?([a-zA-Z0-9_]+)", raw_sql, re.I):
            tbl = sel.group(1).lower()
            if tbl not in {"where", "join", "select", "as"}:
                sql_usages.append({
                    "type": "SELECT_FROM",
                    "table": tbl,
                    "columns": [],
                    "file": rel,
                    "line": ln,
                    "snippet": raw_sql[:120].replace("\n", " "),
                })

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps({
    "baseline_table_count": len(baseline_tables),
    "migration_count": len(migrations),
    "effective_table_count": len(effective_tables),
    "effective_tables": effective_tables,
    "sql_usages_count": len(sql_usages),
    "sql_usages": sql_usages,
    "migrations": migrations,
}, indent=2), encoding="utf-8")

print(f"Extracted schema: {len(baseline_tables)} baseline tables, {len(migrations)} migrations, {len(effective_tables)} effective tables, {len(sql_usages)} code SQL usages.")
