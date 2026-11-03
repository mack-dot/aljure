"""The execution_language plan setting (research/Q_SUBSTRATE_BRIEF.md): the matched Python
surface exists only assisted, bounded, without Clojure-only contract levels, and pinned."""
import json
import unittest
from unittest.mock import patch

from benchmark import paired

CONTROL = json.loads((paired.ROOT / 'config/external-subscription-proposal-native-tools-ten-32k.json').read_text())
PYTHON = {**CONTROL, 'execution_language': 'python', 'aljure_sci': {'surface': 'assisted', 'results': 'bounded', 'worker_output_bytes': 65536},
          **({'execution_images': {**CONTROL['execution_images'], 'python': 'sha256:' + 'b' * 64}} if 'execution_images' in CONTROL else {})}


class ExecutionLanguageTests(unittest.TestCase):
    def test_absent_means_clojure_and_leaves_the_capability_record_unchanged(self):
        self.assertEqual('clojure', paired.execution_language(CONTROL))
        paired.validate_config(CONTROL)
        self.assertEqual(paired.CAPABILITIES['aljure'], paired.capabilities(CONTROL)['aljure'])

    def test_python_needs_the_matched_surface_and_no_clojure_only_levels(self):
        paired.validate_config(PYTHON)
        aljure = paired.capabilities(PYTHON)['aljure']
        self.assertEqual('python', aljure['execution_language'])
        self.assertIn('Python', aljure['language'])
        for bad in ({**PYTHON, 'execution_language': 'ruby'},
                    {**PYTHON, 'aljure_sci': {'surface': 'assisted', 'results': 'raw'}},
                    {**PYTHON, 'aljure_sci': {'surface': 'raw', 'results': 'raw'}},
                    {**CONTROL, 'execution_language': 'python'},
                    {**PYTHON, 'aljure_contract': {'structured_labels': True}},
                    {**PYTHON, 'aljure_contract': {'skill_interface': 'inspect-v1'}}):
            with self.assertRaises(ValueError):
                paired.validate_config(bad)

    def test_a_frozen_python_plan_pins_the_python_image_too(self):
        image = 'sha256:' + 'a' * 64
        with self.assertRaises(ValueError):
            paired.validate_config({**PYTHON, 'execution_images': {'sci': image, 'prime': image}})
        paired.validate_config({**PYTHON, 'execution_images': {'sci': image, 'prime': image, 'python': image}})
        paired.validate_config({**CONTROL, 'execution_images': {'sci': image, 'prime': image}})
        with self.assertRaises(ValueError):
            paired.validate_config({**CONTROL, 'execution_images': {'sci': image, 'prime': image, 'other': image}})

    def test_readiness_blocks_without_a_python_proof_and_never_runs_the_worker(self):
        with patch.object(paired, 'python_readiness', side_effect=ValueError('Python contract proof is missing or stale')) as gate, \
             patch.object(paired.subprocess, 'run', side_effect=AssertionError('no subprocess in this test')):
            ready = paired.readiness({'plan_sha256': 'fixture'}, PYTHON, native_prime=False)
        self.assertTrue(any('Python contract proof' in b for b in ready['blockers']), ready['blockers'])
        gate.assert_called_once()
        self.assertFalse(ready['ready'])


if __name__ == '__main__':
    unittest.main()
