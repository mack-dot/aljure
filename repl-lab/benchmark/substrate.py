"""Q-SUBSTRATE Experiment A driver (research/Q_SUBSTRATE_PROTOCOL.md): the same controller, model,
settings, tasks, budgets, tools and scorer over two execution backends, Clojure/SCI and Python.
Development split only. prepare, plan, preflight and the fixture never call a provider. run
requires the exact plan hash. No resume, retry, acquisition, Prime or held-out path exists here."""
import argparse
import json
import os
from pathlib import Path
import random
import shutil
import time

from . import paired
from .gateway_client import GatewayClient, ClaudeSubscriptionTransport
from .oolong import account, digest, encoded, jsonl, money, require
from .reuse_causal import first_request, prompt_measure
from .reuse_interface import files, write
from . import substrate_tasks as tasks

ROOT = paired.ROOT
VERSION = 'q-substrate-development-v1'
SEED = 'q-substrate-dev-2026110302'
HELDOUT_SEED_RULE = 'q-substrate-heldout-<authorization-id>: generated only under a separate explicit authorization; never here'
PROTOCOL = ROOT / 'research/Q_SUBSTRATE_PROTOCOL.md'
PROOF = ROOT / 'var/substrate-proof.json'
BASE_CONFIG = ROOT / 'config/learning-minimal-sonnet.json'
ARMS = ['clojure', 'python']
CASES_PER_FAMILY = 2
BUDGET = {'aggregate_usd': 12, 'per_task_usd': 5, 'reserve_before_next_task_usd': 5, 'max_calls': 480,
          'max_tasks': 2 * CASES_PER_FAMILY * len(tasks.FAMILIES), 'cost_basis': 'API-rate-equivalent subscription usage'}
ERROR_CLASSES = [('range', 'out of bounds for length'), ('reader', 'not readable'), ('unresolved', 'Could not resolve symbol'),
                 ('denied', 'is not allowed!'), ('worker-stopped', 'The worker stopped'), ('syntax', 'SyntaxError'),
                 ('name', 'NameError'), ('type', 'TypeError'), ('import', 'ImportError'), ('value', 'ValueError')]


def generate():
    return tasks.generate(SEED, CASES_PER_FAMILY)


def configs_from_base():
    base = json.loads(BASE_CONFIG.read_text())
    for key in ('trajectory', 'campaign_version', 'authorization_scope', 'case_reuse'):
        base.pop(key, None)
    base.update(total_usd=BUDGET['aggregate_usd'], usd_per_arm=BUDGET['per_task_usd'], aljure_contract={},
                aljure_only={'disclosure': 'Q-SUBSTRATE compares two Aljure execution backends; no Prime comparison is made.'})
    python = json.loads(json.dumps(base))
    python['execution_language'] = 'python'
    python_env = (ROOT / 'var/python-worker.env').read_text().strip().split('=', 1)[1] if (ROOT / 'var/python-worker.env').exists() else None
    require(python_env, 'Pin the Python worker image first: make python-worker-setup')
    python['execution_images'] = {**base['execution_images'], 'python': python_env}
    return {'clojure': base, 'python': python}


def prepare(out):
    out = Path(out).resolve()
    require(out.is_relative_to(ROOT), 'Suite must be under repl-lab')
    out.mkdir(parents=True, exist_ok=False)
    cases = generate()
    for case in cases:
        write(out / 'public' / (case['task_id'] + '.json'),
              {'task': {'task_id': case['task_id'], 'question': case['question']}, 'context': case['context']})
    write(out / 'controller/cases.json', [{k: v for k, v in case.items() if k not in ('context', 'question')} for case in cases])
    configs = configs_from_base()
    for arm in ARMS:
        write(out / (arm + '.json'), configs[arm])
    manifest = {'version': VERSION, 'origin': 'synthetic development tasks; no official dataset; no held-out rows', 'seed': SEED,
                'heldout_seed_rule': HELDOUT_SEED_RULE, 'families': tasks.FAMILIES, 'cases_per_family': CASES_PER_FAMILY,
                'files': files(out)}
    manifest['suite_sha256'] = digest(encoded(manifest))
    write(out / 'manifest.json', manifest)
    return manifest


