#!/usr/bin/env python3
"""Trace review for the reuse-economics run: one block per task with arm, kind, answer,
attribution level and flags, every tool call with its result, and executable evidence.
Read-only; writes <run>/trace-review.json and prints a text review."""
import json, sys, collections
from pathlib import Path

run = Path(sys.argv[1])
def jsonl(p):
    return [json.loads(l) for l in open(p) if l.strip()] if p.exists() else []

review = []
for d in sorted(p for p in run.iterdir() if p.is_dir()):
    rp = d / 'result.json'
    if not rp.exists():
        review.append({'task': d.name, 'status': 'missing-result'}); continue
    r = json.load(open(rp))
    ev = jsonl(d / 'agent/events.jsonl')
    a = r['attribution']
    calls, pending = [], {}
    for e in ev:
        p = e['payload']
        if e['type'] == 'tool-call':
            pending.setdefault(p.get('session'), []).append(p['command'])
        elif e['type'] == 'tool-result':
            q = pending.get(p.get('session'), [])
            cmd = q.pop(0) if q else {}
            src = cmd.get('source') or cmd.get('summary') or cmd.get('name') or json.dumps({k: v for k, v in cmd.items() if k != 'op'})[:200]
            calls.append({'op': p.get('op') or cmd.get('op'), 'status': p.get('status'),
                          'source': str(src)[:400], 'result': str((p.get('result') or {}).get('value', p.get('result')))[:160]})
    appl = [e['payload'] for e in ev if e['type'] == 'artifact-applicability']
    inv = [e['payload'] for e in ev if e['type'] == 'artifact-invocations']
    block = {'task': d.name, 'arm': r['arm'], 'kind': r['kind'], 'status': r['status'], 'correct': r['correct'],
             'answer': r['answer'], 'failure': r['failure'], 'seconds': round(r['seconds'], 1),
             'requests': r['usage']['calls'], 'cost_usd': r['usage']['known_model_cost_usd'],
             'first_request_tokens': r['prompt'].get('first_request_tokens'), 'tools': r['prompt'].get('tools'),
             'tools_bytes': r['prompt'].get('tools_bytes'),
             'level': a['level'], 'flags': a['flags'], 'inspections': a['inspections'],
             'named_evaluations': a['named_evaluations'], 'artifact_call_attempts': a['artifact_call_attempts'],
             'executions': a['executions'], 'useful_reuse': a['useful_reuse'], 'tool_reliability': a['tool_reliability'],
             'applicability': [{k: x.get(k) for k in ('decision', 'name', 'reason')} for x in appl],
             'invocation_events': inv, 'calls': calls}
    review.append(block)

json.dump(review, open(run / 'trace-review.json', 'w'), indent=1)
for b in review:
    if 'arm' not in b:
        print(b); continue
    print(f"\n=== {b['task']} arm={b['arm']} kind={b['kind']} correct={b['correct']} answer={b['answer']!r} level={b['level']} "
          f"req={b['requests']} ${b['cost_usd']:.4f} {b['seconds']}s tok1={b['first_request_tokens']} tools={b['tools']}")
    if b['applicability']: print('  applicability:', b['applicability'])
    for c in b['calls']:
        print(f"  [{c['op']} {c['status']}] {c['source'][:220].replace(chr(10),' | ')}")
        print(f"      -> {c['result'][:120].replace(chr(10),' | ')}")
    if b['executions']: print('  executions:', json.dumps(b['executions'])[:600])
