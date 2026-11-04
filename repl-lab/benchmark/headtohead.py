"""Head-to-head v8: Aljure (stateless, native tools, assisted bounded SCI, learning disabled) against the
pinned native Prime agent on several pinned official suites under ONE frozen plan.

What this driver adds over benchmark.paired (whose arm execution, gates, gateway, accounting and scorers it
reuses unchanged): a seeded task order across suites, a balanced seeded arm order per task, repeated trials
of a seeded 20% of the tasks, resume of an interrupted run under the same plan hash, an explicit
`not-attempted` status, per-arm latency and tool-reliability measures taken from the recorded traces, and
the pre-registered paired analysis (research/STATISTICAL_EVALUATION_PROTOCOL.md): context-weighted paired
difference with a 10,000-resample cluster bootstrap, TOST equivalence at delta 0.05, exact sign and McNemar
tests, paired cost and latency differences, and a Pareto table per suite.

No arm, timeout or error is ever excluded: every planned (suite, task, trial, harness) gets a row. Only the
infrastructure failures listed in INFRASTRUCTURE stop the run, and a stopped run resumes with --resume.

Commands (no inference except `run`, which needs the exact approved plan hash):
    python3 -m benchmark.headtohead plan --out var/h2h-20261104/plan.json
    python3 -m benchmark.headtohead preflight --plan var/h2h-20261104/plan.json
    python3 -m benchmark.headtohead run --plan ... --out ... --authorize-subscription-plan <hash> [--resume]
    python3 -m benchmark.headtohead report --out <run dir>
"""
import argparse
import glob
import json
import math
import os
from pathlib import Path
import random
import shutil
import time

from . import paired
from .gateway_client import GatewayClient, ClaudeSubscriptionTransport
from .official import score_answer
from .oolong import account, digest, encoded, jsonl, money, read_suite, require
from .prime import container as native
from . import terminal_text

ROOT = paired.ROOT
DELTA = 0.05
RESAMPLES = 10000
SUCCESS = 0.9
MIN_CONTEXTS = 5
HARNESSES = ('aljure', 'prime')
# Suites of the development pilot, in the brief's priority order. `rule` is the task selection, fixed by seed
# and task identity only; `exposure` is the disclosure recorded in the plan.
PILOT = [
    {'name': 'synth8', 'suite': 'var/official/synth8-indep-dev', 'rule': 'all',
     'exposure': 'unexposed: OOLONG-synth test windows ...010 at 8K, never run by any harness'},
    {'name': 'synth32', 'suite': 'var/official/synth32-indep-dev', 'rule': 'one-per-context',
     'exposure': 'development: the 21-task 32K suite was run by both harnesses on 2026-10-29 (plan 0b6a0451) and in four Opus plans'},
    {'name': 'synth128', 'suite': 'var/official/synth128-indep-dev', 'rule': 'all',
     'exposure': 'unexposed: OOLONG-synth test windows ...021 at 128K; negation 40021 appeared only in an import-validation manifest'},
    {'name': 'pairs32', 'suite': 'var/official/pairs32-ten', 'rule': 'seeded-3',
     'exposure': 'development: OOLONG-Pairs 32K, one context, run by both harnesses in control-2, A1 and A1c (2026-10-28/29)'},
]
# Phase B: the sealed held-out OOLONG-synth windows, one question per context (the plan picks it by seed from the
# two prepared per window). Kept apart from the exploratory OBLIQ and LongBench Pro suites (benchmark/exploratory.py).
PHASE_B = [
    {'name': name, 'suite': f'var/official/{name}', 'rule': 'one-per-context',
     'exposure': f'held-out: OOLONG-synth test-split windows at {length}, prepared sealed, never run by any harness, gold unread before the run'}
    for name, length in (('synth4-indep-heldout', '4K'), ('synth8-indep-heldout', '8K'), ('synth16-indep-heldout', '16K'),
                         ('synth32-indep-heldout', '32K'), ('synth64-indep-heldout', '64K'), ('synth128-indep-heldout', '128K'))]
# Per-arm cost priors (API-rate-equivalent USD). Pilot 1 measured 8K $0.025/$0.052, 32K $0.032/$0.066, 128K $0.018/$0.060,
# Pairs 32K $0.054/$0.084 (Aljure/Prime); the pilot priors were scaled guesses kept for the record.
COST_PRIOR = {'synth8': {'aljure': 0.035, 'prime': 0.060}, 'synth32': {'aljure': 0.039, 'prime': 0.076},
              'synth128': {'aljure': 0.120, 'prime': 0.200}, 'pairs32': {'aljure': 0.083, 'prime': 0.095},
              'synth4-indep-heldout': {'aljure': 0.025, 'prime': 0.052}, 'synth8-indep-heldout': {'aljure': 0.025, 'prime': 0.052},
              'synth16-indep-heldout': {'aljure': 0.030, 'prime': 0.060}, 'synth32-indep-heldout': {'aljure': 0.032, 'prime': 0.066},
              'synth64-indep-heldout': {'aljure': 0.030, 'prime': 0.065}, 'synth128-indep-heldout': {'aljure': 0.020, 'prime': 0.060}}
