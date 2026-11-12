"""Evidence gates must not turn scripted reuse, failed calls or partial runs into learning."""
import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from benchmark.learning_report import lifecycle_pass, tool_reliability, task_safety


class LearningEvidenceTests(unittest.TestCase):
    def test_safety_fails_closed_on_missing_cleanup_restart_and_failure(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'gateway').mkdir()
            self.assertFalse(task_safety(root, {}))
            for name, value in [('gateway/cleanup.json', {'ok': True}),
                                ('docker-before.json', {'session': 'one'}),
                                ('docker-after.json', {'session': 'one'})]:
                (root / name).write_text(json.dumps(value))
            self.assertTrue(task_safety(root, {}))
            self.assertFalse(task_safety(root, {'failure': 'IsolationPreflightFailed'}))
            (root / 'docker-after.json').write_text(json.dumps({'session': 'two'}))
            self.assertFalse(task_safety(root, {}))

    def test_missing_tool_results_are_not_counted_as_success(self):
        events = [{'type': 'tool-call'}] * 3 + [
            {'type': 'tool-result', 'payload': {'status': 'ok'}},
            {'type': 'tool-result', 'payload': {'status': 'error'}}]
        self.assertEqual(tool_reliability(events), {'calls': 3, 'results': 2, 'errors': 1, 'missing': 1})

    def test_gate_requires_live_complete_accounted_reuse_of_pre_restart_code(self):
        good = dict(complete=True, live=True, accounting_complete=True, safety_complete=True,
                    pre_restart_hashes={'earlier'}, post_restart_calls=[{'code_hash': 'earlier', 'returns': 2}])
        self.assertTrue(lifecycle_pass(**good))
        for change in ({'live': False}, {'complete': False}, {'accounting_complete': False},
                       {'safety_complete': False}, {'pre_restart_hashes': set()}, {'post_restart_calls': []},
                       {'post_restart_calls': [{'code_hash': 'newly-generated', 'returns': 2}]},
                       {'post_restart_calls': [{'code_hash': 'earlier', 'returns': 0}]}):
            self.assertFalse(lifecycle_pass(**{**good, **change}), change)
