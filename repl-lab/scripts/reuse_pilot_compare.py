"""Pilot 1 of research/UNBLOCK_ACQUISITION.md: arms S (stateless), D (seeded library, the model decides)
and P (positive control: the controller applies the library), two runs each. Endpoints and the
preregistered decision rule (section 8 of the protocol), from recorded evidence only. No model calls.

    python3 scripts/reuse_pilot_compare.py SUITE OUT.json RUN_DIR... (each RUN_DIR named reuse-<arm>-r<n>)
"""
import json
import math
from pathlib import Path
import random
import re
import statistics as st
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from benchmark.oolong import jsonl, read_suite  # noqa: E402

ARMS = ('S', 'D', 'P')


def declared(text):
    found = re.search(r'Answer:\s*\[?\s*(-?\d+)', text or '')
    return int(found.group(1)) if found else None


def rows(run, answers):
    report = json.loads((run / 'report.json').read_text())
    results = {r['task_id']: r for r in jsonl(run / 'results.jsonl')}
    out = {}
    for case in report['cases']:
        r = results[case['task_id']]
        gold = answers[case['task_id']]
        text = (run / r['answer_path']).read_text() if r.get('answer_path') else ''
        row = {'task_id': case['task_id'], 'window': f"{gold['dataset']}-{gold['context_window_id']}", 'dataset': gold['dataset'],
               'numeric': gold['answer_type'] == 'ANSWER_TYPE.NUMERIC', 'status': r['status'], 'score': case['score'],
               'cost': case['usage']['model_cost_usd'], 'calls': case['usage']['calls'], 'wall_s': r['wall_time_ms'] / 1000}
        if row['numeric']:
            value, truth = declared(text), declared('Answer: ' + re.sub(r'[\[\]]', '', gold['answer']))
            row['log_error'] = None if value is None else abs(math.log((max(value, 0) + 1) / (truth + 1)))
        events = jsonl(run / Path(r['trace_path']).parts[0] / 'agent/events.jsonl') if r.get('trace_path') else []
        of = lambda kind: [e['payload'] for e in events if e['type'] == kind]
        reuse = next(iter(of('artifact-reuse-summary')), {})
        row.update(activation=reuse.get('classification'),
                   refused=any(p.get('decision') == 'refuse' for p in of('artifact-applicability')),
                   preloaded=any(p.get('decision') == 'preload' for p in of('artifact-applicability')),
                   supplied=next(iter(of('artifact-supplied')), None))
        out[case['task_id']] = row
    return out


def mean(xs):
    xs = [x for x in xs if x is not None]
    return st.mean(xs) if xs else None


def per_task(runs, key):
    """Each task's value averaged over the arm's runs (a missing numeric parse counts as the worst error seen)."""
    tasks = set().union(*(r.keys() for r in runs))
    worst = max((x[key] for r in runs for x in r.values() if x.get(key) is not None), default=None)
    return {t: mean([(r[t].get(key) if r[t].get(key) is not None else worst) for r in runs if t in r]) for t in tasks}


def bootstrap(diffs, windows, n=10000, seed=0):
    """95% interval of the mean paired difference, resampling windows (clusters)."""
    by = {}
    for t, d in diffs.items():
        if d is not None:
            by.setdefault(windows[t], []).append(d)
    keys = sorted(by)
    rng, stats = random.Random(seed), []
    for _ in range(n):
        sample = [d for k in (rng.choice(keys) for _ in keys) for d in by[k]]
        stats.append(st.mean(sample))
    stats.sort()
    return [round(stats[int(0.025 * n)], 4), round(stats[int(0.975 * n)], 4)]


