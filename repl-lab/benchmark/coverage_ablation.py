"""Evidence-coverage ablation on fresh development contexts (research/EVIDENCE_COVERAGE_DEV_PROTOCOL.md).

Six arms per task, one frozen plan, seeded arm order per task, three label-judgement tasks repeated:
  A0   Aljure, text-answer-v2, no verification contract                      (reference)
  AU   A0 + structured_labels + uncertainty_audit                            (the existing audit contract; the baseline)
  AC   A0 + evidence_coverage                                                (the coverage instruction, no audit)
  AUC  AU + evidence_coverage                                                (both)
  P0   native Prime, unchanged                                               (the competitive baseline)
  PC   native Prime + the same coverage instruction as a prompt             (mechanism control)
Strata (fixed by the suite): label-judgement (fresh contexts; the only stratum of the primary), structural (questions
answered from dates or user ids; negative control), audit-correct (two earlier tasks the audit arm got right on every
trial; negative control). Pre-registered primary: AC - AU on the label-judgement stratum, context-weighted paired score
difference, 10,000-resample cluster bootstrap over contexts.

Budget: four concurrent provider reservations per arm (usd_per_arm = 4 x the gateway reservation + $0.50); an arm starts
only if known spend plus unknown reservations plus usd_per_arm fits under MAX_SPEND_USD, so spend plus outstanding
reservations never exceeds it. No inference except `run` with the exact approved hash.
"""
import argparse
import json
import os
from pathlib import Path
import random
import shutil
import time

from . import coverage
from . import headtohead as h
from . import paired
from .gateway_client import GatewayClient, ClaudeSubscriptionTransport
from .official import score_answer
from .oolong import account, digest, encoded, jsonl, money, require
from .prime import container as native

ROOT = paired.ROOT
VERSION = 'evidence-coverage-dev-v1'
SEED = 2026110412
REPEATS = 3                      # label-judgement tasks run twice (fresh sessions), a seeded choice
MAX_SPEND_USD = 28.2             # reservation ceiling: known spend + unknown reservations + one per-arm cap never exceeds it
CONCURRENCY = 4                  # provider calls in flight inside one arm (native Prime's observed subagent fan-out)
HIGH_MULTIPLIER = 1.8
PROTOCOL = ROOT / 'research/EVIDENCE_COVERAGE_DEV_PROTOCOL.md'
BASE_CONFIG = ROOT / 'config/evidence-coverage-dev-sonnet.json'
SUITES = [{'name': 'coverage', 'suite': 'var/official/coverage-dev', 'rule': 'all',
           'exposure': 'development: twelve fresh context windows (no earlier suite holds them), plus two exposed audit-correct controls'}]
PRIMARY_STRATUM = 'label-judgement'
STRATA = ('label-judgement', 'structural', 'audit-correct')
BASE = {'terminal_text_answer': 'text-answer-v2'}
AUDIT = {'structured_labels': True, 'uncertainty_audit': True}
ARMS = {
    'A0': {'harness': 'aljure', 'aljure_contract': {**BASE}},
    'AU': {'harness': 'aljure', 'aljure_contract': {**BASE, **AUDIT}},
    'AC': {'harness': 'aljure', 'aljure_contract': {**BASE, 'evidence_coverage': True}},
    'AUC': {'harness': 'aljure', 'aljure_contract': {**BASE, **AUDIT, 'evidence_coverage': True}},
    'P0': {'harness': 'prime'},
    'PC': {'harness': 'prime', 'prime_contract': {'coverage_prompt': True}},
}
# Lists, not tuples: the plan is JSON and read_plan compares it with these constants after a round trip. [treated, control].
CONTRASTS = {'coverage_vs_audit': ['AC', 'AU'], 'coverage_added_to_audit': ['AUC', 'AU'], 'coverage_alone': ['AC', 'A0'],
             'audit_replication': ['AU', 'A0'], 'coverage_in_prime': ['PC', 'P0'], 'aljure_audit_vs_prime': ['AU', 'P0'],
             'aljure_coverage_vs_prime': ['AC', 'P0'], 'aljure_both_vs_prime': ['AUC', 'P0']}
