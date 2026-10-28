import json
import os
import unittest
from unittest.mock import patch

from benchmark import paired
from scripts import isolation

CONTROL = json.loads((paired.ROOT / 'config/external-subscription-proposal-native-tools-ten-32k.json').read_text())


class AljureSciSettingsTests(unittest.TestCase):
    def test_absent_settings_are_the_64k_raw_control_and_leave_the_plan_unchanged(self):
        self.assertEqual({'surface': 'raw', 'results': 'raw', 'worker_output_bytes': 65536}, paired.aljure_sci(CONTROL))
        self.assertEqual(paired.ROOT / 'var/isolation-proof.json', paired.sci_proof_path(CONTROL))
        self.assertNotIn('sci', paired.capabilities(CONTROL)['aljure'])
        self.assertEqual(paired.CAPABILITIES['aljure'], paired.capabilities(CONTROL)['aljure'])

    def test_supported_settings_enter_the_capability_record(self):
        config = {**CONTROL, 'aljure_sci': {'surface': 'assisted', 'results': 'bounded', 'worker_output_bytes': 1048576}}
        paired.validate_config(config)
        self.assertEqual(1048576, paired.capabilities(config)['aljure']['expression_output_bytes'])
        self.assertEqual('bounded', paired.capabilities(config)['aljure']['sci']['results'])
        self.assertEqual(paired.ROOT / 'var/sci-contract-proof-1048576.json', paired.sci_contract_proof_path(config))

    def test_unsupported_settings_are_refused(self):
        for sci in ({'surface': 'raw', 'results': 'bounded'}, {'worker_output_bytes': 4194304},
                    {'surface': 'magic'}, {'extra': True}):
            with self.assertRaises(ValueError):
                paired.validate_config({**CONTROL, 'aljure_sci': sci})


class SupervisorOutputBoundTests(unittest.TestCase):
    def test_only_proven_bounds_are_accepted_and_each_has_its_own_proof(self):
        with patch.dict(isolation.LIMITS), patch.dict(isolation.NEGATIVE):
            for value, name, probe in (('65536', 'isolation-proof.json', 1000000),
                                       ('1048576', 'isolation-proof-1048576.json', 2097152)):
                with patch.dict(os.environ, {'REPL_LAB_WORKER_OUTPUT_BYTES': value}):
                    self.assertEqual(int(value), isolation.apply_output_bound())
                    self.assertEqual(name, isolation.proof_path().name)
                    # The oversized control always exceeds the bound it proves.
                    self.assertIn('(repeat %d ' % probe, isolation.NEGATIVE['oversized-result'])
            for value in ('4194304', '1mb', ''):
                with patch.dict(os.environ, {'REPL_LAB_WORKER_OUTPUT_BYTES': value}):
                    with self.assertRaises(RuntimeError):
                        isolation.apply_output_bound()


if __name__ == '__main__':
    unittest.main()
