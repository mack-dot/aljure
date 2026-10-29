"""Control, F1 and F2 (contract ablation, Opus, dev suite): scores, reliability, cost
and the preregistered criteria (research/CONTRACT_FIX_ACCEPTANCE_CRITERIA.md).
Read-only over the recorded runs; no model calls.

    python3 scripts/contract_ablation_compare.py CLEAN_REPL_LAB OUT.json
"""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from benchmark.audit import paired_statistics  # noqa: E402
from contract_audit import audit_run, jsonl  # noqa: E402

PLANS = {'control': '87d8c949a5dafe983c8965fd0d352ebafe8977210d27663a65c64013ff369eb7',
         'f1': '52f51590c44e60df2af1cb7e7284792a2d35b0a6f16f868cb11fbca062bb0773',
         'f2': 'b1844732305d2b9236a89af7ddd7078667fad530b04777ccb326b12547ed6e5d'}
SUITE = 'var/official/synth32-indep-dev'


def text_only_triggers(arm):
    """Each root correction after a text-only reply, and how the arm then ended."""
    events = jsonl(arm + '/agent/events.jsonl')
    out = []
    for i, e in enumerate(events):
        p = e['payload']
        if e['type'] == 'command-rejected' and p.get('reason') == 'no-tool-call' and p.get('session', 'root') == 'root':
            after = [x for x in events[i + 1:] if x['type'] in ('tool-call', 'terminal-text-accepted', 'command-rejected',
                                                                  'session-finished', 'evidence-gate')]
            first = after[0] if after else None
            if not p.get('correction-requested'):
                outcome = 'failed (no correction left)'
            elif first is None:
                outcome = 'unknown'
            elif first['type'] == 'terminal-text-accepted':
                outcome = 'FINAL ANSWER'
            elif first['type'] == 'tool-call' and first['payload']['command'].get('op') in ('done', 'done/eval'):
                outcome = 'done'
            elif first['type'] == 'tool-call':
                outcome = 'continued with a tool call'
            elif first['type'] == 'command-rejected':
                outcome = 'rejected again'
            else:
                outcome = first['type']
            out.append({'correction_granted': bool(p.get('correction-requested')), 'outcome': outcome})
    return out


def plan_summary(clean, name):
    run = Path(clean) / f'var/benchmarks/contract-ablation-opus-{name}'
    plan = json.loads((run / 'plan.json').read_text())
    assert plan['plan_sha256'] == PLANS[name], f'{name}: plan hash differs'
    report = json.loads((run / 'report.json').read_text())
    results = [json.loads(line) for line in (run / 'results.jsonl').read_text().splitlines() if line.strip()]
    stats = paired_statistics(report, Path(clean) / SUITE, results, resamples=10000, seed=0)
    audit = audit_run(str(run))
    arms = {a['arm'].rsplit('/', 1)[-1]: a for a in audit['arms']}
    triggers, by_task = [], {}
    for r in results:
        arm = str(run / Path(r['trace_path']).parts[0]) if r.get('trace_path') else None
        by_task.setdefault(r['task_id'], {})[r['harness']] = {'status': r['status'], 'failure': r.get('failure'),
                                                             'wall_s': round(r['wall_time_ms'] / 1000, 1)}
        if r['harness'] == 'aljure' and arm:
            triggers += [{'task_id': r['task_id'], **t} for t in text_only_triggers(arm)]
    for case in report['cases']:
        by_task[case['task_id']][case['harness']].update(score=round(case['score'], 4), calls=case['usage']['calls'],
                                                         cost=round(case['usage']['model_cost_usd'], 4))
    aljure_arms = [a for a in arms.values()]
    return {'plan_sha256': plan['plan_sha256'], 'contract': plan['config'].get('aljure_contract'),
            'statistics': stats, 'by_task': by_task, 'text_only_triggers': triggers,
            'audit': {'arms': len(aljure_arms),
                      'conformant': sum(a['status'] == 'conformant' for a in aljure_arms),
                      'unauditable': [k for k, a in arms.items() if a['status'] == 'unauditable'],
                      'violations': [dict(v, arm=k) for k, a in arms.items() for v in a.get('violations', [])],
                      'responses': {k: sum(a.get('responses', {}).get(k, 0) for a in aljure_arms)
                                    for k in ('tool-call', 'text-only', 'truncated', 'multiple-commands', 'incomplete-turn', 'content-blocks')},
                      'retries': sum(a.get('retries', 0) for a in aljure_arms),
                      'retries_refused_by_limit': sum(a.get('retries_refused_by_limit', 0) for a in aljure_arms),
                      'terminal_accepted': sum(a.get('terminal_accepted', 0) for a in aljure_arms),
                      'corrections': sum(a.get('corrections', 0) for a in aljure_arms)}}


COUNT_TASKS = ('oolong-synth-test-32768-715070023', 'oolong-synth-test-32768-315030024',
               'oolong-synth-test-32768-315030025', 'oolong-synth-test-32768-315030026')
RUNS = {'d6e9b40d (earlier)': 'var/benchmarks/synth-indep-32k-dev-opus', 'control': 'var/benchmarks/contract-ablation-opus-control',
        'f1': 'var/benchmarks/contract-ablation-opus-f1', 'f2': 'var/benchmarks/contract-ablation-opus-f2'}