PRIMARY = 'coverage_vs_audit'
MECHANISM = {'aljure': ['AC', 'A0'], 'prime': ['PC', 'P0']}      # (AC - A0) - (PC - P0): the harness-specific part
WORK_CONTRASTS = ('coverage_vs_audit', 'coverage_added_to_audit', 'coverage_alone', 'coverage_in_prime')
GO = {'control': 'AU', 'candidates': ['AC', 'AUC'], 'min_gain': 0.10, 'lower_bound_above': 0.0,
      'max_cost_ratio_to_prime': 0.50, 'prime_arm': 'P0'}
# Expected USD per arm, by context length class. A0, AU, P0 are the recorded means of the verification ablation
# (8K, 32K) and Phase B; AC, AUC and PC have never run and are set above their nearest recorded analogue.
COST_PRIOR = {'short': {'A0': 0.017, 'AU': 0.021, 'AC': 0.030, 'AUC': 0.035, 'P0': 0.050, 'PC': 0.060},
              'long': {'A0': 0.018, 'AU': 0.050, 'AC': 0.060, 'AUC': 0.080, 'P0': 0.055, 'PC': 0.100}}
SHORT_MAX = 8192


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


def strata_of(suites):
    """{task_id: stratum} and {task_id: context length} from the suite manifest (fixed when the suite was built)."""
    selection = suites['coverage']['_manifest']['selection']
    strata = {task: stratum for stratum, ids in selection['strata'].items() for task in ids}
    require(set(strata) == set(suites['coverage']['task_ids']) and set(strata.values()) == set(STRATA), 'Suite strata differ from the protocol')
    return strata, dict(selection['lengths'])


def sequence(suites, seed=SEED, repeats=REPEATS):
    """Every task once and a seeded choice of `repeats` label-judgement tasks twice; one seeded task order; within each
    item the six arms run back to back in a seeded order, rotated so each arm is first equally often."""
    strata, _ = strata_of(suites)
    rng = random.Random(f'{seed}:sequence')
    items = [(name, task_id, 0) for name in suites for task_id in suites[name]['task_ids']]
    primary = sorted(i for i in items if strata[i[1]] == PRIMARY_STRATUM)
    items += [(name, task_id, 1) for name, task_id, _ in sorted(rng.sample(primary, repeats))]
    rng.shuffle(items)
    labels = list(ARMS)
    out = []
    for i, (name, task_id, trial) in enumerate(items):
        order = labels[i % len(labels):] + labels[:i % len(labels)]
        tail = order[1:]
        rng.shuffle(tail)
        for position, label in enumerate([order[0]] + tail, 1):
            out.append({'index': len(out), 'suite': name, 'task_id': task_id, 'trial': trial, 'arm': label,
                        'harness': ARMS[label]['harness'], 'position': position, 'stratum': strata[task_id]})
    return out


def estimate(seq, lengths):
    by_arm = {label: 0.0 for label in ARMS}
    for entry in seq:
        by_arm[entry['arm']] += COST_PRIOR['short' if lengths[entry['task_id']] <= SHORT_MAX else 'long'][entry['arm']]
    expected = sum(by_arm.values())
    return {'arms': len(seq), 'expected_usd': round(expected, 2), 'low_usd': round(0.7 * expected, 2),
            'high_usd': round(HIGH_MULTIPLIER * expected, 2), 'expected_by_arm_usd': {k: round(v, 3) for k, v in by_arm.items()},
            'basis': 'per-arm priors by context length (recorded means of the verification ablation and Phase B for A0, AU, P0; '
                     'AC, AUC and PC unmeasured, set above their nearest analogue); high = 1.8 x expected. If spend passes the '
                     'high estimate the stop rule ends the run with not-attempted arms; it cannot overspend.'}


