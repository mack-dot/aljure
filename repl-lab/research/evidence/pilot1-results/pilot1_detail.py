"""Pilot 1, descriptive and post-hoc (not preregistered): per-task S/D/P comparisons, verified
invocations, refusals, coverage, cost and latency, and for count tasks an error split into the
library's part and the residual part. The library's per-record labels come from seed_py (checked
equal to the SCI worker's per-window counts). Controller-only gold, offline, no model calls."""
import glob, json, re, statistics as st, sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, '/Users/mackianni/aljure-unblock-v1/repl-lab')
sys.path.insert(0, str(Path(__file__).parent))
from benchmark.oolong import jsonl, read_suite  # noqa: E402
from benchmark.paired import account  # noqa: E402
from seed_py import seed  # noqa: E402

ROOT = Path('/Users/mackianni/aljure-unblock-v1/repl-lab')
SUITE = ROOT / 'var/official/reuse-pilot-validation-v1'
manifest, tasks, answers = read_suite(SUITE)
items = {w['context_sha256']: w['items'] for w in json.loads((SUITE / 'controller/task-items.json').read_text())['windows']}
F1 = set(manifest['selection']['families']['F1'])


def num(text):
    m = re.search(r'Answer:\s*\[?\s*(-?\d+)', text or '')
    return int(m.group(1)) if m else None


rows = []
for run in sorted(glob.glob(str(ROOT / 'var/reuse-pilot/runs/reuse-*'))):
    arm, rep = re.search(r'reuse-([SDP])-r(\d)', run).groups()
    if not Path(run, 'report.json').exists():
        continue  # a run still in progress
    report = {c['task_id']: c for c in json.loads(Path(run, 'report.json').read_text())['cases']}
    for r in jsonl(Path(run, 'results.jsonl')):
        t, gold = r['task_id'], answers[r['task_id']]
        ev = list(jsonl(Path(run, Path(r['trace_path']).parts[0], 'agent/events.jsonl')))
        of = lambda k: [e['payload'] for e in ev if e['type'] == k]
        usage = account(list(jsonl(Path(run, r['usage_path']))), r['pricing_usd_per_m'])
        text = Path(run, r['answer_path']).read_text() if r.get('answer_path') else ''
        row = {'arm': arm, 'run': int(rep), 'task': t, 'family': 'F1' if t in F1 else 'F2', 'type': gold['answer_type'].split('.')[-1],
               'window': f"{gold['dataset']}-{gold['context_window_id']}", 'status': r['status'], 'failure': r['failure'],
               'score': report[t]['score'], 'cost': float(usage['known_model_cost_usd']), 'calls': report[t]['usage']['calls'],
               'wall_s': r['wall_time_ms'] / 1000, 'answer': text.strip()[:80],
               'preloaded': any(p.get('decision') == 'preload' for p in of('artifact-applicability')),
               'refused': any(p.get('decision') == 'refuse' for p in of('artifact-applicability')),
               'invocations': sum(i.get('calls', 1) for p in of('artifact-invocations') for i in p.get('invocations', [])),
               'invoked': bool(of('artifact-invocations')),
               'supplied': (of('artifact-supplied') or [None])[0],
               'reuse': (of('artifact-reuse-summary') or [{}])[0].get('classification'),
               'text_rejections': len(of('command-rejected'))}
        # Post-hoc, stricter than the preregistered heuristic: an evaluation that called a library
        # function returned the number the model then delivered (numbers only).
        values = {q.get('call-sequence'): (q.get('result') or {}).get('value') for q in of('tool-result')}
        def numbers(v):
            if isinstance(v, bool): return []
            if isinstance(v, (int, float)): return [v]
            if isinstance(v, dict): return [x for y in v.values() for x in numbers(y)]
            if isinstance(v, list): return [x for y in v for x in numbers(y)]
            return []
        declared_number = num(text)
        row['invoked_value_in_answer'] = declared_number is not None and any(
            declared_number in numbers(values.get(q.get('call-sequence'))) for q in of('artifact-invocations'))
        # Attribution by source: model-directed reuse names the function in its own code; controller-supplied
        # reuse reads library-labels. Each root repl_eval call is paired with the next root result, in order.
        calls = [e['payload'] for e in ev if e['type'] == 'tool-call' and e['payload'].get('session') == 'root'
                 and e['payload']['command'].get('op') == 'repl/eval']
        results = [e['payload'] for e in ev if e['type'] == 'tool-result' and e['payload'].get('session') == 'root'
                   and e['payload'].get('op') == 'repl/eval']
        pairs = list(zip([c['command'].get('source', '') for c in calls], [(q.get('result') or {}).get('value') for q in results]))
        names_fn = [v for src, v in pairs if 'a1c-trec-rules' in src]
        reads_labels = [v for src, v in pairs if 'library-labels' in src]
        row['model_directed'] = bool(names_fn)
        row['model_directed_value_in_answer'] = declared_number is not None and any(declared_number in numbers(v) for v in names_fn)
        row['reads_supplied'] = bool(reads_labels)
        row['supplied_value_in_answer'] = declared_number is not None and any(declared_number in numbers(v) for v in reads_labels)
        supplied_calls = sum(x.get('records', 0) for x in of('artifact-supplied'))
        row['model_function_calls'] = max(0, row['invocations'] - supplied_calls)
        if row['type'] == 'NUMERIC' and t in F1:
            label = re.search(r"label '([^']+)'", tasks[t]['question']).group(1)
            recs = items[tasks[t]['context_sha256']]
            decided = [(seed(i['text']), i['label']) for i in recs]
            lib_count = sum(1 for p, _ in decided if p == label)
            gold_dec = sum(1 for p, g in decided if p is not None and g == label)
            gold_total = num('Answer: ' + re.sub(r'[\[\]]', '', gold['answer']))
            a = num(text)
            row.update(label=label, gold=gold_total, declared=a, records=len(recs), residual_records=sum(1 for p, _ in decided if p is None),
                       library_count=lib_count, library_error=lib_count - gold_dec,
                       residual_error=None if a is None else (a - lib_count) - (gold_total - gold_dec),
                       error=None if a is None else a - gold_total)
        rows.append(row)

