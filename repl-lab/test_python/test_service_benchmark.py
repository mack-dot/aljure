"""The programmatic-execution development benchmark (benchmark/service_benchmark.py): seeded suites
load through the official suite reader, tasks carry pinned fixtures, scoring separates answers from
effects, reports read recorded evidence, and a plan can be frozen only Aljure-only under a programs
grant. FIXTURES ONLY: no Docker, no model call, no network."""
import json
from pathlib import Path
import tempfile
import unittest

from benchmark import oolong, paired, service_benchmark as sb
from benchmark.oolong import digest, encoded, write_jsonl
from test_thesis_trajectory import CONFIG

BASE = {k: v for k, v in CONFIG.items() if k != 'trajectory'}
GRANT = {'tools': [{'name': 'service_list'}, {'name': 'service_get'}, {'name': 'service_update', 'approval': 'preapproved'}]}
PLAN = {**BASE, 'total_usd': BASE['usd_per_arm'] * 20,
        'aljure_only': {'disclosure': 'development benchmark; no Prime comparison is made'},
        'aljure_contract': {'programs': GRANT}}


class GeneratorTests(unittest.TestCase):
    def test_instances_are_deterministic_and_cover_every_family(self):
        a, b = sb.instances(7, 2), sb.instances(7, 2)
        self.assertEqual(encoded(a), encoded(b))
        self.assertNotEqual(encoded(a), encoded(sb.instances(8, 2)))
        self.assertEqual([r['family'] for r in a], [f for f in sb.FAMILIES for _ in range(2)])
        for row in a:
            self.assertIsInstance(row['answer'], str)
            self.assertEqual(set(row['expected_state']), {'issues', 'users'})
            if not row['effects_expected']:
                self.assertEqual(row['expected_state'], row['fixture']['collections'])
            else:
                self.assertNotEqual(row['expected_state'], row['fixture']['collections'], row['family'])
        fault = next(r for r in a if r['family'] == 'fault')
        self.assertTrue(fault['fixture']['faults']['fail_ids'])
        self.assertEqual(fault['answer'], ', '.join(fault['fixture']['faults']['fail_ids']))
        self.assertEqual(next(r for r in a if r['family'] == 'auth')['answer'], 'unsupported')
        self.assertEqual(next(r for r in a if r['family'] == 'direct')['optimum_ops'], 0)

    def test_a_suite_loads_through_the_official_reader_and_tasks_carry_their_fixture(self):
        with tempfile.TemporaryDirectory() as root:
            suite = Path(root) / 'suite'
            manifest = sb.write_suite(suite, seed=3, per_family=1)
            loaded, tasks, answers = oolong.read_suite(suite)
            self.assertEqual(loaded['suite_sha256'], manifest['suite_sha256'])
            self.assertEqual(loaded['input_provenance'], 'synthetic-service-fixture')
            self.assertEqual(len(tasks), len(sb.FAMILIES))
            task = next(iter(tasks.values()))
            data = paired.public_input(suite, task)
            self.assertEqual(set(data['service_fixture']), {'collections', 'faults'})
            self.assertIn('issues', data['context'])
            self.assertEqual(set(answers[task['task_id']]) >= {'answer', 'expected_state', 'initial_state', 'optimum_ops'}, True)
            # The scorer is this module, pinned by hash: a changed module invalidates the suite.
            self.assertEqual(loaded['scorer_sha256'], digest(Path(sb.__file__).read_bytes()))


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.case = next(r for r in sb.instances(5, 1) if r['family'] == 'cond')
        self.answer = {'answer': self.case['answer'], 'initial_state': self.case['fixture']['collections'],
                       'expected_state': self.case['expected_state'], 'family': 'cond'}

    def test_the_answer_is_scored_after_the_last_marker_and_exactly(self):
        n = self.case['answer']
        self.assertEqual(sb.score(self.answer, f'I closed them.\nAnswer: {n}')['score'], 1.0)
        self.assertEqual(sb.score(self.answer, f'[{n}]')['score'], 1.0)
        self.assertEqual(sb.score(self.answer, f'about {n}')['score'], 0.0)
        self.assertEqual(sb.score(self.answer, '')['score'], 0.0)
        self.assertNotIn('state_ok', sb.score(self.answer, n))

    def test_effects_are_scored_against_the_expected_state_with_missing_and_unintended_changes_apart(self):
        expected = self.case['expected_state']
        ok = sb.score(self.answer, self.case['answer'], {'collections': expected, 'calls': 9})
        self.assertTrue(ok['state_ok']); self.assertEqual(ok['service_calls'], 9)
        untouched = sb.score(self.answer, self.case['answer'], {'collections': self.case['fixture']['collections']})
        self.assertFalse(untouched['state_ok'])
        self.assertTrue(untouched['missing_changes']); self.assertEqual(untouched['unintended_changes'], [])
        wrong = json.loads(json.dumps(expected))
        victim = next(i for i, r in wrong['issues'].items() if r['status'] == 'closed' and expected['issues'][i] == self.case['fixture']['collections']['issues'][i])
        wrong['issues'][victim] = {**wrong['issues'][victim], 'status': 'open'}
        bad = sb.score(self.answer, self.case['answer'], {'collections': wrong})
        self.assertEqual(bad['unintended_changes'], [f'issues/{victim}'])
        self.assertEqual(bad['missing_changes'], [])


