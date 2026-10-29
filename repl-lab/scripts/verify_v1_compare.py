"""Answer-format verification A/B (research/ANSWER_FORMAT_VERIFICATION_PROTOCOL.md): parse
failures, notice activation, count accuracy, scores, cost and latency, against the cited
Prime reference, and the preregistered decision rule. Read-only; no model calls.

    python3 scripts/verify_v1_compare.py EXEC_REPL_LAB OUT.json
"""
import json
from pathlib import Path
import re
import statistics as st
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from contract_audit import audit_run, jsonl  # noqa: E402

SUITES = {'counts': 'var/official/synth32-dev-label-counts', 'synth21': 'var/official/synth32-indep-dev'}


def number(text):
    found = re.search(r'Answer:\s*\[?\s*(-?\d+)', text or '')
    return int(found.group(1)) if found else None


def gold_of(root, suite):
    rows = [json.loads(line) for line in (Path(root) / SUITES[suite] / 'controller/answers.jsonl').read_text().splitlines()]
    return {r['task_id']: r for r in rows}


def arm_rows(run, harness, gold, counts):
    report = json.loads((run / 'report.json').read_text())
    results = {(r['task_id'], r['harness']): r for r in map(json.loads, (run / 'results.jsonl').read_text().splitlines())}
    out = []
    for case in report['cases']:
        if case['harness'] != harness:
            continue
        r = results[(case['task_id'], harness)]
        text = (run / r['answer_path']).read_text() if r.get('answer_path') else ''
        truth = number('Answer: ' + re.sub(r'[\[\]]', '', gold[case['task_id']]['answer'])) if counts else None
        value = number(text) if counts else None
        row = {'task_id': case['task_id'], 'status': r['status'], 'failure': r.get('failure'), 'score': case['score'],
               'parse_low': r['status'] == 'completed' and case.get('parse_confidence') not in ('vhigh', 'high'),
               'error': None if value is None or truth is None else value - truth,
               'cost': case['usage']['model_cost_usd'], 'calls': case['usage']['calls'], 'wall_s': r['wall_time_ms'] / 1000}
        if harness == 'aljure' and r.get('trace_path'):
            events = jsonl(str(run / Path(r['trace_path']).parts[0]) + '/agent/events.jsonl')
            notices = [e for e in events if e['type'] == 'answer-format-notice']
            dones = [e['payload']['command'].get('summary', '') for e in events
                     if e['type'] == 'tool-call' and e['payload']['command'].get('op') == 'done']
            row.update(notices=len(notices), accepted_nonconforming=sum(e['type'] == 'answer-format-accepted-nonconforming' for e in events),
                       final_conforms=bool(dones) and len(dones[-1].strip().splitlines()) <= 1 and len(dones[-1]) <= 256)
        out.append(row)
    return out


def summarize(rows):
    errs = [r['error'] for r in rows if r['error'] is not None]
    walls = sorted(r['wall_s'] for r in rows)
    pct = lambda p: walls[min(len(walls) - 1, round(p * (len(walls) - 1)))] if walls else None
    return {'arms': len(rows), 'completed': sum(r['status'] == 'completed' for r in rows),
            'parse_failures': sum(r['parse_low'] for r in rows),
            'notices': sum(r.get('notices', 0) for r in rows),
            'notices_followed_by_conforming': sum(1 for r in rows if r.get('notices') and r.get('final_conforms')),
            'accepted_nonconforming': sum(r.get('accepted_nonconforming', 0) for r in rows),
            'mae': round(st.mean(abs(e) for e in errs), 3) if errs else None,
            'mean_signed_error': round(st.mean(errs), 3) if errs else None,
            'mean_score': round(st.mean(r['score'] for r in rows), 4) if rows else None,
            'cost': round(sum(r['cost'] for r in rows), 4), 'calls': sum(r['calls'] for r in rows),
            'p50_s': pct(.5), 'p95_s': pct(.95)}


