"""Read-only analysis of the finished L0-L2 review-level arms, for
research/CONTROLLER_VERIFICATION_DESIGN.md. No model calls. It reads only the
execution checkout and writes one JSON file. Dev-suite gold is used for offline
error analysis only, never by any inference-time mechanism.

    python3 -I scripts/verification_trace_analysis.py EXEC_REPL_LAB OUT.json
"""
import json, re, statistics as st, sys
from pathlib import Path

root, out = Path(sys.argv[1]), Path(sys.argv[2])
gold = {}
for line in (root / 'var/official/synth32-dev-label-counts/controller/answers.jsonl').read_text().splitlines():
    g = json.loads(line)
    gold[g['task_id']] = {'value': int(json.loads(g['answer'])[0]), 'dataset': g['dataset']}

def jsonl(p):
    p = Path(p)
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []

def official_parse(answer):
    # Mirrors benchmark/vendor/oolong_synth.py synth_attempt_answer_parse for numeric answers.
    if ':' not in answer:
        return answer if len(answer) < 20 else answer.split()[-1]
    return answer.split(':')[-1].strip().replace('*', '').replace('[', '').replace(']', '')

def parse_int(s):
    try:
        return int(s)
    except Exception:
        return None

INT_COLL = re.compile(r'(?:#\{|\[)\s*(\d+(?:[\s,]+\d+){4,})\s*[\]}]')
rows = []
for level in ['l0-baseline', 'l1-labels', 'l2-audit']:
    plan = root / f'var/benchmarks/review-levels-opus-{level}'
    results = {(r['task_id'], r['harness']): r for r in jsonl(plan / 'results.jsonl')}
    report = json.loads((plan / 'report.json').read_text()) if (plan / 'report.json').exists() else None
    cases = {(c['task_id'], c['harness']): c for c in (report or {}).get('cases', [])}
    for arm in sorted(plan.glob('[0-9][0-9]-*')):
        if not (arm / 'trace.json').exists():
            continue
        pub = json.loads((arm / 'public-input.json').read_text())
        task_id = pub['task']['task_id']
        harness = arm.name.split('-', 1)[1]
        r = results.get((task_id, harness), {})
        answer = (arm / 'answer.txt').read_text() if (arm / 'answer.txt').exists() else None
        parsed = parse_int(official_parse(answer)) if answer is not None else None
        g = gold[task_id]['value']
        q = pub['task']['question']
        label = (re.findall(r"label '([^']+)'", q) or [None])[0]
        row = {'level': level[:2].upper(), 'arm': arm.name, 'task': task_id[-9:], 'dataset': gold[task_id]['dataset'],
               'label': label, 'harness': harness, 'status': r.get('status'), 'failure': r.get('failure'),
               'gold': g, 'answer_text': None if answer is None else answer[:160], 'answer_lines': None if answer is None else len(answer.strip().splitlines()),
               'answer_chars': None if answer is None else len(answer), 'official_parse_int': parsed,
               'signed_error': None if parsed is None else parsed - g,
               'leading_int': (lambda m: int(m.group(1)) if m else None)(re.search(r'Answer:\s*(-?\d+)', answer or '')),
               'score': cases.get((task_id, harness), {}).get('score'),
               'parse_confidence': cases.get((task_id, harness), {}).get('parse_confidence'),
               'cost': cases.get((task_id, harness), {}).get('usage', {}).get('model_cost_usd'),
               'calls': cases.get((task_id, harness), {}).get('usage', {}).get('calls')}
        if harness == 'aljure':
            ev = jsonl(arm / 'agent/events.jsonl')
            calls = [e['payload']['command'] for e in ev if e['type'] == 'tool-call']
            srcs = [c.get('source', '') for c in calls if c.get('op') == 'repl/eval']
            results_ok = [e['payload'].get('result', {}).get('value') for e in ev
                          if e['type'] == 'tool-result' and e['payload'].get('op') == 'repl/eval' and e['payload'].get('status') == 'ok']
            done = [c for c in calls if c.get('op') in ('done', 'done/eval')]
            atom_sets = sum(bool(re.search(r'\(def\s+\S+\s+\(atom\s+(#\{\}|\[\]|\{\}|\(sorted-set\))', s)) for s in srcs)
            literal_id_colls = sum(len(INT_COLL.findall(s)) for s in srcs)
            items_in_literals = sum(len(re.findall(r'\d+', m)) for s in srcs for m in INT_COLL.findall(s))
            row.update({
                'repl_calls': len(srcs), 'context_queries': sum(c.get('op') == 'context/query' for c in calls),
                'done_ops': [c.get('op') for c in done],
                'done_summary': [c.get('summary', '')[:200] for c in done if c.get('op') == 'done'],
                'atom_collections_defined': atom_sets, 'literal_id_collections': literal_id_colls,
                'ids_written_in_literals': items_in_literals,
                'answer_in_tool_result': row['official_parse_int'] is not None and
                    re.search(rf'(?<![\d-]){row["leading_int"] or row["official_parse_int"]}(?!\d)', json.dumps(results_ok)) is not None,
                'unknown_labels': sum(':unknown' in s for s in srcs), 'audit_calls': sum('audit-labels' in s for s in srcs),
                'show_items_calls': sum('show-items' in s for s in srcs),
                'command_rejected': sum(e['type'] == 'command-rejected' for e in ev),
                'evidence_gate': sum(e['type'] == 'evidence-gate' for e in ev),
                'agent_call': sum(c.get('op') == 'agent/call' for c in calls)})
        rows.append(row)

