"""Development learning evidence from recorded runs; never calls a provider."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path

from .oolong import account, digest, encoded, jsonl, require
from .paired import trajectory_report, trajectory_ledger, verify_library_chain


def quantile(values, p):
    values = sorted(values)
    return values[max(0, math.ceil(p * len(values)) - 1)] if values else None


def lifecycle_pass(*, complete, live, accounting_complete, safety_complete, pre_restart_hashes, post_restart_calls):
    """A scripted fixture, incomplete run, or preload alone cannot establish autonomy."""
    return bool(complete and live and accounting_complete and safety_complete and pre_restart_hashes and
                any(call['code_hash'] in pre_restart_hashes and call['returns'] > 0
                    for call in post_restart_calls))


def tool_reliability(events):
    calls = sum(e['type'] == 'tool-call' for e in events)
    results = [e['payload'] for e in events if e['type'] == 'tool-result']
    return {'calls': calls, 'results': len(results),
            'errors': sum(r.get('status') != 'ok' for r in results),
            'missing': max(0, calls - len(results))}


def task_safety(task, row):
    """Missing cleanup or Docker evidence is not evidence of a safe live run."""
    try:
        cleanup = json.loads((task / 'gateway/cleanup.json').read_text())
        before = json.loads((task / 'docker-before.json').read_text())
        after = json.loads((task / 'docker-after.json').read_text())
        return bool(cleanup.get('ok') is True and before.get('session') and
                    before['session'] == after.get('session') and row.get('failure') in (None, 'ProposalTurnDeadline'))
    except (OSError, ValueError):
        return False


def report(plan_path, suite, runs):
    plan = json.loads(Path(plan_path).read_text())
    require(digest(encoded({k: v for k, v in plan.items() if k != 'plan_sha256'})) == plan['plan_sha256'],
            'Plan hash mismatch')
    runs = Path(runs)
    base = trajectory_report(runs, suite)
    require(base['suite_sha256'] == plan['suite_sha256'], 'Wrong suite')
    summaries = {}
    for entry in plan['trajectories']:
        name = entry['id']
        directory = runs / name
        trajectory = base['trajectories'].get(name, {'cases': [], 'complete': False})
        rows = list(jsonl(directory / 'results.jsonl')) if (directory / 'results.jsonl').exists() else []
        require([r['task_id'] for r in rows] == entry['order'][:len(rows)], 'Unexpected recorded task order')
        require(all(r['source_sha256'] == plan['source']['sha256'] for r in rows), 'Run source differs from plan')
        ledger = trajectory_ledger(directory)
        if ledger:
            require(ledger[0]['plan_sha256'] == plan['plan_sha256'], 'Trajectory has another plan')
            verify_library_chain(directory / 'library', ledger, entry['initial_library_sha256'])
        cold = plan['config']['trajectory']['cold_restart_after']
        committed = {r.get('receipt_sha256') for r in ledger if r['type'] == 'promotion' and r['status'] == 'committed'}
        learned, validation_seconds = {}, 0.0
        for path in (directory / 'library/receipts').glob('*.json'):
            receipt = json.loads(path.read_text())
            validation_seconds += (receipt.get('validation-ms') or 0) / 1000
            if path.stem in committed and receipt.get('decision') == 'approved' and receipt.get('arm') == 'E':
                code_hash = receipt['candidate']['code-hash']
                learned[code_hash] = min(learned.get(code_hash, receipt['position']), receipt['position'])
        usage, live, operations, failed, tool_calls, missing, post_calls, decisions = [], bool(rows), 0, 0, 0, 0, [], Counter()
        known, unknown, accounting_complete, requests = 0.0, 0.0, True, 0
        safety_complete = not any(r.get('status') in ('stage-failed', 'crashed') for r in ledger)
        promotion_seconds = sum(c.get('validation_seconds') or 0 for c in trajectory['cases'])
        for row in rows:
            task = directory / f"{row['position']:02}-aljure"
            gateway_path = task / 'gateway/report.json'
            gateway = json.loads(gateway_path.read_text()) if gateway_path.is_file() else {}
            live = live and gateway.get('evidence') == 'LIVE MODEL RUN'
            safety_complete = safety_complete and task_safety(task, row)
            usage = list(jsonl(directory / row['usage_path']))
            charged = account(usage, row['pricing_usd_per_m'])
            known += charged['known_model_cost_usd']
            unknown += charged['reserved_unknown_usd']
            requests += charged['calls']
            accounting_complete = accounting_complete and charged['accounting_complete']
            path = task / 'agent/events.jsonl'
            events = list(jsonl(path)) if path.is_file() else []
            reliability = tool_reliability(events)
            tool_calls += reliability['calls']
            operations += reliability['results']
            failed += reliability['errors']
            missing += reliability['missing']
            for event in events:
                payload = event['payload']
                if event['type'] == 'artifact-proposal':
                    decisions[payload['decision']] += 1
                if event['type'] == 'artifact-invocations' and payload.get('session') == 'root' and row['position'] > cold:
                    for invocation in payload.get('invocations', []):
                        post_calls.append({'position': row['position'], 'task_id': row['task_id'],
                                           'code_hash': invocation['code-hash'],
                                           'calls': invocation['calls'], 'returns': invocation['returns']})
        success = sum(c['verified'] for c in trajectory['cases'])
        complete = len(rows) == len(entry['order']) and trajectory['complete']
        prior = {h for h, position in learned.items() if position <= cold}
        restarted = any(r['type'] == 'cold-restart' and r.get('after') == cold for r in ledger)
        passed = lifecycle_pass(complete=complete and restarted, live=live, accounting_complete=accounting_complete,
                                safety_complete=safety_complete,
                                pre_restart_hashes=prior, post_restart_calls=post_calls)
        summaries[name] = {
            'complete': complete, 'live_model_evidence': live, 'lifecycle_pass': passed,
            'cold_restart_recorded': restarted,
            'safety_evidence_complete': safety_complete,
            'planned_tasks': len(entry['order']), 'attempted_tasks': len(rows), 'successful_tasks': success,
            'accuracy_attempted': success / len(rows) if rows else None,
            'accuracy_full_trajectory': success / len(entry['order']) if complete else None,
            'mean_official_score': sum(c['score'] for c in trajectory['cases']) / len(rows) if rows else None,
            'known_model_cost_usd': known, 'unknown_reserved_usd': unknown, 'accounting_complete': accounting_complete,
            'cost_per_success_usd': known / success if success and accounting_complete else None,
            'zero_success_cost_ratio': 'infinite' if rows and not success else None,
            'acquisition_cost_usd': sum(c.get('acquisition_usd') or 0 for c in trajectory['cases']),
            'validation_seconds': validation_seconds, 'promotion_stage_seconds': promotion_seconds,
            'model_requests': requests,
            'latency_p50_seconds': quantile([r['wall_time_ms'] / 1000 for r in rows], .5),
            'latency_p95_seconds': quantile([r['wall_time_ms'] / 1000 for r in rows], .95),
            'tool_calls': tool_calls, 'tool_results': operations, 'tool_errors': failed,
            'tool_missing_results': missing,
            'tool_success_rate': (operations - failed) / tool_calls if tool_calls else None,
            'proposal_decisions': dict(decisions), 'promoted_code_hashes': learned,
            'pre_restart_code_hashes': sorted(prior), 'post_restart_invocations': post_calls,
            'post_restart_tasks_reusing_earlier_skill': len({c['task_id'] for c in post_calls
                                                           if c['code_hash'] in prior and c['returns'] > 0})}
    sufficient = len(summaries) == 3 and all(s['complete'] for s in summaries.values())
    return {'schema': 'learning-development-report-v1', 'plan_sha256': plan['plan_sha256'],
            'model_calls_in_analysis': 0, 'heldout_access': False, 'trajectories': summaries,
            'development_gate': ('NOT_APPLICABLE' if plan['config']['trajectory']['arms'] != ['ES'] else
                                 'INCOMPLETE' if not sufficient else
                                 'GO' if sum(s['lifecycle_pass'] for s in summaries.values()) >= 2 else 'NO-GO'),
            'claim': 'Development mechanism evidence only; no held-out or comparative superiority claim.',
            'cost_basis': 'All task and acquisition inference at frozen rates. Validation seconds are separate; local USD cost and subscription invoice are unknown.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('plan', 'suite', 'runs', 'out'):
        parser.add_argument('--' + key, type=Path, required=True)
    args = parser.parse_args()
    value = report(args.plan, args.suite, args.runs)
    with args.out.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps(value, indent=2))
