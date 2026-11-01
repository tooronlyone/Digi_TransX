"""Check for discrepancies between schema.sql and migrations.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_FILE = ROOT / "supabase" / "schema.sql"
MIGRATIONS_DIR = ROOT / "supabase" / "migrations"

schema_content = SCHEMA_FILE.read_text(encoding="utf-8")

# Extract all CREATE TABLE in schema.sql
schema_tables = set(re.findall(r"CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+(?:public\.)?([a-zA-Z0-9_]+)", schema_content, re.I))

# Extract all CREATE TABLE in migrations
migration_tables = set()
for mf in MIGRATIONS_DIR.glob("*.sql"):
    mig_content = mf.read_text(encoding="utf-8")
    for tbl in re.findall(r"CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+(?:public\.)?([a-zA-Z0-9_]+)", mig_content, re.I):
        migration_tables.add(tbl.lower())

print(f"Tables in schema.sql: {len(schema_tables)}")
print(f"Tables created in migrations: {len(migration_tables)}")

in_migrations_not_schema = migration_tables - {t.lower() for t in schema_tables}
print(f"Tables created in migrations but missing in schema.sql: {in_migrations_not_schema}")

# Check columns added in migrations: do they appear in schema.sql?
missing_columns_in_schema = []
for mf in sorted(MIGRATIONS_DIR.glob("*.sql")):
    mig_content = mf.read_text(encoding="utf-8")
    for m in re.finditer(r"ALTER\s+TABLE\s+(?:ONLY\s+)?(?:public\.)?([a-zA-Z0-9_]+)\s+ADD\s+(?:COLUMN\s+)?(?:IF\s+NOT\s+EXISTS\s+)?([a-zA-Z0-9_]+)", mig_content, re.I):
        tbl = m.group(1).lower()
        col = m.group(2).lower()
        if col in {"constraint", "primary", "foreign", "unique", "check"}:
            continue
        # check if col appears in schema.sql
        if not re.search(r"\b" + re.escape(col) + r"\b", schema_content, re.I):
            missing_columns_in_schema.append({"file": mf.name, "table": tbl, "column": col})

print(f"Columns added in migrations missing from schema.sql: {len(missing_columns_in_schema)}")
for mc in missing_columns_in_schema:
    print(f"  {mc['file']}: Table {mc['table']}, Column {mc['column']}")
