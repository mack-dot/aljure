#!/usr/bin/env python3
"""Phase 4 paired analysis of one Experiment A run. Read-only over the run directory, the host-policy
records and worker audits. Writes <run>/analysis.json and prints Markdown tables."""
import json, random, statistics, sys
from pathlib import Path

run = Path(sys.argv[1]); policy = Path(sys.argv[2]); stamp = sys.argv[3]   # e.g. 20261103-172829
rows = json.loads((run / 'results.json').read_text()); report = json.loads((run / 'report.json').read_text())
ARMS = ('clojure', 'python')
INTERFACE = {'range', 'reader', 'unresolved', 'denied', 'syntax', 'name', 'type', 'import', 'value'}

def boot(diffs, n=4000, seed=2026110302):
    if not diffs: return None
    rng = random.Random(seed); m = sorted(sum(rng.choice(diffs) for _ in diffs) / len(diffs) for _ in range(n))
    return [round(m[int(.025 * n)], 4), round(m[int(.975 * n) - 1], 4)]

def tokens(r):
    k = r['usage']['known_tokens']; return k['input_tokens'] + k['cache_creation_input_tokens'] + k['cache_read_input_tokens'] + k['output_tokens']

def audit(r):
    """Worker startup, supervisor errors, OOM, cleanup from the task's worker audits."""
    out = {'startup_ms': [], 'supervisor_errors': [], 'oom': 0, 'cleanup_unconfirmed': 0, 'workers': 0}
    for p in (run / r['dir']).glob('worker-audit/repl-lab-*.json'):
        a = json.loads(p.read_text()); out['workers'] += 1
        out['startup_ms'] += [e['startup_ms'] for e in a['events'] if e['event'] == 'worker-ready']
        out['supervisor_errors'] += [e.get('message', '') for e in a['events'] if e['event'] == 'supervisor-error']
        out['oom'] += bool((a.get('state_before_cleanup') or {}).get('OOMKilled'))
        out['cleanup_unconfirmed'] += not a.get('cleanup_confirmed')
    return out

for i, r in enumerate(rows):
    r['dir'] = f"{i + 1:02}-{r['arm']}"
    m = r['measures']; r['_'] = {
        'correct': int(bool(r['correct'])), 'completed': int(r['status'] == 'completed'),
        'first_valid': int(bool(m.get('first_evaluation_valid'))), 'eval_errors': m.get('evaluation_errors', 0),
        'evaluations': m.get('evaluations', 0), 'tool_calls': m.get('tool_calls', 0), 'requests': r['usage']['calls'],
        'tokens': tokens(r), 'output_tokens': r['usage']['known_tokens']['output_tokens'], 'cost': r['usage']['known_model_cost_usd'],
        'seconds': r['seconds'], 'eval_ms_total': sum(float(x) for x in m.get('evaluation_ms', []) if x is not None),
        'cold_ms': m.get('cold_evaluation_ms'), 'source_chars': m.get('source_chars', 0), 'restarts': m.get('worker_restarts', 0)}
    r['_audit'] = audit(r)
    # Failure category: interface (surface/language error classes), computational (ran clean, wrong answer),
    # controller (not completed / safety / accounting), none.
    classes = set(m.get('error_classes', []))
    r['_category'] = ('controller' if r['status'] != 'completed' or not r.get('safety_complete') else
                      'interface-recovered' if r['correct'] and classes else
                      'interface' if not r['correct'] and classes & INTERFACE else
                      'computational' if not r['correct'] else 'none')

by = {}
for r in rows: by.setdefault(r['task_id'], {})[r['arm']] = r
pairs = [(t, a) for t, a in by.items() if all(k in a for k in ARMS)]
measures = ['correct', 'completed', 'first_valid', 'eval_errors', 'evaluations', 'tool_calls', 'requests', 'tokens', 'output_tokens',
            'cost', 'seconds', 'eval_ms_total', 'cold_ms', 'source_chars', 'restarts']