def budget(config, seq, lengths):
    est = estimate(seq, lengths)
    policy = h.reservation_policy(config, est['high_usd'])
    return {'per_arm_usd': config['usd_per_arm'], 'max_spend_usd': MAX_SPEND_USD, 'reservation_policy': policy,
            'required_ceiling_usd': policy['required_ceiling_usd'],
            'maximum_reservation_exposure_usd': MAX_SPEND_USD,
            'run_can_spend_until_usd': round(MAX_SPEND_USD - config['usd_per_arm'], 2),
            'stop_rule': 'refuse the next arm when known spend plus unknown reservations plus the per-arm cap would exceed max_spend_usd',
            'calls_per_arm': config['calls_per_arm'], 'task_seconds': paired.task_limits(config)['task_seconds'], 'estimate': est}


def plan(out):
    configs = configs_of()
    for config in configs.values():
        h.check_reservation_policy(config)
    base = configs['A0']
    require(base['concurrent_requests'] == CONCURRENCY == h.admitted_concurrency(base), 'The per-arm cap must admit exactly the declared concurrency')
    suites = h.load_suites(SUITES)
    strata, lengths = strata_of(suites)
    seq = sequence(suites)
    money_plan = budget(base, seq, lengths)
    require(money_plan['required_ceiling_usd'] <= MAX_SPEND_USD, 'The high spend estimate plus one per-arm cap exceeds the ceiling')
    require(money(base['total_usd']) == money(MAX_SPEND_USD), 'config total_usd must equal the reservation ceiling')
    value = {'version': VERSION, 'authorized': False, 'model_calls': 0, 'seed': SEED, 'repeats': REPEATS,
             'protocol_sha256': digest(PROTOCOL.read_bytes()), 'base_config_sha256': digest(BASE_CONFIG.read_bytes()),
             'arms': ARMS, 'configs': configs, 'contrasts': CONTRASTS, 'primary': PRIMARY, 'primary_stratum': PRIMARY_STRATUM,
             'mechanism_control': MECHANISM, 'go_rule': GO, 'suites': h.public(suites), 'strata': strata, 'lengths': lengths,
             'sequence': seq, 'prime_commit': native.PIN,
             'capabilities': {label: paired.capabilities(config) for label, config in configs.items()},
             'source': paired.source_snapshot(), 'runtime_source': paired.runtime_snapshot(), 'budget': money_plan,
             'analysis': {'delta': h.DELTA, 'resamples': h.RESAMPLES, 'success_threshold': h.SUCCESS, 'min_contexts': h.MIN_CONTEXTS,
                          'primary': 'AC minus AU on the label-judgement stratum, context-weighted mean paired deadline-aware score '
                                     'difference, repeats averaged within task, 10,000-resample cluster bootstrap over contexts',
                          'claim': 'Development ablation on fresh development contexts; no held-out or superiority claim.'}}
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
    require(value['configs'] == configs_of() and value['arms'] == ARMS and value['contrasts'] == CONTRASTS and value['primary'] == PRIMARY and
            value['mechanism_control'] == MECHANISM and value['go_rule'] == GO and value['primary_stratum'] == PRIMARY_STRATUM,
            'Arms, configs or pre-registered analysis changed')
    suites = h.load_suites(SUITES)
    strata, lengths = strata_of(suites)
    seq = sequence(suites, value['seed'], value['repeats'])
    require(value['suites'] == h.public(suites) and value['strata'] == strata and value['lengths'] == lengths and value['sequence'] == seq,
            'Suite, strata or order changed')
    require(value['budget'] == budget(value['configs']['A0'], seq, lengths) and value['budget']['max_spend_usd'] == MAX_SPEND_USD,
            'Budget policy changed')
    require(value['source']['sha256'] == paired.source_snapshot()['sha256'] and value['runtime_source'] == paired.runtime_snapshot() and
            value['capabilities'] == {l: paired.capabilities(c) for l, c in value['configs'].items()} and value['prime_commit'] == native.PIN,
            'Source or capability pins changed')
    return value, suites


