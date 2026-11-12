"""Three-arm causal development protocol for artifact reuse (research/REUSE_CAUSAL_PROTOCOL.md).

A: stateless baseline, full task information, no library.  B: the same information plus the
retained library through inspect-v1.  C: necessity diagnostic, the asked rule withheld from the
task text, library available.  C0: the withheld text without any library (guess floor).
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
from .learning_development import HEADER, PARITY, bundle, score
from .learning_report import tool_reliability
from .oolong import account, digest, encoded, jsonl, money, require
from . import reuse_interface

ROOT = paired.ROOT
VERSION = 'reuse-causal-development-v1'
SEED = 2026110301
HISTORY = reuse_interface.HISTORY
PROTOCOL = ROOT / 'research/REUSE_CAUSAL_PROTOCOL.md'
PROOF = ROOT / 'var/reuse-causal-proof.json'
write, files = reuse_interface.write, reuse_interface.files

# The v1 fragment "age_minutes>=60 means expedite", the quoted label 'hold' and a blocked= field are
# what the retained applicability predicate matches. The withheld text keeps them and omits only
# the rule that separates retry from hold; it names no library, tool or function.
WITHHELD = ("Routing v1. Classify each Instance as 'hold', 'expedite', or 'retry'. The rules apply in order. "
            "Two of the three are restated here: blocked=yes means hold; otherwise age_minutes>=60 means expedite. "
            "The third rule, which decides between 'retry' and 'hold' for the remaining records, is not restated "
            "in this text. The id is an identifier and does not affect the label.")
CHANGED = ("Routing v2. Labels are 'hold', 'expedite', or 'retry'. These rules replace Routing v1, in which "
           "blocked=yes means hold and age_minutes>=60 means expedite. Apply the v2 rules in order: "
           "blocked=yes means expedite; otherwise age_minutes>=30 means retry; otherwise hold. "
           "attempts and id do not affect the label.")
CASES = [('retry', 40, 'eligible', 'ab'), ('hold', 48, 'eligible', 'ab'), ('expedite', 56, 'eligible', 'ab'),
         ('even', 20, 'parity', 'ab'), ('hold', 48, 'changed-rules', 'ab'),
         ('retry', 44, 'withheld', 'c'), ('hold', 52, 'withheld', 'c'), ('expedite', 36, 'sufficient', 'c'),
         ('even', 24, 'parity', 'c'), ('hold', 40, 'changed-rules', 'c')]
ARMS = {'A': ['stateless', 'ab'], 'B': ['library', 'ab'], 'C0': ['stateless', 'c'], 'C': ['library', 'c']}
LEVELS = ['no-library', 'library-present', 'exposed', 'admitted', 'inspected', 'attempted', 'executed', 'useful', 'used']
SYMBOL = paired.SYMBOL_EDGE


def v1(blocked, age, attempts):
    return 'hold' if blocked == 'yes' else 'expedite' if age >= 60 else 'retry' if attempts >= 3 else 'hold'


def generate():
    """Deterministic cases whose record texts and feature tuples are disjoint from every earlier
    development record (six-task bundle, validation panel and the reuse-interface suite)."""
    _, old = bundle()
    old_text = '\n'.join(v.decode() for k, v in old.items() if k.endswith('.txt')) + old['controller/panel.json'].decode()
    pattern = r'blocked=(yes|no) age_minutes=(\d+) attempts=(\d+)'
    used = set(re.findall(pattern, old_text))
    for case in reuse_interface.generate():
        used.update(re.findall(pattern, case['input']['context']))
    rng, result = random.Random(SEED), []
    for index, (label, count, kind, group) in enumerate(CASES, 1):
        header = {'parity': PARITY, 'changed-rules': CHANGED, 'withheld': WITHHELD, 'sufficient': WITHHELD}.get(kind, HEADER)
        texts, labels, legacy = [], [], []
        for n in range(count):
            if kind == 'parity':
                code = (80003 + n * 13) if group == 'ab' else (90007 + n * 17)
                text, gold, prior = f'code={code}', 'even' if code % 2 == 0 else 'odd', None
            else:
                while True:
                    triple = (rng.choice(('yes', 'no')), str(rng.randrange(120)), str(rng.randrange(10)))
                    if triple not in used:
                        used.add(triple)
                        break
                blocked, age, attempts = triple
                text = f'blocked={blocked} age_minutes={age} attempts={attempts}'
                prior = v1(blocked, int(age), int(attempts))
                gold = ('expedite' if blocked == 'yes' else 'retry' if int(age) >= 30 else 'hold') if kind == 'changed-rules' else prior
            texts.append(f'id=reuse-causal-{index}-{n} ' + text)
            labels.append(gold)
            legacy.append(prior)
        task_id = f'reuse-causal-{index}'
        context = '\n'.join([header, ''] + [f'Date: Nov 03, 2026 || User: {n} || Instance: {text}' for n, text in enumerate(texts)])
        case = {'task_id': task_id, 'kind': kind, 'group': group, 'label': label, 'answer': str(labels.count(label)),
                'legacy_answer': str(legacy.count(label)), 'records': count,
                'input': {'context': context, 'task': {'task_id': task_id,
                          'question': f"In the above data, how many data points should be classified as label '{label}'? Return only Answer: N."}}}
        if kind == 'withheld':
            # Without the third rule the natural readings are "no retry" (0) or "retry and hold merge";
            # the gold must differ from both so an answer without the rule is wrong by construction.
            merged = sum(l in ('retry', 'hold') for l in labels)
            case['without_rule_answers'] = sorted({'0', str(merged)} if label == 'retry' else {str(merged)})
            require(case['answer'] not in case['without_rule_answers'], 'Withheld case must need the withheld rule')
        result.append(case)
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
    # The stateless arm carries the same explicit (default) execution contract with no library at all.
    base['aljure_contract'] = {}
    write(out / 'stateless.json', base)
    library_config = json.loads(json.dumps(base))
    library_config['aljure_contract'] = {'artifacts': {'library': str(library.relative_to(ROOT)), 'library_sha256': pin},
                                         'skill_interface': 'inspect-v1'}
    write(out / 'library.json', library_config)
    manifest = {'version': VERSION, 'origin': 'new synthetic development only', 'seed': SEED,
                'historical_commit': 'e6d17fee98bb40ad9119ca0f3b15533f5b76ad67',
                'historical_index_sha256': digest((HISTORY / 'index.json').read_bytes()),
                'reuse_interface_result_commit': '82d82e5',
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
    pairs = {'ab': ('A', 'B'), 'c': ('C0', 'C')}
    out = []
    for group in ('ab', 'c'):
        for i, case in enumerate(c for c in cases if c['group'] == group):
            first, second = pairs[group]
            for arm in ((first, second) if i % 2 == 0 else (second, first)):
                out.append({'task_id': case['task_id'], 'arm': arm})
    return out


def configs_of(suite):
    return {name: json.loads((Path(suite) / (name + '.json')).read_text()) for name in ('stateless', 'library')}


def plan(suite, out):
    manifest, cases = verify_suite(suite)
    configs = configs_of(suite)
    for config in configs.values():
        paired.validate_config(config)
    expected = json.loads(json.dumps(configs['stateless']))
    expected['aljure_contract'] = {**configs['library']['aljure_contract']}
    require(expected == configs['library'] and set(configs['library']['aljure_contract']) == {'artifacts', 'skill_interface'}
            and configs['stateless']['aljure_contract'] == {}, 'Only the library and its interface may differ between configurations')
    value = {'version': VERSION, 'authorized': False, 'model_calls': 0, 'suite_sha256': manifest['suite_sha256'],
             'protocol_sha256': digest(PROTOCOL.read_bytes()), 'source': paired.source_snapshot(),
             'runtime_source': paired.runtime_snapshot(), 'configs': configs, 'arms': ARMS, 'sequence': sequence(cases),
             'budget': {'aggregate_usd': 6, 'per_task_usd': 5, 'reserve_before_next_task_usd': 5,
                        'max_calls': 240, 'max_tasks': 20, 'cost_basis': 'API-rate-equivalent subscription usage'}}
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
        paired.validate_config(value['configs']['stateless'])
        proof = json.loads(PROOF.read_text())
        require(proof['evidence'] == 'FIXTURE' and proof['status'] == 'PASSED' and all(proof['checks'].values()), 'Causal fixture did not pass')
        require(proof['runtime_source'] == value['runtime_source'] and proof['suite_sha256'] == value['suite_sha256'] and
                proof['transport_contract'] == paired.transport_contract(value['configs']['library']) and
                proof['sci_image'] == value['configs']['library']['execution_images']['sci'], 'Causal fixture proof is stale')
        ready['checks']['causal_fixture'] = digest(PROOF.read_bytes())
    except (OSError, ValueError, KeyError) as error:
        ready['blockers'].append('Causal fixture: ' + str(error))
    if shutil.disk_usage(ROOT).free < 6 * 2**30:
        ready['blockers'].append('Less than 6 GiB free disk')
    ready['ready'] = not ready['blockers']
    return ready


def asked_label(question):
    found = re.search(r"label '([a-z]+)'", question or '')
    return found.group(1) if found else None


def first_request(task_out):
    path = Path(task_out) / 'gateway/events.jsonl'
    if not path.exists():
        return None
    return next((e['payload']['input'] for e in jsonl(path) if e['type'] == 'gateway-request-intent'), None)


def prompt_measure(task_out):
    """Prompt and tool-schema overhead of the task's first provider request, from the recorded
    request body and its usage receipt. Tokens are the provider's own counts."""
    body = first_request(task_out)
    usage_path = Path(task_out) / 'gateway/usage.jsonl'
    receipts = [u for u in (jsonl(usage_path) if usage_path.exists() else []) if u.get('kind') == 'provider-call']
    first = receipts[0] if receipts else {}
    tokens = None
    if first.get('status') == 'complete':
        tokens = sum(first.get(k, 0) or 0 for k in ('input_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens'))
    if body is None:
        return {'first_request_tokens': tokens}
    return {'first_request_tokens': tokens, 'tools': len(body.get('tools', [])),
            'tools_bytes': len(encoded(body.get('tools', []))), 'messages_bytes': len(encoded(body.get('messages', []))),
            'system_bytes': len(encoded(body.get('system', ''))),
            'inventory_in_prompt': ':approved-functions' in json.dumps(body.get('messages', []))}