CAMPAIGNS = {
    'pilot-1': {'version': 'head-to-head-v8-pilot-1', 'seed': 2026110405, 'repeat_fraction': 0.2, 'suites': PILOT,
                'protocol': 'research/HEAD_TO_HEAD_V8_PROTOCOL.md', 'config': 'config/head-to-head-v8-sonnet.json',
                'max_spend_usd': None, 'claim': 'Development pilot on pinned official inputs; descriptive; no held-out or superiority claim.'},
    'phase-b': {'version': 'head-to-head-v8-phase-b', 'seed': 2026110408, 'repeat_fraction': 0.2, 'suites': PHASE_B,
                'protocol': 'research/HEAD_TO_HEAD_V8_PHASE_B_PROTOCOL.md', 'config': 'config/head-to-head-v8-phase-b-sonnet.json',
                'max_spend_usd': 12, 'claim': 'Held-out Q-HARNESS evidence under the pre-registered primary endpoint; one run of one frozen plan.'},
}
DEFAULT_CAMPAIGN = 'pilot-1'
# Module defaults are the pilot's; task selection (select_tasks) always uses the pilot seed so a suite's chosen
# tasks do not change between campaigns, while the order and arm balance use each campaign's own seed.
VERSION = CAMPAIGNS[DEFAULT_CAMPAIGN]['version']
SEED = CAMPAIGNS[DEFAULT_CAMPAIGN]['seed']
REPEAT_FRACTION = CAMPAIGNS[DEFAULT_CAMPAIGN]['repeat_fraction']
INFRASTRUCTURE = ('DockerNotReady', 'DockerRestartedDuringArm', 'ProviderOutcomeUnknown', 'IsolationPreflightFailed',
                  'GatewayCleanupFailure', 'IncompleteAccounting')


def write(path, value):
    Path(path).write_bytes(encoded(value) + b'\n')


# ---------------------------------------------------------------- selection, sequence, plan

def scorable(suite_name, answers):
    """Task ids whose gold passes the official scorer's self-test (benchmark.audit: the scorer must give its own
    gold full credit). Mechanical, answer-blind to the planner: the gold is read only by the scorer. A task that
    fails is never chosen for a one-per-context plan while another task of its context passes."""
    from .audit import _correct_response
    out = set()
    for task_id, gold in answers.items():
        try:
            if score_answer(suite_name, gold, _correct_response(suite_name, gold))['score'] == 1:
                out.add(task_id)
        except Exception:
            pass
    return out


def select_tasks(name, manifest, answers, rule, usable=None):
    """Task ids chosen by the rule, the seed and task identity alone; answers only supply the context grouping
    and, for one-per-context, the scorer self-test (usable)."""
    rng = random.Random(f'{SEED}:{name}:{rule}')
    ids = list(manifest['task_ids'])
    if rule == 'all':
        return ids
    if rule == 'one-per-context':
        contexts = {}
        for task_id in ids:
            contexts.setdefault(str(answers[task_id].get('context_window_id')), []).append(task_id)
        chosen = []
        for key in sorted(contexts):
            candidates = [t for t in contexts[key] if usable is None or t in usable] or contexts[key]
            chosen.append(rng.choice(candidates))
        return chosen
    if rule.startswith('seeded-'):
        return sorted(rng.sample(ids, int(rule.split('-')[1])), key=ids.index)
    raise ValueError('Unknown selection rule')


def load_suites(spec=PILOT):
    suites = {}
    for entry in spec:
        manifest, tasks, answers = read_suite(ROOT / entry['suite'])
        usable = scorable(manifest['suite'], answers) if entry['rule'] == 'one-per-context' else None
        suites[entry['name']] = {'path': entry['suite'], 'suite_sha256': manifest['suite_sha256'], 'suite': manifest['suite'],
                                 'rule': entry['rule'], 'exposure': entry['exposure'],
                                 'task_ids': select_tasks(entry['name'], manifest, answers, entry['rule'], usable),
                                 'unscorable_tasks': sorted(set(manifest['task_ids']) - usable) if usable is not None else [],
                                 'contexts': {t: str(answers[t].get('context_window_id')) for t in manifest['task_ids']},
                                 '_tasks': tasks, '_answers': answers, '_manifest': manifest}
    return suites


def public(suites):
    # unscorable_tasks appears only when non-empty, so earlier plans (pilot 1) still verify byte for byte.
    return {name: {k: v for k, v in s.items() if not k.startswith('_') and not (k == 'unscorable_tasks' and not v)}
            for name, s in suites.items()}


