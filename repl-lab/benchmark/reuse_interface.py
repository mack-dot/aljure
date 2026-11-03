"""Small development A/B protocol. Uses the existing gateway, isolated runner and accounting.

prepare, plan, preflight and report never call a provider. run requires the exact
new plan hash. There is no resume, retry, acquisition, or held-out input path.
"""
import argparse
import json
import os
from pathlib import Path
import random
import re
import shutil
import time

from . import paired
from .gateway_client import GatewayClient, ClaudeSubscriptionTransport
from .learning_development import HEADER, PARITY, bundle, score
from .learning_report import tool_reliability
from .oolong import account, digest, encoded, jsonl, money, require

ROOT = paired.ROOT
VERSION = 'reuse-interface-development-v1'
HISTORY = ROOT / 'research/evidence/learning-minimal-results-20261102'
PROTOCOL = ROOT / 'research/REUSE_INTERFACE_PROTOCOL.md'


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(encoded(value) + b'\n')


def files(root):
    return {str(p.relative_to(root)): digest(p.read_bytes()) for p in sorted(root.rglob('*')) if p.is_file()}


def generate():
    # Only the already-public synthetic development generator. No held-out reader.
    _, old = bundle()
    old_text = '\n'.join(v.decode() for k, v in old.items() if k.endswith('.txt'))
    old_text += old['controller/panel.json'].decode()
    used = set(re.findall(r'blocked=(yes|no) age_minutes=(\d+) attempts=(\d+)', old_text))
    rng, result = random.Random(2026110202), []
    for index, (label, count, kind) in enumerate([('retry', 40, 'eligible'), ('hold', 48, 'eligible'),
                                                 ('expedite', 56, 'eligible'), ('even', 20, 'parity'),
                                                 ('hold', 48, 'changed-rules')], 1):
        header = PARITY if kind == 'parity' else HEADER
        if kind == 'changed-rules':
            header = ("Routing v2. Labels are 'hold', 'expedite', or 'retry'. Apply these rules in order: "
                      "blocked=yes means expedite; otherwise age_minutes>=30 means retry; otherwise hold. "
                      "attempts and id do not affect the label. These rules replace Routing v1.")
        texts, labels, legacy = [], [], []
        for n in range(count):
            if kind == 'parity':
                code = 70001 + n * 11
                text, gold, prior = f'code={code}', 'even' if code % 2 == 0 else 'odd', None
            else:
                while True:
                    triple = (rng.choice(('yes', 'no')), str(rng.randrange(120)), str(rng.randrange(10)))
                    if triple not in used:
                        used.add(triple)
                        break
                blocked, age, attempts = triple
                text = f'blocked={blocked} age_minutes={age} attempts={attempts}'
                prior = 'hold' if blocked == 'yes' else 'expedite' if int(age) >= 60 else 'retry' if int(attempts) >= 3 else 'hold'
                gold = ('expedite' if blocked == 'yes' else 'retry' if int(age) >= 30 else 'hold') if kind == 'changed-rules' else prior
            texts.append(f'id=reuse-dev-{index}-{n} ' + text)
            labels.append(gold)
            legacy.append(prior)
        context = '\n'.join([header, ''] + [f'Date: Nov 02, 2026 || User: {n} || Instance: {text}' for n, text in enumerate(texts)])
        result.append({'task_id': f'reuse-dev-{index}', 'kind': kind, 'answer': str(labels.count(label)),
                       'legacy_answer': str(legacy.count(label)), 'records': count,
                       'input': {'context': context, 'task': {'task_id': f'reuse-dev-{index}',
                           'question': f"In the above data, how many data points should be classified as label '{label}'? Return only Answer: N."}}})
    require(result[-1]['answer'] != result[-1]['legacy_answer'], 'Negative transfer control must distinguish old rules')
    return result


def prepare(out):
    out = Path(out).resolve()
    require(out.is_relative_to(ROOT), 'Input bundle must be under repl-lab')
    out.mkdir(parents=True, exist_ok=False)
    history_index = json.loads((HISTORY / 'index.json').read_text())
    require(all(digest((HISTORY / p).read_bytes()) == h for p, h in history_index['files'].items()), 'Historical evidence changed')
    prior = json.loads((HISTORY / 'task-summary.json').read_text())
    pin = prior[-1]['reuse']['library-sha256']
    library = out / 'library'
    shutil.copytree(HISTORY / 'runs/ES-s101/library', library)
    cases = generate()
    for case in cases:
        write(out / 'public' / (case['task_id'] + '.json'), case['input'])
    write(out / 'controller/cases.json', [{k: v for k, v in c.items() if k != 'input'} for c in cases])
    base = json.loads((ROOT / 'config/learning-minimal-sonnet.json').read_text())
    for key in ('trajectory', 'campaign_version', 'authorization_scope', 'case_reuse'):
        base.pop(key, None)
    base['total_usd'] = 6
    base['aljure_contract'] = {'artifacts': {'library': str(library.relative_to(ROOT)), 'library_sha256': pin}}
    write(out / 'baseline.json', base)
    repaired = json.loads(json.dumps(base))
    repaired['aljure_contract']['skill_interface'] = 'inspect-v1'
    write(out / 'repaired.json', repaired)
    manifest = {'version': VERSION, 'origin': 'new synthetic development only',
                'historical_commit': 'e6d17fee98bb40ad9119ca0f3b15533f5b76ad67',
                'historical_index_sha256': digest((HISTORY / 'index.json').read_bytes()),
                'library_sha256': pin, 'files': files(out),
                'records_and_feature_tuples_disjoint_from_prior_development': True,
                'shared_historical_acquisition_cost_usd': .025166}
    manifest['suite_sha256'] = digest(encoded(manifest))
    write(out / 'manifest.json', manifest)
    return manifest