def attribution(events, answer_text, question, request=None):
    """Reuse evidence as separate levels, from controller events and executable dependencies.
    exposed: the first provider request carried the approved-functions inventory. admitted: an
    export was preloaded. inspected: artifact_inspect calls. attempted: artifact_call calls plus
    evaluations whose source names an export. executed: a counted call of a loaded export.
    useful: an execution returned a non-nil value. used: the evaluation that executed the export
    returned the delivered number, the answer was computed in a done source that executed it, or
    the artifact_call values for the asked label count to the delivered number. A nil probe is
    executed but never useful."""
    loaded = {f['code-hash']: f.get('name') for e in events if e['type'] == 'artifact-preloaded'
              for f in e['payload']['functions'] if str(f.get('role', '')).lstrip(':') == 'export'}
    decisions = [e['payload'] for e in events if e['type'] == 'artifact-applicability']
    present = any(e['type'] == 'artifact-library-loaded' for e in events)
    exposed = bool(request) and ':approved-functions' in json.dumps(request.get('messages', []))
    number = paired.declared_number(answer_text)
    label = asked_label(question)
    # Pair each tool call with its result in order, per session.
    pending, calls = {}, []
    for e in events:
        p = e['payload']
        if e['type'] == 'tool-call':
            pending.setdefault(p.get('session'), []).append(p['command'])
        elif e['type'] == 'tool-result':
            queue = pending.get(p.get('session'), [])
            command = queue.pop(0) if queue else {}
            calls.append({'session': p.get('session'), 'call_sequence': p.get('call-sequence'), 'op': p.get('op'),
                          'status': p.get('status'), 'result': p.get('result'), 'command': command})
    patterns = [re.compile(f'(?<!{SYMBOL}){re.escape(n)}(?!{SYMBOL})') for n in loaded.values() if n]
    inspections = [c['command'] for c in calls if c['op'] == 'skill/inspect']
    named = [c for c in calls if c['op'] in ('repl/eval', 'done/eval') and any(p.search(c['command'].get('source') or '') for p in patterns)]
    call_attempts = [c for c in calls if c['op'] == 'artifact/call']
    executions = []
    for e in events:
        p = e['payload']
        if e['type'] == 'artifact-invocations':
            for x in p.get('invocations', []):
                if x['code-hash'] in loaded:
                    nils = x.get('nils')
                    useful = bool(x.get('values')) or (nils is not None and x['returns'] > nils)
                    executions.append({'path': 'preloaded', 'code_hash': x['code-hash'], 'calls': x['calls'], 'returns': x['returns'],
                                       'nils': nils, 'values': x.get('values', []), 'useful': useful,
                                       'session': p.get('session'), 'op': p.get('op'), 'call_sequence': p.get('call-sequence')})
        if e['type'] == 'artifact-invoked' and p.get('origin') == 'approved-external-library' and p.get('code-hash') in loaded:
            executions.append({'path': 'artifact_call', 'code_hash': p['code-hash'], 'calls': 1, 'returns': 1,
                               'nils': int(p.get('value') is None), 'values': [p.get('value')] if p.get('value') is not None else [],
                               'useful': p.get('value') is not None, 'session': p.get('session'), 'op': 'artifact/call',
                               'call_sequence': p.get('call-sequence')})
    executed = [x for x in executions if x['returns'] > 0]
    useful = [x for x in executed if x['useful']]
    by_sequence = {(c['session'], c['call_sequence']): c for c in calls}
    used = []
    for x in useful:
        if x['path'] != 'preloaded':
            continue
        c = by_sequence.get((x['session'], x['call_sequence']))
        if not c or c['status'] != 'ok':
            continue
        value = (c['result'] or {}).get('value')
        if c['op'] == 'done/eval' or (number is not None and value == number and not isinstance(value, bool)):
            used.append(x)
    labels = [x['values'][0] for x in useful if x['path'] == 'artifact_call']
    if labels and label is not None and number is not None and number == labels.count(label) and number > 0:
        used.extend(x for x in useful if x['path'] == 'artifact_call')
    flags = {'library-present': present, 'exposed': exposed, 'admitted': bool(loaded) and any(d.get('decision') == 'preload' for d in decisions),
             'inspected': bool(inspections), 'attempted': bool(call_attempts or named), 'executed': bool(executed),
             'useful': bool(useful), 'used': bool(used)}
    level = 'no-library'
    for name in LEVELS[1:]:
        if flags[name]:
            level = name
    return {'level': level, 'flags': flags, 'inspections': inspections, 'named_evaluations': len(named),
            'artifact_call_attempts': len(call_attempts), 'executions': executions,
            'useful_reuse': bool(used), 'tool_reliability': tool_reliability(events)}


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
        row.update(kind=case['kind'], group=case['group'], safety_complete=safe,
                   correct=row['status'] == 'completed' and bool(score(case, answer)['score']),
                   answer=answer, seconds=time.monotonic() - begin, usage=usage, prompt=prompt_measure(task_out),
                   attribution=attribution(events, answer, question, first_request(task_out)))
        row['files'] = files(task_out)
        write(task_out / 'result.json', row)
        rows.append(row)
    write(out / 'results.json', rows)
    report = summarize(rows)
    write(out / 'report.json', report)
    return report


