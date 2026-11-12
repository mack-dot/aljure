"""L0-L3 review ablation on the dev label-count suite: count accuracy, scores, cost,
latency, activation of each mechanism, and the preregistered decision rules
(research/REVIEW_ABLATION_PROTOCOL.md). Read-only over the recorded runs; no model calls.

    python3 scripts/review_levels_compare.py EXEC_REPL_LAB OUT.json
"""
import json
from pathlib import Path
import random
import re
import statistics as st
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from contract_audit import audit_run, jsonl  # noqa: E402

LEVELS = {'L0': 'l0-baseline', 'L1': 'l1-labels', 'L2': 'l2-audit', 'L3': 'l3-review'}
SUITE = 'var/official/synth32-dev-label-counts'
# Activation heuristics, reported with the results so a reader can audit them.
RULES = {
    'count': 'declared count: the integer right after "Answer:" in the delivered answer; official scores unchanged',
    'label_map': 'per-item state: an executed repl_eval source that binds or updates (def / atom / swap! / reset! / into / conj) '
                 'a map, set or vector literal holding >= 10 integer item ids, or builds a def with zipmap / into {} / assoc / '
                 'merge / reduce-kv',
    'computed_answer': 'the submitted number appears as a value in a tool result before done',
    'audit': 'an executed source that calls audit-labels; its returned map, when shown, gives open/unknown/conflict counts',
}
MAP_LITERAL = re.compile(r'\(def\s+[\w\-?!*]+\s+\{((?:[^{}]|\{[^{}]*\})*)\}', re.S)
MAP_BUILD = re.compile(r'\(def\s+[\w\-?!*]+\s+\((zipmap|into \{\}|assoc|merge|reduce-kv|reduce|into \(sorted-map\))')
STATE_UPDATE = re.compile(r'\((def|atom|swap!|reset!|into|conj)\b')
ID_COLLECTION = re.compile(r'(?:#\{|\{|\[)([^\[\]{}]*)[\]}]')


def number(text):
    found = re.findall(r'-?\d+', text or '')
    return int(found[-1]) if found else None


def activation(arm):
    events = jsonl(arm + '/agent/events.jsonl')
    sources = [e['payload']['command'].get('source', '') for e in events
               if e['type'] == 'tool-call' and e['payload']['command'].get('op') == 'repl/eval']
    results = [e['payload'].get('result', {}).get('value') for e in events
               if e['type'] == 'tool-result' and e['payload'].get('op') == 'repl/eval' and e['payload'].get('status') == 'ok']
    audits = [v for v in results if isinstance(v, dict) and ({'open', 'counts', 'unresolved-count', 'count-range'} & set(v))]
    label_map = any((m and m.group(1).count(':') >= 10) for s in sources for m in MAP_LITERAL.finditer(s)) or \
        any(MAP_BUILD.search(s) for s in sources) or \
        any(STATE_UPDATE.search(s) and any(len(re.findall(r'\b\d+\b', c)) >= 10 for c in ID_COLLECTION.findall(s))
            for s in sources)
    answer = next((e['payload'].get('result', {}).get('summary') for e in reversed(events)
                   if e['type'] == 'tool-result' and e['payload'].get('op') in ('done', 'done/eval')), None)
    claimed = number(answer)
    shown = json.dumps(results)
    first, last = (audits[0], audits[-1]) if audits else (None, None)
    pick = lambda a, k: a.get(k) if a else None
    return {'label_map': label_map, 'show_items_calls': sum('show-items' in s for s in sources),
            'audit_calls': sum('audit-labels' in s for s in sources), 'audits_shown': len(audits),
            'first_audit': {k: pick(first, k) for k in ('open', 'unresolved-count', 'conflict-count', 'missing-count', 'counts', 'count-range')},
            'last_audit': {k: pick(last, k) for k in ('open', 'unresolved-count', 'conflict-count', 'missing-count', 'counts', 'count-range')},
            'open_reduced': bool(first and last and isinstance(pick(first, 'open'), int) and isinstance(pick(last, 'open'), int)
                                 and pick(last, 'open') < pick(first, 'open')),
            'gate_fired': sum(e['type'] == 'evidence-gate' for e in events),
            'computed_answer': claimed is not None and re.search(rf'(?<![\d-]){claimed}(?!\d)', shown) is not None,
            'repl_calls': len(sources)}