def verify_suite(suite):
    suite = Path(suite)
    manifest = json.loads((suite / 'manifest.json').read_text())
    require(digest(encoded({k: v for k, v in manifest.items() if k != 'suite_sha256'})) == manifest['suite_sha256'], 'Suite hash mismatch')
    require(all((suite / p).is_file() and not (suite / p).is_symlink() and digest((suite / p).read_bytes()) == h
                for p, h in manifest['files'].items()), 'Input or library bytes changed')
    cases = json.loads((suite / 'controller/cases.json').read_text())
    generated = generate()
    require(cases == [{k: v for k, v in c.items() if k != 'input'} for c in generated], 'Cases differ from fixed generator')
    require(all(json.loads((suite / 'public' / (c['task_id'] + '.json')).read_text()) == c['input'] for c in generated), 'Public inputs changed')
    return manifest, cases


def sequence(cases):
    return [{'task_id': case['task_id'], 'arm': arm} for i, case in enumerate(cases)
            for arm in (('baseline', 'repaired') if i % 2 == 0 else ('repaired', 'baseline'))]


def plan(suite, out):
    manifest, cases = verify_suite(suite)
    configs = {arm: json.loads((Path(suite) / (arm + '.json')).read_text()) for arm in ('baseline', 'repaired')}
    for config in configs.values():
        paired.validate_config(config)
    expected = json.loads(json.dumps(configs['baseline']))
    expected['aljure_contract']['skill_interface'] = 'inspect-v1'
    require(expected == configs['repaired'], 'Only the interface may differ between arms')
    require('skill_interface' not in configs['baseline']['aljure_contract'] and
            set(configs['baseline']['aljure_contract']) == {'artifacts'}, 'Baseline must have no other intervention')
    value = {'version': VERSION, 'authorized': False, 'model_calls': 0, 'suite_sha256': manifest['suite_sha256'],
             'protocol_sha256': digest(PROTOCOL.read_bytes()), 'source': paired.source_snapshot(),
             'runtime_source': paired.runtime_snapshot(), 'configs': configs, 'sequence': sequence(cases),
             'budget': {'aggregate_usd': 6, 'per_task_usd': 5, 'reserve_before_next_task_usd': 5,
                        'max_calls': 120, 'max_tasks': 10, 'cost_basis': 'API-rate-equivalent subscription usage'}}
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
    require(value['sequence'] == sequence(cases) and value['protocol_sha256'] == digest(PROTOCOL.read_bytes()), 'Protocol or order changed')
    return value, cases


def preflight(path, suite):
    value, _ = read_plan(path, suite)
    ready = paired.readiness(value, value['configs']['baseline'], native_prime=False, acquisition=True)
    proof_path = ROOT / 'var/reuse-interface-proof.json'
    try:
        proof = json.loads(proof_path.read_text())
        require(proof['evidence'] == 'FIXTURE' and proof['status'] == 'PASSED' and all(proof['checks'].values()), 'Interface fixture did not pass')
        require(proof['runtime_source'] == value['runtime_source'] and proof['suite_sha256'] == value['suite_sha256'] and
                proof['transport_contract'] == paired.transport_contract(value['configs']['baseline']) and
                proof['sci_image'] == value['configs']['baseline']['execution_images']['sci'], 'Interface proof is stale')
        ready['checks']['interface_fixture'] = digest(proof_path.read_bytes())
    except (OSError, ValueError, KeyError) as error:
        ready['blockers'].append('Interface fixture: ' + str(error))
    if shutil.disk_usage(ROOT).free < 6 * 2**30:
        ready['blockers'].append('Less than 6 GiB free disk')
    ready['ready'] = not ready['blockers']
    return ready