def main(root, out):
    root = Path(root)
    runs = sorted(root.glob('var/benchmarks/verify-v1-*'))
    result = {'model_calls': 0, 'runs': {}, 'pooled': {}, 'prime_reference': {}}
    pooled = {}
    for run in runs:
        name = run.name.replace('verify-v1-', '')
        suite, arm, tag = name.split('-')
        if not (run / 'report.json').exists():
            result['runs'][name] = {'status': 'incomplete'}
            continue
        gold = gold_of(root, suite)
        rows = arm_rows(run, 'aljure', gold, suite == 'counts')
        audit = audit_run(str(run))
        result['runs'][name] = {**summarize(rows), 'auditor_violations': [v for a in audit['arms'] for v in a.get('violations', [])],
                                'tasks': rows}
        pooled.setdefault(f'{suite}-{arm}', []).extend(rows)
    for key, rows in pooled.items():
        result['pooled'][key] = summarize(rows)
    # The cited, non-contemporaneous Prime reference, read from the recorded runs the plans name.
    for suite in ('counts', 'synth21'):
        plan_file = root / f'var/verify-v1/{suite}-v1-plan.json'
        if not plan_file.exists():
            continue
        plan = json.loads(plan_file.read_text())
        gold = gold_of(root, suite)
        prime = [r for cited in plan['prime_reference']['runs'] for r in arm_rows(Path(cited['run_dir']), 'prime', gold, suite == 'counts')]
        runs_cited = len(plan['prime_reference']['runs'])
        result['prime_reference'][suite] = {**summarize(prime), 'runs_cited': runs_cited,
                                            'mean_cost_per_run': round(sum(r['cost'] for r in prime) / runs_cited, 4)}
    p, ref = result['pooled'], result['prime_reference']
    if all(k in p for k in ('counts-v0', 'counts-v1', 'synth21-v0', 'synth21-v1')):
        v1_runs = [r for k, r in result['runs'].items() if '-v1-' in f'-{k}-' and 'auditor_violations' in r]
        per_run_cost = lambda key, suite: p[key]['cost'] / (3 if suite == 'counts' else 1)
        result['decision'] = {
            '1_contract_intact': all(not r['auditor_violations'] for r in result['runs'].values() if 'auditor_violations' in r),
            '2_effective_zero_v1_parse_failures': p['counts-v1']['parse_failures'] + p['synth21-v1']['parse_failures'] == 0,
            '3_activated': p['counts-v1']['notices'] + p['synth21-v1']['notices'] > 0,
            '4a_count_mae_no_worse_than_2': p['counts-v1']['mae'] - p['counts-v0']['mae'] <= 2.0,
            '4b_synth21_score_no_worse_than_0.05': p['synth21-v1']['mean_score'] >= p['synth21-v0']['mean_score'] - 0.05,
            '5a_cost_at_most_1.05x_v0': all(p[f'{s}-v1']['cost'] <= 1.05 * p[f'{s}-v0']['cost'] for s in ('counts', 'synth21')),
            '5b_cost_at_most_0.6x_prime': all(per_run_cost(f'{s}-v1', s) <= 0.6 * ref[s]['mean_cost_per_run'] for s in ('counts', 'synth21')),
            'v1_runs': len(v1_runs)}
        result['decision']['adopt'] = all(v for k, v in result['decision'].items() if k[0].isdigit())
    Path(out).write_text(json.dumps(result, indent=1))
    for name, r in result['runs'].items():
        print(name, {k: r.get(k) for k in ('arms', 'completed', 'parse_failures', 'notices', 'notices_followed_by_conforming',
                                           'accepted_nonconforming', 'mae', 'mean_score', 'cost', 'p50_s', 'p95_s')},
              'violations', len(r.get('auditor_violations', [])))
    print('pooled', json.dumps(result['pooled'], indent=1))
    print('prime reference', json.dumps({k: {x: v[x] for x in ('mae', 'mean_score', 'mean_cost_per_run', 'parse_failures')}
                                         for k, v in result['prime_reference'].items()}))
    print('decision', json.dumps(result.get('decision'), indent=1))


if __name__ == '__main__':
    main(*sys.argv[1:3])
