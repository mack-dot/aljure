#!/usr/bin/env python3
"""Post-run review for head-to-head v8 Phase B run-1 (derived, read-only; never alters the frozen run):
1. Mechanical classification of cap-affected arms: an Aljure arm whose controller result says the provider
   budget was exhausted, or a Prime arm whose session log ends with a provider error carrying the relay's 429.
2. The official pre-registered endpoint is left exactly as report.json computed it (cap failures score 0).
3. A diagnostic cap-unaffected comparison: the same paired_analysis over the items where neither arm was
   cap-affected, labelled diagnostic.
4. A round-by-round reconciliation table with exact score differences (ties are differences of exactly 0).
Writes <run>/phase-b-review.json and prints a summary."""
import glob, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from benchmark import headtohead as h  # noqa: E402

run = Path(sys.argv[1])
plan = json.loads((run / 'plan.json').read_text())
rows = [json.loads(l) for l in open(run / 'results.jsonl') if l.strip()]


def cap_affected(r):
    d = run / f"{r['index']:03}-{r['suite']}-{r['harness']}"
    if r['harness'] == 'aljure':
        p = d / 'agent/result.json'
        if p.exists():
            err = str((json.loads(p.read_text()).get('result') or {}).get('error') or '')
            if 'budget exhausted' in err:
                return 'aljure-controller-budget-exhausted'
        return None
    for f in glob.glob(str(d / 'native/sessions/*.jsonl')):
        for line in open(f):
            try:
                m = json.loads(line).get('message') or {}
            except ValueError:
                continue
            if m.get('role') == 'assistant' and m.get('stopReason') == 'error' and '429' in str(m.get('errorMessage')):
                return 'prime-relay-429-after-gateway-refusal'
    return None


for r in rows:
    r['cap_affected'] = cap_affected(r)
items = {}
for r in rows:
    items.setdefault((r['suite'], r['task_id'], r['trial']), {})[r['harness']] = r
affected_items = sorted(k for k, v in items.items() if any(x.get('cap_affected') for x in v.values()))
clean = [r for r in rows if (r['suite'], r['task_id'], r['trial']) not in set(affected_items)]

# Diagnostic pooled analysis on cap-unaffected items.
contexts = {}
for name, suite in plan['suites'].items():
    contexts.update({f"{name}:{t}": f"{name}:{c}" for t, c in suite['contexts'].items()})
pooled_clean = [{**r, 'task_id': f"{r['suite']}:{r['task_id']}"} for r in clean]
diagnostic = h.paired_analysis(pooled_clean, contexts) if clean else None
per_length_clean = {}
for name in plan['suites']:
    mine = [r for r in clean if r['suite'] == name]
    if mine and {x['harness'] for x in mine} == {'aljure', 'prime'}:
        per_length_clean[name] = h.paired_analysis(mine, plan['suites'][name]['contexts'])

# Round-by-round reconciliation (items in run order).
rounds = []
w = t = l = 0
for k in sorted(items, key=lambda k: min(x['index'] for x in items[k].values())):
    v = items[k]
    if set(v) != {'aljure', 'prime'}:
        continue
    a, p = v['aljure'], v['prime']
    d = a['score'] - p['score']
    if d > 0:
        w += 1; res = 'A'
    elif d < 0:
        l += 1; res = 'P'
    else:
        t += 1; res = 'tie'
    rounds.append({'round': len(rounds) + 1, 'length': k[0][5:-14] + 'K', 'task': k[1], 'trial': k[2], 'aljure': a['score'], 'prime': p['score'],
                   'difference': d, 'result': res, 'running_wtl': [w, t, l],
                   'cap': {hh: v[hh].get('cap_affected') for hh in ('aljure', 'prime') if v[hh].get('cap_affected')} or None,
                   'provenance': {hh: (v[hh].get('answer_provenance') or {}).get('source') for hh in ('aljure', 'prime')}})

review = {'run': str(run), 'plan_sha256': plan['plan_sha256'], 'arms': len(rows),
          'cap_affected_arms': [{'index': r['index'], 'suite': r['suite'], 'harness': r['harness'], 'kind': r['cap_affected']} for r in rows if r['cap_affected']],
          'cap_affected_items': [list(k) for k in affected_items],
          'official_endpoint_note': 'report.json primary_pooled is the pre-registered endpoint and keeps every cap failure as a 0 score',
          'diagnostic_cap_unaffected': {'label': 'DIAGNOSTIC, not pre-registered', 'items_excluded': len(affected_items),
                                        'pooled': diagnostic, 'per_length': per_length_clean},
          'rounds': rounds, 'final_wtl_official': [w, t, l]}
(run / 'phase-b-review.json').write_text(json.dumps(review, indent=1) + '\n')
print('cap-affected arms:', review['cap_affected_arms'])
print('official W/T/L', [w, t, l])
if diagnostic:
    print('DIAGNOSTIC pooled (cap-unaffected): tasks', diagnostic['tasks'], 'contexts', diagnostic['independent_contexts'],
          'ctx-weighted', round(diagnostic['context_weighted_mean_difference'], 4), 'CI95', [round(x, 4) for x in diagnostic['cluster_bootstrap']['ci95']],
          'CI90', [round(x, 4) for x in diagnostic['cluster_bootstrap']['ci90']], 'decision', diagnostic['decision'], 'WTL', diagnostic['wins_ties_losses'])
for rr in rounds:
    print(f"{rr['round']:2} {rr['length']:>5} {rr['result']:3} A={rr['aljure']:.4f} P={rr['prime']:.4f} d={rr['difference']:+.4f} -> {rr['running_wtl']}" + (f"  cap={rr['cap']}" if rr['cap'] else ''))
