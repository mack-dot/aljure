"""Reuse-economics development protocol (research/REUSE_ECONOMICS_PROTOCOL.md).

The causal study (REUSE_CAUSAL_RESULT.md) found reuse only under necessity: with the rule in
the text the model reimplemented it as one short expression every time. This protocol keeps
the retained library, predicate and interface fixed and states the same Routing v1 rule in a
long form (six ordered clauses) whose fresh implementation is longer than one call of the
retained skill. A: stateless, long rule. B: library through inspect-v1, long rule. BN: the
same library through inspect-v1-names, so the inventory shows names, hashes and call syntax
but no model-authored summary; this separates execution reuse from description reuse.
prepare, plan, preflight and the fixture never call a provider. run requires the exact new
plan hash. No resume, retry, acquisition or held-out path exists.
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
from .learning_development import PARITY, bundle, score
from .oolong import account, digest, encoded, jsonl, money, require
from . import reuse_causal, reuse_interface
from .reuse_causal import HISTORY, LEVELS, attribution, files, first_request, prompt_measure, write

ROOT = paired.ROOT
VERSION = 'reuse-economics-development-v1'
SEED = 2026110401
PROTOCOL = ROOT / 'research/REUSE_ECONOMICS_PROTOCOL.md'
PROOF = ROOT / 'var/reuse-economics-proof.json'
CONFIGS = ('stateless', 'library', 'library-names')
INTERFACES = {'library': 'inspect-v1', 'library-names': 'inspect-v1-names'}

# Routing v1 stated as six ordered clauses. It is equal to the three-rule statement on every
# record (test_reuse_economics checks the full domain), so the retained skill answers it in one
# call. The retained applicability predicate's three literals are kept: `blocked=`, the quoted
# label `'hold'`, and `age_minutes>=60 means expedite`. The text names no library, tool or function.
LONG = ("Routing v1, full statement. Classify each Instance as 'hold', 'expedite', or 'retry'. Evaluate the six "
        "clauses in order and assign the label of the first clause that matches: (1) blocked=yes means hold, "
        "whatever the other fields are; (2) otherwise age_minutes>=60 means expedite, whatever attempts is; "
        "(3) otherwise age_minutes>=30 and attempts>=3 means retry; (4) otherwise age_minutes>=30 and attempts<3 "
        "means hold; (5) otherwise age_minutes<30 and attempts>=3 means retry; (6) otherwise, that is "
        "age_minutes<30 and attempts<3, means hold. The id is an identifier and does not affect the label.")
# Routing v2 in the same six-clause form; it keeps the predicate's literals and differs from v1, so the
# retained skill is admitted but wrong: the negative-transfer control for long rules.
LONG_CHANGED = ("Routing v2, full statement. Labels are 'hold', 'expedite', or 'retry'. These rules replace Routing v1, in which "
                "blocked=yes means hold and age_minutes>=60 means expedite. Evaluate the six v2 clauses in order and assign "
                "the label of the first clause that matches: (1) blocked=yes and attempts>=3 means expedite; (2) blocked=yes "
                "and attempts<3 means hold; (3) otherwise age_minutes>=60 means hold; (4) otherwise age_minutes>=30 and "
                "attempts>=1 means retry; (5) otherwise age_minutes>=30 and attempts=0 means hold; (6) otherwise means "
                "retry. The id is an identifier and does not affect the label.")
CASES = [('retry', 48, 'eligible'), ('hold', 56, 'eligible'), ('expedite', 44, 'eligible'),
         ('retry', 52, 'eligible'), ('hold', 40, 'eligible'), ('expedite', 60, 'eligible'),
         ('even', 28, 'parity'), ('retry', 48, 'changed-rules')]
ARMS = {'A': ['stateless', 'long'], 'B': ['library', 'long'], 'BN': ['library-names', 'long']}
ORDER = [('A', 'B', 'BN'), ('B', 'BN', 'A'), ('BN', 'A', 'B')]
ATTEMPTS = len(CASES) * len(ARMS)


def long_v1(blocked, age, attempts):
    """The six clauses of LONG, literally."""
    if blocked == 'yes':
        return 'hold'
    if age >= 60:
        return 'expedite'
    if age >= 30 and attempts >= 3:
        return 'retry'
    if age >= 30 and attempts < 3:
        return 'hold'
    if age < 30 and attempts >= 3:
        return 'retry'
    return 'hold'


def long_v2(blocked, age, attempts):
    """The six clauses of LONG_CHANGED, literally."""
    if blocked == 'yes':
        return 'expedite' if attempts >= 3 else 'hold'
    if age >= 60:
        return 'hold'
    if age >= 30:
        return 'retry' if attempts >= 1 else 'hold'
    return 'retry'


def prior_tuples():
    """Every routing feature tuple used by earlier development records: the six-task bundle, the
    validation panel, the reuse-interface suite and the causal suite."""
    _, old = bundle()
    old_text = '\n'.join(v.decode() for k, v in old.items() if k.endswith('.txt')) + old['controller/panel.json'].decode()
    pattern = r'blocked=(yes|no) age_minutes=(\d+) attempts=(\d+)'
    used = set(re.findall(pattern, old_text))
    for case in reuse_interface.generate() + reuse_causal.generate():
        used.update(re.findall(pattern, case['input']['context']))
    return used


def generate():
    """Deterministic cases; record texts and feature tuples are disjoint from every earlier
    development record and from each other."""
    used = prior_tuples()
    rng, result = random.Random(SEED), []
    for index, (label, count, kind) in enumerate(CASES, 1):
        header = {'parity': PARITY, 'changed-rules': LONG_CHANGED}.get(kind, LONG)
        texts, labels, legacy = [], [], []
        for n in range(count):
            if kind == 'parity':
                code = 60013 + n * 23
                text, gold, prior = f'code={code}', 'even' if code % 2 == 0 else 'odd', None
            else:
                while True:
                    triple = (rng.choice(('yes', 'no')), str(rng.randrange(120)), str(rng.randrange(10)))
                    if triple not in used:
                        used.add(triple)
                        break
                blocked, age, attempts = triple
                text = f'blocked={blocked} age_minutes={age} attempts={attempts}'
                prior = reuse_causal.v1(blocked, int(age), int(attempts))
                gold = long_v2(blocked, int(age), int(attempts)) if kind == 'changed-rules' else long_v1(blocked, int(age), int(attempts))
            texts.append(f'id=reuse-economics-{index}-{n} ' + text)
            labels.append(gold)
            legacy.append(prior)
        task_id = f'reuse-economics-{index}'
        context = '\n'.join([header, ''] + [f'Date: Nov 04, 2026 || User: {n} || Instance: {text}' for n, text in enumerate(texts)])
        result.append({'task_id': task_id, 'kind': kind, 'label': label, 'answer': str(labels.count(label)),
                       'legacy_answer': str(legacy.count(label)), 'records': count,
                       'input': {'context': context, 'task': {'task_id': task_id,
                                 'question': f"In the above data, how many data points should be classified as label '{label}'? Return only Answer: N."}}})
    require(all(c['answer'] == c['legacy_answer'] for c in result if c['kind'] == 'eligible'),
            'The long statement must agree with the retained skill on every eligible case')
    require(all(c['answer'] != c['legacy_answer'] for c in result if c['kind'] == 'changed-rules'),
            'Negative transfer controls must distinguish old rules')
    return result


def prepare(out):
    out = Path(out).resolve()
    require(out.is_relative_to(ROOT), 'Input bundle must be under repl-lab')
    out.mkdir(parents=True, exist_ok=False)
    history_index = json.loads((HISTORY / 'index.json').read_text())
    require(all(digest((HISTORY / p).read_bytes()) == h for p, h in history_index['files'].items()), 'Historical evidence changed')
    pin = json.loads((HISTORY / 'task-summary.json').read_text())[-1]['reuse']['library-sha256']
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
    base['aljure_contract'] = {}
    write(out / 'stateless.json', base)
    for name, interface in INTERFACES.items():
        config = json.loads(json.dumps(base))
        config['aljure_contract'] = {'artifacts': {'library': str(library.relative_to(ROOT)), 'library_sha256': pin},
                                     'skill_interface': interface}
        write(out / (name + '.json'), config)
    manifest = {'version': VERSION, 'origin': 'new synthetic development only', 'seed': SEED,
                'historical_commit': 'e6d17fee98bb40ad9119ca0f3b15533f5b76ad67',
                'historical_index_sha256': digest((HISTORY / 'index.json').read_bytes()),
                'reuse_causal_result_commit': '0efefde',
                'library_sha256': pin, 'files': files(out),
                'records_and_feature_tuples_disjoint_from_prior_development': True,
                'shared_historical_acquisition_cost_usd': .025166}
    manifest['suite_sha256'] = digest(encoded(manifest))
    write(out / 'manifest.json', manifest)
    return manifest


def verify_suite(suite):
    suite = Path(suite)
    manifest = json.loads((suite / 'manifest.json').read_text())
    require(manifest['version'] == VERSION, 'Wrong suite version')
    require(digest(encoded({k: v for k, v in manifest.items() if k != 'suite_sha256'})) == manifest['suite_sha256'], 'Suite hash mismatch')
    require(all((suite / p).is_file() and not (suite / p).is_symlink() and digest((suite / p).read_bytes()) == h
                for p, h in manifest['files'].items()), 'Input or library bytes changed')
    cases = json.loads((suite / 'controller/cases.json').read_text())
    generated = generate()
    require(cases == [{k: v for k, v in c.items() if k != 'input'} for c in generated], 'Cases differ from fixed generator')
    require(all(json.loads((suite / 'public' / (c['task_id'] + '.json')).read_text()) == c['input'] for c in generated), 'Public inputs changed')
    return manifest, cases


def sequence(cases):
    """Every case in all three arms; the arm order rotates with the case index so each arm is
    first, second and third about equally often."""
    return [{'task_id': case['task_id'], 'arm': arm} for i, case in enumerate(cases) for arm in ORDER[i % len(ORDER)]]


def configs_of(suite):
    return {name: json.loads((Path(suite) / (name + '.json')).read_text()) for name in CONFIGS}


def plan(suite, out):
    manifest, cases = verify_suite(suite)
    configs = configs_of(suite)
    for config in configs.values():
        paired.validate_config(config)
    for name, interface in INTERFACES.items():
        expected = json.loads(json.dumps(configs['stateless']))
        expected['aljure_contract'] = {**configs[name]['aljure_contract']}
        require(expected == configs[name] and set(configs[name]['aljure_contract']) == {'artifacts', 'skill_interface'}
                and configs[name]['aljure_contract']['skill_interface'] == interface,
                'Only the library and its interface may differ between configurations')
    require(configs['stateless']['aljure_contract'] == {} and
            configs['library']['aljure_contract']['artifacts'] == configs['library-names']['aljure_contract']['artifacts'],
            'The two library configurations must share the pinned library')
    value = {'version': VERSION, 'authorized': False, 'model_calls': 0, 'suite_sha256': manifest['suite_sha256'],
             'protocol_sha256': digest(PROTOCOL.read_bytes()), 'source': paired.source_snapshot(),
             'runtime_source': paired.runtime_snapshot(), 'configs': configs, 'arms': ARMS, 'sequence': sequence(cases),
             'budget': {'aggregate_usd': 6, 'per_task_usd': 5, 'reserve_before_next_task_usd': 5,
                        'max_calls': 12 * ATTEMPTS, 'max_tasks': ATTEMPTS, 'cost_basis': 'API-rate-equivalent subscription usage'}}
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
    require(value['sequence'] == sequence(cases) and value['arms'] == ARMS and
            value['protocol_sha256'] == digest(PROTOCOL.read_bytes()), 'Protocol or order changed')
    require(value['configs'] == configs_of(suite), 'Configurations changed')
    return value, cases


def preflight(path, suite):
    value, _ = read_plan(path, suite)
    ready = paired.readiness(value, value['configs']['library'], native_prime=False, acquisition=True)
    try:
        for name in ('stateless', 'library-names'):
            paired.validate_config(value['configs'][name])
        proof = json.loads(PROOF.read_text())
        require(proof['evidence'] == 'FIXTURE' and proof['status'] == 'PASSED' and all(proof['checks'].values()), 'Economics fixture did not pass')
        require(proof['runtime_source'] == value['runtime_source'] and proof['suite_sha256'] == value['suite_sha256'] and
                proof['transport_contract'] == paired.transport_contract(value['configs']['library']) and
                proof['sci_image'] == value['configs']['library']['execution_images']['sci'], 'Economics fixture proof is stale')
        ready['checks']['economics_fixture'] = digest(PROOF.read_bytes())
    except (OSError, ValueError, KeyError) as error:
        ready['blockers'].append('Economics fixture: ' + str(error))
    if shutil.disk_usage(ROOT).free < 6 * 2**30:
        ready['blockers'].append('Less than 6 GiB free disk')
    ready['ready'] = not ready['blockers']
    return ready


def evaluations(events):
    """How much fresh computation the model ran: evaluations and their errors, from tool results."""
    results = [e['payload'] for e in events if e['type'] == 'tool-result' and e['payload'].get('op') in ('repl/eval', 'done/eval')]
    return {'evaluations': len(results), 'evaluation_errors': sum(r.get('status') != 'ok' for r in results),
            'inspections': sum(e['type'] == 'tool-result' and e['payload'].get('op') == 'skill/inspect' for e in events),
            'artifact_calls': sum(e['type'] == 'tool-result' and e['payload'].get('op') == 'artifact/call' for e in events)}


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
        config = value['configs'][ARMS[entry['arm']][0]]
        case = by_id[entry['task_id']]
        question = json.loads((Path(suite) / 'public' / (entry['task_id'] + '.json')).read_text())['task']['question']
        row = {**entry, 'configuration': ARMS[entry['arm']][0], 'status': 'not-attempted', 'failure': stop, 'fresh_process': True}
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
        row.update(kind=case['kind'], safety_complete=safe,
                   correct=row['status'] == 'completed' and bool(score(case, answer)['score']),
                   answer=answer, seconds=time.monotonic() - begin, usage=usage, prompt=prompt_measure(task_out),
                   computation=evaluations(events),
                   attribution=attribution(events, answer, question, first_request(task_out)))
        row['files'] = files(task_out)
        write(task_out / 'result.json', row)
        rows.append(row)
    write(out / 'results.json', rows)
    report = summarize(rows)
    write(out / 'report.json', report)
    return report


def mean(values):
    values = [v for v in values if v is not None]
    return (sum(values) / len(values)) if values else None


def summarize(rows):
    result = {'claim': 'Small development mechanism test; no superiority claim or held-out evidence.', 'arms': {}}
    for arm in ARMS:
        selected = [r for r in rows if r['arm'] == arm]
        eligible = [r for r in selected if r['kind'] == 'eligible']
        cost = sum(money(r['usage']['known_model_cost_usd']) for r in selected)
        successes = sum(r['correct'] for r in selected)
        result['arms'][arm] = {
            'configuration': ARMS[arm][0], 'cases': ARMS[arm][1], 'tasks': len(selected), 'correct': successes,
            'known_cost_usd': float(cost), 'cost_per_success_usd': float(cost / successes) if successes else None,
            'requests': sum(r['usage']['calls'] for r in selected), 'seconds': sum(r['seconds'] for r in selected),
            'first_request_tokens_mean': mean([r.get('prompt', {}).get('first_request_tokens') for r in selected]),
            'tools_bytes': sorted({r['prompt'].get('tools_bytes') for r in selected if r.get('prompt', {}).get('tools_bytes') is not None}),
            'levels': {level: sum(r['attribution']['level'] == level for r in selected) for level in LEVELS},
            'eligible': {'tasks': len(eligible), 'correct': sum(r['correct'] for r in eligible),
                         'known_cost_usd': float(sum(money(r['usage']['known_model_cost_usd']) for r in eligible)),
                         'requests': sum(r['usage']['calls'] for r in eligible), 'seconds': sum(r['seconds'] for r in eligible),
                         'evaluations': sum(r['computation']['evaluations'] for r in eligible),
                         'evaluation_errors': sum(r['computation']['evaluation_errors'] for r in eligible),
                         'inspected_tasks': sum(r['attribution']['flags'].get('inspected', False) for r in eligible),
                         'executed_tasks': sum(r['attribution']['flags'].get('executed', False) for r in eligible),
                         'used_correct_tasks': sum(r['attribution']['useful_reuse'] and r['correct'] for r in eligible)},
            'negative_control_failures': sum(not r['correct'] for r in selected if r['kind'] in ('parity', 'changed-rules')),
            'negative_control_executions': sum(r['attribution']['flags']['executed'] for r in selected if r['kind'] in ('parity', 'changed-rules'))}
    arms = result['arms']
    endpoints = {
        **{f'{arm}_eligible_correct': arms[arm]['eligible']['correct'] for arm in ARMS},
        **{f'{arm}_eligible_used_correct': arms[arm]['eligible']['used_correct_tasks'] for arm in ('B', 'BN')},
        **{f'{arm}_eligible_inspected': arms[arm]['eligible']['inspected_tasks'] for arm in ('B', 'BN')},
        **{f'{arm}_eligible_evaluations': arms[arm]['eligible']['evaluations'] for arm in ARMS},
        **{f'{arm}_eligible_requests': arms[arm]['eligible']['requests'] for arm in ARMS},
        **{f'{arm}_eligible_known_cost_usd': arms[arm]['eligible']['known_cost_usd'] for arm in ARMS},
        **{f'{arm}_eligible_seconds': arms[arm]['eligible']['seconds'] for arm in ARMS},
        'negative_control_executions': sum(a['negative_control_executions'] for a in arms.values()),
        'negative_control_failures_library_arms': sum(arms[a]['negative_control_failures'] for a in ('B', 'BN'))}
    result['endpoints'] = endpoints
    complete = len(rows) == ATTEMPTS and all(r['status'] == 'completed' and r.get('safety_complete') and r['usage']['accounting_complete'] for r in rows)
    pattern = effect = None
    if not complete:
        gate = 'INCOMPLETE'
    elif endpoints['negative_control_executions'] or endpoints['negative_control_failures_library_arms']:
        gate = 'NEGATIVE-CONTROL-FAILURE'
    else:
        gate = 'COMPLETE-PENDING-ATTRIBUTION-REVIEW'
        b, bn = endpoints['B_eligible_used_correct'], endpoints['BN_eligible_used_correct']
        pattern = ('reuse-under-long-rules' if b >= 3 else 'occasional-reuse-under-long-rules' if b >= 1
                   else 'reimplementation-regardless-of-length')
        effect = ('none' if b == 0 and bn == 0 else 'summary-mediated' if b > bn else 'execution-independent-of-summary')
    result.update(development_gate=gate, outcome_pattern=pattern, summary_effect=effect,
                  note='Patterns are the frozen mapping in research/REUSE_ECONOMICS_PROTOCOL.md. Review every execution trace '
                       'for copying, counter manipulation and decision use before accepting an attribution.')
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