def verify_suite(suite):
    suite = Path(suite)
    manifest = json.loads((suite / 'manifest.json').read_text())
    require(manifest['version'] == VERSION and manifest['seed'] == SEED, 'Wrong suite version or seed')
    require(digest(encoded({k: v for k, v in manifest.items() if k != 'suite_sha256'})) == manifest['suite_sha256'], 'Suite hash mismatch')
    require(all((suite / p).is_file() and not (suite / p).is_symlink() and digest((suite / p).read_bytes()) == h
                for p, h in manifest['files'].items()), 'Suite bytes changed')
    generated = generate()
    cases = json.loads((suite / 'controller/cases.json').read_text())
    require(cases == [{k: v for k, v in c.items() if k not in ('context', 'question')} for c in generated], 'Cases differ from the fixed generator')
    for c in generated:
        public = json.loads((suite / 'public' / (c['task_id'] + '.json')).read_text())
        require(public == {'task': {'task_id': c['task_id'], 'question': c['question']}, 'context': c['context']}, 'Public inputs changed')
    return manifest, cases


def configs_of(suite):
    return {arm: json.loads((Path(suite) / (arm + '.json')).read_text()) for arm in ARMS}


def sequence(cases):
    """Every case in both arms; the first arm alternates by case so order effects are balanced."""
    out = []
    for i, case in enumerate(cases):
        for arm in (ARMS if i % 2 == 0 else ARMS[::-1]):
            out.append({'task_id': case['task_id'], 'family': case['family'], 'arm': arm})
    return out


def plan(suite, out):
    manifest, cases = verify_suite(suite)
    configs = configs_of(suite)
    for config in configs.values():
        paired.validate_config(config)
    expected = json.loads(json.dumps(configs['clojure']))
    expected['execution_language'] = 'python'
    expected['execution_images'] = {**expected['execution_images'], 'python': configs['python']['execution_images']['python']}
    require(expected == configs['python'] and 'execution_language' not in configs['clojure'],
            'Only the execution language and its worker image may differ between arms')
    require(configs['clojure']['aljure_sci'] == {'surface': 'assisted', 'results': 'bounded', 'worker_output_bytes': 65536}
            and configs['clojure']['aljure_contract'] == {}, 'Both arms use the assisted bounded surface and the default contract')
    value = {'version': VERSION, 'authorized': False, 'model_calls': 0, 'suite_sha256': manifest['suite_sha256'],
             'protocol_sha256': digest(PROTOCOL.read_bytes()), 'source': paired.source_snapshot(),
             'runtime_source': paired.runtime_snapshot(), 'configs': configs, 'arms': ARMS, 'sequence': sequence(cases),
             'budget': BUDGET, 'criteria_sha256': digest(encoded(CRITERIA))}
    require(not value['source']['dirty'], 'Freeze from a clean committed source checkout')
    value['plan_sha256'] = digest(encoded(value))
    write(Path(out), value)
    return value


def read_plan(path, suite):
    value = json.loads(Path(path).read_text())
    require(digest(encoded({k: v for k, v in value.items() if k != 'plan_sha256'})) == value['plan_sha256'], 'Plan hash mismatch')
    manifest, cases = verify_suite(suite)
    require(value['version'] == VERSION and manifest['suite_sha256'] == value['suite_sha256'], 'Wrong suite/version')
    require(value['source']['sha256'] == paired.source_snapshot()['sha256'] and value['runtime_source'] == paired.runtime_snapshot(), 'Frozen source changed')
    require(value['sequence'] == sequence(cases) and value['arms'] == ARMS and value['budget'] == BUDGET and
            value['protocol_sha256'] == digest(PROTOCOL.read_bytes()) and value['criteria_sha256'] == digest(encoded(CRITERIA)),
            'Protocol, criteria or order changed')
    require(value['configs'] == configs_of(suite), 'Configurations changed')
    return value, cases