paired = {}
for k in measures:
    d = [a['clojure']['_'][k] - a['python']['_'][k] for _, a in pairs if a['clojure']['_'][k] is not None and a['python']['_'][k] is not None]
    if not d: continue
    sd = statistics.pstdev(d) if len(d) > 1 else 0
    paired[k] = {'n': len(d), 'mean_diff': round(sum(d) / len(d), 4), 'ci95': boot(d), 'wins_clojure': sum(x > 0 for x in d),
                 'wins_python': sum(x < 0 for x in d), 'ties': sum(x == 0 for x in d), 'cohen_dz': round((sum(d) / len(d)) / sd, 3) if sd else None,
                 'clojure_mean': round(sum(a['clojure']['_'][k] for _, a in pairs) / len(pairs), 4),
                 'python_mean': round(sum(a['python']['_'][k] for _, a in pairs) / len(pairs), 4)}
families = {}
for t, a in pairs:
    f = families.setdefault(a['clojure']['family'], {'cases': 0, 'clojure_correct': 0, 'python_correct': 0, 'clojure_errors': 0, 'python_errors': 0,
                                                     'clojure_seconds': 0, 'python_seconds': 0, 'clojure_cost': 0, 'python_cost': 0})
    f['cases'] += 1
    for arm in ARMS:
        f[f'{arm}_correct'] += a[arm]['_']['correct']; f[f'{arm}_errors'] += a[arm]['_']['eval_errors']
        f[f'{arm}_seconds'] += a[arm]['_']['seconds']; f[f'{arm}_cost'] += a[arm]['_']['cost']
arms = {}
for arm in ARMS:
    sel = [r for r in rows if r['arm'] == arm]
    arms[arm] = {'tasks': len(sel), 'correct': sum(r['_']['correct'] for r in sel), 'completed': sum(r['_']['completed'] for r in sel),
                 'first_valid': sum(r['_']['first_valid'] for r in sel), 'eval_errors': sum(r['_']['eval_errors'] for r in sel),
                 'evaluations': sum(r['_']['evaluations'] for r in sel), 'error_classes': sorted(c for r in sel for c in r['measures'].get('error_classes', [])),
                 'categories': {c: sum(r['_category'] == c for r in sel) for c in ('none', 'interface-recovered', 'interface', 'computational', 'controller')},
                 'requests': sum(r['_']['requests'] for r in sel), 'tokens': sum(r['_']['tokens'] for r in sel), 'output_tokens': sum(r['_']['output_tokens'] for r in sel),
                 'cost_usd': round(sum(r['_']['cost'] for r in sel), 4), 'seconds_total': round(sum(r['_']['seconds'] for r in sel), 1),
                 'seconds_median': round(statistics.median(r['_']['seconds'] for r in sel), 1),
                 'eval_ms_median': round(statistics.median(r['_']['eval_ms_total'] for r in sel), 1),
                 'cold_ms_median': round(statistics.median(r['_']['cold_ms'] for r in sel if r['_']['cold_ms'] is not None), 1),
                 'source_chars_median': statistics.median(r['_']['source_chars'] for r in sel), 'restarts': sum(r['_']['restarts'] for r in sel),
                 'workers': sum(r['_audit']['workers'] for r in sel), 'startup_ms_median': round(statistics.median(v for r in sel for v in r['_audit']['startup_ms']), 0),
                 'startup_ms_max': round(max(v for r in sel for v in r['_audit']['startup_ms']), 0),
                 'supervisor_errors': [e for r in sel for e in r['_audit']['supervisor_errors']], 'oom': sum(r['_audit']['oom'] for r in sel),
                 'cleanup_unconfirmed': sum(r['_audit']['cleanup_unconfirmed'] for r in sel)}
