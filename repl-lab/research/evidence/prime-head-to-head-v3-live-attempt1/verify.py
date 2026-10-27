"""Read-only V3 result audit. Does not dispatch inference or execute agent code.

Run with the frozen repl-lab directory on PYTHONPATH:
  python3 verify.py RUN_DIRECTORY SUITE_DIRECTORY > independent-audit.json
"""
import hashlib
import json
import sqlite3
import sys
from decimal import Decimal
from pathlib import Path

from benchmark.official import score_answer
from benchmark.oolong import compare, read_suite
from benchmark.vendor.oolong_pairs import _parse_pairs


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def lines(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def response_receipt(path):
    raw = path.read_text()
    if raw.lstrip().startswith('{'):
        message = json.loads(raw)
        return message['id'], message['model'], message['usage']
    events = [json.loads(line[6:]) for line in raw.splitlines()
              if line.startswith('data: ') and line[6:] != '[DONE]']
    message = next(e['message'] for e in events if e['type'] == 'message_start')
    usage = dict(message['usage'])
    terminal = False
    for event in events:
        if event['type'] == 'message_delta':
            terminal = True
            assert type(event['usage']['output_tokens']) is int
            usage.update(event['usage'])  # Cumulative counters; never sum deltas.
    assert terminal and events[-1]['type'] == 'message_stop'
    return message['id'], message['model'], usage


run, suite = map(Path, sys.argv[1:])
before = {str(p.relative_to(run)): sha(p) for p in run.rglob('*') if p.is_file()}
report = json.loads((run / 'report.json').read_text())
rescored = json.loads(json.dumps(compare(suite, run / 'results.jsonl')))
for key in rescored:
    assert rescored[key] == report[key], key
manifest, tasks, answers = read_suite(suite)
results = lines(run / 'results.jsonl')
audit = {'evidence': 'LIVE MODEL RUN', 'new_model_calls_during_audit': 0,
         'plan_sha256': json.loads((run / 'plan.json').read_text())['plan_sha256'],
         'official_report_reproduced': True, 'arms': {}, 'sqlite_integrity': {}}
seen_ids = set()
total_cost = Decimal(0)
for index, result in enumerate(results):
    harness = result['harness']
    arm = run / f'{index:02}-{harness}'
    trace = json.loads((arm / 'trace.json').read_text())
    for file, expected in trace['artifacts'].items():
        assert sha(arm / file) == expected, file
    receipts = lines(arm / 'gateway/usage.jsonl')
    raw_receipts = {}
    for path in (arm / 'gateway/transport-bodies').glob('*.body'):
        identity, model, usage = response_receipt(path)
        assert identity not in seen_ids and model == 'claude-sonnet-5-5'
        seen_ids.add(identity)
        raw_receipts[identity] = usage
    assert len(raw_receipts) == len(receipts)
    totals = dict.fromkeys(('input_tokens', 'output_tokens', 'cache_read_input_tokens',
                           'cache_creation_input_tokens'), 0)
    cost = Decimal(0)
    for receipt in receipts:
        assert receipt['status'] == 'complete'
        usage = raw_receipts[receipt['provider_request_id']]
        for key in totals:
            assert receipt[key] == usage[key]
            totals[key] += usage[key]
        cache = usage['cache_creation']
        assert cache == receipt['cache_creation']
        assert sum(cache.values()) == usage['cache_creation_input_tokens']
        charge = (Decimal(2) * usage['input_tokens'] + Decimal(10) * usage['output_tokens']
                  + Decimal('0.1') * usage['cache_read_input_tokens']
                  + Decimal('2.5') * cache['ephemeral_5m_input_tokens']
                  + Decimal(4) * cache['ephemeral_1h_input_tokens']) / 1000000
        assert abs(charge - Decimal(str(receipt['estimated_usd']))) < Decimal('1e-15')
        cost += charge
    total_cost += cost
    gateway = json.loads((arm / 'gateway/report.json').read_text())
    assert gateway['uncertain_requests'] == 0
    assert all(value == 0 for value in gateway['reserved'].values())
    assert gateway['spent']['tokens'] == sum(totals.values())
    assert Decimal(str(gateway['spent']['usd'])) == cost <= Decimal(12)
    assert json.loads((arm / 'gateway/cleanup.json').read_text())['ok']
    gateway_events = lines(arm / 'gateway/events.jsonl')
    requests = [e['payload'] for e in gateway_events if e['type'] == 'gateway-request-intent']
    assert len(requests) == len(receipts)
    for request in requests:
        body = request['input']
        assert body['model'] == 'claude-sonnet-5-5' and body['max_tokens'] == 32768
        assert body['thinking'] == {'type': 'adaptive', 'display': 'summarized'}
        assert body['output_config'] == {'effort': 'medium'}
    transport = lines(arm / 'gateway/transport.jsonl')
    completed = [e for e in transport if e['event'] == 'response']
    assert len(completed) == len(receipts)
    assert all(e['http_status'] == 200 and e['task_elapsed_ms'] < 120000 for e in completed)
    arm_audit = {'status': result['status'], 'calls': len(receipts), 'tokens': totals,
                 'total_input_including_cache': totals['input_tokens'] + totals['cache_read_input_tokens'] + totals['cache_creation_input_tokens'],
                 'known_equivalent_usd': str(cost), 'unknown_reserved_usd': '0',
                 'wall_time_ms': result['wall_time_ms'],
                 'provider_transport_ms': sum(e['elapsed_ms'] for e in completed),
                 'request_transport_ms': [e['elapsed_ms'] for e in completed],
                 'request_contracts_verified': len(requests),
                 'artifact_hashes_verified': len(trace['artifacts']),
                 'gateway_cleanup_ok': True}
    if result['status'] == 'completed':
        answer = (run / result['answer_path']).read_text()
        scored = score_answer(manifest['suite'], answers[result['task_id']], answer)
        predicted = _parse_pairs(answer)
        gold = _parse_pairs(answers[result['task_id']]['answer'])
        arm_audit['official_score'] = {k: v for k, v in scored.items() if k != 'attempted_parse'}
        arm_audit['pairs'] = {'gold': len(gold), 'predicted': len(predicted),
                              'correct': len(gold & predicted), 'false_positive': len(predicted - gold),
                              'false_negative': len(gold - predicted)}
        native = lines(arm / 'native/native.jsonl')
        tools = [e for e in native if e['type'] == 'tool_execution_end']
        arm_audit['native_tools'] = [{'id': e['toolCallId'], 'tool': e['toolName'],
                                      'status': e['result']['details']['status'],
                                      'duration_ms': e['result']['details']['durationMs']} for e in tools]
        timing = lines(arm / 'event-timing.jsonl')
        starts = {e['toolCallId']: e['elapsed_ms'] for e in timing if e.get('native_type') == 'tool_execution_start'}
        arm_audit['host_observed_tool_ms'] = sum(e['elapsed_ms'] - starts[e['toolCallId']]
                                               for e in timing if e.get('native_type') == 'tool_execution_end')
    else:
        arm_audit['official_score'] = None
        arm_audit['denominator_failure_score'] = 0
        arm_audit['terminal_result'] = json.loads((arm / 'agent/result.json').read_text())
        events = lines(arm / 'agent/events.jsonl')
        arm_audit['tools'] = [e for e in events if e['type'] in ('tool-call', 'tool-result')]
        arm_audit['tool_elapsed_ms'] = sum(e['payload']['elapsed-ms'] for e in events if e['type'] == 'tool-result')
        arm_audit['worker_started'] = (arm / 'worker-audit').exists()
    audit['arms'][harness] = arm_audit
for path in run.rglob('*.sqlite'):
    with sqlite3.connect(path.resolve().as_uri() + '?mode=ro&immutable=1', uri=True) as db:
        check = db.execute('PRAGMA integrity_check').fetchone()[0]
        assert check == 'ok'
        audit['sqlite_integrity'][str(path.relative_to(run))] = check
assert before == {str(p.relative_to(run)): sha(p) for p in run.rglob('*') if p.is_file()}
assert total_cost <= Decimal(24)
audit.update(known_equivalent_usd=str(total_cost), unknown_reserved_usd='0',
             unique_provider_receipts=len(seen_ids), originals_unchanged=True)
print(json.dumps(audit, indent=2, sort_keys=True))
