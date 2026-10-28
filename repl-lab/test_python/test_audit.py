"""Offline audit checks on synthetic suites. Not benchmark evidence."""
import json
import os
import unittest

from benchmark import audit
from benchmark.oolong import compare, write_jsonl
import test_benchmark


class AuditTests(unittest.TestCase):
    # Borrow the synthetic suite fixture without re-running its tests here.
    setUp = test_benchmark.BenchmarkTests.setUp
    prepare = test_benchmark.BenchmarkTests.prepare
    pilot = test_benchmark.BenchmarkTests.pilot
    compare = test_benchmark.BenchmarkTests.compare

    def test_suite_checks_report_gold_isolation_and_context_grouping(self):
        report = audit.audit_suite(self.suite)
        self.assertTrue(all(report['checks'].values()))
        self.assertEqual((report['tasks'], report['independent_contexts']), (10, 1))
        os.chmod(self.suite / 'controller', 0o755)
        self.assertFalse(audit.audit_suite(self.suite)['checks']['controller_private'])

    def test_scorer_selftest_uses_real_gold_answers(self):
        report = audit.scorer_selftest(self.suite)
        self.assertTrue(report['passed'])
        self.assertEqual(report['tasks'], 10)

    def test_one_context_gives_no_cross_context_interval(self):
        stats = audit.paired_statistics(self.compare(self.pilot()), self.suite)
        paired = stats['paired']
        self.assertEqual(paired['independent_contexts'], 1)
        self.assertIsNone(paired['cluster_bootstrap_95'])
        self.assertIn('does not generalize', paired['uncertainty_note'])
        # Ten wins and no losses: exact two-sided sign test.
        self.assertEqual(paired['wins_ties_losses'], [10, 0, 0])
        self.assertAlmostEqual(paired['within_context_sign_test_p'], 2 / 1024)
        self.assertEqual(stats['per_harness']['aljure']['completion_rate'], 1.0)

    def test_enough_contexts_give_a_cluster_bootstrap_interval(self):
        self.data = [{**row, 'context_window_id': i % 5} for i, row in enumerate(self.data)]
        write_jsonl(self.raw, self.data)
        self.suite = self.root / 'suite-5'
        self.manifest = self.prepare(self.suite)
        stats = audit.paired_statistics(self.compare(self.pilot()), self.suite)
        low, high = stats['paired']['cluster_bootstrap_95']
        self.assertLessEqual(low, stats['paired']['mean_difference_aljure_minus_prime'])
        self.assertGreaterEqual(high, stats['paired']['mean_difference_aljure_minus_prime'])
        self.assertEqual(stats['paired']['independent_contexts'], 5)

    def test_a_tampered_report_is_not_reproduced(self):
        results = self.pilot()
        run = self.root / 'run'
        run.mkdir()
        for result in results:
            for key in ('answer_path', 'trace_path', 'usage_path'):
                (run / result[key]).write_bytes((self.root / result[key]).read_bytes())
        write_jsonl(run / 'results.jsonl', results)
        report = compare(self.suite, run / 'results.jsonl')
        (run / 'report.json').write_text(json.dumps(report))
        suites = {self.manifest['suite_sha256']: self.suite}
        self.assertTrue(audit.audit_run(run, suites)['reproduced'])
        report['mean_score']['aljure'] = 0.5
        (run / 'report.json').write_text(json.dumps(report))
        self.assertFalse(audit.audit_run(run, suites)['reproduced'])
        self.assertEqual(audit.audit_run(run, {})['status'], 'suite-unavailable')


if __name__ == '__main__':
    unittest.main()


@unittest.skipUnless((audit.UPSTREAM / 'research-environments-tree.json').exists(), 'pinned upstream cache absent')
class ScorerEquivalenceTests(unittest.TestCase):
    def test_vendored_pairs_scorer_equals_the_pinned_upstream_functions(self):
        report = audit.scorer_equivalence()
        self.assertTrue(report['oolong_pairs']['identical'])
        self.assertEqual(report['oolong_pairs']['upstream_commit'], 'ba10ef5a303943a08e1ccf92f9c0d63b1159b369')

    def test_a_changed_function_body_is_detected(self):
        source = (audit.ROOT / 'benchmark/vendor/oolong_pairs.py').read_text()
        changed = source.replace('flags=re.DOTALL', 'flags=re.IGNORECASE')
        ours = audit._functions(changed, ('_strip_think_tags',))['_strip_think_tags']
        theirs = audit._functions(audit._upstream_source('oolong_pairs/oolong_pairs/taskset.py')[0],
                                  ('_strip_think_tags',))['_strip_think_tags']
        self.assertNotEqual(audit.ast.dump(ours), audit.ast.dump(theirs))
