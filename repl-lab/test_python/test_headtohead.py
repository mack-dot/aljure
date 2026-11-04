import json
import tempfile
import unittest
from pathlib import Path

from benchmark import headtohead as h


def fake_suites():
    """Three suites shaped like load_suites() output, without touching var/."""
    def suite(name, task_ids, contexts, rule='all'):
        return {'path': f'var/official/{name}', 'suite_sha256': 'x' * 64, 'suite': 'oolong-synth', 'rule': rule, 'exposure': 'test',
                'task_ids': task_ids, 'contexts': contexts}
    return {'synth8': suite('synth8', [f'a{i}' for i in range(12)], {f'a{i}': str(i // 2) for i in range(12)}),
            'synth32': suite('synth32', [f'b{i}' for i in range(7)], {f'b{i}': str(10 + i) for i in range(7)}),
            'synth128': suite('synth128', [f'c{i}' for i in range(6)], {f'c{i}': str(20 + i // 2) for i in range(6)}),
            'pairs32': suite('pairs32', ['p0', 'p1', 'p2'], {'p0': '0', 'p1': '0', 'p2': '0'}, 'seeded-3')}


def fake_rows(seq, suites, score_fn, cost_fn=lambda e: 0.05 if e['harness'] == 'aljure' else 0.08, latency_fn=lambda e: 20000.0):
    rows = []
    for e in seq:
        rows.append({**e, 'suite_sha256': 'x' * 64, 'context_window_id': suites[e['suite']]['contexts'][e['task_id']],
                     'status': 'completed', 'failure': None, 'score': score_fn(e),
                     'usage': {'calls': 3, 'known_model_cost_usd': cost_fn(e), 'reserved_unknown_usd': 0.0, 'accounting_complete': True,
                               'known_tokens': {'input_tokens': 100, 'output_tokens': 50, 'cache_read_input_tokens': 0, 'cache_creation_input_tokens': 0}},
                     'measures': {'agent_wall_ms': latency_fn(e), 'first_request_ms': 3000, 'tool_calls': 3, 'tool_errors': 0, 'http_errors': 0},
                     'wall_time_ms': latency_fn(e) + 2000})
    return rows


class SequenceTest(unittest.TestCase):
    def test_sequence_is_deterministic_complete_balanced_and_interleaved(self):
        suites = fake_suites()
        seq = h.sequence(suites)
        self.assertEqual(seq, h.sequence(suites))
        tasks = {(e['suite'], e['task_id']) for e in seq}
        self.assertEqual(tasks, {(n, t) for n in suites for t in suites[n]['task_ids']})
        items = {(e['suite'], e['task_id'], e['trial']) for e in seq}
        self.assertEqual(len(seq), 2 * len(items))
        self.assertEqual(sum(e['trial'] == 1 for e in seq) // 2, round(0.2 * len(tasks)))
        # Every item is two consecutive arms, one of each harness, with positions 1 then 2.
        for first, second in zip(seq[::2], seq[1::2]):
            self.assertEqual((first['suite'], first['task_id'], first['trial']), (second['suite'], second['task_id'], second['trial']))
            self.assertEqual({first['harness'], second['harness']}, {'aljure', 'prime'})
            self.assertEqual((first['position'], second['position']), (1, 2))
        for name in suites:
            firsts = [e['harness'] for e in seq if e['suite'] == name and e['position'] == 1]
            self.assertLessEqual(abs(firsts.count('aljure') - firsts.count('prime')), 1)
        self.assertEqual([e['index'] for e in seq], list(range(len(seq))))
        self.assertNotEqual(h.sequence(suites, seed=1), seq)

    def test_selection_rules_depend_on_identity_only(self):
        manifest = {'task_ids': [f't{i}' for i in range(9)]}
        answers = {f't{i}': {'context_window_id': i // 3, 'answer': i} for i in range(9)}
        one = h.select_tasks('s', manifest, answers, 'one-per-context')
        self.assertEqual(len(one), 3)
        self.assertEqual(len({answers[t]['context_window_id'] for t in one}), 3)
        self.assertEqual(one, h.select_tasks('s', manifest, {t: {'context_window_id': a['context_window_id']} for t, a in answers.items()}, 'one-per-context'))
        three = h.select_tasks('s', manifest, answers, 'seeded-3')
        self.assertEqual(len(three), 3)
        self.assertEqual(three, sorted(three, key=manifest['task_ids'].index))
        self.assertEqual(h.select_tasks('s', manifest, answers, 'all'), manifest['task_ids'])

    def test_estimate_uses_priors_for_every_arm(self):
        suites = fake_suites()
        seq = h.sequence(suites)
        est = h.estimate(suites, seq)
        self.assertEqual(est['arms'], len(seq))
        self.assertAlmostEqual(est['expected_usd'], round(sum(h.COST_PRIOR[e['suite']][e['harness']] for e in seq), 2))
        self.assertLess(est['low_usd'], est['expected_usd'])
        self.assertGreater(est['high_usd'], est['expected_usd'])


class StatisticsTest(unittest.TestCase):
    def test_decision_rules_follow_the_protocol(self):
        self.assertEqual(h.decision(0.1, {'ci95': [0.02, 0.2], 'ci90': [0.03, 0.18]}), 'superior')
        self.assertEqual(h.decision(-0.1, {'ci95': [-0.2, -0.02], 'ci90': [-0.18, -0.03]}), 'inferior')
        self.assertEqual(h.decision(0.0, {'ci95': [-0.06, 0.06], 'ci90': [-0.04, 0.04]}), 'equivalent')
        self.assertEqual(h.decision(0.03, {'ci95': [-0.1, 0.2], 'ci90': [-0.08, 0.15]}), 'inconclusive')
        self.assertEqual(h.decision(0.03, {'ci95': [0.01, 0.2], 'ci90': [0.02, 0.15]}), 'inconclusive')  # significant but below delta
        self.assertEqual(h.decision(0.03, None), 'no-interval')

    def test_sign_and_mcnemar(self):
        self.assertEqual(h.sign_test([0, 0]), 1.0)
        self.assertAlmostEqual(h.sign_test([1, 1, 1, 1, 1]), 2 / 32)
        m = h.mcnemar([(1.0, 0.0), (1.0, 0.0), (0.0, 1.0), (1.0, 1.0), (0.5, 0.5)])
        self.assertEqual((m['aljure_only_success'], m['prime_only_success']), (2, 1))
        self.assertEqual(m['p_exact'], 1.0)

    def test_cluster_bootstrap_contains_the_estimate_and_is_seeded(self):
        per_context = {str(i): d for i, d in enumerate([0.1, -0.05, 0.2, 0.0, 0.15, 0.05, 0.1])}
        a = h.cluster_bootstrap(per_context, resamples=500)
        b = h.cluster_bootstrap(per_context, resamples=500)
        self.assertEqual(a, b)
        estimate = sum(per_context.values()) / len(per_context)
        self.assertLessEqual(a['ci95'][0], estimate)
        self.assertGreaterEqual(a['ci95'][1], estimate)
        self.assertLessEqual(a['ci95'][0], a['ci90'][0])
        self.assertIsNone(h.cluster_bootstrap({'only': 0.1}))

    def test_paired_analysis_averages_repeats_and_weights_contexts(self):
        suites = fake_suites()
        seq = h.sequence(suites)
        synth8 = [e for e in seq if e['suite'] == 'synth8']
        # Aljure scores 1 on every task; Prime scores 1 on trial 0 and 0 on trial 1, so repeated tasks average 0.5 for Prime.
        rows = fake_rows(synth8, suites, lambda e: 1.0 if e['harness'] == 'aljure' or e['trial'] == 0 else 0.0)
        analysis = h.paired_analysis(rows, suites['synth8']['contexts'])
        self.assertEqual(analysis['tasks'], 12)
        self.assertEqual(analysis['independent_contexts'], 6)
        repeated = {e['task_id'] for e in synth8 if e['trial'] == 1}
        expected = sum(0.5 if t in repeated else 0.0 for t in suites['synth8']['task_ids']) / 12
        self.assertAlmostEqual(analysis['task_weighted_mean_difference'], expected)
        self.assertEqual(analysis['wins_ties_losses'][0], len(repeated))
        self.assertAlmostEqual(analysis['cost_difference_usd']['mean'], -0.03)
        self.assertEqual(analysis['repeat_absolute_score_change']['prime']['mean'], 1.0)
        self.assertEqual(analysis['repeat_absolute_score_change']['aljure']['mean'], 0.0)
        self.assertIn(analysis['decision'], ('superior', 'inconclusive', 'equivalent', 'inferior'))

    def test_pareto_dominance(self):
        table = h.pareto({'a': (0.9, 0.05, 20.0), 'b': (0.9, 0.08, 25.0), 'c': (0.95, 0.09, 30.0)})
        self.assertEqual(table['b']['dominated_by'], ['a'])
        self.assertEqual(table['a']['dominated_by'], [])
        self.assertEqual(table['c']['dominated_by'], [])


class SummaryTest(unittest.TestCase):
    def test_summary_keeps_every_outcome_and_reports_failures(self):
        suites = fake_suites()
        seq = h.sequence(suites)
        value = {'plan_sha256': 'p' * 64, 'sequence': seq, 'suites': suites}
        rows = fake_rows(seq, suites, lambda e: 0.9)
        rows[3]['status'], rows[3]['failure'], rows[3]['score'] = 'timeout', None, 0.0
        rows[5]['status'], rows[5]['failure'], rows[5]['score'] = 'error', 'NativeCompletionMissing', 0.0
        rows[-1]['status'], rows[-1]['failure'], rows[-1]['score'] = 'not-attempted', 'DockerNotReady', 0.0
        report = h.summarize(value, rows)
        self.assertEqual(report['arms_recorded'], len(seq))
        self.assertFalse(report['complete'])
        self.assertEqual(report['stopped_by'], 'DockerNotReady')
        overall = report['overall']
        self.assertEqual(sum(s['arms'] for s in overall.values()), len(seq))
        self.assertEqual(overall[rows[3]['harness']]['timeouts'] + overall[rows[3]['harness']]['errors'] +
                         overall[rows[3]['harness']]['not_attempted'] >= 1, True)
        self.assertIn('timeout:', ''.join(overall[rows[3]['harness']]['failures']))
        self.assertTrue(set(report['pareto']) >= {'synth8:aljure', 'synth8:prime'})
        for name, section in report['suites'].items():
            self.assertIsNotNone(section['paired'])
            self.assertEqual(section['paired']['tasks'], len(suites[name]['task_ids']))

    def test_prime_tool_errors_are_read_from_session_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / 'native/sessions').mkdir(parents=True)
            lines = [{'type': 'message', 'message': {'role': 'toolResult', 'isError': False, 'details': {'status': 'ok'}, 'content': [{'type': 'text', 'text': '38'}]}},
                     {'type': 'message', 'message': {'role': 'toolResult', 'isError': True, 'content': 'Traceback (most recent call last)'}},
                     {'type': 'message', 'message': {'role': 'toolResult', 'isError': False, 'details': {'status': 'ok'}, 'content': [{'type': 'text', 'text': 'Traceback: x'}]}},
                     {'type': 'message', 'message': {'role': 'assistant', 'stopReason': 'error'}}]
            (out / 'native/sessions/s.jsonl').write_text('\n'.join(json.dumps(l) for l in lines) + '\n')
            self.assertEqual(h.prime_tools(out), {'tool_calls': 3, 'tool_errors': 2, 'tool_ops': ['python_repl'], 'provider_stop_errors': 1})
            (out / 'agent').mkdir()
            events = [{'type': 'tool-result', 'payload': {'op': 'repl/eval', 'status': 'ok'}},
                      {'type': 'tool-result', 'payload': {'op': 'repl/eval', 'status': 'error'}},
                      {'type': 'command-rejected', 'payload': {}}]
            (out / 'agent/events.jsonl').write_text('\n'.join(json.dumps(e) for e in events) + '\n')
            self.assertEqual(h.aljure_tools(out), {'tool_calls': 2, 'tool_errors': 1, 'tool_ops': ['repl/eval'], 'rejections': 1})
            self.assertEqual(h.measure_arm(out, 'aljure')['agent_wall_ms'], None)


if __name__ == '__main__':
    unittest.main()