def plan_rows(root, name, gold):
    run = Path(root) / f'var/benchmarks/review-levels-opus-{name}'
    report = json.loads((run / 'report.json').read_text())
    results = {(r['task_id'], r['harness']): r for r in map(json.loads, (run / 'results.jsonl').read_text().splitlines())}
    rows = []
    for case in report['cases']:
        r = results[(case['task_id'], case['harness'])]
        # Count accuracy uses the declared count: the integer right after "Answer:", the task's requested
        # form. The official score is kept as scored; a low-confidence official parse is reported separately.
        text = (run / r['answer_path']).read_text() if r.get('answer_path') else ''
        declared = re.search(r'Answer:\s*\[?\s*(-?\d+)', text)
        value = int(declared.group(1)) if declared else (number(case.get('attempted_parse')) if r['status'] == 'completed' else None)
        truth = gold[case['task_id']]['value']
        u = case['usage']
        row = {'task_id': case['task_id'], 'window': gold[case['task_id']]['dataset'], 'harness': case['harness'],
               'status': r['status'], 'failure': r.get('failure'), 'answer': value, 'gold': truth,
               'signed_error': None if value is None else value - truth,
               'abs_error': None if value is None else abs(value - truth),
               'rel_error': None if value is None else round(abs(value - truth) / truth, 4),
               'score': round(case['score'], 4), 'official_parse_confidence': case.get('parse_confidence'),
               'answer_chars': len(text), 'calls': u['calls'], 'cost': round(u['model_cost_usd'], 5),
               'tokens': u.get('known_tokens'), 'wall_s': round(r['wall_time_ms'] / 1000, 1)}
        if case['harness'] == 'aljure':
            arm = str(run / Path(r['trace_path']).parts[0])
            row['activation'] = activation(arm) if (Path(arm) / 'agent/events.jsonl').exists() else None
        rows.append(row)
    return run, rows


def summary(rows):
    done = [r for r in rows if r['abs_error'] is not None]
    walls = sorted(r['wall_s'] for r in rows)
    pct = lambda p: walls[min(len(walls) - 1, round(p * (len(walls) - 1)))]
    tokens = {}
    for r in rows:
        for k, v in (r['tokens'] or {}).items():
            tokens[k] = tokens.get(k, 0) + v
    return {'answered': len(done), 'tasks': len(rows),
            'mae': round(st.mean(r['abs_error'] for r in done), 3) if done else None,
            'mean_signed_error': round(st.mean(r['signed_error'] for r in done), 3) if done else None,
            'mean_rel_error': round(st.mean(r['rel_error'] for r in done), 4) if done else None,
            'mean_score': round(sum(r['score'] for r in rows) / len(rows), 4),
            'calls': sum(r['calls'] for r in rows), 'cost': round(sum(r['cost'] for r in rows), 4), 'tokens': tokens,
            'wall_s': round(sum(r['wall_s'] for r in rows), 1), 'p50_s': pct(.5), 'p95_s': pct(.95),
            'failures': [(r['task_id'][-9:], r['failure']) for r in rows if r['status'] != 'completed'],
            'official_parse_low_confidence': [r['task_id'][-9:] for r in rows if r['status'] == 'completed'
                                              and r.get('official_parse_confidence') not in ('vhigh', 'high')]}


def paired(a_rows, b_rows, *, resamples=10000, seed=0):
    """b minus a in absolute error, by task; bootstrap over window clusters (5 contexts)."""
    a = {r['task_id']: r for r in a_rows}
    pairs = [(t, b['abs_error'] - a[t]['abs_error'], b['window']) for t, b in ((r['task_id'], r) for r in b_rows)
             if b['abs_error'] is not None and a[t]['abs_error'] is not None]
    if not pairs:
        return None
    windows = sorted({w for _, _, w in pairs})
    by_window = {w: [d for _, d, x in pairs if x == w] for w in windows}
    rng, means = random.Random(seed), []
    for _ in range(resamples):
        sample = [d for w in (rng.choice(windows) for _ in windows) for d in by_window[w]]
        means.append(st.mean(sample))
    means.sort()
    return {'tasks_compared': len(pairs), 'mean_abs_error_change': round(st.mean(d for _, d, _ in pairs), 3),
            'better': sum(d < 0 for _, d, _ in pairs), 'ties': sum(d == 0 for _, d, _ in pairs), 'worse': sum(d > 0 for _, d, _ in pairs),
            'window_bootstrap_95': [round(means[int(.025 * resamples)], 3), round(means[int(.975 * resamples)], 3)],
            'by_window': {w: round(st.mean(v), 3) for w, v in by_window.items()}}