def preflight(path, suite):
    value, _ = read_plan(path, suite)
    ready = paired.readiness(value, value['configs']['python'], native_prime=False)
    try:
        paired.validate_config(value['configs']['clojure'])
        proof = json.loads(PROOF.read_text())
        require(proof['evidence'] == 'FIXTURE' and proof['status'] == 'PASSED' and all(proof['checks'].values()), 'Substrate fixture did not pass')
        require(proof['runtime_source'] == value['runtime_source'] and proof['suite_sha256'] == value['suite_sha256'] and
                proof['images'] == {'sci': value['configs']['clojure']['execution_images']['sci'],
                                    'python': value['configs']['python']['execution_images']['python']}, 'Substrate fixture proof is stale')
        ready['checks']['substrate_fixture'] = digest(PROOF.read_bytes())
    except (OSError, ValueError, KeyError) as error:
        ready['blockers'].append('Substrate fixture: ' + str(error))
    if shutil.disk_usage(ROOT).free < 6 * 2**30:
        ready['blockers'].append('Less than 6 GiB free disk')
    ready['ready'] = not ready['blockers']
    return ready


def error_class(message):
    return next((name for name, needle in ERROR_CLASSES if needle in (message or '')), 'other')


def measure(events):
    """Per-task execution measures from controller events (the ledger, not the model's words)."""
    calls = [e['payload'] for e in events if e['type'] == 'tool-call']
    results = [e['payload'] for e in events if e['type'] == 'tool-result']
    evals = [r for r in results if r.get('op') in ('repl/eval', 'done/eval', 'program/run')]
    sources = [c['command'].get('source', '') for c in calls if c['command'].get('op') in ('repl/eval', 'done/eval')]
    errors = [r for r in evals if r.get('status') != 'ok']
    first = evals[0] if evals else None
    return {'tool_calls': len(calls), 'evaluations': len(evals), 'evaluation_errors': len(errors),
            'first_evaluation_valid': None if first is None else first.get('status') == 'ok',
            'execution_success_rate': None if not evals else (len(evals) - len(errors)) / len(evals),
            'worker_restarts': sum('The worker stopped' in (r.get('error') or '') for r in errors),
            'error_classes': sorted(error_class(r.get('error')) for r in errors),
            'evaluation_ms': [r.get('elapsed-ms') for r in evals],
            'cold_evaluation_ms': first.get('elapsed-ms') if first else None,
            'warm_evaluation_ms': [r.get('elapsed-ms') for r in evals[1:]],
            'source_chars': sum(len(s) for s in sources), 'source_calls': len(sources),
            'done_path': next((c['command']['op'] for c in reversed(calls) if c['command'].get('op') in ('done', 'done/eval')), None),
            'corrections': sum(e['type'] == 'command-rejected' for e in events),
            'children': sum(e['type'] == 'child-result-consumed' for e in events)}


