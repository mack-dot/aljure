"""Evidence gates must not turn scripted reuse, failed calls or partial runs into learning."""
import unittest
from benchmark.learning_report import lifecycle_pass, tool_reliability


class LearningEvidenceTests(unittest.TestCase):
    def test_missing_tool_results_are_not_counted_as_success(self):
        events = [{'type': 'tool-call'}] * 3 + [
            {'type': 'tool-result', 'payload': {'status': 'ok'}},
            {'type': 'tool-result', 'payload': {'status': 'error'}}]
        self.assertEqual(tool_reliability(events), {'calls': 3, 'results': 2, 'errors': 1, 'missing': 1})

    def test_gate_requires_live_complete_accounted_reuse_of_pre_restart_code(self):
        good = dict(complete=True, live=True, accounting_complete=True,
                    pre_restart_hashes={'earlier'}, post_restart_calls=[{'code_hash': 'earlier', 'returns': 2}])
        self.assertTrue(lifecycle_pass(**good))
        for change in ({'live': False}, {'complete': False}, {'accounting_complete': False},
                       {'pre_restart_hashes': set()}, {'post_restart_calls': []},
                       {'post_restart_calls': [{'code_hash': 'newly-generated', 'returns': 2}]},
                       {'post_restart_calls': [{'code_hash': 'earlier', 'returns': 0}]}):
            self.assertFalse(lifecycle_pass(**{**good, **change}), change)
