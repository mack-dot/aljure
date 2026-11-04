"""Verification ablation on development data (research/VERIFICATION_DEV_PROTOCOL.md).

Six arms per task, one frozen plan, seeded arm order per task, a seeded 20% of tasks repeated:
  A0  Aljure, text-answer-v2, no verification contract           (the Phase B harness)
  A1  A0 + structured_labels + uncertainty_audit                  (prompt text and SCI helpers)
  A2  Aljure with text answers off, no verification               (the text-channel ablation)
  A3  A1 + targeted_review                                        (the controller's one-time evidence gate)
  P0  native Prime, unchanged
  P1  native Prime + the same verification contract as a prompt   (resources/prime-verification.txt)
Pre-registered primary: A1 - A0 (context-weighted paired score difference). Secondary: A2 - A0 (text channel),
A3 - A1 (gate), P1 - P0 (the contract in Prime), and (A1 - A0) - (P1 - P0) (harness-specific part). Each with a
10,000-resample cluster bootstrap over contexts. GO rule for a later held-out run is in the protocol.

Reuses benchmark.headtohead for suites, arm execution, measures, provenance and statistics; benchmark.paired for
the arms themselves. No inference except `run` with the exact approved hash.
"""
import argparse
import json
import os
from pathlib import Path
import random
import shutil
import time

from . import headtohead as h
from . import paired
from .gateway_client import GatewayClient, ClaudeSubscriptionTransport
from .official import score_answer
from .oolong import account, digest, encoded, jsonl, money, require
from .prime import container as native

ROOT = paired.ROOT
VERSION = 'verification-dev-v1'
SEED = 2026110410
REPEAT_FRACTION = 0.2
MAX_SPEND_USD = 12
PROTOCOL = ROOT / 'research/VERIFICATION_DEV_PROTOCOL.md'
BASE_CONFIG = ROOT / 'config/verification-dev-sonnet.json'
SUITES = [
    {'name': 'verify8', 'suite': 'var/official/verify8-dev', 'rule': 'all', 'exposure': 'development: unused comparison and count questions of the 8K development windows'},
    {'name': 'verify32', 'suite': 'var/official/verify32-dev', 'rule': 'all', 'exposure': 'development: unused comparison and count questions of four 32K development windows'},
]
ARMS = {
    'A0': {'harness': 'aljure', 'aljure_contract': {'terminal_text_answer': 'text-answer-v2'}},
    'A1': {'harness': 'aljure', 'aljure_contract': {'terminal_text_answer': 'text-answer-v2', 'structured_labels': True, 'uncertainty_audit': True}},
    'A2': {'harness': 'aljure', 'aljure_contract': {}},
    'A3': {'harness': 'aljure', 'aljure_contract': {'terminal_text_answer': 'text-answer-v2', 'structured_labels': True, 'uncertainty_audit': True, 'targeted_review': True}},
    'P0': {'harness': 'prime'},
    'P1': {'harness': 'prime', 'prime_contract': {'verification_prompt': True}},
}
CONTRASTS = {'verification_in_aljure': ('A1', 'A0'), 'text_channel': ('A2', 'A0'), 'evidence_gate': ('A3', 'A1'),
             'verification_in_prime': ('P1', 'P0'), 'prime_vs_aljure_base': ('A0', 'P0'), 'prime_vs_aljure_verified': ('A1', 'P1')}
PRIMARY = 'verification_in_aljure'
COST_PRIOR = {'aljure': 0.030, 'prime': 0.060}
GO = {'min_primary_gain': 0.10, 'max_cost_ratio_to_prime': 0.50}


def configs_of(base_path=BASE_CONFIG):
    base = json.loads(Path(base_path).read_text())
    out = {}
    for label, arm in ARMS.items():
        config = json.loads(json.dumps(base))
        config['aljure_contract'] = arm.get('aljure_contract', base.get('aljure_contract', {}))
        if 'prime_contract' in arm:
            config['prime_contract'] = arm['prime_contract']
        paired.validate_config(config)
        out[label] = config
    return out