def variation(clean, plans):
    """Run-to-run spread: Prime's four identical Opus runs, and Aljure where no fix fired."""
    import re
    import statistics as st
    gold = {r['task_id']: r['answer'] for r in map(json.loads, (Path(clean) / SUITE / 'controller/answers.jsonl').read_text().splitlines())}
    runs = {}
    for name, rel in RUNS.items():
        run = Path(clean) / rel
        if not (run / 'report.json').exists():
            continue
        report = json.loads((run / 'report.json').read_text())
        results = {(r['task_id'], r['harness']): r for r in map(json.loads, (run / 'results.jsonl').read_text().splitlines())}
        rows = {}
        for case in report['cases']:
            r = results[(case['task_id'], case['harness'])]
            answer = (run / r['answer_path']).read_text() if r.get('answer_path') and (run / r['answer_path']).exists() else ''
            number = re.findall(r'-?\d+', answer)
            truth = re.findall(r'-?\d+', gold[case['task_id']])
            error = int(number[-1]) - int(truth[0]) if case['task_id'] in COUNT_TASKS and number and truth else None
            rows[(case['task_id'], case['harness'])] = {'score': case['score'], 'count_error': error}
        runs[name] = rows
    tasks = sorted({t for rows in runs.values() for t, _ in rows})
    triggered = {(t['task_id']) for name in ('f1', 'f2') if name in plans for t in plans[name]['text_only_triggers']}
    out = {'runs': list(runs)}
    for harness in ('aljure', 'prime'):
        means = {name: st.mean(rows[(t, harness)]['score'] for t in tasks) for name, rows in runs.items()}
        per_task_sd = [st.pstdev([rows[(t, harness)]['score'] for rows in runs.values()]) for t in tasks]
        out[harness] = {'run_means': {k: round(v, 3) for k, v in means.items()},
                        'sd_of_run_means': round(st.stdev(means.values()), 3) if len(means) > 1 else None,
                        'range_of_run_means': round(max(means.values()) - min(means.values()), 3),
                        'tasks_that_varied': sum(1 for sd in per_task_sd if sd > 0),
                        'count_errors': {t[-9:]: [rows[(t, harness)]['count_error'] for rows in runs.values()] for t in COUNT_TASKS}}
    out['aljure']['tasks_with_a_fix_trigger_in_f1_or_f2'] = sorted(t[-9:] for t in triggered)
    diffs = {name: st.mean(rows[(t, 'aljure')]['score'] - rows[(t, 'prime')]['score'] for t in tasks) for name, rows in runs.items()}
    out['paired_difference_by_run'] = {k: round(v, 3) for k, v in diffs.items()}
    return out


def criteria(plans):
    c, f1, f2 = plans['control'], plans['f1'], plans['f2']
    a = {'all_auditable_and_conformant': all(p['audit']['conformant'] == p['audit']['arms'] == 21 and not p['audit']['unauditable']
                                             for p in plans.values()),
         'control_no_retry_no_terminal': c['audit']['retries'] == 0 and c['audit']['terminal_accepted'] == 0,
         'f1_no_terminal': f1['audit']['terminal_accepted'] == 0,
         'f2_no_retry': f2['audit']['retries'] == 0}
    truncations = f1['audit']['responses']['truncated']
    f1_failed_on_truncation = [t for t, h in f1['by_task'].items()
                               if h['aljure']['status'] != 'completed' and 'truncat' in str(h['aljure'].get('failure') or '').lower()]
    b = ('not fixed' if f1_failed_on_truncation or any(v['check'] == 'f1-retry' for v in f1['audit']['violations'])
         else 'fixed live' if truncations else 'not triggered')
    granted = [t for t in f2['text_only_triggers'] if t['correction_granted']]
    unrecovered = [t for t in f2['text_only_triggers'] if t['outcome'].startswith('failed')]
    cc = 'not fixed' if unrecovered else ('fixed live' if len(granted) >= 3 else 'not shown')
    return {'A_contract_integrity': a, 'A_pass': all(a.values()), 'B_f1': b, 'B_truncations_in_f1': truncations,
            'C_f2': cc, 'C_triggers': len(granted), 'C_outcomes': [t['outcome'] for t in f2['text_only_triggers']],
            'C_rule_of_three_upper_bound': round(3 / len(granted), 2) if granted else None,
            'verdict': 'fixed without compromising the contract'
            if all(a.values()) and cc == 'fixed live' and b in ('fixed live', 'not triggered') else 'see criteria'}


def main(clean, out):
    plans = {name: plan_summary(clean, name) for name in PLANS}
    result = {'model_calls': 0, 'plans': plans, 'criteria': criteria(plans), 'variation': variation(clean, plans)}
    Path(out).write_text(json.dumps(result, indent=1))
    for name, p in plans.items():
        s = p['statistics']
        print(name, {h: {k: s['per_harness'][h][k] for k in ('deadline_aware_mean', 'completion_rate', 'cost_usd',
                                                               'latency_s_p50', 'latency_s_p95', 'model_calls')}
                     for h in ('aljure', 'prime')}, p['audit'] | {'violations': len(p['audit']['violations'])})
    print(json.dumps(result['criteria'], indent=1))
    print(json.dumps(result['variation'], indent=1))


if __name__ == '__main__':
    main(*sys.argv[1:3])