def sequence(suites, seed=SEED, repeat_fraction=REPEAT_FRACTION):
    """Interleaved arms: every (suite, task) once, a seeded fraction twice (fresh sessions), tasks in one seeded
    order across suites, and within each suite exactly half the tasks run Aljure first."""
    rng = random.Random(f'{seed}:sequence')
    items = [(name, task_id, 0) for name in suites for task_id in suites[name]['task_ids']]
    repeats = sorted(rng.sample(items, round(repeat_fraction * len(items))))
    items += [(name, task_id, 1) for name, task_id, _ in repeats]
    rng.shuffle(items)
    first = {}
    for name in suites:
        mine = [i for i in items if i[0] == name]
        order = ['aljure'] * (len(mine) // 2) + ['prime'] * (len(mine) - len(mine) // 2)
        rng.shuffle(order)
        first.update(dict(zip(mine, order)))
    out = []
    for name, task_id, trial in items:
        a, b = (('aljure', 'prime') if first[(name, task_id, trial)] == 'aljure' else ('prime', 'aljure'))
        for position, harness in ((1, a), (2, b)):
            out.append({'index': len(out), 'suite': name, 'task_id': task_id, 'trial': trial, 'harness': harness,
                        'position': position})
    return out


def estimate(suites, seq):
    per_arm = [COST_PRIOR[e['suite']][e['harness']] for e in seq]
    expected = sum(per_arm)
    return {'arms': len(seq), 'expected_usd': round(expected, 2), 'low_usd': round(0.7 * expected, 2),
            'high_usd': round(1.8 * expected, 2), 'basis': 'API-rate-equivalent; per-arm priors from recorded Sonnet 5.5 runs (COST_PRIOR)',
            'priors': COST_PRIOR}


MIN_ALLOWANCE_USD = 0.50


def reservation_usd(config):
    """The gateway's per-call reservation (src/repl_lab/gateway.clj reservation): the whole declared context
    bound at the highest input or cache rate plus the maximum output, released only on the receipt."""
    rates = config['rates']
    top = max(rates[k] for k in ('input', 'cache-read', 'cache-write-5m', 'cache-write-1h'))
    return (config['context_window'] * top + config['max_output_tokens'] * rates['output']) / 1_000_000


def spend_allowance_usd(config):
    """What an arm can actually spend before its next call is refused: the per-arm cap less one reservation.
    Phase B run-1 set the cap to $4.40 against a $4.33 reservation, an allowance of $0.07, and lost five
    64K arms to it (HEAD_TO_HEAD_V8_PHASE_B_RESULTS.md section 4). New plans require at least MIN_ALLOWANCE_USD."""
    return config['usd_per_arm'] - reservation_usd(config)


def plan(out, campaign=DEFAULT_CAMPAIGN):
    spec = CAMPAIGNS[campaign]
    config_path, protocol = ROOT / spec['config'], ROOT / spec['protocol']
    config = json.loads(Path(config_path).read_text())
    paired.validate_config(config)
    require(spend_allowance_usd(config) >= MIN_ALLOWANCE_USD,
            f'usd_per_arm must exceed one gateway reservation (${reservation_usd(config):.2f}) by at least ${MIN_ALLOWANCE_USD:.2f}; '
            f'allowance is ${spend_allowance_usd(config):.2f}')
    contract = paired.aljure_contract(config)
    require(not any(k in contract for k in ('artifacts', 'acquisition', 'programs', 'skill_interface')) and
            paired.execution_language(config) == 'clojure' and
            paired.aljure_sci(config)['surface'] == 'assisted' and paired.aljure_sci(config)['results'] == 'bounded',
            'The primary comparison is stateless Aljure (no artifacts, acquisition or programs) on the assisted, bounded SCI surface')
    suites = load_suites(spec['suites'])
    seq = sequence(suites, spec['seed'], spec['repeat_fraction'])
    require(money(config['usd_per_arm']) * len(seq) <= money(config['total_usd']), 'Per-arm allowances exceed the ceiling')
    if spec['max_spend_usd'] is not None:
        require(money(config['usd_per_arm']) < money(spec['max_spend_usd']), 'The per-arm cap must fit under the maximum spend')
    value = {'version': spec['version'], 'campaign': campaign, 'authorized': False, 'model_calls': 0, 'seed': spec['seed'],
             'repeat_fraction': spec['repeat_fraction'],
             'protocol_sha256': digest(protocol.read_bytes()), 'config_sha256': digest(Path(config_path).read_bytes()),
             'configs': {'aljure': config}, 'harnesses': list(HARNESSES), 'suites': public(suites), 'sequence': seq,
             'prime_commit': native.PIN, 'capabilities': paired.capabilities(config),
             'source': paired.source_snapshot(), 'runtime_source': paired.runtime_snapshot(),
             'budget': {'per_arm_usd': config['usd_per_arm'], 'aggregate_usd': config['total_usd'], 'max_spend_usd': spec['max_spend_usd'],
                        'reservation_per_call_usd': round(reservation_usd(config), 5), 'spend_allowance_per_arm_usd': round(spend_allowance_usd(config), 5),
                        'stop_rule': ('refuse the next arm when known spend plus the per-arm cap would exceed max_spend_usd'
                                      if spec['max_spend_usd'] is not None else 'refuse the next arm when spend plus the per-arm cap would exceed aggregate_usd'),
                        'calls_per_arm': config['calls_per_arm'], 'max_calls': config['calls_per_arm'] * len(seq),
                        'task_seconds': paired.task_limits(config)['task_seconds'], 'estimate': estimate(suites, seq),
                        'cost_basis': 'API-rate-equivalent subscription usage; actual invoice unknown'},
             'analysis': {'delta': DELTA, 'resamples': RESAMPLES, 'success_threshold': SUCCESS, 'claim': spec['claim'],
                          'primary': ('context-weighted mean paired deadline-aware score difference, Aljure minus Prime, over every held-out context pooled across lengths'
                                      if campaign == 'phase-b' else
                                      'context-weighted mean paired deadline-aware score difference, Aljure minus Prime, per suite'),
                          'rules': 'research/STATISTICAL_EVALUATION_PROTOCOL.md section 5'}}
    require(not value['source']['dirty'], 'Freeze from a clean committed source checkout')
    value['plan_sha256'] = digest(encoded(value))
    with Path(out).open('xb') as stream:
        stream.write(encoded(value) + b'\n')
    return value


def read_plan(path):
    value = json.loads(Path(path).read_text())
    require(digest(encoded({k: v for k, v in value.items() if k != 'plan_sha256'})) == value['plan_sha256'], 'Plan hash mismatch')
    spec = CAMPAIGNS[value.get('campaign', DEFAULT_CAMPAIGN)]
    config_path, protocol = ROOT / spec['config'], ROOT / spec['protocol']
    require(value['version'] == spec['version'] and value['protocol_sha256'] == digest(protocol.read_bytes()) and
            value['config_sha256'] == digest(config_path.read_bytes()), 'Protocol, config or version changed after freeze')
    config = value['configs']['aljure']
    paired.validate_config(config)
    require(config == json.loads(config_path.read_text()), 'Config file differs from the frozen plan')
    suites = load_suites(spec['suites'])
    require(value['suites'] == public(suites) and value['sequence'] == sequence(suites, value['seed'], value['repeat_fraction']),
            'Suites or order changed after freeze')
    require(value['source']['sha256'] == paired.source_snapshot()['sha256'] and value['runtime_source'] == paired.runtime_snapshot() and
            value['capabilities'] == paired.capabilities(config) and value['prime_commit'] == native.PIN, 'Source or capability pins changed')
    return value, suites


def preflight(path):
    value, suites = read_plan(path)
    config = value['configs']['aljure']
    ready = paired.readiness(value, config)
    if shutil.disk_usage(ROOT).free < 10 * 2**30:
        ready['blockers'].append('Less than 10 GiB free disk')
    ready['suites'] = {name: s['suite_sha256'] for name, s in suites.items()}
    ready['ready'] = not ready['blockers']
    return ready


# ---------------------------------------------------------------- answer provenance (both harnesses, same rule)

def answer_provenance(task_out, harness, config, execution):
    """How the arm's answer.txt came to exist. Aljure: a done call or an accepted terminal text reply (the
    Clojure runtime applies the contract). Prime: its /work/answer.txt, or, under text-answer-v2 only, its final
    assistant text accepted by the identical Python rule, written to answer.txt here with the provenance kept."""
    contract = paired.aljure_contract(config)
    answer = task_out / 'answer.txt'
    if harness == 'aljure':
        result = json.loads((task_out / 'agent/result.json').read_text()) if (task_out / 'agent/result.json').exists() else {}
        if not answer.exists():
            return None
        if result.get('finalization') == 'terminal-text':
            return {'source': 'terminal-text', **(result.get('finalization-provenance') or {})}
        return {'source': 'done', 'version': None}
    if answer.exists():
        return {'source': 'file', 'version': None}
    if contract['terminal_text_answer'] == paired.TERMINAL_TEXT_V2 and (execution.get('completion') or {}).get('native_exit_code') == 0:
        accepted = terminal_text.prime_terminal_answer(task_out)
        if accepted:
            answer.write_text(accepted['answer'], encoding='utf-8')
            return {'source': 'terminal-text', **accepted['provenance']}
    return None


# ---------------------------------------------------------------- per-arm measures from the recorded traces

def _transport_measures(task_out):
    rows = list(jsonl(task_out / 'gateway/transport.jsonl')) if (task_out / 'gateway/transport.jsonl').exists() else []
    started = [r['task_elapsed_ms'] for r in rows if r.get('event') == 'started']
    responses = [r for r in rows if r.get('event') == 'response']
    return {'first_request_ms': min(started) if started else None, 'requests': len(started),
            'responses': len(responses), 'http_errors': sum(1 for r in responses if r.get('http_status') != 200),
            'model_time_ms': sum(r.get('elapsed_ms') or 0 for r in responses)}


def aljure_tools(task_out):
    events = list(jsonl(task_out / 'agent/events.jsonl')) if (task_out / 'agent/events.jsonl').exists() else []
    results = [e['payload'] for e in events if e.get('type') == 'tool-result']
    return {'tool_calls': len(results), 'tool_errors': sum(1 for r in results if r.get('status') != 'ok'),
            'tool_ops': sorted({str(r.get('op')) for r in results}), 'rejections': sum(1 for e in events if e.get('type') == 'command-rejected')}


def prime_tools(task_out):
    calls, errors, stops = 0, 0, 0
    for path in sorted(glob.glob(str(task_out / 'native/sessions/*.jsonl'))):
        for line in open(path, encoding='utf-8', errors='replace'):
            try:
                record = json.loads(line)
            except ValueError:
                continue
            message = record.get('message') or {}
            if message.get('role') == 'toolResult':
                calls += 1
                content = message.get('content')
                text = ' '.join(b.get('text', '') for b in content if isinstance(b, dict)) if isinstance(content, list) else str(content)
                ok = not message.get('isError') and (message.get('details') or {}).get('status', 'ok') == 'ok' and 'Traceback' not in text
                errors += not ok
            elif message.get('role') == 'assistant' and message.get('stopReason') == 'error':
                stops += 1
    return {'tool_calls': calls, 'tool_errors': errors, 'tool_ops': ['python_repl'] if calls else [], 'provider_stop_errors': stops}


def measure_arm(task_out, harness):
    execution = json.loads((task_out / 'execution.json').read_text()) if (task_out / 'execution.json').exists() else {}
    tools = aljure_tools(task_out) if harness == 'aljure' else prime_tools(task_out)
    return {'agent_wall_ms': execution.get('wall_ms'), 'agent_failure': execution.get('failure'), **_transport_measures(task_out), **tools}


# ---------------------------------------------------------------- run

def _load_rows(out):
    path = out / 'results.jsonl'
    return list(jsonl(path)) if path.exists() else []


def run(path, out, approval, *, resume=False):
    value, suites = read_plan(path)
    require(approval == value['plan_sha256'], 'Explicit approval of this exact NEW plan required')
    ready = preflight(path)
    require(ready['ready'], 'Preflight refused: ' + '; '.join(ready['blockers']))
    config = value['configs']['aljure']
    out = Path(out).resolve()
    if resume:
        require(out.is_dir() and json.loads((out / 'plan.json').read_text()) == value, 'Resume needs the same frozen plan in the run directory')
        rows = _load_rows(out)
        require(rows and all(r['index'] == i for i, r in enumerate(rows)), 'Nothing to resume or results out of order')
        # Rows that were never attempted because an earlier failure stopped the run are retried now; completed rows stay.
        rows = [r for r in rows if r['status'] != 'not-attempted']
        require(all(r['index'] == i for i, r in enumerate(rows)), 'Only a trailing not-attempted block can be resumed')
        for stale in sorted(out.glob('[0-9][0-9][0-9]-*')):
            if int(stale.name[:3]) >= len(rows):
                shutil.rmtree(stale)
        (out / 'resumes.jsonl').open('ab').write(encoded({'time': time.time(), 'from_index': len(rows), 'preflight': ready}) + b'\n')
    else:
        out.mkdir(parents=True, exist_ok=False)
        write(out / 'plan.json', value)
        write(out / 'preflight.json', ready)
        write(out / 'authorization.json', {'approved_plan': approval, 'runner_pid': os.getpid(), 'time': time.time()})
        rows = []
    spent = sum((money(r['usage']['known_model_cost_usd']) + money(r['usage']['reserved_unknown_usd']) for r in rows), money(0))
    images = [config['execution_images']['prime'], config['execution_images']['sci']]
    pricing = {paired.RATE_KEYS[k]: v for k, v in config['rates'].items()}
    stop = None
    for entry in value['sequence'][len(rows):]:
        name, harness = entry['suite'], entry['harness']
        suite = suites[name]
        task = suite['_tasks'][entry['task_id']]
        task_out = out / f"{entry['index']:03}-{name}-{harness}"
        task_out.mkdir()
        row = {**entry, 'suite_sha256': suite['suite_sha256'], 'task_sha256': task['task_sha256'],
               'context_window_id': suite['contexts'][entry['task_id']], 'status': 'not-attempted', 'failure': stop,
               'fresh_session': True, 'harness_revision': value['source']['commit'] if harness == 'aljure' else native.PIN}
        gateway, begin = None, time.monotonic()
        try:
            require(stop is None, 'Not attempted: an earlier infrastructure failure stopped this run')
            ceiling = value['budget'].get('max_spend_usd')
            require(spent + money(config['usd_per_arm']) <= money(ceiling if ceiling is not None else value['budget']['aggregate_usd']),
                    'BudgetCeiling: the next arm could take known spend past the maximum')
            require(shutil.disk_usage(ROOT).free >= 10 * 2**30, 'Disk floor refused')
            before = paired.docker_state(images)
            write(task_out / 'docker-before.json', before)
            if paired.docker_blockers(before):
                row['failure'], stop = 'DockerNotReady', 'DockerNotReady'
            else:
                data = paired.public_input(ROOT / suite['path'], task)
                write(task_out / 'public-input.json', data)
                gateway = GatewayClient(task_out / 'gateway', paired.gateway_config(config, harness),
                                        ClaudeSubscriptionTransport(authorized=True), evidence='LIVE MODEL RUN')
                execution = paired.run_arm(harness, data, task_out, config, gateway, ready)
                row['answer_provenance'] = answer_provenance(task_out, harness, config, execution)
                row['status'], row['failure'] = paired.arm_status(execution, (task_out / 'answer.txt').exists())
                after = paired.docker_state(images)
                write(task_out / 'docker-after.json', after)
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
                except Exception as error:
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
                   usage=usage, measures=measure_arm(task_out, harness) if gateway else {}, cleanup_ok=cleanup.get('ok'),
                   budget_usd=config['usd_per_arm'], pricing_usd_per_m=pricing)
        write(task_out / 'result.json', row)
        rows.append(row)
        paired.write_jsonl(out / 'results.jsonl', rows)
    write(out / 'results.json', rows)
    report = summarize(value, rows)
    write(out / 'report.json', report)
    return report


