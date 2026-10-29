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


class TaskLimitTests(unittest.TestCase):
    def test_absent_limits_keep_the_original_defaults_and_capabilities(self):
        self.assertEqual({'task_seconds': 120, 'request_bytes': 1048576, 'task_output_bytes': 4194304,
                          'session_steps': 64}, paired.task_limits(CONTROL))
        self.assertEqual(paired._capabilities(CONTROL), paired.capabilities(CONTROL))
        gateway = paired.gateway_config(CONTROL, 'aljure')
        self.assertEqual(120000, gateway['limits']['wall-ms'])
        self.assertNotIn('request-bytes', gateway)

    def test_configured_limits_reach_the_gateway_and_the_capability_record(self):
        config = {**CONTROL, 'task_seconds': 900, 'request_bytes': 4194304, 'task_output_bytes': 67108864,
                  'session_steps': 1000}
        paired.validate_config(config)
        gateway = paired.gateway_config(config, 'prime')
        self.assertEqual(900000, gateway['limits']['wall-ms'])
        self.assertEqual(4194304, gateway['request-bytes'])
        declared = paired.capabilities(config)
        self.assertEqual(900, declared['shared']['task_seconds'])
        self.assertEqual(67108864, declared['prime']['task_output_bytes'])
        self.assertEqual(1000, declared['aljure']['session_steps'])
        self.assertNotEqual(paired.capabilities(CONTROL), declared)

    def test_out_of_range_limits_are_refused(self):
        for bad in ({'task_seconds': 60}, {'task_seconds': 7200}, {'request_bytes': 8 * 1048576},
                    {'task_output_bytes': 1024}, {'session_steps': 10}, {'task_seconds': 900.0}):
            with self.assertRaises(ValueError):
                paired.validate_config({**CONTROL, **bad})


class SessionDeadlineTests(unittest.TestCase):
    def test_only_an_explicit_plan_bound_extends_the_session(self):
        with patch.object(isolation.time, 'time', return_value=10), patch.object(isolation.time, 'monotonic', return_value=100):
            far = {'REPL_LAB_TASK_DEADLINE_MS': '999999999'}
            with patch.dict(os.environ, far):
                os.environ.pop('REPL_LAB_SESSION_SECONDS', None)
                self.assertEqual(220, isolation.task_deadline())
            with patch.dict(os.environ, {**far, 'REPL_LAB_SESSION_SECONDS': '900'}):
                self.assertEqual(1000, isolation.task_deadline())
            with patch.dict(os.environ, {'REPL_LAB_TASK_DEADLINE_MS': '70000', 'REPL_LAB_SESSION_SECONDS': '900'}):
                self.assertEqual(160, isolation.task_deadline())
            for bad in ('60', '7200', '900.5', 'x'):
                with patch.dict(os.environ, {**far, 'REPL_LAB_SESSION_SECONDS': bad}):
                    with self.assertRaisesRegex(RuntimeError, 'Invalid session bound'):
                        isolation.task_deadline()