def preflight(path):
    value, suites = read_plan(path)
    ready = paired.readiness(value, value['configs']['A0'])
    for label, config in value['configs'].items():
        try:
            paired.validate_config(config)
            h.check_reservation_policy(config)
            contract = paired.aljure_contract(config)
            if value['arms'][label]['harness'] == 'aljure' and contract['structured_labels']:
                require((ROOT / 'resources/sci-verify.edn').exists(), 'sci-verify.edn missing')
            if value['arms'][label]['harness'] == 'aljure' and contract['evidence_coverage']:
                require((ROOT / 'resources/evidence-coverage.txt').exists(), 'evidence-coverage.txt missing')
            if paired.prime_contract(config)['coverage_prompt']:
                require((ROOT / 'resources/prime-evidence-coverage.txt').exists(), 'prime-evidence-coverage.txt missing')
        except Exception as error:
            ready['blockers'].append(f'{label}: {error}')
    if shutil.disk_usage(ROOT).free < 10 * 2**30:
        ready['blockers'].append('Less than 10 GiB free disk')
    ready['suites'] = {name: s['suite_sha256'] for name, s in suites.items()}
    ready['budget'] = {k: value['budget'][k] for k in ('per_arm_usd', 'max_spend_usd', 'required_ceiling_usd')}
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
    ceiling = money(value['budget']['max_spend_usd'])
    # Known spend plus every reservation whose outcome is unknown: both count against the ceiling.
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
               'context_window_id': suite['contexts'][entry['task_id']], 'context_len': value['lengths'][entry['task_id']],
               'status': 'not-attempted', 'failure': stop, 'fresh_session': True,
               'harness_revision': value['source']['commit'] if harness == 'aljure' else native.PIN}
        gateway, begin = None, time.monotonic()
        try:
            require(stop is None, 'Not attempted: an earlier infrastructure failure stopped this run')
            require(spent + money(config['usd_per_arm']) <= ceiling,
                    'BudgetCeiling: known spend plus outstanding reservations plus the per-arm cap would pass the ceiling')
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
        try:
            covered = coverage.measure(task_out, harness) if gateway else None
        except Exception as error:               # a measurement, never a reason to lose the arm's record
            covered = {'error': type(error).__name__}
        row.update(score=float(scored['score']), parse_confidence=scored['parse_confidence'], attempted_parse=scored['attempted_parse'],
                   answer_sha256=digest(answer.encode()) if answer is not None else None, wall_time_ms=(time.monotonic() - begin) * 1000,
                   usage=usage, measures=h.measure_arm(task_out, harness) if gateway else {}, coverage=covered,
                   cleanup_ok=cleanup.get('ok'), budget_usd=config['usd_per_arm'], pricing_usd_per_m=pricing,
                   spend_after_usd=float(spent))
        h.write(task_out / 'result.json', row)
        rows.append(row)
        paired.write_jsonl(out / 'results.jsonl', rows)
    h.write(out / 'results.json', rows)
    report = summarize(value, rows)
    h.write(out / 'report.json', report)
    return report


# ---------------------------------------------------------------- analysis

def _mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def work(row):
    """What one arm did, as plain numbers (None when not recorded)."""
    tokens = (row.get('usage') or {}).get('known_tokens') or {}
    measures, covered = row.get('measures') or {}, row.get('coverage') or {}
    return {'cost_usd': float((row.get('usage') or {}).get('known_model_cost_usd') or 0),
            'model_calls': (row.get('usage') or {}).get('calls'),
            'input_tokens': sum(tokens.get(k, 0) for k in ('input_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens')) if tokens else None,
            'output_tokens': tokens.get('output_tokens'), 'tool_calls': measures.get('tool_calls'),
            'latency_s': measures['agent_wall_ms'] / 1000 if measures.get('agent_wall_ms') is not None else None,
            'coverage_seen': covered.get('seen_fraction'), 'coverage_full': covered.get('full_fraction'),
            'output_chars_read': covered.get('output_chars'), 'completed': 1.0 if row['status'] == 'completed' else 0.0,
            'score': row['score']}