def main(root, out):
    gold = {}
    for line in (Path(root) / SUITE / 'controller/answers.jsonl').read_text().splitlines():
        g = json.loads(line)
        gold[g['task_id']] = {'value': number(g['answer']), 'dataset': g['dataset']}
    plans, aljure, prime = {}, {}, {}
    for level, name in LEVELS.items():
        if not (Path(root) / f'var/benchmarks/review-levels-opus-{name}/report.json').exists():
            continue
        run, rows = plan_rows(root, name, gold)
        plan = json.loads((run / 'plan.json').read_text())
        attempted = [r for r in rows if r['failure'] != 'ValueError']
        if len(attempted) < len(rows):
            # A plan the runner stopped (gate failure) is reported, never analysed as a configuration.
            plans[level] = {'plan_sha256': plan['plan_sha256'], 'stopped': True, 'arms_attempted': len(attempted),
                            'failures': sorted({(r['task_id'][-9:], r['harness'], r['failure']) for r in attempted if r['failure']}),
                            'cost_spent': round(sum(r['cost'] for r in attempted), 4)}
            continue
        audit = audit_run(str(run))
        aljure[level] = [r for r in rows if r['harness'] == 'aljure']
        prime[level] = [r for r in rows if r['harness'] == 'prime']
        sa, sp = summary(aljure[level]), summary(prime[level])
        acts = [r['activation'] for r in aljure[level] if r['activation']]
        plans[level] = {'plan_sha256': plan['plan_sha256'], 'aljure_contract': plan['config']['aljure_contract'],
                        'aljure': sa, 'prime': sp, 'cost_ratio': round(sa['cost'] / sp['cost'], 3) if sp['cost'] else None,
                        'contract_audit': {'conformant': sum(a['status'] == 'conformant' for a in audit['arms']),
                                           'arms': len(audit['arms']),
                                           'violations': [v for a in audit['arms'] for v in a.get('violations', [])],
                                           'retries': sum(a.get('retries', 0) for a in audit['arms']),
                                           'corrections': sum(a.get('corrections', 0) for a in audit['arms']),
                                           'gates': sum(a.get('evidence_gates', 0) for a in audit['arms'])},
                        'activation': {'label_map': sum(a['label_map'] for a in acts),
                                       'audit_used': sum(a['audit_calls'] > 0 for a in acts),
                                       'open_reduced': sum(a['open_reduced'] for a in acts),
                                       'gate_fired': sum(a['gate_fired'] > 0 for a in acts),
                                       'computed_answer': sum(a['computed_answer'] for a in acts), 'arms': len(acts)},
                        'tasks': rows}
    comparisons = {}
    for a, b in (('L0', 'L1'), ('L1', 'L2'), ('L2', 'L3'), ('L0', 'L3')):
        if a in aljure and b in aljure:
            comparisons[f'{b}-{a}'] = paired(aljure[a], aljure[b])
    prime_all = [r for rows in prime.values() for r in rows if r['abs_error'] is not None]
    prime_ref = {'mae_over_runs': round(st.mean(r['abs_error'] for r in prime_all), 3) if prime_all else None,
                 'runs': len(prime), 'mae_by_run': {k: summary(v)['mae'] for k, v in prime.items()}}
    decision = None
    if 'L2' in plans and 'L3' in plans and not plans['L3'].get('stopped'):
        c = comparisons['L3-L2']
        decision = {'L3_beats_L2_on_at_least_7_of_11': c['better'] >= 7,
                    'L3_mae_below_L2': plans['L3']['aljure']['mae'] < plans['L2']['aljure']['mae'],
                    'L3_cost_ratio_at_most_0.6': plans['L3']['cost_ratio'] <= 0.6,
                    'invocation': {lvl: plans[lvl]['activation'] for lvl in plans}}
        decision['targeted_review_earns_its_place'] = all(v for k, v in decision.items() if k.startswith('L3_'))
        decision['impressive'] = (plans['L3']['aljure']['mae'] < prime_ref['mae_over_runs'] and plans['L3']['cost_ratio'] <= 0.6)
    result = {'model_calls': 0, 'rules': RULES, 'plans': plans, 'comparisons': comparisons, 'prime_reference': prime_ref,
              'decision': decision}
    Path(out).write_text(json.dumps(result, indent=1))
    for level, p in plans.items():
        if p.get('stopped'):
            print(level, 'STOPPED', p)
            continue
        print(level, {k: p['aljure'][k] for k in ('answered', 'mae', 'mean_signed_error', 'mean_score', 'calls', 'cost', 'p50_s', 'p95_s')},
              'prime', {k: p['prime'][k] for k in ('mae', 'mean_signed_error', 'cost')}, 'ratio', p['cost_ratio'],
              'activation', p['activation'], 'audit', {k: v for k, v in p['contract_audit'].items() if k != 'violations'},
              'violations', len(p['contract_audit']['violations']))
    print(json.dumps(comparisons, indent=1))
    print('prime reference', prime_ref)
    print('decision', json.dumps(decision, indent=1))


if __name__ == '__main__':
    main(*sys.argv[1:3])