# ---------------------------------------------------------------- statistics

def quantile(values, q):
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    position = (len(values) - 1) * q
    low, high = math.floor(position), math.ceil(position)
    return values[low] + (values[high] - values[low]) * (position - low)


def mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def sign_test(deltas):
    wins, losses = sum(d > 0 for d in deltas), sum(d < 0 for d in deltas)
    n = wins + losses
    if not n:
        return 1.0
    return min(1.0, 2 * sum(math.comb(n, k) for k in range(0, min(wins, losses) + 1)) / 2 ** n)


def mcnemar(pairs, threshold=SUCCESS):
    """Exact McNemar on success/failure at the threshold: b = Aljure success only, c = Prime success only."""
    b = sum(1 for a, p in pairs if a >= threshold > p)
    c = sum(1 for a, p in pairs if p >= threshold > a)
    return {'aljure_only_success': b, 'prime_only_success': c, 'p_exact': sign_test([1] * b + [-1] * c)}


def cluster_bootstrap(per_context, resamples=RESAMPLES, seed=0):
    """Resample contexts with replacement; the statistic is the context-weighted mean difference."""
    keys = sorted(per_context)
    if len(keys) < 2:
        return None
    rng, means = random.Random(seed), []
    for _ in range(resamples):
        draw = [per_context[rng.choice(keys)] for _ in keys]
        means.append(sum(draw) / len(draw))
    return {'ci95': [quantile(means, .025), quantile(means, .975)], 'ci90': [quantile(means, .05), quantile(means, .95)]}