WORK_KEYS = ('score', 'cost_usd', 'model_calls', 'input_tokens', 'output_tokens', 'tool_calls', 'latency_s', 'coverage_seen',
             'coverage_full', 'output_chars_read', 'completed')


def arm_work(rows):
    return {key: _mean([work(r)[key] for r in rows]) for key in WORK_KEYS} | {'arms': len(rows)}


def work_difference(rows, treated, control):
    """Mean paired difference (treated - control) of every work measure, trials averaged within task first."""
    by = {}
    for r in rows:
        if r['arm'] in (treated, control):
            by.setdefault((r['task_id'], r['arm']), []).append(work(r))
    tasks = sorted({t for t, _ in by})
    out = {'tasks': len(tasks)}
    for key in WORK_KEYS:
        deltas = []
        for t in tasks:
            a, b = _mean([w[key] for w in by.get((t, treated), [])]), _mean([w[key] for w in by.get((t, control), [])])
            if a is not None and b is not None:
                deltas.append(a - b)
        out[key] = _mean(deltas)
    return out


def contrast(rows, contexts, treated, control):
    """h.paired_analysis with the treated arm playing 'aljure' and the control 'prime' (difference = treated - control)."""
    relabelled = [{**r, 'harness': 'aljure' if r['arm'] == treated else 'prime'} for r in rows if r['arm'] in (treated, control)]
    return h.paired_analysis(relabelled, contexts) if relabelled else None


def mechanism(rows, contexts, spec):
    """(treated - control in Aljure) - (treated - control in Prime), per task, clustered by context."""
    by = {}
    for r in rows:
        by.setdefault((r['task_id'], r['arm']), []).append(r['score'])
    (at, ac), (pt, pc) = spec['aljure'], spec['prime']
    per = {}
    for task in sorted({t for t, _ in by}):
        values = [_mean(by.get((task, label), [])) for label in (at, ac, pt, pc)]
        if None not in values:
            per.setdefault(contexts[task], []).append((values[0] - values[1]) - (values[2] - values[3]))
    per = {c: sum(v) / len(v) for c, v in per.items()}
    if not per:
        return None
    estimate_ = sum(per.values()) / len(per)
    interval = h.cluster_bootstrap(per) if len(per) >= h.MIN_CONTEXTS else None
    return {'estimate': estimate_, 'contexts': len(per), 'cluster_bootstrap': interval, 'decision': h.decision(estimate_, interval)}