# Host monitor and gate.
mon = [json.loads(l) for l in (policy / f'monitor-substrate-{stamp}.jsonl').read_text().splitlines()]
samples = [s for s in mon if s['kind'] == 'sample']; events = [e for e in mon if e['kind'] == 'event']
stats_lines = [l for s in samples for l in (s['docker'].get('stats') if isinstance(s['docker'].get('stats'), list) else [])]
def mb(text):
    v, unit = text.split('/')[0].strip().split(None, 1) if ' ' in text.split('/')[0].strip() else (text.split('/')[0].strip()[:-3], text.split('/')[0].strip()[-3:])
    return float(v) * {'MiB': 1, 'GiB': 1024, 'KiB': 1 / 1024, 'B': 1 / 2**20}.get(unit.strip(), 1)
worker_mem = [mb(l.split('\t')[2]) for l in stats_lines if l.startswith('repl-lab-')]
host = {'samples': len(samples), 'swap_fraction_min_max': [round(min(s['host']['swap_used_mb'] / s['host']['swap_total_mb'] for s in samples), 3),
                                                            round(max(s['host']['swap_used_mb'] / s['host']['swap_total_mb'] for s in samples), 3)],
        'mem_free_mb_min': min(s['host']['mem_free_mb'] for s in samples), 'load1_max': round(max(s['host']['load'][0] for s in samples), 2),
        'docker_query_timeouts': sum(1 for s in samples if 'error' in s['docker'].get('containers', {}) or 'error' in s['docker'].get('desktop', {})),
        'desktop_sessions': sorted({s['docker'].get('desktop', {}).get('session') for s in samples} - {None}),
        'worker_events': {a: sum(e['action'] == a and e['owner'] == 'worker' for e in events) for a in ('create', 'start', 'die', 'oom', 'kill', 'destroy')},
        'other_project_events': sum(e['owner'] == 'other' for e in events),
        'worker_stats_samples': len(worker_mem), 'worker_mem_mb_max_sampled': round(max(worker_mem), 1) if worker_mem else None,
        'note': 'docker stats sampled every 5 s; a sample is not a peak. CPU-seconds not measured.'}
out = {'run': str(run), 'outcome': report['outcome'], 'gate': report['development_gate'], 'paired_cases': len(pairs),
       'primary': {'mean_paired_difference': report['mean_paired_difference'], 'interval': report['paired_difference_interval']},
       'arms': arms, 'paired': paired, 'families': families, 'host': host,
       'per_task': [{k: r[k] for k in ('dir', 'task_id', 'family', 'arm', 'status', 'failure', 'correct')} | r['_'] | {'category': r['_category'],
                     'error_classes': r['measures'].get('error_classes', []), 'startup_ms': r['_audit']['startup_ms']} for r in rows]}
(run / 'analysis.json').write_text(json.dumps(out, indent=2) + '\n')
print('| Measure | Clojure | Python | mean diff (C−P) | 95% CI | wins C/P/tie |'); print('|---|---|---|---|---|---|')
for k, v in paired.items():
    print(f"| {k} | {v['clojure_mean']} | {v['python_mean']} | {v['mean_diff']} | {v['ci95']} | {v['wins_clojure']}/{v['wins_python']}/{v['ties']} |")
print(); print('| Family | cases | Clojure correct | Python correct | C errors | P errors | C s | P s |'); print('|---|---|---|---|---|---|---|---|')
for f, v in sorted(families.items()):
    print(f"| {f} | {v['cases']} | {v['clojure_correct']} | {v['python_correct']} | {v['clojure_errors']} | {v['python_errors']} | {v['clojure_seconds']:.0f} | {v['python_seconds']:.0f} |")
print(); print(json.dumps({'outcome': out['outcome'], 'gate': out['gate'], 'primary': out['primary'], 'host': host}, indent=1))
print(json.dumps({a: {k: arms[a][k] for k in ('correct', 'completed', 'first_valid', 'eval_errors', 'evaluations', 'error_classes', 'categories', 'requests', 'tokens', 'cost_usd', 'seconds_total', 'seconds_median', 'restarts', 'workers', 'startup_ms_median', 'startup_ms_max', 'supervisor_errors', 'oom', 'cleanup_unconfirmed')} for a in ARMS}, indent=1))
