"""Offline benchmark audit. Reads local suites, proofs and recorded runs only.

Checks suite integrity and gold isolation, runs the official scorer against
real gold answers, verifies that environment proofs match the current code,
re-scores every recorded run independently, and computes paired statistics
that treat tasks sharing a context as one cluster. No inference.
"""
import ast
import hashlib
import json
import math
import random
import stat
from pathlib import Path

from .official import score_answer
from .oolong import compare, digest, jsonl, read_suite

ROOT = Path(__file__).resolve().parents[1]
GOLD_FIELDS = {'answer', 'answers', 'gold', 'label', 'labels', 'target', 'expected'}
REPORT_KEYS = ('mean_score', 'wins_ties_losses', 'accounting_complete', 'results_sha256', 'scorer_sha256')
# Cross-context uncertainty needs enough independent contexts to resample.
MIN_CLUSTERS_FOR_INTERVAL = 5


def _private(path):
    return stat.S_IMODE(path.stat().st_mode) & 0o077 == 0


def audit_suite(root):
    """Integrity (via read_suite), gold isolation and context grouping."""
    root = Path(root)
    manifest, tasks, answers = read_suite(root)
    public_fields = set().union(*(set(task) for task in tasks.values()))
    public_text = (root / 'public/tasks.jsonl').read_text(errors='replace') + ''.join(
        (root / 'public' / path).read_text(errors='replace') for path in {t['context_path'] for t in tasks.values()})
    # Short golds (a single number or label) can occur in context by chance.
    leaked = sorted(t for t, a in answers.items()
                    if isinstance(a.get('answer'), str) and len(a['answer']) >= 24 and a['answer'] in public_text)
    groups = {}
    for task_id, answer in answers.items():
        groups.setdefault(str(answer.get('context_window_id')), []).append(task_id)
    controller = root / 'controller'
    return {'suite': root.name, 'suite_sha256': manifest['suite_sha256'], 'benchmark': manifest['suite'],
            'input_provenance': manifest['input_provenance'], 'selection': manifest.get('selection'),
            'tasks': len(tasks), 'independent_contexts': len(groups), 'context_groups': groups,
            'checks': {'integrity': True, 'public_has_no_gold_fields': not public_fields & GOLD_FIELDS,
                       'gold_text_absent_from_public': not leaked,
                       'controller_private': _private(controller) and all(_private(p) for p in controller.iterdir())},
            'leaked_tasks': leaked}