def summarize(value, rows):
    rows = [{**r, 'stratum': r.get('stratum') or value['strata'][r['task_id']]} for r in rows]
    contexts = {t: f"coverage:{c}" for t, c in value['suites']['coverage']['contexts'].items()}
    of = {s: [r for r in rows if r['stratum'] == s] for s in STRATA}
    primary_rows = of[value['primary_stratum']]
    report = {'version': VERSION, 'plan_sha256': value['plan_sha256'], 'arms_planned': len(value['sequence']), 'arms_recorded': len(rows),
              'complete': len(rows) == len(value['sequence']) and all(r['status'] != 'not-attempted' for r in rows),
              'stopped_by': next((r['failure'] for r in rows if r['status'] == 'not-attempted'), None),
              'claim': value['analysis']['claim'],
              'per_arm': {s: {label: {**h.harness_stats([r for r in of[s] if r['arm'] == label]),
                                      'work': arm_work([r for r in of[s] if r['arm'] == label])} for label in value['arms']} for s in STRATA},
              'contrasts': {name: {**(contrast(primary_rows, contexts, t, c) or {}), 'work_difference': work_difference(primary_rows, t, c)}
                            for name, (t, c) in value['contrasts'].items()},
              'cost_total_usd': round(sum(float(r['usage']['known_model_cost_usd'] or 0) for r in rows), 6),
              'accounting_complete': all(r['usage']['accounting_complete'] for r in rows)}
    report['primary'] = {'name': value['primary'], 'stratum': value['primary_stratum'], **report['contrasts'][value['primary']]}
    report['mechanism_control'] = mechanism(primary_rows, contexts, value['mechanism_control'])
    # Negative controls: did the coverage instruction add work where it could not help?
    control = value['go_rule']['control']
    scores = {}
    for r in primary_rows:
        if r['arm'] == control:
            scores.setdefault(r['task_id'], []).append(r['score'])
    already = sorted(t for t, v in scores.items() if all(x >= 1.0 for x in v))
    subsets = {'structural': of['structural'], 'audit-correct': of['audit-correct'],
               'fresh-audit-already-correct': [r for r in primary_rows if r['task_id'] in already]}
    report['negative_controls'] = {
        name: {'tasks': len({r['task_id'] for r in sub}),
               'per_arm': {label: arm_work([r for r in sub if r['arm'] == label]) for label in value['arms']},
               'work_difference': {c: work_difference(sub, *value['contrasts'][c]) for c in WORK_CONTRASTS}}
        for name, sub in subsets.items()}
    report['negative_controls']['fresh-audit-already-correct']['note'] = (
        'Selected on the audit arm scoring 1.0 in this run: its score difference is biased against the treated arm '
        '(regression to the mean); read the work measures, not the score.')
    prime = report['per_arm'][value['primary_stratum']][value['go_rule']['prime_arm']]['cost_per_task_usd']
    go = {}
    for label in value['go_rule']['candidates']:
        name = next(n for n, pair in value['contrasts'].items() if pair == [label, control])
        result = report['contrasts'][name]
        gain, interval = result.get('context_weighted_mean_difference'), result.get('cluster_bootstrap')
        cost = report['per_arm'][value['primary_stratum']][label]['cost_per_task_usd']
        ratio = cost / prime if (cost is not None and prime) else None
        lower = interval['ci95'][0] if interval else None
        go[label] = {'contrast': name, 'gain': gain, 'lower_bound': lower, 'cost_ratio_to_prime': ratio,
                     'primary_endpoint': name == value['primary'],
                     'go': bool(gain is not None and gain >= value['go_rule']['min_gain'] and lower is not None and
                                lower > value['go_rule']['lower_bound_above'] and ratio is not None and
                                ratio <= value['go_rule']['max_cost_ratio_to_prime'])}
    report['go_rule'] = {**value['go_rule'], 'results': go}
    points = {label: (s['deadline_aware_mean_score'], s['cost_per_task_usd'], s['latency_s']['agent_p50'])
              for label, s in report['per_arm'][value['primary_stratum']].items() if s['arms']}
    report['pareto'] = h.pareto({f'label-judgement:{k}': v for k, v in points.items()})
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', choices=['plan', 'preflight', 'run', 'report', 'estimate'])
    parser.add_argument('--plan')
    parser.add_argument('--out')
    parser.add_argument('--suite', help='accepted for the host launcher; the plan binds its suite itself')
    parser.add_argument('--authorize-subscription-plan')
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args(argv)
    if args.command == 'plan':
        value = plan(args.out)
        print(json.dumps({'plan_sha256': value['plan_sha256'], 'arms': len(value['sequence']), 'budget': value['budget']}, indent=2))
    elif args.command == 'estimate':
        suites = h.load_suites(SUITES)
        seq = sequence(suites)
        print(json.dumps(budget(configs_of()['A0'], seq, strata_of(suites)[1]), indent=2))
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