def decision(estimate, interval, delta=DELTA):
    if interval is None or estimate is None:
        return 'no-interval'
    lo95, hi95 = interval['ci95']
    lo90, hi90 = interval['ci90']
    if lo95 > 0 and estimate >= delta:
        return 'superior'
    if hi95 < 0 and estimate <= -delta:
        return 'inferior'
    if -delta <= lo90 and hi90 <= delta:
        return 'equivalent'
    return 'inconclusive'


def paired_analysis(rows, contexts):
    """rows: completed-plan rows of one suite (all trials). Trials are averaged within (task, harness) before pairing."""
    by = {}
    for r in rows:
        by.setdefault((r['task_id'], r['harness']), []).append(r)
    tasks = sorted({r['task_id'] for r in rows})
    score = {(t, h): mean([x['score'] for x in by.get((t, h), [])]) for t in tasks for h in HARNESSES}
    cost = {(t, h): mean([float(x['usage']['known_model_cost_usd'] or 0) for x in by.get((t, h), [])]) for t in tasks for h in HARNESSES}
    latency = {(t, h): mean([(x.get('measures') or {}).get('agent_wall_ms') for x in by.get((t, h), [])]) for t in tasks for h in HARNESSES}
    deltas = [score[t, 'aljure'] - score[t, 'prime'] for t in tasks]
    per_context = {}
    for t, d in zip(tasks, deltas):
        per_context.setdefault(contexts[t], []).append(d)
    per_context = {c: sum(v) / len(v) for c, v in per_context.items()}
    weighted = mean(list(per_context.values()))
    # The protocol reports no cross-context interval below five independent contexts.
    interval = cluster_bootstrap(per_context) if len(per_context) >= MIN_CONTEXTS else None
    cost_deltas = [cost[t, 'aljure'] - cost[t, 'prime'] for t in tasks]
    latency_deltas = [latency[t, 'aljure'] - latency[t, 'prime'] for t in tasks if latency[t, 'aljure'] is not None and latency[t, 'prime'] is not None]
    repeats = {h: [abs(x[0]['score'] - x[1]['score']) for (t, hh), x in by.items() if hh == h and len(x) >= 2] for h in HARNESSES}
    return {'tasks': len(tasks), 'independent_contexts': len(per_context),
            'task_weighted_mean_difference': mean(deltas), 'context_weighted_mean_difference': weighted,
            'cluster_bootstrap': interval, 'decision': decision(weighted, interval),
            'wins_ties_losses': [sum(d > 0 for d in deltas), sum(d == 0 for d in deltas), sum(d < 0 for d in deltas)],
            'sign_test_p': sign_test(deltas), 'mcnemar': mcnemar([(score[t, 'aljure'], score[t, 'prime']) for t in tasks]),
            'differences': [round(d, 4) for d in deltas], 'per_context_difference': {c: round(v, 4) for c, v in sorted(per_context.items())},
            'cost_difference_usd': {'mean': mean(cost_deltas), 'per_task': [round(d, 5) for d in cost_deltas]},
            'latency_difference_ms': {'mean': mean(latency_deltas), 'n': len(latency_deltas)},
            'repeat_absolute_score_change': {h: {'n': len(v), 'mean': mean(v)} for h, v in repeats.items()}}


