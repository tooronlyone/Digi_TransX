"""Deduplicate this task's JUnit receipts against the current test collection.

Run after collection and verification have completed. A later run START time
takes precedence, because a long broad run can finish after a corrected focused
run while still holding earlier imported Python source. Raw receipts are never
edited. This index establishes executed case coverage; source compatibility of
each follow-up remains an explicit part of the implementation report.
"""
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[4]
EVIDENCE = Path(__file__).resolve().parent


def main():
    collected = {
        line.strip() for line in (EVIDENCE / 'final-collected-tests.txt').read_text(encoding='utf-8').splitlines()
        if line.startswith('backend/tests/') and '::' in line
    }
    modules = {path.stem: str(path.relative_to(ROOT)).replace('\\', '/')
               for path in (ROOT / 'backend/tests').glob('test_*.py')}
    chosen = {}
    receipts = []
    unmatched = []
    for directory in (EVIDENCE, ROOT / 'docs/audit-evidence/2026-10-26-business-rules'):
        for path in sorted(directory.glob('*.xml')):
            try:
                tree = ET.parse(path)
            except ET.ParseError:
                continue
            suites = tree.findall('.//testsuite')
            receipts.append({'path': str(path.relative_to(ROOT)).replace('\\','/'),
                             **{key: sum(int(suite.get(key,0)) for suite in suites)
                                for key in ('tests','errors','failures','skipped')}})
            for suite in suites:
                started = datetime.fromisoformat(suite.get('timestamp'))
                if started.tzinfo is None:
                    started = started.replace(tzinfo=timezone.utc)
                for case in suite.findall('testcase'):
                    parts = case.get('classname','').split('.')
                    index = next((i for i,value in enumerate(parts) if value in modules),None)
                    if index is None:
                        unmatched.append({'receipt':str(path.relative_to(ROOT)),'classname':case.get('classname'),'name':case.get('name')})
                        continue
                    node = modules[parts[index]]+'::'+'::'.join(parts[index+1:]+[case.get('name')])
                    failure = case.find('failure')
                    error = case.find('error')
                    skipped = case.find('skipped')
                    status = 'failed' if failure is not None else 'error' if error is not None else 'skipped' if skipped is not None else 'passed'
                    record = {'node_id':node,'status':status,'run_started_at':started.isoformat(),
                              'receipt':str(path.relative_to(ROOT)).replace('\\','/'),
                              'message':failure.get('message') if failure is not None else error.get('message') if error is not None else skipped.get('message') if skipped is not None else None}
                    previous = chosen.get(node)
                    if previous is None or started > datetime.fromisoformat(previous['run_started_at']):
                        chosen[node] = record
    applicable = {node:chosen[node] for node in sorted(collected) if node in chosen}
    missing = sorted(collected-set(applicable))
    counts = Counter(record['status'] for record in applicable.values())
    result = {'collected_cases':len(collected),'covered_cases':len(applicable),
              'counts':dict(counts),'not_covered':missing,
              'unresolved':[record for record in applicable.values() if record['status']!='passed'],
              'superseded_or_retired_case_ids':sorted(set(chosen)-collected),
              'source_compatibility_note':'Case coverage is deduplicated by current node ID and later run start time. See the report for source revisions, interrupted runs and superseding focused validation. Raw JUnit receipts are retained.',
              'receipts':receipts,'unmatched_receipt_cases':unmatched,
              'cases':list(applicable.values())}
    output=EVIDENCE/'regression-receipt-union.json'
    output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({key:result[key] for key in ('collected_cases','covered_cases','counts','not_covered','unresolved')},indent=2))


if __name__=='__main__':
    main()
