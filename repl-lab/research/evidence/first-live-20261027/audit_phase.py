"""Read recorded evidence only. No provider or worker execution."""
import collections
import hashlib
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
out = pathlib.Path(sys.argv[2])
d = json.loads((root / 'report.json').read_text())
events = [json.loads(x) for x in (root / 'events.jsonl').read_text().splitlines()]
requests = {x['payload']['request-id']: x for x in events if x['type'] == 'provider-input'}
results = {x['payload']['request-id']: x for x in events if x['type'] == 'provider-result'}
usage = collections.defaultdict(collections.Counter)
receipts = []
for request_id, event in requests.items():
    p = event['payload']
    trace = pathlib.Path(p['trace-path']) / 'stdout.jsonl'
    if not trace.exists():
        receipts.append({'request_id': request_id, 'receipt': None, 'state': 'no transport receipt'})
        continue
    terminal = [json.loads(x) for x in trace.read_text().splitlines() if x and json.loads(x).get('type') == 'result']
    assert len(terminal) == 1, (trace, len(terminal))
    r = terminal[0]
    u = r['usage']
    assert u.get('cache_creation_input_tokens', 0) == u.get('cache_read_input_tokens', 0) == 0
    assert r['num_turns'] == 1 and not r['is_error']
    assert set(r['modelUsage']) == {'claude-sonnet-5-5'}
    assert r['subagent_stats']['spawned'] == 0
    measured = {'calls': 1, 'input_tokens': u['input_tokens'], 'output_tokens': u['output_tokens']}
    measured['tokens'] = measured['input_tokens'] + measured['output_tokens']
    measured['equivalent_usd'] = (measured['input_tokens'] * 2 + measured['output_tokens'] * 10) / 1000000
    ledger = results[request_id]['payload']
    assert measured['tokens'] == ledger['tokens']
    assert abs(measured['equivalent_usd'] - ledger['usd']) < 1e-10
    arm = event.get('arm', event.get('task', 'unknown').split('-')[0])
    role = 'root' if p['session'] == 'root' else 'child'
    for key in ['total', arm, arm + '/' + role]:
        usage[key].update(measured)
    receipts.append({'request_id': request_id, 'task': event.get('task'), 'arm': arm,
                     'role': role, 'cli_session_id': r['session_id'], **measured,
                     'raw_trace': str(trace), 'sha256': hashlib.sha256(trace.read_bytes()).hexdigest()})
source = d.get('manifest', d.get('acquisition-manifest', {}))
source_mismatches = [p for p, sha in source.get('source-files', {}).items()
                     if hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest() != sha]
assert not source_mismatches, source_mismatches
compact = {
    'evidence_category': 'HELD-OUT EXPERIMENT' if 'evaluation-' in root.name else 'LIVE MODEL RUN',
    'run_id': root.name, 'raw_report': str(root / 'report.json'),
    'raw_report_sha256': hashlib.sha256((root / 'report.json').read_bytes()).hexdigest(),
    'source_commit': source.get('source-commit'), 'source_hash': source.get('source-hash'),
    'source_files_verified': len(source.get('source-files', {})),
    'conditions': d['conditions'], 'costs': d.get('costs'), 'ablation': d.get('ablation'),
    'artifact_remap': d.get('artifact-remap'),
    'raw_usage_reconciled_to_ledger': dict(usage), 'receipts': receipts,
    'cases': [{k: x.get(k) for k in ['arm', 'case', 'artifact', 'workflow', 'metrics', 'wall-ms', 'error', 'usage']}
              for x in d.get('raw-cases', [])],
    'session_outcomes': [{'task': x.get('task'), 'arm': x.get('arm'),
                          'id': x['payload']['id'], 'status': x['payload']['status'],
                          'error': x['payload'].get('summary', {}).get('error')}
                         for x in events if x['type'] == 'session-finished'],
    'workflow_invocations': [{'task': x.get('task'), 'arm': x.get('arm'),
                              'artifact': x['payload']['artifact'], 'policy': x['payload']['policy'],
                              'selected_count': len(x['payload']['selected']),
                              'selected_fields': sorted(set().union(*(set(v) for v in x['payload']['selected']))),
                              'delegated': x['payload'].get('child-result') is not None}
                             for x in events if x['type'] == 'workflow-invoked'],
    'tools_by_arm': {arm: dict(collections.Counter(x['payload']['command']['op'] for x in events
                       if x.get('arm') == arm and x['type'] == 'tool-call')) for arm in ['frozen', 'evolving']},
    'tool_errors': [{'task': x.get('task'), **x['payload']} for x in events
                   if x['type'] == 'tool-result' and x['payload'].get('status') == 'error'],
    'temporary_policy_selections': [{'task': x.get('task'), 'arm': x.get('arm'),
                                     'hash': x['payload']['result']['hash'],
                                     'trace_sequence': x['sequence']}
                                    for x in events if x['type'] == 'tool-result'
                                    and x['payload'].get('op') == 'policy/use'
                                    and x['payload'].get('status') == 'ok'],
    'context_query_handles': {arm: dict(collections.Counter(x['payload']['command'].get('handle')
                             for x in events if x.get('arm') == arm and x['type'] == 'tool-call'
                             and x['payload']['command']['op'] == 'context/query'))
                             for arm in ['frozen', 'evolving']},
}
out.write_text(json.dumps(compact, indent=2) + '\n')
print(json.dumps({k: compact[k] for k in ['run_id', 'source_files_verified', 'raw_usage_reconciled_to_ledger', 'conditions', 'ablation']}))