def scorer_selftest(root):
    """The pinned official scorer against real gold answers."""
    manifest, _, answers = read_suite(root)
    suite, failures = manifest['suite'], []
    for task_id, gold in answers.items():
        text = gold['answer']
        def score(output):
            return score_answer(suite, gold, output)['score']
        checks = {'gold_scores_one': score(_correct_response(suite, gold)) == 1}
        pairs = [line for line in text.splitlines() if line.strip()] if suite == 'oolong-pairs' else []
        if len(pairs) >= 2:
            swapped = '\n'.join(_swap(line) for line in pairs)
            checks.update({'order_invariant': score('\n'.join(reversed(pairs))) == 1,
                           'within_pair_order_invariant': score(swapped) == 1,
                           'duplicates_not_rewarded': score(text + '\n' + text) == 1,
                           'partial_credit_between': 0 < score('\n'.join(pairs[:len(pairs) // 2])) < 1,
                           'empty_scores_zero': score('') == 0,
                           'wrong_pair_lowers_score': score(text + '\n(1, 2)') < 1})
        elif suite != 'oolong-pairs':
            checks['empty_not_full_credit'] = score('') < 1
        failed = sorted(k for k, ok in checks.items() if not ok)
        if failed:
            failures.append({'task_id': task_id, 'failed': failed})
    return {'suite': Path(root).name, 'benchmark': suite, 'scorer_sha256': manifest['scorer_sha256'],
            'tasks': len(answers), 'passed': not failures, 'failures': failures}


def _correct_response(suite, gold):
    """A correct model response for this gold. OOLONG-synth stores gold as a
    list literal ("[997]"); its scorer expects the value itself ("Answer: 997")."""
    if suite == 'oolong-synth':
        try:
            value = ast.literal_eval(gold['answer'])
        except (ValueError, SyntaxError):
            return gold['answer']
        return f'Answer: {value[0]}' if isinstance(value, list) and value else gold['answer']
    return gold['answer']


def _swap(line):
    inner = line.strip()
    if inner.startswith('(') and inner.endswith(')') and inner.count(',') == 1:
        a, b = (part.strip() for part in inner[1:-1].split(','))
        return f'({b}, {a})'
    return line


UPSTREAM = ROOT / 'var/upstream-metadata'
PRIME_ENV = UPSTREAM / 'prime-research/environments/long_context'


def _git_blob(data):
    return hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest()


def _upstream_source(relative):
    """A cached upstream file, verified against the pinned research-environments tree."""
    tree = json.loads((UPSTREAM / 'research-environments-tree.json').read_text())
    path = 'environments/long_context/' + relative
    expected = next(item['sha'] for item in tree['tree'] if item['path'] == path)
    data = (PRIME_ENV / relative).read_bytes()
    if _git_blob(data) != expected:
        raise ValueError(f'Cached upstream {path} differs from pinned tree {tree["sha"]}')
    return data.decode(), tree['sha']


def _functions(source, names):
    return {node.name: node for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef) and node.name in names}


def scorer_equivalence(synth_suite=None):
    """Pairs: the vendored functions equal the pinned upstream ones exactly.
    Synth: our scorer (original OOLONG) against Prime's environment scorer."""
    names = ('_strip_think_tags', '_parse_pairs', '_pair_metrics')
    upstream, commit = _upstream_source('oolong_pairs/oolong_pairs/taskset.py')
    ours = _functions((ROOT / 'benchmark/vendor/oolong_pairs.py').read_text(), names)
    theirs = _functions(upstream, names)
    pairs = {'upstream_commit': commit, 'functions': list(names),
             'identical': all(n in ours and n in theirs and ast.dump(ours[n]) == ast.dump(theirs[n]) for n in names)}
    report = {'oolong_pairs': pairs}
    if synth_suite and Path(synth_suite).exists():
        source, _ = _upstream_source('oolong_synth/oolong_synth/taskset.py')
        module = ast.Module(body=list(_functions(source, ('attempt_answer_parse', 'parse_gold', 'score')).values()),
                            type_ignores=[])
        scope = {}
        exec('import ast\nfrom datetime import datetime', scope)
        exec(compile(module, 'prime-oolong-synth-taskset', 'exec'), scope)
        _, _, answers = read_suite(synth_suite)
        compared, disagreements = 0, []
        for task_id, gold in answers.items():
            value = _correct_response('oolong-synth', gold).removeprefix('Answer: ')
            outputs = [f'Answer: {value}', value, f'**{value}**', f'The answer is: {value}', f'Answer: [{value}]',
                       f'After counting every relevant line in the context window the final result is {value}',
                       f'Answer: {value} ', '']
            if gold.get('answer_type') == 'ANSWER_TYPE.NUMERIC' and str(value).lstrip('-').isdigit():
                outputs += [f'Answer: {int(value) + 1}', f'Answer: {int(value) + 3}']
            for output in outputs:
                mine = score_answer('oolong-synth', gold, output)['score']
                prime = scope['score'](gold['answer'], gold.get('answer_type', ''), output)
                compared += 1
                if abs(mine - prime) > 1e-9:
                    disagreements.append({'task_id': task_id, 'answer_type': gold.get('answer_type'), 'output': output[:80],
                                          'original_oolong': mine, 'prime_environment': prime})
        report['oolong_synth'] = {'ours': 'abertsch72/oolong synth_process_response (vendored)',
                                  'prime': f'research-environments {commit} oolong_synth score()',
                                  'compared': compared, 'disagreements': disagreements}
    return report


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def environment(root=ROOT):
    """Whether each recorded proof exists, passed and matches the current code."""
    root = Path(root)
    def load(name):
        path = root / 'var' / name
        return json.loads(path.read_text()) if path.exists() else None
    supervisor = _sha(root / 'scripts/isolation.py')
    current = {'contract-sha256': _sha(root / 'resources/sci-contract.json'),
               'prelude-sha256': _sha(root / 'resources/sci-prelude.edn'),
               'model-protocol-sha256': _sha(root / 'src/repl_lab/model_protocol.clj')}
    report = {}
    for bound, suffix in ((65536, ''), (1048576, '-1048576')):
        iso, contract = load(f'isolation-proof{suffix}.json'), load(f'sci-contract-proof{suffix}.json')
        report[f'sci_isolation_{bound}'] = None if iso is None else {
            'status': iso.get('status'), 'image': iso.get('image'), 'output_bytes': iso.get('output-bytes'),
            'boundary': iso.get('boundary'), 'controls_passed': sum(map(bool, iso.get('results', {}).values())),
            'controls': len(iso.get('results', {})), 'matches_current_supervisor': iso.get('supervisor-sha256') == supervisor}
        report[f'sci_contract_{bound}'] = None if contract is None else {
            'status': contract.get('status'), 'checks': len(contract.get('results', [])),
            'passed': sum(1 for r in contract.get('results', []) if r.get('passed')),
            'matches_current_code': all(contract.get(k) == v for k, v in current.items())}
    prime = load('prime-isolation-proof.json')
    if prime is not None:
        from .prime.isolation import gate_digest
        results = prime.get('results', prime.get('controls', {}))
        prime = {'status': prime.get('status'), 'image': prime.get('image'),
                 'controls_passed': sum(1 for v in results.values() if v is True or (isinstance(v, dict) and v.get('passed'))),
                 'controls': len(results), 'matches_current_gate': prime.get('gate_sha256') == gate_digest()}
    report['prime_isolation'] = prime
    return report


def audit_run(run, suites):
    """Re-score a recorded run independently and summarise its provenance."""
    run = Path(run)
    saved = json.loads((run / 'report.json').read_text())
    suite = suites.get(saved.get('suite_sha256'))
    summary = {'run': run.name, 'suite_sha256': saved.get('suite_sha256'), 'evidence': saved.get('evidence')}
    if suite is None:
        return {**summary, 'status': 'suite-unavailable'}
    again = compare(suite, run / 'results.jsonl')
    same_cases = ([(c['task_id'], c['harness'], c['score']) for c in again['cases']] ==
                  [(c['task_id'], c['harness'], c['score']) for c in saved['cases']])
    results = list(jsonl(run / 'results.jsonl'))
    plan_path = run / 'plan.json'
    plan = json.loads(plan_path.read_text()) if plan_path.exists() else {}
    sequence = [step['harness'] for step in plan.get('sequence', [])]
    firsts = sequence[0::2]
    libraries = {r.get('learning_library_sha256') for r in results if r['harness'] == 'aljure'}
    return {**summary, 'status': 'audited', 'suite': Path(suite).name,
            'reproduced': all(again[k] == saved.get(k) for k in REPORT_KEYS) and same_cases,
            'accounting_complete': again['accounting_complete'],
            'plan_sha256': plan.get('plan_sha256'), 'source_commit': plan.get('source', {}).get('commit'),
            'source_dirty': plan.get('source', {}).get('dirty'),
            'campaign': plan.get('config', {}).get('campaign_version'),
            'command_contract': plan.get('config', {}).get('command_contract', {}).get('version'),
            'aljure_sci': plan.get('capabilities', {}).get('aljure', {}).get('sci') if plan else None,
            'arm_order_counterbalanced': bool(firsts) and abs(firsts.count('aljure') - firsts.count('prime')) <= 1,
            'one_aljure_library_state': len(libraries) <= 1,
            'failures': sorted({(r['harness'], r['status'], r.get('failure') or '') for r in results if r['status'] != 'completed'}),
            'statistics': paired_statistics(again, suite, results)}


def _quantile(values, q):
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _sign_test(deltas):
    wins, losses = sum(d > 0 for d in deltas), sum(d < 0 for d in deltas)
    n = wins + losses
    if not n:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(0, min(wins, losses) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def paired_statistics(report, suite, results=(), *, success_threshold=0.9, resamples=2000, seed=0):
    """Deadline-aware paired statistics. Timeouts, errors and missing answers
    score 0 (as in compare). Tasks sharing a context form one cluster; a
    cross-context interval is reported only with enough clusters."""
    _, _, answers = read_suite(suite)
    failures = {(r['task_id'], r['harness']): r.get('failure') for r in results}
    by_task = {}
    for row in report['cases']:
        by_task.setdefault(row['task_id'], {})[row['harness']] = row
    stats = {}
    for harness in ('aljure', 'prime'):
        rows = [by_task[t][harness] for t in sorted(by_task)]
        costs = [float(r['usage'].get('known_model_cost_usd') or 0) for r in rows]
        successes = [r for r in rows if r['status'] == 'completed' and r['score'] >= success_threshold]
        latencies = [r['wall_time_ms'] / 1000 for r in rows]
        stats[harness] = {
            'deadline_aware_mean': sum(r['score'] for r in rows) / len(rows),
            'scores': [round(r['score'], 4) for r in rows],
            'completion_rate': sum(r['status'] == 'completed' for r in rows) / len(rows),
            'timeout_rate': sum(r['status'] == 'timeout' for r in rows) / len(rows),
            'infrastructure_failures': sum(1 for r in rows if failures.get((r['task_id'], harness)) in
                                           ('ProviderOutcomeUnknown', 'NativeCompletionMissing', 'GatewayCleanupFailure',
                                            'DockerNotReady', 'DockerRestartedDuringArm')),
            f'successes_at_{success_threshold}': len(successes),
            'cost_usd': round(sum(costs), 6),
            'cost_per_success_usd': round(sum(costs) / len(successes), 6) if successes else None,
            'latency_s_p50': _quantile(latencies, .5), 'latency_s_p95': _quantile(latencies, .95),
            'model_calls': sum(r['usage'].get('calls', 0) for r in rows)}
    deltas = [by_task[t]['aljure']['score'] - by_task[t]['prime']['score'] for t in sorted(by_task)]
    clusters = {}
    for task_id in by_task:
        clusters.setdefault(str(answers[task_id].get('context_window_id')), []).append(task_id)
    paired = {'mean_difference_aljure_minus_prime': sum(deltas) / len(deltas), 'differences': [round(d, 4) for d in deltas],
              'wins_ties_losses': [sum(d > 0 for d in deltas), sum(d == 0 for d in deltas), sum(d < 0 for d in deltas)],
              'independent_contexts': len(clusters),
              'within_context_sign_test_p': _sign_test(deltas)}
    if len(clusters) >= MIN_CLUSTERS_FOR_INTERVAL:
        rng, means = random.Random(seed), []
        keys = sorted(clusters)
        index = {t: i for i, t in enumerate(sorted(by_task))}
        for _ in range(resamples):
            draw = [t for _ in keys for t in clusters[rng.choice(keys)]]
            means.append(sum(deltas[index[t]] for t in draw) / len(draw))
        paired['cluster_bootstrap_95'] = [_quantile(means, .025), _quantile(means, .975)]
    else:
        paired['cluster_bootstrap_95'] = None
        paired['uncertainty_note'] = (f'{len(clusters)} independent context(s): no cross-context interval. '
                                      'The sign test treats tasks as exchangeable within one context and does not generalize.')
    return {'per_harness': stats, 'paired': paired}


def full_audit(root=ROOT):
    root = Path(root)
    suites, suite_reports, scorer_reports = {}, [], []
    for path in sorted((root / 'var/official').glob('*/manifest.json')):
        suite = path.parent
        try:
            report = audit_suite(suite)
            suites[report['suite_sha256']] = suite
            suite_reports.append(report)
            scorer_reports.append(scorer_selftest(suite))
        except Exception as error:
            suite_reports.append({'suite': suite.name, 'checks': {'integrity': False}, 'error': f'{type(error).__name__}: {error}'})
    runs = []
    for report in sorted((root / 'var/benchmarks').glob('*/report.json')):
        try:
            runs.append(audit_run(report.parent, suites))
        except Exception as error:
            runs.append({'run': report.parent.name, 'status': 'audit-failed', 'error': f'{type(error).__name__}: {error}'})
    try:
        equivalence = scorer_equivalence(root / 'var/official-import-validation/oolong-synth-32768-10')
    except Exception as error:
        equivalence = {'error': f'{type(error).__name__}: {error}'}
    violations = (['scorer equivalence: ' + equivalence['error']] if 'error' in equivalence else
                  ['scorer equivalence: vendored OOLONG-Pairs scorer differs from pinned upstream']
                  if not equivalence['oolong_pairs']['identical'] else []) + ([f"suite {s['suite']}: {k}" for s in suite_reports for k, ok in s['checks'].items() if not ok] +
                  [f"scorer {s['suite']}: {len(s['failures'])} task(s)" for s in scorer_reports if not s['passed']] +
                  [f"run {r['run']}: not reproduced" for r in runs if r.get('status') == 'audited' and not r['reproduced']] +
                  [f"run {r['run']}: {r['error']}" for r in runs if r.get('status') == 'audit-failed'])
    return {'schema_version': 1, 'evidence': 'OFFLINE AUDIT OF RECORDED EVIDENCE; no inference',
            'suites': suite_reports, 'scorers': scorer_reports, 'scorer_equivalence': equivalence,
            'environment': environment(root),
            'runs': runs, 'violations': violations}