class ReportAndPlanTests(unittest.TestCase):
    def test_a_report_reads_recorded_evidence_only(self):
        with tempfile.TemporaryDirectory() as root:
            suite = Path(root) / 'suite'
            sb.write_suite(suite, seed=1, per_family=1)
            _, tasks, answers = oolong.read_suite(suite)
            run = Path(root) / 'run'
            rows = []
            for i, (task_id, task) in enumerate(sorted(tasks.items())):
                d = run / f'{i:02}-aljure'
                (d / 'agent').mkdir(parents=True)
                answer = answers[task_id]
                (d / 'answer.txt').write_text(f"Answer: {answer['answer']}")
                (d / 'agent/service-state.json').write_text(json.dumps({'collections': answer['expected_state'], 'calls': 4, 'log': []}))
                events = [{'type': 'provider-input', 'payload': {}}, {'type': 'provider-input', 'payload': {}},
                          {'type': 'program-started', 'payload': {}},
                          *[{'type': 'program-op', 'payload': {'decision': 'allowed', 'status': 'ok', 'class': 'read', 'elapsed-ms': 1.5, 'origin': 'root/program-1'}}] * 3,
                          {'type': 'program-op', 'payload': {'decision': 'allowed', 'status': 'ok', 'class': 'effect', 'acted': True, 'elapsed-ms': 2.0, 'origin': 'root/program-1'}},
                          {'type': 'program-op', 'payload': {'decision': 'deduplicated', 'status': 'ok', 'class': 'effect', 'acted': False, 'elapsed-ms': 0.1, 'origin': 'root/program-1'}},
                          {'type': 'program-finished', 'payload': {'status': 'ok'}}]
                write_jsonl(d / 'agent/events.jsonl', events)
                write_jsonl(d / 'usage.jsonl', [{'kind': 'provider-call', 'call_id': f'c{i}{k}', 'session_id': 'root', 'status': 'complete',
                                                 'provider_request_id': f'p{i}{k}', 'input_tokens': 1000, 'output_tokens': 100,
                                                 'cache_read_input_tokens': 0, 'cache_creation_input_tokens': 0} for k in range(2)])
                rows.append({'task_id': task_id, 'harness': 'aljure', 'status': 'completed', 'wall_time_ms': 1000 + i,
                             'usage_path': f'{i:02}-aljure/usage.jsonl', 'answer_path': f'{i:02}-aljure/answer.txt',
                             'pricing_usd_per_m': None})
            write_jsonl(run / 'results.jsonl', rows)
            value = sb.report(run, suite)
            self.assertEqual(value['tasks'], len(sb.FAMILIES))
            case = value['cases'][0]
            self.assertEqual((case['score'], case['state_ok'], case['model_requests'], case['tool_operations'],
                              case['effects'], case['operations_deduplicated'], case['input_tokens']),
                             (1.0, True, 2, 5, 1, 1, 2000))
            self.assertEqual(value['families']['read']['success'], 1.0)
            self.assertEqual(value['families']['read']['effects_correct'], 1.0)
            self.assertIsNotNone(value['families']['read']['wall_ms_p95'])

    def test_a_service_sim_plan_freezes_only_aljure_only_under_a_programs_grant(self):
        with tempfile.TemporaryDirectory() as root:
            suite = Path(root) / 'suite'
            sb.write_suite(suite, seed=2, per_family=1)
            config = Path(root) / 'config.json'
            config.write_text(json.dumps({**PLAN, 'aljure_contract': {}}))
            with self.assertRaisesRegex(ValueError, 'programs'):
                paired.plan(suite, config, Path(root) / 'p0.json')
            config.write_text(json.dumps({k: v for k, v in PLAN.items() if k != 'aljure_only'}))
            with self.assertRaisesRegex(ValueError, 'aljure_only'):
                paired.plan(suite, config, Path(root) / 'p1.json')
            config.write_text(json.dumps(PLAN))
            plan = paired.plan(suite, config, Path(root) / 'p2.json')
            self.assertEqual(plan['authorized'], False)
            self.assertIn('programmatic tool bridge', plan['capabilities']['aljure']['execution_contract']['programs'])
            self.assertEqual(len(plan['sequence']), len(sb.FAMILIES))
            read_back, _, _ = paired.read_plan(Path(root) / 'p2.json', suite)
            self.assertEqual(read_back['plan_sha256'], plan['plan_sha256'])


if __name__ == '__main__':
    unittest.main()