# Summary. "leading" counts an unparsed answer by its leading "Answer: N" number.
RECORDS = {'negation': 683, 'formality': 602, 'imdb': 81, 'app_reviews': 627, 'multinli': 438}
lead = lambda r: (r['leading_int'] - r['gold']) if r['leading_int'] is not None else r['signed_error']
summary = {'levels': {}, 'shared_bias': {}, 'evidence_in_worker_state': {}}
for level in ['L0', 'L1', 'L2']:
    for h in ['aljure', 'prime']:
        rs = [r for r in rows if r['level'] == level and r['harness'] == h]
        parsed = [abs(r['signed_error']) for r in rs if r['signed_error'] is not None]
        leading = [abs(lead(r)) for r in rs if lead(r) is not None]
        summary['levels'][f'{level}-{h}'] = {
            'finished_arms': len(rs), 'official_parse_failures': sum(r['official_parse_int'] is None for r in rs),
            'mae_parsed_only': round(st.mean(parsed), 2) if parsed else None,
            'mae_leading_number': round(st.mean(leading), 2) if leading else None,
            'cost_per_arm': round(st.mean([r['cost'] for r in rs if r['cost'] is not None]), 4) if any(r['cost'] for r in rs) else None}
al = [r for r in rows if r['harness'] == 'aljure']
summary['activation_aljure'] = {k: sum(r[k] for r in al) for k in ('unknown_labels', 'audit_calls', 'show_items_calls', 'evidence_gate', 'agent_call')}
summary['activation_aljure']['arms'] = len(al)
pa, pp = [], []
for t in sorted({r['task'] for r in rows}):
    a = [lead(r) for r in rows if r['task'] == t and r['harness'] == 'aljure' and lead(r) is not None]
    p = [r['signed_error'] for r in rows if r['task'] == t and r['harness'] == 'prime' and r['signed_error'] is not None]
    if a and p:
        pa.append(st.mean(a)); pp.append(st.mean(p))
        summary['shared_bias'][t] = {'aljure_signed': a, 'prime_signed': p}
summary['shared_bias_correlation'] = round(st.correlation(pa, pp), 3)
answered = [r for r in al if r['leading_int'] is not None]
literal = [r for r in answered if r['ids_written_in_literals'] > 0 and
           r['ids_written_in_literals'] in (r['leading_int'], RECORDS[r['dataset']] - r['leading_int'])]
summary['evidence_in_worker_state'] = {
    'answered_arms': len(answered), 'literal_id_sets_equal_answer_or_complement': len(literal),
    'atom_collection_defined': sum(r['atom_collections_defined'] > 0 for r in answered),
    'either': sum(r in literal or r['atom_collections_defined'] > 0 for r in answered)}
out.write_text(json.dumps({'summary': summary, 'rows': rows}, indent=1))
print(json.dumps(summary['levels']), json.dumps(summary['evidence_in_worker_state']), summary['shared_bias_correlation'])