def run(path, suite, out, approval):
    value, cases = read_plan(path, suite)
    require(approval == value['plan_sha256'], 'Explicit approval of this exact NEW plan required')
    ready = preflight(path, suite)
    require(ready['ready'], 'Preflight refused: ' + '; '.join(ready['blockers']))
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    write(out / 'plan.json', value)
    write(out / 'preflight.json', ready)
    write(out / 'authorization.json', {'approved_plan': approval, 'runner_pid': os.getpid(), 'time': time.time()})
    rows, spent, stop, all_receipts = [], money(0), None, []
    by_id = {c['task_id']: c for c in cases}
    images = [value['configs']['clojure']['execution_images']['sci'], value['configs']['python']['execution_images']['python']]
    for index, entry in enumerate(value['sequence']):
        task_out = out / f'{index + 1:02}-{entry["arm"]}'
        task_out.mkdir()
        config = value['configs'][entry['arm']]
        case = by_id[entry['task_id']]
        row = {**entry, 'status': 'not-attempted', 'failure': stop, 'fresh_process': True}
        gateway, begin = None, time.monotonic()
        try:
            require(stop is None, 'Campaign already stopped')
            require(spent + money(config['usd_per_arm']) <= money(value['budget']['aggregate_usd']), 'Aggregate budget reserve refused')
            require(shutil.disk_usage(ROOT).free >= 6 * 2**30, 'Disk floor refused')
            verify_suite(suite)
            before = paired.docker_state(images)
            write(task_out / 'docker-before.json', before)
            require(not paired.docker_blockers(before), 'Docker readiness refused')
            data = json.loads((Path(suite) / 'public' / (entry['task_id'] + '.json')).read_text())
            write(task_out / 'public-input.json', data)
            gateway = GatewayClient(task_out / 'gateway', paired.gateway_config(config, 'aljure'),
                                    ClaudeSubscriptionTransport(authorized=True), evidence='LIVE MODEL RUN')
            execution = paired.run_arm('aljure', data, task_out, config, gateway, ready)
            row['status'], row['failure'] = paired.arm_status(execution, (task_out / 'answer.txt').exists())
            after = paired.docker_state(images)
            write(task_out / 'docker-after.json', after)
            require(before['session'] == after['session'] and not paired.docker_blockers(after), 'Docker changed during task')
            require(not paired.worker_isolation_refused(task_out), 'Isolation refused')
            if row['failure']:
                stop = row['failure']
        except Exception as error:
            row['failure'] = stop = type(error).__name__
            row['status'] = 'error' if gateway else 'not-attempted'
        finally:
            if gateway:
                try:
                    gateway.close()
                except Exception as error:
                    row['failure'] = stop = 'Cleanup' + type(error).__name__
                    row['status'] = 'error'
        usage_path = task_out / 'gateway/usage.jsonl'
        receipts = list(jsonl(usage_path)) if usage_path.exists() else []
        require(gateway is None or usage_path.exists(), 'Missing usage: stop and recover ledger before reporting')
        usage = account(receipts, {paired.RATE_KEYS[k]: v for k, v in config['rates'].items()})
        all_receipts.extend(receipts)
        account(all_receipts, {paired.RATE_KEYS[k]: v for k, v in config['rates'].items()})
        spent += money(usage['known_model_cost_usd']) + money(usage['reserved_unknown_usd'])
        if not usage['accounting_complete']:
            stop = 'IncompleteAccounting'
        answer = (task_out / 'answer.txt').read_text() if (task_out / 'answer.txt').exists() else None
        events = list(jsonl(task_out / 'agent/events.jsonl')) if (task_out / 'agent/events.jsonl').exists() else []
        cleanup = json.loads((task_out / 'gateway/cleanup.json').read_text()) if (task_out / 'gateway/cleanup.json').exists() else {}
        safe = row['status'] == 'completed' and cleanup.get('ok') is True and row['failure'] is None
        if gateway and not safe:
            stop = stop or 'SafetyEvidenceIncomplete'
        row.update(safety_complete=safe, correct=row['status'] == 'completed' and bool(tasks.score(case, answer)['score']),
                   answer=(answer or '')[:300], seconds=time.monotonic() - begin, usage=usage,
                   prompt=prompt_measure(task_out), measures=measure(events))
        row['files'] = files(task_out)
        write(task_out / 'result.json', row)
        rows.append(row)
    write(out / 'results.json', rows)
    report = summarize(rows)
    write(out / 'report.json', report)
    return report


CRITERIA = {
    'version': 'q-substrate-criteria-v1',
    'primary_endpoint': 'paired difference in independently scored correctness, Clojure minus Python, over the 20 development cases',
    'interval': '95% percentile bootstrap of the mean paired difference, 4000 resamples, seed 2026110302',
    'success_clojure': 'interval excludes 0 above, and Clojure worker restarts <= Python worker restarts',
    'success_python': 'interval excludes 0 below, and Python worker restarts <= Clojure worker restarts',
    'inconclusive': 'interval includes 0 (20 paired cases cannot establish equivalence)',
    'equivalence': 'not claimable from this development run; requires a held-out run of at least 60 paired cases with the interval inside [-0.1, 0.1]',
    'failure': 'any task not completed with complete safety evidence and complete accounting (INCOMPLETE)',
    'secondary': ['first-attempt program validity', 'execution success rate', 'requests and tokens', 'known cost', 'cold and warm evaluation latency',
                  'end-to-end seconds', 'worker restarts', 'source characters', 'error classes', 'done path'],
    'not_measured': ['CPU-seconds and peak memory of the worker (no per-call instrumentation in the supervisor)',
                     'structural patch correctness through artifact tools (both arms use repl_eval only)'],
    'no_prompt_changes_after_results': True}


def bootstrap_interval(differences, resamples=4000, seed=2026110302):
    if not differences:
        return None
    rng = random.Random(seed)
    means = sorted(sum(rng.choice(differences) for _ in differences) / len(differences) for _ in range(resamples))
    return [means[int(.025 * resamples)], means[int(.975 * resamples) - 1]]