def harness_stats(rows):
    completed = [r for r in rows if r['status'] == 'completed']
    costs = [float(r['usage']['known_model_cost_usd'] or 0) for r in rows]
    successes = [r for r in completed if r['score'] >= SUCCESS]
    m = [r.get('measures') or {} for r in rows]
    tokens = {k: sum((r['usage'].get('known_tokens') or {}).get(k, 0) for r in rows)
              for k in ('input_tokens', 'output_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens')}
    failures = {}
    for r in rows:
        if r['status'] != 'completed':
            key = f"{r['status']}:{r.get('failure') or ''}"
            failures[key] = failures.get(key, 0) + 1
    score_sum = sum(r['score'] for r in rows)
    return {'arms': len(rows), 'deadline_aware_mean_score': score_sum / len(rows) if rows else None,
            'completed': len(completed), 'timeouts': sum(r['status'] == 'timeout' for r in rows),
            'errors': sum(r['status'] == 'error' for r in rows), 'not_attempted': sum(r['status'] == 'not-attempted' for r in rows),
            'infrastructure_failures': sum(r.get('failure') in INFRASTRUCTURE for r in rows), 'failures': failures,
            f'successes_at_{SUCCESS}': len(successes), 'cost_usd': round(sum(costs), 6),
            'cost_per_task_usd': round(sum(costs) / len(rows), 6) if rows else None,
            'cost_per_success_usd': round(sum(costs) / len(successes), 6) if successes else None,
            'cost_per_score_point_usd': round(sum(costs) / score_sum, 6) if score_sum else None,
            'model_calls': sum(r['usage'].get('calls', 0) for r in rows), 'tokens': tokens,
            'latency_s': {'agent_p50': (quantile([x.get('agent_wall_ms') for x in m], .5) or 0) / 1000 if m else None,
                          'agent_p95': (quantile([x.get('agent_wall_ms') for x in m], .95) or 0) / 1000 if m else None,
                          'driver_p50': (quantile([r['wall_time_ms'] for r in rows], .5) or 0) / 1000 if rows else None,
                          'driver_p95': (quantile([r['wall_time_ms'] for r in rows], .95) or 0) / 1000 if rows else None,
                          'first_request_p50': (quantile([x.get('first_request_ms') for x in m], .5) or 0) / 1000 if m else None},
            'tools': {'calls': sum(x.get('tool_calls', 0) for x in m), 'errors': sum(x.get('tool_errors', 0) for x in m),
                      'error_rate': (sum(x.get('tool_errors', 0) for x in m) / sum(x.get('tool_calls', 0) for x in m))
                      if sum(x.get('tool_calls', 0) for x in m) else None,
                      'http_errors': sum(x.get('http_errors', 0) for x in m),
                      'aljure_rejections': sum(x.get('rejections', 0) for x in m), 'prime_stop_errors': sum(x.get('provider_stop_errors', 0) for x in m)}}