def main(suite, out, *run_dirs):
    manifest, _, answers = read_suite(suite)
    runs = {arm: [] for arm in ARMS}
    for d in map(Path, run_dirs):
        arm = re.match(r'reuse-([SDP])-r\d+$', d.name).group(1)
        runs[arm].append(rows(d, answers))
    families = manifest['selection']['families']
    f1, f2 = set(families['F1']), set(families['F2'])
    windows = {t: r['window'] for arm in runs.values() for run in arm for t, r in run.items()}
    result = {'model_calls': 0, 'runs': {a: len(v) for a, v in runs.items()}, 'arms': {}}
    for arm, rs in runs.items():
        cases = [x for r in rs for x in r.values()]
        on = lambda fam: [x for x in cases if x['task_id'] in fam]
        result['arms'][arm] = {
            'f1_mean_score': mean(x['score'] for x in on(f1)), 'f2_mean_score': mean(x['score'] for x in on(f2)),
            'f1_numeric_log_error': mean(x.get('log_error') for x in on(f1) if x['numeric']),
            'f1_cost_per_run': sum(x['cost'] for x in on(f1)) / max(1, len(rs)),
            'cost_per_run': sum(x['cost'] for x in cases) / max(1, len(rs)), 'calls': sum(x['calls'] for x in cases),
            'p50_s': st.median(x['wall_s'] for x in cases) if cases else None,
            'p95_s': sorted(x['wall_s'] for x in cases)[int(0.95 * (len(cases) - 1))] if cases else None,
            'not_completed': sum(x['status'] != 'completed' for x in cases),
            'f1_activation': {k: sum(x['activation'] == k for x in on(f1)) for k in
                              ('eligible-reuse', 'invoked-not-in-answer', 'available-not-invoked', 'direct-answer',
                               'no-applicable-artifact', 'no-answer')},
            'f1_preloaded': sum(x['preloaded'] for x in on(f1)), 'f2_refused': sum(x['refused'] for x in on(f2)),
            'f2_preloaded': sum(x['preloaded'] for x in on(f2)),
            'f1_undecided_records': [x['supplied']['records'] - x['supplied']['decided'] for x in on(f1) if x['supplied']]}
    s, d, p = (result['arms'][a] for a in ARMS)
    paired = {}
    for arm in ('D', 'P'):
        score = {t: v for t, v in per_task(runs[arm], 'score').items() if t in f1}
        base = per_task(runs['S'], 'score')
        err, base_err = per_task(runs[arm], 'log_error'), per_task(runs['S'], 'log_error')
        score_diff = {t: score[t] - base[t] for t in score}
        err_diff = {t: err[t] - base_err[t] for t in err if t in f1 and err[t] is not None and base_err.get(t) is not None}
        paired[arm] = {'f1_score_diff': round(mean(score_diff.values()), 4), 'f1_score_diff_ci': bootstrap(score_diff, windows),
                       'f1_log_error_diff': round(mean(err_diff.values()), 4) if err_diff else None,
                       'f1_log_error_diff_ci': bootstrap(err_diff, windows) if err_diff else None}
    result['paired_vs_S'] = paired
    if all(runs[a] for a in ARMS):
        useful = {
            'a_score_plus_0.05_at_cost_le_1.2x': p['f1_mean_score'] >= s['f1_mean_score'] + 0.05 and p['f1_cost_per_run'] <= 1.2 * s['f1_cost_per_run'],
            'b_log_error_minus_25pct_at_score_ge_minus_0.03': (p['f1_numeric_log_error'] is not None and s['f1_numeric_log_error']
                                                              and p['f1_numeric_log_error'] <= 0.75 * s['f1_numeric_log_error']
                                                              and p['f1_mean_score'] >= s['f1_mean_score'] - 0.03),
            'c_cost_le_0.8x_at_score_ge_minus_0.03': p['f1_cost_per_run'] <= 0.8 * s['f1_cost_per_run'] and p['f1_mean_score'] >= s['f1_mean_score'] - 0.03}
        n_f1 = len(f1) * len(runs['D'])
        result['decision'] = {
            'library_useful_when_supplied': any(useful.values()), 'criteria': useful,
            'no_negative_transfer': all(x['f2_preloaded'] == 0 for x in (d, p)) and
                                    all(x['f2_mean_score'] >= s['f2_mean_score'] - 0.05 for x in (d, p)),
            'd_activation_share': round(d['f1_activation']['eligible-reuse'] / n_f1, 4) if n_f1 else None,
            'd_used_reliably': n_f1 > 0 and d['f1_activation']['eligible-reuse'] * 2 >= n_f1 and
                               (p['f1_mean_score'] - s['f1_mean_score'] <= 0 or
                                d['f1_mean_score'] - s['f1_mean_score'] >= 0.5 * (p['f1_mean_score'] - s['f1_mean_score']))}
    Path(out).write_text(json.dumps(result, indent=1))
    print(json.dumps({k: v for k, v in result.items() if k != 'arms'}, indent=1))
    for arm, v in result['arms'].items():
        print(arm, {k: v[k] for k in ('f1_mean_score', 'f2_mean_score', 'f1_numeric_log_error', 'cost_per_run', 'not_completed', 'f2_refused')})


if __name__ == '__main__':
    main(*sys.argv[1:])