def sequence(suites, seed=SEED, repeat_fraction=REPEAT_FRACTION):
    """Every (suite, task) once, a seeded fraction twice; task order seeded across suites; within each item the six
    arms run back to back in a seeded order, balanced so that each arm is first equally often over the plan."""
    rng = random.Random(f'{seed}:sequence')
    items = [(name, task_id, 0) for name in suites for task_id in suites[name]['task_ids']]
    repeats = sorted(rng.sample(items, round(repeat_fraction * len(items))))
    items += [(name, task_id, 1) for name, task_id, _ in repeats]
    rng.shuffle(items)
    labels = list(ARMS)
    orders = []
    for i, _ in enumerate(items):
        order = labels[i % len(labels):] + labels[:i % len(labels)]  # rotate so first positions are balanced
        tail = order[1:]
        rng.shuffle(tail)
        orders.append([order[0]] + tail)
    out = []
    for (name, task_id, trial), order in zip(items, orders):
        for position, label in enumerate(order, 1):
            out.append({'index': len(out), 'suite': name, 'task_id': task_id, 'trial': trial, 'arm': label,
                        'harness': ARMS[label]['harness'], 'position': position})
    return out


def estimate(seq):
    expected = sum(COST_PRIOR[e['harness']] for e in seq)
    return {'arms': len(seq), 'expected_usd': round(expected, 2), 'low_usd': round(0.7 * expected, 2), 'high_usd': round(1.8 * expected, 2),
            'basis': 'per-arm priors from Phase B (Aljure $0.02-0.03, Prime $0.05-0.07); verification arms may cost more'}


def plan(out):
    configs = configs_of()
    for config in configs.values():
        require(h.spend_allowance_usd(config) >= h.MIN_ALLOWANCE_USD, 'per-arm cap below one reservation plus the minimum allowance')
    suites = h.load_suites(SUITES)
    seq = sequence(suites)
    base = configs['A0']
    require(money(base['usd_per_arm']) * len(seq) <= money(base['total_usd']), 'Per-arm allowances exceed the ceiling')
    require(money(base['usd_per_arm']) < money(MAX_SPEND_USD), 'The per-arm cap must fit under the maximum spend')
    value = {'version': VERSION, 'authorized': False, 'model_calls': 0, 'seed': SEED, 'repeat_fraction': REPEAT_FRACTION,
             'protocol_sha256': digest(PROTOCOL.read_bytes()), 'base_config_sha256': digest(BASE_CONFIG.read_bytes()),
             'arms': ARMS, 'configs': configs, 'contrasts': CONTRASTS, 'primary': PRIMARY, 'go_rule': GO,
             'suites': h.public(suites), 'sequence': seq, 'prime_commit': native.PIN,
             'capabilities': {label: paired.capabilities(config) for label, config in configs.items()},
             'source': paired.source_snapshot(), 'runtime_source': paired.runtime_snapshot(),
             'budget': {'per_arm_usd': base['usd_per_arm'], 'aggregate_usd': base['total_usd'], 'max_spend_usd': MAX_SPEND_USD,
                        'reservation_per_call_usd': round(h.reservation_usd(base), 5), 'spend_allowance_per_arm_usd': round(h.spend_allowance_usd(base), 5),
                        'stop_rule': 'refuse the next arm when known spend plus the per-arm cap would exceed max_spend_usd',
                        'calls_per_arm': base['calls_per_arm'], 'task_seconds': paired.task_limits(base)['task_seconds'], 'estimate': estimate(seq)},
             'analysis': {'delta': h.DELTA, 'resamples': h.RESAMPLES, 'success_threshold': h.SUCCESS,
                          'primary': 'A1 minus A0, context-weighted mean paired deadline-aware score difference, 10,000-resample cluster bootstrap',
                          'claim': 'Development ablation; mechanism effects on development data; no held-out or superiority claim.'}}
    require(not value['source']['dirty'], 'Freeze from a clean committed source checkout')
    value['plan_sha256'] = digest(encoded(value))
    with Path(out).open('xb') as stream:
        stream.write(encoded(value) + b'\n')
    return value


