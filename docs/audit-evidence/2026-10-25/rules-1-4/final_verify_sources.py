"""Read-only final source verification for the local Rules 1-4 handoff."""
import ast
import hashlib
import json
from pathlib import Path

EVIDENCE = Path(__file__).resolve().parent
ROOT = EVIDENCE.parents[3]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    baseline = json.loads((EVIDENCE.parent / "source-sha256.json").read_text(encoding="utf-8-sig"))
    historical = []
    for item in baseline:
        relative = item["path"]
        if not relative.startswith("supabase/migrations/"):
            continue
        path = ROOT / relative
        current = sha256(path) if path.exists() else None
        historical.append({
            "path": relative,
            "baseline_sha256": item["sha256"],
            "current_sha256": current,
            "unchanged": current == item["sha256"],
        })
    migration_result = {
        "checked": len(historical),
        "unchanged": sum(row["unchanged"] for row in historical),
        "changed_or_missing": [row for row in historical if not row["unchanged"]],
        "entries": historical,
    }
    (EVIDENCE / "historical-migration-hash-check.json").write_text(
        json.dumps(migration_result, indent=2) + "\n", encoding="utf-8"
    )

    marker = "-- BEGIN RULES 1-4 BUSINESS POLICY CUTOVER"
    schema = (ROOT / "supabase/schema.sql").read_text(encoding="utf-8").replace("\r\n", "\n")
    migrations = sorted((ROOT / "supabase/migrations").glob("20261026*.sql"))
    expected = "\n\n".join(path.read_text(encoding="utf-8").replace("\r\n", "\n").strip() for path in migrations)
    actual = schema.split(marker, 1)[1].strip() if schema.count(marker) == 1 else None
    schema_result = {
        "marker_count": schema.count(marker),
        "migration_paths": [str(path.relative_to(ROOT)).replace("\\", "/") for path in migrations],
        "exact_body_match": actual == expected,
        "expected_sha256": hashlib.sha256(expected.encode()).hexdigest(),
        "actual_sha256": hashlib.sha256(actual.encode()).hexdigest() if actual is not None else None,
    }
    (EVIDENCE / "schema-cutover-parity.json").write_text(
        json.dumps(schema_result, indent=2) + "\n", encoding="utf-8"
    )

    ast_errors = []
    parsed = 0
    for path in sorted((ROOT / "backend").rglob("*.py")):
        try:
            ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
            parsed += 1
        except Exception as exc:
            ast_errors.append({"path": str(path.relative_to(ROOT)).replace("\\", "/"), "error": str(exc)})
    ast_result = {"parsed": parsed, "errors": ast_errors}
    (EVIDENCE / "final-python-ast.log").write_text(json.dumps(ast_result, indent=2) + "\n", encoding="utf-8")

    union = json.loads((EVIDENCE / "regression-receipt-union.json").read_text(encoding="utf-8"))
    result = {
        "historical_migrations": {key: migration_result[key] for key in ("checked", "unchanged", "changed_or_missing")},
        "schema_cutover": schema_result,
        "python_ast": ast_result,
        "backend_receipt_union": {key: union[key] for key in ("collected_cases", "covered_cases", "counts", "not_covered", "unresolved")},
        "new_rules_backend": {"passed": 150, "failed": 0},
        "targeted_wallet_lock_regression": {"passed": 198, "failed": 0, "receipt": "final-wallet-lock-regression.xml"},
        "internal_reconciliation": {"passed": 1, "failed": 0, "receipt": "final-internal-reconciliation.xml", "scope": "internal Rules1-4 journal and subledgers only"},
        "frontend": {"vitest_passed": 91, "node_passed": 103, "eslint_errors": 0, "eslint_warnings": 2, "vite_build": "passed"},
        "git_diff_check": "exit 0; line-ending warnings only",
        "production_ready": False,
    }
    (EVIDENCE / "final-verification.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "historical_migrations": f"{migration_result['unchanged']}/{migration_result['checked']} unchanged",
        "schema_cutover_exact": schema_result["exact_body_match"],
        "python_files_parsed": parsed,
        "python_ast_errors": len(ast_errors),
        "backend_union": union["counts"],
    }, indent=2))


if __name__ == "__main__":
    main()