def pareto(points):
    """points: {'suite:harness': (score, cost, latency)}; higher score, lower cost and lower latency are better.
    Dominance is judged only within a suite: suites are never pooled or compared with each other."""
    def dominates(a, b):
        return a[0] >= b[0] and a[1] <= b[1] and a[2] <= b[2] and a != b
    return {label: {'score': p[0], 'cost_per_task_usd': p[1], 'latency_p50_s': p[2],
                    'dominated_by': [o for o, q in points.items()
                                     if o != label and o.split(':')[0] == label.split(':')[0] and dominates(q, p)]}
            for label, p in points.items()}


def summarize(value, rows):
    rows = list(rows)
    report = {'version': value.get('version'), 'campaign': value.get('campaign'), 'plan_sha256': value['plan_sha256'], 'arms_planned': len(value['sequence']),
              'arms_recorded': len(rows), 'complete': len(rows) == len(value['sequence']) and all(r['status'] != 'not-attempted' for r in rows),
              'stopped_by': next((r['failure'] for r in rows if r['status'] == 'not-attempted'), None),
              'claim': (value.get('analysis') or {}).get('claim', 'Development pilot on pinned official inputs; descriptive; no held-out or superiority claim.'),
              'suites': {}, 'overall': {}}
    points = {}
    for name, suite in value['suites'].items():
        mine = [r for r in rows if r['suite'] == name]
        if not mine:
            continue
        stats = {h: harness_stats([r for r in mine if r['harness'] == h]) for h in HARNESSES}
        report['suites'][name] = {'suite_sha256': suite['suite_sha256'], 'exposure': suite['exposure'], 'per_harness': stats,
                                  'paired': paired_analysis(mine, suite['contexts']) if all(stats[h]['arms'] for h in HARNESSES) else None}
        for h in HARNESSES:
            if stats[h]['arms']:
                points[f'{name}:{h}'] = (stats[h]['deadline_aware_mean_score'], stats[h]['cost_per_task_usd'], stats[h]['latency_s']['agent_p50'])
    report['overall'] = {h: harness_stats([r for r in rows if r['harness'] == h]) for h in HARNESSES}
    if value.get('campaign') == 'phase-b' and rows:
        contexts = {}
        for name, suite in value['suites'].items():
            contexts.update({f"{name}:{t}": f"{name}:{c}" for t, c in suite['contexts'].items()})
        pooled = [{**r, 'task_id': f"{r['suite']}:{r['task_id']}"} for r in rows]
        report['primary_pooled'] = paired_analysis(pooled, contexts) if all(report['overall'][h]['arms'] for h in HARNESSES) else None
    report['pareto'] = pareto(points)
    report['infrastructure_failure_rate'] = {h: (report['overall'][h]['infrastructure_failures'] / report['overall'][h]['arms'])
                                             if report['overall'][h]['arms'] else None for h in HARNESSES}
    report['cost_total_usd'] = round(sum(float(r['usage']['known_model_cost_usd'] or 0) for r in rows), 6)
    report['accounting_complete'] = all(r['usage']['accounting_complete'] for r in rows)
    return report


