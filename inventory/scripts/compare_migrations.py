"""Compare schema.sql baseline vs migration-built schema.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_FILE = ROOT / "inventory" / "db_schema.json"

data = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
effective_tables = data["effective_tables"]

# Check migration files
MIGRATIONS_DIR = ROOT / "supabase" / "migrations"
mig_files = sorted(MIGRATIONS_DIR.glob("*.sql"))

print(f"Total migrations: {len(mig_files)}")
for mf in mig_files:
    content = mf.read_text(encoding="utf-8")
    # Check for DROP TABLE, DROP COLUMN, or ALTER COLUMN TYPE
    drops = re.findall(r"DROP\s+(TABLE|COLUMN)\s+(?:IF\s+EXISTS\s+)?([a-zA-Z0-9_.]+)", content, re.I)
    alters = re.findall(r"ALTER\s+TABLE\s+(?:ONLY\s+)?([a-zA-Z0-9_.]+)\s+ALTER\s+(?:COLUMN\s+)?([a-zA-Z0-9_]+)\s+TYPE\s+([^;,\n]+)", content, re.I)
    renames = re.findall(r"RENAME\s+COLUMN\s+([a-zA-Z0-9_]+)\s+TO\s+([a-zA-Z0-9_]+)", content, re.I)
    if drops or alters or renames:
        print(f"Migration: {mf.name}")
        if drops:
            print(f"    Drops: {drops}")
        if alters:
            print(f"    Alters: {alters}")
        if renames:
            print(f"    Renames: {renames}")