def summarize(rows):
    result = {'claim': 'Development mechanism comparison of two execution backends; no held-out, no Prime, no superiority claim.',
              'criteria': CRITERIA, 'arms': {}, 'families': {}}
    def dist(values):
        values = sorted(v for v in values if v is not None)
        return None if not values else {'n': len(values), 'min': values[0], 'median': values[len(values) // 2], 'max': values[-1],
                                        'mean': sum(values) / len(values)}
    for arm in ARMS:
        selected = [r for r in rows if r['arm'] == arm]
        m = [r.get('measures', {}) for r in selected]
        cost = sum(money(r['usage']['known_model_cost_usd']) for r in selected)
        result['arms'][arm] = {
            'tasks': len(selected), 'completed': sum(r['status'] == 'completed' for r in selected),
            'correct': sum(r['correct'] for r in selected), 'known_cost_usd': float(cost),
            'requests': sum(r['usage']['calls'] for r in selected),
            'first_evaluation_valid': sum(bool(x.get('first_evaluation_valid')) for x in m),
            'execution_success_rate': dist([x.get('execution_success_rate') for x in m]),
            'worker_restarts': sum(x.get('worker_restarts', 0) for x in m),
            'evaluation_errors': sum(x.get('evaluation_errors', 0) for x in m),
            'error_classes': sorted(c for x in m for c in x.get('error_classes', [])),
            'cold_evaluation_ms': dist([x.get('cold_evaluation_ms') for x in m]),
            'warm_evaluation_ms': dist([v for x in m for v in x.get('warm_evaluation_ms', [])]),
            'seconds': dist([r['seconds'] for r in selected]),
            'source_chars': dist([x.get('source_chars') for x in m]),
            'first_request_tokens': dist([r['prompt'].get('first_request_tokens') for r in selected if r.get('prompt')]),
            'done_paths': sorted(str(x.get('done_path')) for x in m)}
    by = {}
    for r in rows:
        by.setdefault(r['task_id'], {})[r['arm']] = r
    differences = []
    for task_id, arms in by.items():
        if all(a in arms for a in ARMS):
            d = int(arms['clojure']['correct']) - int(arms['python']['correct'])
            differences.append(d)
            fam = result['families'].setdefault(arms['clojure']['family'], {'cases': 0, 'clojure_correct': 0, 'python_correct': 0})
            fam['cases'] += 1
            fam['clojure_correct'] += int(arms['clojure']['correct'])
            fam['python_correct'] += int(arms['python']['correct'])
    interval = bootstrap_interval(differences)
    complete = len(rows) == BUDGET['max_tasks'] and all(r['status'] == 'completed' and r.get('safety_complete') and r['usage']['accounting_complete'] for r in rows)
    restarts = {arm: result['arms'][arm]['worker_restarts'] for arm in ARMS}
    if not complete:
        gate, outcome = 'INCOMPLETE', 'failure'
    elif interval[0] > 0 and restarts['clojure'] <= restarts['python']:
        gate, outcome = 'COMPLETE-PENDING-REVIEW', 'success-clojure'
    elif interval[1] < 0 and restarts['python'] <= restarts['clojure']:
        gate, outcome = 'COMPLETE-PENDING-REVIEW', 'success-python'
    else:
        gate, outcome = 'COMPLETE-PENDING-REVIEW', 'inconclusive'
    result.update(paired_cases=len(differences), mean_paired_difference=(sum(differences) / len(differences)) if differences else None,
                  paired_difference_interval=interval, differences=differences, development_gate=gate, outcome=outcome,
                  note='Outcomes are the frozen mapping in CRITERIA. Review every trace for the error classes and delivery path before accepting.')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'plan', 'preflight', 'run'])
    parser.add_argument('--suite', type=Path)
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--authorize-subscription-plan')
    args = parser.parse_args()
    fn = {'prepare': lambda: prepare(args.out), 'plan': lambda: plan(args.suite, args.out),
          'preflight': lambda: preflight(args.plan, args.suite),
          'run': lambda: run(args.plan, args.suite, args.out, args.authorize_subscription_plan)}[args.command]
    print(json.dumps(fn(), indent=2))
