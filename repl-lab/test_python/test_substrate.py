import copy
import json
import unittest
from unittest.mock import patch

from benchmark import substrate, substrate_tasks as tasks


class SubstrateTasksTests(unittest.TestCase):
    def test_generation_is_deterministic_and_covers_every_family(self):
        cases = tasks.generate('seed-a', 2)
        self.assertEqual(cases, tasks.generate('seed-a', 2))
        self.assertNotEqual([c['answer'] for c in cases], [c['answer'] for c in tasks.generate('seed-b', 2)])
        self.assertEqual([f for f in tasks.FAMILIES for _ in range(2)], [c['family'] for c in cases])
        self.assertEqual(10, len(tasks.FAMILIES))
        for case in cases:
            self.assertTrue(case['answer'] and case['context'] and case['question'])
            self.assertNotIn(case['answer'], case['question'])

    def test_gold_is_checked_by_independent_arithmetic(self):
        # Transformation preserves value; simplification removes every identity node.
        for case in tasks.generate('seed-c', 3):
            if case['family'] == 'transformation':
                self.assertNotIn('(add 0 ', case['answer'])
                self.assertNotIn('(mul 1 ', case['answer'])
        tree = ['add', ['mul', 'x', 1], ['add', 0, ['mul', 2, 'y']]]
        self.assertEqual(['add', 'x', ['mul', 2, 'y']], tasks.simplify(tree))
        self.assertEqual(tasks.evaluate(tree, {'x': 3, 'y': 4}), tasks.evaluate(tasks.simplify(tree), {'x': 3, 'y': 4}))
        self.assertEqual((9, 3), (tasks.nodes(tree), tasks.depth(tree)))

    def test_scorer_is_exact_after_trimming_only(self):
        case = {'answer': 'east 42'}
        self.assertEqual(1.0, tasks.score(case, ' east 42\n')['score'])
        for wrong in ('east  42', 'East 42', '42', None, 'east 42.'):
            self.assertEqual(0.0, tasks.score(case, wrong)['score'])


class SubstrateDriverTests(unittest.TestCase):
    def test_sequence_pairs_every_case_and_alternates_the_first_arm(self):
        cases = [{'task_id': f't{i}', 'family': 'f'} for i in range(4)]
        seq = substrate.sequence(cases)
        self.assertEqual(8, len(seq))
        self.assertEqual(['clojure', 'python', 'python', 'clojure', 'clojure', 'python', 'python', 'clojure'], [s['arm'] for s in seq])
        self.assertEqual(40, substrate.BUDGET['max_tasks'])

    def test_no_paid_transport_without_the_exact_new_approval(self):
        with patch.object(substrate, 'read_plan', return_value=({'plan_sha256': 'new-plan'}, [])), \
             patch.object(substrate, 'preflight') as preflight, \
             patch.object(substrate, 'ClaudeSubscriptionTransport') as paid:
            for approval in (None, '', 'other-plan', '97fd6e92487dba95600bd234d831f15a45e6d520413b8e7eef201d308300c6af'):
                with self.assertRaises(ValueError):
                    substrate.run(None, None, None, approval)
            preflight.assert_not_called()
            paid.assert_not_called()

    def rows(self, clojure_correct, python_correct, restarts=(0, 0)):
        rows = []
        for i in range(20):
            for arm, correct, restart in (('clojure', clojure_correct[i], restarts[0]), ('python', python_correct[i], restarts[1])):
                rows.append({'task_id': f't{i}', 'family': tasks.FAMILIES[i // 2], 'arm': arm, 'status': 'completed', 'safety_complete': True,
                             'correct': correct, 'seconds': 1.0, 'prompt': {'first_request_tokens': 100},
                             'usage': {'known_model_cost_usd': .01, 'accounting_complete': True, 'calls': 3},
                             'measures': {'first_evaluation_valid': True, 'execution_success_rate': 1.0, 'worker_restarts': restart,
                                          'evaluation_errors': 0, 'error_classes': [], 'cold_evaluation_ms': 100, 'warm_evaluation_ms': [50],
                                          'source_chars': 100, 'done_path': 'done/eval'}})
        return rows

    def test_frozen_outcomes(self):
        all_true, none = [True] * 20, [False] * 20
        self.assertEqual('success-clojure', substrate.summarize(self.rows(all_true, [i % 2 == 0 for i in range(20)]))['outcome'])
        self.assertEqual('success-python', substrate.summarize(self.rows([i % 2 == 0 for i in range(20)], all_true))['outcome'])
        self.assertEqual('inconclusive', substrate.summarize(self.rows(all_true, all_true))['outcome'])
        self.assertEqual('inconclusive', substrate.summarize(self.rows([i < 11 for i in range(20)], [i < 9 for i in range(20)]))['outcome'])
        # A reliability deficit blocks a success claim.
        self.assertEqual('inconclusive', substrate.summarize(self.rows(all_true, none, restarts=(3, 0)))['outcome'])
        incomplete = self.rows(all_true, none)
        incomplete[-1]['status'] = 'error'
        report = substrate.summarize(incomplete)
        self.assertEqual(('INCOMPLETE', 'failure'), (report['development_gate'], report['outcome']))
        short = substrate.summarize(self.rows(all_true, none)[:-2])
        self.assertEqual('INCOMPLETE', short['development_gate'])
        self.assertEqual(10, len(substrate.summarize(self.rows(all_true, none))['families']))

    def test_criteria_are_frozen_into_the_plan_hash(self):
        self.assertEqual('q-substrate-criteria-v1', substrate.CRITERIA['version'])
        self.assertTrue(substrate.CRITERIA['no_prompt_changes_after_results'])
        self.assertIn('CPU-seconds', ' '.join(substrate.CRITERIA['not_measured']))


if __name__ == '__main__':
    unittest.main()