def read_plan(path):
    value = json.loads(Path(path).read_text())
    require(digest(encoded({k: v for k, v in value.items() if k != 'plan_sha256'})) == value['plan_sha256'], 'Plan hash mismatch')
    require(value['version'] == VERSION and value['protocol_sha256'] == digest(PROTOCOL.read_bytes()) and
            value['base_config_sha256'] == digest(BASE_CONFIG.read_bytes()), 'Protocol, config or version changed after freeze')
    require(value['configs'] == configs_of() and value['arms'] == ARMS and value['contrasts'] == CONTRASTS, 'Arms or configs changed')
    suites = h.load_suites(SUITES)
    require(value['suites'] == h.public(suites) and value['sequence'] == sequence(suites, value['seed'], value['repeat_fraction']), 'Suites or order changed')
    require(value['source']['sha256'] == paired.source_snapshot()['sha256'] and value['runtime_source'] == paired.runtime_snapshot() and
            value['capabilities'] == {l: paired.capabilities(c) for l, c in value['configs'].items()} and value['prime_commit'] == native.PIN,
            'Source or capability pins changed')
    return value, suites


def preflight(path):
    value, suites = read_plan(path)
    ready = paired.readiness(value, value['configs']['A0'])
    for label in ('A1', 'A2', 'A3', 'P0', 'P1'):
        try:
            paired.validate_config(value['configs'][label])
            if value['arms'][label]['harness'] == 'aljure' and value['configs'][label]['aljure_contract'].get('structured_labels'):
                require((ROOT / 'resources/sci-verify.edn').exists(), 'sci-verify.edn missing')
        except Exception as error:
            ready['blockers'].append(f'{label}: {error}')
    if shutil.disk_usage(ROOT).free < 10 * 2**30:
        ready['blockers'].append('Less than 10 GiB free disk')
    ready['suites'] = {name: s['suite_sha256'] for name, s in suites.items()}
    ready['ready'] = not ready['blockers']
    return ready