# ---------------------------------------------------------------- CLI

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', choices=['plan', 'preflight', 'run', 'report', 'estimate'])
    parser.add_argument('--plan')
    parser.add_argument('--out')
    parser.add_argument('--suite', help='accepted for the host launcher; the plan binds every suite itself')
    parser.add_argument('--authorize-subscription-plan')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--campaign', choices=sorted(CAMPAIGNS), default=DEFAULT_CAMPAIGN)
    args = parser.parse_args(argv)
    if args.command == 'plan':
        value = plan(args.out, args.campaign)
        print(json.dumps({'plan_sha256': value['plan_sha256'], 'arms': len(value['sequence']), 'estimate': value['budget']['estimate']}, indent=2))
    elif args.command == 'estimate':
        spec = CAMPAIGNS[args.campaign]
        suites = load_suites(spec['suites'])
        print(json.dumps(estimate(suites, sequence(suites, spec['seed'], spec['repeat_fraction'])), indent=2))
    elif args.command == 'preflight':
        print(json.dumps(preflight(args.plan), indent=2))
    elif args.command == 'run':
        report = run(args.plan, args.out, args.authorize_subscription_plan, resume=args.resume)
        print(json.dumps({k: report[k] for k in ('complete', 'stopped_by', 'cost_total_usd', 'arms_recorded')}, indent=2))
    elif args.command == 'report':
        out = Path(args.out)
        value = json.loads((out / 'plan.json').read_text())
        report = summarize(value, _load_rows(out))
        write(out / 'report.json', report)
        print(json.dumps(report, indent=2)[:4000])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