def observations(events):
    loaded = {f['code-hash'] for e in events if e['type'] == 'artifact-preloaded' for f in e['payload']['functions'] if f['role'] == 'export'}
    calls = []
    for e in events:
        p = e['payload']
        if e['type'] == 'artifact-invocations':
            calls.extend({'code_hash': x['code-hash'], 'calls': x['calls'], 'returns': x['returns'], 'path': 'preloaded',
                          'call_sequence': p['call-sequence']} for x in p.get('invocations', []) if x['code-hash'] in loaded)
        if e['type'] == 'artifact-invoked' and p.get('origin') == 'approved-external-library' and p.get('code-hash') in loaded:
            calls.append({'code_hash': p['code-hash'], 'calls': 1, 'returns': 1, 'path': 'artifact_call', 'call_sequence': p['call-sequence']})
    return {'source_attributed_invocation': any(x['returns'] > 0 for x in calls), 'invocations': calls,
            'inspection_calls': sum(e['type'] == 'tool-call' and e['payload']['command']['op'] == 'skill/inspect' for e in events),
            'tool_reliability': tool_reliability(events)}


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
    for index, entry in enumerate(value['sequence']):
        task_out = out / f'{index + 1:02}-{entry["arm"]}'
        task_out.mkdir()
        config = value['configs'][entry['arm']]
        row = {**entry, 'status': 'not-attempted', 'failure': stop, 'fresh_process': True}
        gateway, begin = None, time.monotonic()
        try:
            require(stop is None, 'Campaign already stopped')
            require(spent + money(config['usd_per_arm']) <= money(value['budget']['aggregate_usd']), 'Aggregate budget reserve refused')
            require(shutil.disk_usage(ROOT).free >= 6 * 2**30, 'Disk floor refused')
            verify_suite(suite)
            before = paired.docker_state([config['execution_images']['sci']])
            write(task_out / 'docker-before.json', before)
            require(not paired.docker_blockers(before), 'Docker readiness refused')
            data = json.loads((Path(suite) / 'public' / (entry['task_id'] + '.json')).read_text())
            write(task_out / 'public-input.json', data)
            gateway = GatewayClient(task_out / 'gateway', paired.gateway_config(config, 'aljure'),
                                    ClaudeSubscriptionTransport(authorized=True), evidence='LIVE MODEL RUN')
            execution = paired.run_arm('aljure', data, task_out, config, gateway, ready)
            row['status'], row['failure'] = paired.arm_status(execution, (task_out / 'answer.txt').exists())
            after = paired.docker_state([config['execution_images']['sci']])
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
        # Detect duplicate accounting across task gateways too, not only within one.
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
        row.update(kind=by_id[entry['task_id']]['kind'], safety_complete=safe,
                   correct=row['status'] == 'completed' and bool(score(by_id[entry['task_id']], answer)['score']),
                   seconds=time.monotonic() - begin, usage=usage, **observations(events))
        row['files'] = files(task_out)
        write(task_out / 'result.json', row)
        rows.append(row)
    write(out / 'results.json', rows)
    report = summarize(rows)
    write(out / 'report.json', report)
    return report


def summarize(rows):
    result = {'claim': 'Small development mechanism test; no superiority claim or held-out evidence.', 'arms': {}}
    for arm in ('baseline', 'repaired'):
        selected = [r for r in rows if r['arm'] == arm]
        cost = sum(money(r['usage']['known_model_cost_usd']) for r in selected)
        successes = sum(r['correct'] for r in selected)
        eligible = [r for r in selected if r['kind'] == 'eligible']
        result['arms'][arm] = {'tasks': len(selected), 'correct': successes,
             'primary_invoked_eligible_tasks': sum(r['source_attributed_invocation'] for r in eligible),
             'correct_invoked_eligible_tasks': sum(r['source_attributed_invocation'] and r['correct'] for r in eligible),
             'known_cost_usd': float(cost), 'cost_per_success_usd': float(cost / successes) if successes else None,
             'standalone_cost_including_shared_acquisition_usd': float(cost + money(.025166)),
             'negative_control_failures': sum(not r['correct'] for r in selected if r['kind'] != 'eligible'),
             'negative_control_invocations': sum(r['source_attributed_invocation'] for r in selected if r['kind'] != 'eligible'),
             'correct_reuse_tasks_per_new_usd': (float(sum(r['source_attributed_invocation'] and r['correct'] for r in eligible) / cost) if cost else None),
             'seconds': sum(r['seconds'] for r in selected)}
    complete = len(rows) == 10 and all(r['status'] == 'completed' and r.get('safety_complete') and r['usage']['accounting_complete'] for r in rows)
    repair = result['arms']['repaired']
    result['development_gate'] = ('INCOMPLETE' if not complete else 'PENDING-ATTRIBUTION-REVIEW' if repair['correct'] == 5 and
        repair['correct_invoked_eligible_tasks'] > 0 and repair['negative_control_invocations'] == 0 else 'NO-GO')
    result['note'] = 'GO means the repaired mechanism worked at least once with all five answers correct; it does not show an A/B effect. Review source traces for copying, log manipulation and decision use before accepting attribution.'
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