def run(path, out, approval, *, resume=False):
    value, suites = read_plan(path)
    require(approval == value['plan_sha256'], 'Explicit approval of this exact NEW plan required')
    ready = preflight(path)
    require(ready['ready'], 'Preflight refused: ' + '; '.join(ready['blockers']))
    out = Path(out).resolve()
    if resume:
        require(out.is_dir() and json.loads((out / 'plan.json').read_text()) == value, 'Resume needs the same frozen plan in the run directory')
        rows = [r for r in h._load_rows(out) if r['status'] != 'not-attempted']
        require(rows and all(r['index'] == i for i, r in enumerate(rows)), 'Only a trailing not-attempted block can be resumed')
        for stale in sorted(out.glob('[0-9][0-9][0-9]-*')):
            if int(stale.name[:3]) >= len(rows):
                shutil.rmtree(stale)
        (out / 'resumes.jsonl').open('ab').write(encoded({'time': time.time(), 'from_index': len(rows), 'preflight': ready}) + b'\n')
    else:
        out.mkdir(parents=True, exist_ok=False)
        h.write(out / 'plan.json', value)
        h.write(out / 'preflight.json', ready)
        h.write(out / 'authorization.json', {'approved_plan': approval, 'runner_pid': os.getpid(), 'time': time.time()})
        rows = []
    spent = sum((money(r['usage']['known_model_cost_usd']) + money(r['usage']['reserved_unknown_usd']) for r in rows), money(0))
    stop = None
    for entry in value['sequence'][len(rows):]:
        name, label, harness = entry['suite'], entry['arm'], entry['harness']
        config = value['configs'][label]
        suite = suites[name]
        task = suite['_tasks'][entry['task_id']]
        images = [config['execution_images']['prime'], config['execution_images']['sci']]
        pricing = {paired.RATE_KEYS[k]: v for k, v in config['rates'].items()}
        task_out = out / f"{entry['index']:03}-{name}-{label}"
        task_out.mkdir()
        row = {**entry, 'suite_sha256': suite['suite_sha256'], 'task_sha256': task['task_sha256'],
               'context_window_id': suite['contexts'][entry['task_id']], 'status': 'not-attempted', 'failure': stop,
               'fresh_session': True, 'harness_revision': value['source']['commit'] if harness == 'aljure' else native.PIN}
        gateway, begin = None, time.monotonic()
        try:
            require(stop is None, 'Not attempted: an earlier infrastructure failure stopped this run')
            require(spent + money(config['usd_per_arm']) <= money(MAX_SPEND_USD), 'BudgetCeiling: the next arm could take known spend past the maximum')
            require(shutil.disk_usage(ROOT).free >= 10 * 2**30, 'Disk floor refused')
            before = paired.docker_state(images)
            h.write(task_out / 'docker-before.json', before)
            if paired.docker_blockers(before):
                row['failure'], stop = 'DockerNotReady', 'DockerNotReady'
            else:
                data = paired.public_input(ROOT / suite['path'], task)
                h.write(task_out / 'public-input.json', data)
                gateway = GatewayClient(task_out / 'gateway', paired.gateway_config(config, harness),
                                        ClaudeSubscriptionTransport(authorized=True), evidence='LIVE MODEL RUN')
                execution = paired.run_arm(harness, data, task_out, config, gateway, ready)
                row['answer_provenance'] = h.answer_provenance(task_out, harness, config, execution)
                row['status'], row['failure'] = paired.arm_status(execution, (task_out / 'answer.txt').exists())
                after = paired.docker_state(images)
                h.write(task_out / 'docker-after.json', after)
                if after['session'] != before['session']:
                    row['status'], row['failure'], stop = 'error', 'DockerRestartedDuringArm', 'DockerRestartedDuringArm'
        except Exception as error:
            reason = 'BudgetCeiling' if str(error).startswith('BudgetCeiling') else type(error).__name__
            row['failure'] = stop = reason if gateway else (stop or reason)
            row['status'] = 'error' if gateway else 'not-attempted'
        finally:
            if gateway:
                try:
                    gateway.close()
                except Exception:
                    row['failure'] = stop = 'GatewayCleanupFailure'
                    row['status'] = 'error'
        usage_path = task_out / 'gateway/usage.jsonl'
        require(gateway is None or usage_path.exists(), 'Missing usage: stop and recover the ledger before reporting')
        receipts = list(jsonl(usage_path)) if usage_path.exists() else []
        if any(r.get('status') == 'unknown' for r in receipts):
            row['status'], row['failure'], stop = 'error', 'ProviderOutcomeUnknown', 'ProviderOutcomeUnknown'
        if gateway and paired.worker_isolation_refused(task_out):
            row['status'], row['failure'], stop = 'error', 'IsolationPreflightFailed', 'IsolationPreflightFailed'
        usage = account(receipts, pricing)
        spent += money(usage['known_model_cost_usd']) + money(usage['reserved_unknown_usd'])
        if not usage['accounting_complete']:
            stop = 'IncompleteAccounting'
        answer = (task_out / 'answer.txt').read_text(encoding='utf-8') if (task_out / 'answer.txt').exists() else None
        scored = (score_answer(suite['suite'], suite['_answers'][entry['task_id']], answer)
                  if row['status'] == 'completed' else {'score': 0, 'parse_confidence': 'not-completed', 'attempted_parse': ''})
        cleanup = json.loads((task_out / 'gateway/cleanup.json').read_text()) if (task_out / 'gateway/cleanup.json').exists() else {}
        row.update(score=float(scored['score']), parse_confidence=scored['parse_confidence'], attempted_parse=scored['attempted_parse'],
                   answer_sha256=digest(answer.encode()) if answer is not None else None, wall_time_ms=(time.monotonic() - begin) * 1000,
                   usage=usage, measures=h.measure_arm(task_out, harness) if gateway else {}, cleanup_ok=cleanup.get('ok'),
                   budget_usd=config['usd_per_arm'], pricing_usd_per_m=pricing)
        h.write(task_out / 'result.json', row)
        rows.append(row)
        paired.write_jsonl(out / 'results.jsonl', rows)
    h.write(out / 'results.json', rows)
    report = summarize(value, rows)
    h.write(out / 'report.json', report)
    return report


def contrast(rows, contexts, treated, control):
    """paired_analysis with the treated arm playing 'aljure' and the control arm 'prime' (difference = treated - control)."""
    relabelled = [{**r, 'harness': 'aljure' if r['arm'] == treated else 'prime'} for r in rows if r['arm'] in (treated, control)]
    return h.paired_analysis(relabelled, contexts) if relabelled else None