def summarize(rows):
    result = {'claim': 'Small development mechanism test; no superiority claim or held-out evidence.', 'arms': {}}
    for arm in ARMS:
        selected = [r for r in rows if r['arm'] == arm]
        cost = sum(money(r['usage']['known_model_cost_usd']) for r in selected)
        successes = sum(r['correct'] for r in selected)
        levels = {level: sum(r['attribution']['level'] == level for r in selected) for level in LEVELS}
        tokens = [r['prompt'].get('first_request_tokens') for r in selected if r.get('prompt', {}).get('first_request_tokens') is not None]
        result['arms'][arm] = {
            'configuration': ARMS[arm][0], 'cases': ARMS[arm][1], 'tasks': len(selected), 'correct': successes,
            'known_cost_usd': float(cost), 'cost_per_success_usd': float(cost / successes) if successes else None,
            'requests': sum(r['usage']['calls'] for r in selected), 'seconds': sum(r['seconds'] for r in selected),
            'first_request_tokens_mean': (sum(tokens) / len(tokens)) if tokens else None,
            'tools_bytes': sorted({r['prompt'].get('tools_bytes') for r in selected if r.get('prompt', {}).get('tools_bytes') is not None}),
            'levels': levels,
            'useful_reuse_tasks': sum(r['attribution']['useful_reuse'] for r in selected),
            'useful_reuse_correct_tasks': sum(r['attribution']['useful_reuse'] and r['correct'] for r in selected),
            'negative_control_failures': sum(not r['correct'] for r in selected if r['kind'] in ('parity', 'changed-rules')),
            'negative_control_executions': sum(r['attribution']['flags']['executed'] for r in selected if r['kind'] in ('parity', 'changed-rules'))}
    by = lambda arm, kind: [r for r in rows if r['arm'] == arm and r['kind'] == kind]
    endpoints = {
        'B_eligible_useful_reuse_correct': sum(r['attribution']['useful_reuse'] and r['correct'] for r in by('B', 'eligible')),
        'A_eligible_correct': sum(r['correct'] for r in by('A', 'eligible')),
        'B_eligible_correct': sum(r['correct'] for r in by('B', 'eligible')),
        'C_withheld_correct': sum(r['correct'] for r in by('C', 'withheld')),
        'C0_withheld_correct': sum(r['correct'] for r in by('C0', 'withheld')),
        'C_withheld_levels': [r['attribution']['level'] for r in by('C', 'withheld')],
        'C_withheld_useful_reuse_correct': sum(r['attribution']['useful_reuse'] and r['correct'] for r in by('C', 'withheld')),
        'C_withheld_correct_without_execution': sum(r['correct'] and not r['attribution']['flags']['executed'] for r in by('C', 'withheld')),
        'C_sufficient_correct': sum(r['correct'] for r in by('C', 'sufficient')),
        'C0_sufficient_correct': sum(r['correct'] for r in by('C0', 'sufficient')),
        'negative_control_executions': sum(a['negative_control_executions'] for a in result['arms'].values()),
        'negative_control_failures_library_arms': sum(result['arms'][a]['negative_control_failures'] for a in ('B', 'C'))}
    result['endpoints'] = endpoints
    complete = len(rows) == 20 and all(r['status'] == 'completed' and r.get('safety_complete') and r['usage']['accounting_complete'] for r in rows)
    if not complete:
        gate, pattern = 'INCOMPLETE', None
    elif endpoints['negative_control_executions'] or endpoints['negative_control_failures_library_arms']:
        gate, pattern = 'NEGATIVE-CONTROL-FAILURE', None
    else:
        gate = 'COMPLETE-PENDING-ATTRIBUTION-REVIEW'
        if endpoints['B_eligible_useful_reuse_correct'] > 0:
            pattern = 'voluntary-useful-reuse'
        elif endpoints['C_withheld_useful_reuse_correct'] > 0:
            pattern = 'reuse-only-when-necessary'
        elif endpoints['C_withheld_correct_without_execution'] > 0 and endpoints['C_withheld_correct'] > endpoints['C0_withheld_correct']:
            pattern = 'knowledge-reuse-without-execution'
        elif endpoints['C_withheld_correct'] > 0 and endpoints['C_withheld_correct'] <= endpoints['C0_withheld_correct']:
            pattern = 'rule-recoverable-without-library'
        else:
            pattern = 'no-reuse-even-when-necessary'
    result.update(development_gate=gate, outcome_pattern=pattern,
                  note='Patterns are the frozen mapping in research/REUSE_CAUSAL_PROTOCOL.md. Review every execution trace '
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
