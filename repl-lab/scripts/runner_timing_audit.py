"""Where paired-run wall time goes: model time, task startup, SCI worker startup and
SCI execution, runner overhead, and gaps between arms. Read-only over recorded arms.

    python3 scripts/runner_timing_audit.py OUT.json RUN_DIR [RUN_DIR ...]
"""
import glob
import json
from pathlib import Path
import statistics as st
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from contract_audit import jsonl  # noqa: E402


def union(spans):
    """Seconds covered by at least one request: overlapping child requests count once."""
    total, end = 0.0, None
    for start, stop in sorted(spans):
        if end is None or start > end:
            total, end = total + (stop - start), stop
        elif stop > end:
            total, end = total + (stop - end), stop
    return total


def arm_timing(arm, wall_s):
    """All times on the gateway's arm clock (task_elapsed_ms), which starts with the arm."""
    transport = jsonl(arm + '/gateway/transport.jsonl')
    started = {t['gateway_request_id']: t for t in transport if t.get('event') == 'started'}
    answered = {t['gateway_request_id']: t for t in transport if t.get('event') == 'response'}
    spans = sorted((started[k]['task_elapsed_ms'] / 1000, answered[k]['task_elapsed_ms'] / 1000) for k in started if k in answered)
    origin = min((started[k]['time_unix_ms'] - started[k]['task_elapsed_ms'] for k in started), default=None)
    model_s = union(spans)
    first, last = (spans[0][0], max(b for _, b in spans)) if spans else (None, None)
    events = jsonl(arm + '/agent/events.jsonl')
    sci_s = sum(e['payload'].get('elapsed-ms', 0) for e in events if e['type'] == 'tool-result') / 1000
    ready = [e['elapsed_ms'] / 1000 for f in glob.glob(arm + '/worker-audit/*.json')
             for e in json.loads(Path(f).read_text()).get('events', []) if e['event'] == 'worker-ready']
    preflight_s = sum(q.get('elapsed_ms', 0) for f in glob.glob(arm + '/worker-audit/preflight/*.json')
                      for q in json.loads(Path(f).read_text()).get('queries', [])) / 1000
    return {'wall_s': round(wall_s, 2), 'model_s': round(model_s, 2), 'model_s_summed': round(sum(b - a for a, b in spans), 2),
            'requests': len(spans), 'before_first_request_s': round(first, 2) if spans else None,
            'after_last_response_s': round(wall_s - last, 2) if spans else None,
            'between_requests_s': round((last - first) - model_s, 2) if spans else None,
            'sci_execution_s': round(sci_s, 2), 'sci_worker_ready_s': min(ready) if ready else None,
            'sci_workers_started': len(ready), 'isolation_preflight_s': round(preflight_s, 2), 'arm_origin_unix_ms': origin}


def run_timing(run):
    rows = [json.loads(line) for line in Path(run, 'results.jsonl').read_text().splitlines() if line.strip()]
    arms = []
    for index, row in enumerate(rows):
        arm = str(Path(run) / f'{index:02}-{row["harness"]}')
        arms.append({'arm': Path(arm).name, 'harness': row['harness'], 'status': row['status'],
                     **arm_timing(arm, row['wall_time_ms'] / 1000)})
    return arms


def summarize(arms):
    out = {}
    for harness in ('aljure', 'prime'):
        a = [x for x in arms if x['harness'] == harness and x['requests']]
        if not a:
            continue
        total = sum(x['wall_s'] for x in a)
        part = lambda k: round(sum((x[k] or 0) for x in a), 1)
        out[harness] = {'arms': len(a), 'wall_s': round(total, 1), 'mean_wall_s': round(total / len(a), 1),
                        'model_s': part('model_s'), 'model_share': round(part('model_s') / total, 3),
                        'before_first_request_s': part('before_first_request_s'), 'between_requests_s': part('between_requests_s'),
                        'after_last_response_s': part('after_last_response_s'), 'sci_execution_s': part('sci_execution_s'),
                        'isolation_preflight_s': part('isolation_preflight_s'),
                        'median_before_first_request_s': round(st.median(x['before_first_request_s'] for x in a), 1),
                        'median_after_last_response_s': round(st.median(x['after_last_response_s'] for x in a), 1)}
    # Gaps between consecutive arms: runner work outside any arm's clock.
    ordered = [x for x in arms if x['arm_origin_unix_ms']]
    gaps = [(b['arm_origin_unix_ms'] - (a['arm_origin_unix_ms'] + a['wall_s'] * 1000)) / 1000 for a, b in zip(ordered, ordered[1:])]
    out['between_arms_s'] = round(sum(gaps), 1)
    out['plan_span_s'] = round((ordered[-1]['arm_origin_unix_ms'] - ordered[0]['arm_origin_unix_ms']) / 1000 + ordered[-1]['wall_s'], 1) if ordered else None
    return out


def main(out, *runs):
    result = {'model_calls': 0, 'runs': {}}
    for run in runs:
        arms = run_timing(run)
        result['runs'][Path(run).name] = {'summary': summarize(arms), 'arms': arms}
    Path(out).write_text(json.dumps(result, indent=1))
    for name, r in result['runs'].items():
        print(name)
        for h, s in r['summary'].items():
            print('  ', h, s)


if __name__ == '__main__':
    main(*sys.argv[1:])