out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('pilot1-detail.json')
out.write_text(json.dumps(rows, indent=1))
by = defaultdict(list)
for r in rows:
    by[(r['arm'], r['family'])].append(r)
for (arm, fam), rs in sorted(by.items()):
    num_rs = [r for r in rs if r.get('gold') is not None]
    print(f"{arm} {fam} n={len(rs)} score {st.mean(r['score'] for r in rs):.3f} completed {sum(r['status']=='completed' for r in rs)} "
          f"cost ${sum(r['cost'] for r in rs):.3f} calls {sum(r['calls'] for r in rs)} p50 {st.median(r['wall_s'] for r in rs):.0f}s "
          f"preloaded {sum(r['preloaded'] for r in rs)} refused {sum(r['refused'] for r in rs)} invoked {sum(r['invoked'] for r in rs)} "
          f"eligible-reuse {sum(r['reuse']=='eligible-reuse' for r in rs)} model-directed {sum(r['model_directed'] for r in rs)} "
          f"(value in answer {sum(r['model_directed_value_in_answer'] for r in rs)}) reads-supplied {sum(r['reads_supplied'] for r in rs)} "
          f"(value in answer {sum(r['supplied_value_in_answer'] for r in rs)}) "
          f"text-rejections {sum(r['text_rejections'] for r in rs)}")
    if num_rs:
        errs = [abs(r['error']) for r in num_rs if r['error'] is not None]
        res = [abs(r['residual_error']) for r in num_rs if r['residual_error'] is not None]
        print(f"     count tasks {len(num_rs)} |error| median {st.median(errs) if errs else None} mean {st.mean(errs) if errs else None:.1f} "
              f"| library |error| mean {st.mean(abs(r['library_error']) for r in num_rs):.1f} | residual |error| mean {st.mean(res) if res else float('nan'):.1f}")
