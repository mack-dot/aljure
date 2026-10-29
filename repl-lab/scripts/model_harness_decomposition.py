"""Per-task decomposition of the Sonnet and Opus OOLONG-synth 32K dev runs, both harnesses.
Read-only over recorded traces; no model calls.

    python3 scripts/model_harness_decomposition.py CLEAN_REPL_LAB OUT.json
"""
import glob
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from benchmark.official import score_answer  # noqa: E402
from benchmark.oolong import read_suite  # noqa: E402

RUNS = {'sonnet': 'var/benchmarks/synth-indep-32k-dev', 'opus': 'var/benchmarks/synth-indep-32k-dev-opus'}


def records(path):
    if not os.path.exists(path):
        return []
    text, decoder, at, out = open(path).read(), json.JSONDecoder(), 0, []
    while at < len(text):
        while at < len(text) and text[at].isspace():
            at += 1
        if at < len(text):
            value, at = decoder.raw_decode(text, at)
            out.append(value)
    return out


def prime_steps(arm):
    """Every python_repl call and its result text, root and any native child sessions."""
    calls, results = [], []
    # Root session files and native child sessions only; native.jsonl repeats the same messages.
    files = glob.glob(arm + '/native/sessions/*.jsonl') + [
        f for f in glob.glob(arm + '/native/agent/session-artifacts/**/sub-*/*.jsonl', recursive=True)
        if not f.endswith('semantic-edges.jsonl')]
    for f in sorted(files):
        for line in open(f):
            if not line.strip():
                continue
            x = json.loads(line)
            m = x.get('message') or {}
            c = m.get('content')
            if m.get('role') == 'assistant' and isinstance(c, list):
                calls += [json.dumps(b.get('arguments') or b.get('input')) for b in c if b.get('type') in ('toolCall', 'tool_use')]
            elif m.get('role') == 'toolResult':
                results.append(' '.join(b.get('text', '') for b in c) if isinstance(c, list) else str(c))
    return calls, results


def aljure_steps(arm):
    ev = records(arm + '/agent/events.jsonl')
    calls = [e['payload']['command'] for e in ev if e['type'] == 'tool-call']
    results = [json.dumps(e['payload'].get('result') or e['payload'].get('error') or '') for e in ev if e['type'] == 'tool-result']
    return ev, calls, results


def arm_metrics(root, run, row, answers):
    arm = os.path.join(root, run, (row.get('trace_path') or row.get('usage_path')).split('/')[0])
    tid, harness = row['task_id'], row['harness']
    answer_path = os.path.join(root, run, row['answer_path']) if row.get('answer_path') else None
    answer = open(answer_path).read() if answer_path and os.path.exists(answer_path) else ''
    usage = records(arm + '/gateway/usage.jsonl')
    context = json.load(open(arm + '/public-input.json'))['context']
    instances = {re.sub(r'^.*Instance: ', '', l)[:60] for l in context.split('\n') if 'Instance:' in l}
    m = {'task_id': tid, 'harness': harness, 'status': row['status'], 'answer': answer.strip()[:120],
         'score': score_answer('oolong-synth', answers[tid], answer)['score'] if row['status'] == 'completed' else 0.0,
         'wall_s': round((row.get('wall_time_ms') or 0) / 1000, 1), 'model_calls': len(usage),
         'output_tokens': sum(u.get('output_tokens') or 0 for u in usage),
         'cost_usd': round(sum(u.get('estimated_usd') or 0 for u in usage), 5)}
    if harness == 'aljure':
        ev, calls, results = aljure_steps(arm)
        shown = ' '.join(results)
        m.update(tool_executions=len(calls), tool_errors=sum(1 for e in ev if e['type'] == 'tool-result'
                                                            and e['payload'].get('status') != 'ok'),
                 child_sessions=sum(1 for e in ev if e['type'] == 'session-created') - 1,
                 corrections=sum(1 for e in ev if e['type'] == 'command-rejected'),
                 rejection_reasons=[e['payload'].get('reason') for e in ev if e['type'] == 'command-rejected'],
                 finalization=next((c['op'] for c in reversed(calls) if c.get('op') in ('done', 'done/eval')), None))
    else:
        calls, results = prime_steps(arm)
        shown = ' '.join(results)
        code = ' '.join(calls)
        m.update(tool_executions=len(calls), tool_errors=sum(1 for r in results if re.search(r'Traceback|Error:', r)),
                 child_sessions=len(glob.glob(arm + '/native/agent/session-artifacts/*/sub-*')), corrections=0, rejection_reasons=[],
                 finalization='answer-file' if answer else 'no-answer-file')
    m['instances_total'] = len(instances)
    m['instances_shown'] = sum(1 for i in instances if i and i in shown)
    m['review_fraction'] = round(m['instances_shown'] / max(1, len(instances)), 3)
    return m


def main(root, out):
    manifest, tasks, answers = read_suite(os.path.join(root, 'var/official/synth32-indep-dev'))
    rows = []
    for model, run in RUNS.items():
        for r in records(os.path.join(root, run, 'results.jsonl')):
            m = arm_metrics(root, run, r, answers)
            m.update(model=model, dataset=answers[r['task_id']]['dataset'],
                     answer_type=answers[r['task_id']]['answer_type'].split('.')[-1])
            rows.append(m)
    Path(out).write_text(json.dumps(rows, indent=1) + '\n')
    key = {(r['model'], r['harness'], r['task_id']): r for r in rows}
    print('task        type        |  A-son  A-opus |  P-son  P-opus | rev A s/o  rev P s/o | calls A s/o P s/o | final A-opus')
    for tid in manifest['task_ids']:
        g = lambda mo, h, k: key[(mo, h, tid)][k]  # noqa: E731
        print(f"{answers[tid]['dataset']:11} {key[('opus','aljure',tid)]['answer_type'][:10]:10} | "
              f"{g('sonnet','aljure','score'):5.2f} {g('opus','aljure','score'):6.2f} | {g('sonnet','prime','score'):5.2f} {g('opus','prime','score'):6.2f} | "
              f"{g('sonnet','aljure','review_fraction'):4.2f}/{g('opus','aljure','review_fraction'):4.2f}  {g('sonnet','prime','review_fraction'):4.2f}/{g('opus','prime','review_fraction'):4.2f} | "
              f"{g('sonnet','aljure','model_calls'):2}/{g('opus','aljure','model_calls'):2} {g('sonnet','prime','model_calls'):2}/{g('opus','prime','model_calls'):2} | "
              f"{g('opus','aljure','finalization')} {g('opus','aljure','rejection_reasons')}")


if __name__ == '__main__':
    main(*sys.argv[1:3])