def summarize(value, rows):
    rows = list(rows)
    contexts = {}
    for name, suite in value['suites'].items():
        contexts.update({f"{name}:{t}": f"{name}:{c}" for t, c in suite['contexts'].items()})
    pooled = [{**r, 'task_id': f"{r['suite']}:{r['task_id']}"} for r in rows]
    report = {'version': VERSION, 'plan_sha256': value['plan_sha256'], 'arms_planned': len(value['sequence']), 'arms_recorded': len(rows),
              'complete': len(rows) == len(value['sequence']) and all(r['status'] != 'not-attempted' for r in rows),
              'stopped_by': next((r['failure'] for r in rows if r['status'] == 'not-attempted'), None),
              'claim': value['analysis']['claim'],
              'per_arm': {label: h.harness_stats([r for r in rows if r['arm'] == label]) for label in value['arms']},
              'contrasts': {name: contrast(pooled, contexts, t, c) for name, (t, c) in value['contrasts'].items()},
              'cost_total_usd': round(sum(float(r['usage']['known_model_cost_usd'] or 0) for r in rows), 6),
              'accounting_complete': all(r['usage']['accounting_complete'] for r in rows)}
    # Harness-specific part of the verification effect: (A1 - A0) - (P1 - P0), bootstrapped over contexts.
    by = {}
    for r in pooled:
        by.setdefault((r['task_id'], r['arm']), []).append(r['score'])
    tasks = sorted({r['task_id'] for r in pooled})
    def mean(xs):
        return sum(xs) / len(xs) if xs else None
    dd = {}
    for t in tasks:
        a0, a1, p0, p1 = (mean(by.get((t, l), [])) for l in ('A0', 'A1', 'P0', 'P1'))
        if None not in (a0, a1, p0, p1):
            dd.setdefault(contexts[t], []).append((a1 - a0) - (p1 - p0))
    per_context = {c: sum(v) / len(v) for c, v in dd.items()}
    if per_context:
        interval = h.cluster_bootstrap(per_context) if len(per_context) >= h.MIN_CONTEXTS else None
        report['harness_specific_verification_effect'] = {'estimate': sum(per_context.values()) / len(per_context), 'contexts': len(per_context),
                                                           'cluster_bootstrap': interval, 'decision': h.decision(sum(per_context.values()) / len(per_context), interval)}
    primary = report['contrasts'].get(value['primary'])
    if primary and report['per_arm']['A1']['arms'] and report['per_arm']['P1']['arms']:
        a1c, p1c = report['per_arm']['A1']['cost_per_task_usd'], report['per_arm']['P1']['cost_per_task_usd']
        ratio = (a1c / p1c) if (a1c is not None and p1c) else None
        report['go_rule'] = {**value['go_rule'], 'primary_gain': primary['context_weighted_mean_difference'], 'aljure_cost_ratio_to_prime': ratio,
                             'go': bool(primary['context_weighted_mean_difference'] is not None and
                                        primary['context_weighted_mean_difference'] >= value['go_rule']['min_primary_gain'] and
                                        ratio is not None and ratio <= value['go_rule']['max_cost_ratio_to_prime'])}
    arm_points = {label: (s['deadline_aware_mean_score'], s['cost_per_task_usd'], s['latency_s']['agent_p50'])
                  for label, s in report['per_arm'].items() if s['arms']}
    report['pareto'] = h.pareto({f'dev:{k}': v for k, v in arm_points.items()})
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', choices=['plan', 'preflight', 'run', 'report', 'estimate'])
    parser.add_argument('--plan')
    parser.add_argument('--out')
    parser.add_argument('--suite', help='accepted for the host launcher; the plan binds every suite itself')
    parser.add_argument('--authorize-subscription-plan')
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args(argv)
    if args.command == 'plan':
        value = plan(args.out)
        print(json.dumps({'plan_sha256': value['plan_sha256'], 'arms': len(value['sequence']), 'estimate': value['budget']['estimate']}, indent=2))
    elif args.command == 'estimate':
        print(json.dumps(estimate(sequence(h.load_suites(SUITES))), indent=2))
    elif args.command == 'preflight':
        print(json.dumps(preflight(args.plan), indent=2))
    elif args.command == 'run':
        report = run(args.plan, args.out, args.authorize_subscription_plan, resume=args.resume)
        print(json.dumps({k: report[k] for k in ('complete', 'stopped_by', 'cost_total_usd', 'arms_recorded')}, indent=2))
    elif args.command == 'report':
        out = Path(args.out)
        value = json.loads((out / 'plan.json').read_text())
        report = summarize(value, h._load_rows(out))
        h.write(out / 'report.json', report)
        print(json.dumps(report, indent=2)[:4000])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
