"""scripts/reuse_pilot_compare.py: numeric parsing follows the official scorer, and one failure policy
applies to every mean, paired difference and decision. Synthetic run directories; no inference."""
import json
import math
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import reuse_pilot_compare as rpc  # noqa: E402
from benchmark.oolong import encoded, write_jsonl  # noqa: E402


class ParsingTests(unittest.TestCase):
    def test_declared_count_matches_the_official_parser(self):
        self.assertEqual(rpc.declared('Answer: 42'), 42)
        self.assertEqual(rpc.declared('Answer: [42]'), 42)
        self.assertEqual(rpc.declared('Answer: **42**'), 42)
        self.assertEqual(rpc.declared('I counted carefully.\nAnswer: 7'), 7)
        # The scorer reads the text after the LAST colon: prose after the number is not a count.
        self.assertIsNone(rpc.declared('Answer: 42\n\nNote: this is approximate'))
        for bad in ('Answer: about 40', 'Answer: 4O', 'Answer: 1,200', 'Answer: 3.5', 'Answer:', '', None, 'location'):
            self.assertIsNone(rpc.declared(bad), bad)

    def test_non_delivery_takes_the_fixed_zero_answer_penalty(self):
        self.assertAlmostEqual(rpc.count_log_error(None, 99), math.log(100))
        self.assertAlmostEqual(rpc.count_log_error(0, 99), math.log(100))
        self.assertAlmostEqual(rpc.count_log_error(99, 99), 0.0)
        self.assertAlmostEqual(rpc.count_log_error(-5, 99), math.log(100))  # a negative count is an under-count of 0
        self.assertLess(rpc.count_log_error(50, 99), rpc.count_log_error(None, 99))


def case(task, numeric, score, calls=1, cost=0.01):
    return {'task_id': task, 'harness': 'aljure', 'score': score, 'usage': {'model_cost_usd': cost, 'calls': calls}}


class SyntheticSuite:
    """Two windows, four tasks: two counts (gold 9 and 99) and two comparisons; F1 only."""
    TASKS = {'w1-c': ('[9]', 'ANSWER_TYPE.NUMERIC', 1), 'w1-x': ('[more common]', 'ANSWER_TYPE.COMPARISON', 1),
             'w2-c': ('[99]', 'ANSWER_TYPE.NUMERIC', 2), 'w2-x': ('[less common]', 'ANSWER_TYPE.COMPARISON', 2)}

    def __init__(self, root):
        self.root = Path(root)
        suite = self.root / 'suite'
        (suite / 'public').mkdir(parents=True)
        (suite / 'controller').mkdir()
        from benchmark.oolong import digest as _digest
        (suite / 'public/contexts').mkdir()
        context = b'Date: Jan 01, 2023 || User: 1 || Instance: Where is x ?\n'
        (suite / 'public/contexts/c.txt').write_bytes(context)
        tasks = [{'task_id': t, 'question': 'q', 'context_path': 'contexts/c.txt', 'context_sha256': _digest(context)} for t in self.TASKS]
        for task in tasks:
            task['task_sha256'] = _digest(encoded(task))
        write_jsonl(suite / 'public/tasks.jsonl', tasks)
        write_jsonl(suite / 'controller/answers.jsonl',
                    [{'task_id': t, 'id': i, 'context_window_id': w, 'dataset': 'trec_coarse', 'answer': a, 'answer_type': k}
                     for i, (t, (a, k, w)) in enumerate(self.TASKS.items())])
        from benchmark.official import suite_pins
        from benchmark.oolong import digest
        dataset, scorer, scorer_path = suite_pins('oolong-synth')
        body = {'suite': 'oolong-synth', 'dataset': dataset, 'scorer': scorer, 'scorer_sha256': digest(scorer_path.read_bytes()),
                'input_provenance': 'synthetic-test-fixture', 'task_ids': list(self.TASKS),
                'selection': {'families': {'F1': list(self.TASKS), 'F2': []}},
                'files': {name: digest((suite / name).read_bytes()) for name in ('public/tasks.jsonl', 'controller/answers.jsonl')}}
        (suite / 'manifest.json').write_bytes(encoded({**body, 'suite_sha256': digest(encoded(body))}))
        self.suite = suite

    def run(self, arm, n, answers):
        """answers: task -> delivered text, or None for no answer. Scores are 1.0 for an exact match, else 0."""
        run = self.root / f'reuse-{arm}-r{n}'
        rows, cases = [], []
        for i, t in enumerate(self.TASKS):
            text = answers.get(t)
            d = run / f'{i:02}-aljure' / 'agent'
            d.mkdir(parents=True)
            (d / 'events.jsonl').write_text('')
            row = {'task_id': t, 'harness': 'aljure', 'status': 'completed' if text is not None else 'error',
                   'wall_time_ms': 1000, 'usage_path': f'{i:02}-aljure/usage.jsonl', 'trace_path': f'{i:02}-aljure/trace.json'}
            (run / f'{i:02}-aljure/usage.jsonl').write_text('')
            if text is not None:
                (run / f'{i:02}-aljure/answer.txt').write_text(text)
                row['answer_path'] = f'{i:02}-aljure/answer.txt'
            gold = self.TASKS[t][0].strip('[]')
            exact = text is not None and text.split(':')[-1].strip() == gold
            cases.append(case(t, self.TASKS[t][1] == 'ANSWER_TYPE.NUMERIC', 1.0 if exact else 0.0))
            rows.append(row)
        write_jsonl(run / 'results.jsonl', rows)
        (run / 'report.json').write_bytes(encoded({'cases': cases}))
        return run


class FailurePolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp, True)
        self.fx = SyntheticSuite(self.temp)
        self.out = Path(self.temp) / 'out.json'

    def compare(self, runs):
        rpc.main(str(self.fx.suite), str(self.out), *[str(r) for r in runs])
        return json.loads(self.out.read_text())

    def exact(self):
        return {'w1-c': 'Answer: 9', 'w1-x': 'Answer: more common', 'w2-c': 'Answer: 99', 'w2-x': 'Answer: less common'}

    def test_mixed_numeric_and_comparison_tasks_count_only_numeric_errors(self):
        r = self.compare([self.fx.run('S', 1, self.exact()), self.fx.run('D', 1, self.exact()), self.fx.run('P', 1, self.exact())])
        for arm in 'SDP':
            self.assertAlmostEqual(r['arms'][arm]['f1_numeric_log_error'], 0.0)
            self.assertEqual(r['arms'][arm]['f1_counts_delivered'], [2, 2])
            self.assertAlmostEqual(r['arms'][arm]['f1_mean_score'], 1.0)

    def test_a_missing_count_is_penalised_in_the_mean_and_the_paired_difference_alike(self):
        missing = {**self.exact(), 'w2-c': None}
        r = self.compare([self.fx.run('S', 1, self.exact()), self.fx.run('D', 1, missing), self.fx.run('P', 1, self.exact())])
        penalty = math.log(100) / 2  # one of two count tasks
        self.assertAlmostEqual(r['arms']['D']['f1_numeric_log_error'], penalty)
        self.assertAlmostEqual(r['paired_vs_S']['D']['f1_log_error_diff'], penalty, places=4)
        self.assertEqual(r['arms']['D']['f1_counts_delivered'], [1, 2])
        self.assertAlmostEqual(r['arms']['D']['f1_mean_score'], 0.75)

    def test_an_arm_that_delivers_no_counts_gets_the_full_penalty_not_none(self):
        none = {'w1-c': None, 'w1-x': 'Answer: more common', 'w2-c': None, 'w2-x': 'Answer: less common'}
        r = self.compare([self.fx.run('S', 1, self.exact()), self.fx.run('D', 1, none), self.fx.run('P', 1, self.exact())])
        self.assertAlmostEqual(r['arms']['D']['f1_numeric_log_error'], (math.log(10) + math.log(100)) / 2)
        self.assertEqual(r['arms']['D']['f1_counts_delivered'], [0, 2])
        self.assertFalse(r['decision']['d_used_reliably'])

    def test_half_delivered_but_exact_cannot_beat_a_fully_delivered_near_miss(self):
        # P delivers both counts, each one off; D delivers only the small one, exactly, and nothing for the other.
        near = {**self.exact(), 'w1-c': 'Answer: 8', 'w2-c': 'Answer: 98'}
        half = {**self.exact(), 'w2-c': None}
        r = self.compare([self.fx.run('S', 1, near), self.fx.run('D', 1, half), self.fx.run('P', 1, near)])
        self.assertLess(r['arms']['S']['f1_numeric_log_error'], r['arms']['D']['f1_numeric_log_error'])
        self.assertGreater(r['paired_vs_S']['D']['f1_log_error_diff'], 0)
        self.assertFalse(r['decision']['criteria']['b_log_error_minus_25pct_at_score_ge_minus_0.03'])

    def test_malformed_numeric_strings_are_non_delivery(self):
        bad = {**self.exact(), 'w1-c': 'Answer: about 9', 'w2-c': 'Answer: 99\n\nNote: estimated'}
        r = self.compare([self.fx.run('S', 1, self.exact()), self.fx.run('D', 1, bad), self.fx.run('P', 1, self.exact())])
        self.assertEqual(r['arms']['D']['f1_counts_delivered'], [0, 2])
        self.assertAlmostEqual(r['arms']['D']['f1_numeric_log_error'], (math.log(10) + math.log(100)) / 2)

    def test_two_runs_average_per_task_and_the_usefulness_rule_needs_delivery(self):
        r = self.compare([self.fx.run('S', 1, self.exact()), self.fx.run('S', 2, {**self.exact(), 'w2-c': 'Answer: 50'}),
                          self.fx.run('D', 1, self.exact()), self.fx.run('D', 2, self.exact()),
                          self.fx.run('P', 1, self.exact()), self.fx.run('P', 2, {**self.exact(), 'w2-c': None})])
        self.assertEqual(r['runs'], {'S': 2, 'D': 2, 'P': 2, 'R': 0})
        # S run 2 was off by 49 on w2-c; P run 2 did not deliver it: P's penalty is larger, so P is not "useful" on error.
        self.assertGreater(r['arms']['P']['f1_numeric_log_error'], r['arms']['S']['f1_numeric_log_error'])
        self.assertFalse(r['decision']['criteria']['b_log_error_minus_25pct_at_score_ge_minus_0.03'])


if __name__ == '__main__':
    unittest.main()
