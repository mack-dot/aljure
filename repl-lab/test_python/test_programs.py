"""aljure_contract.programs (research/PROGRAMMATIC_EXECUTION.md): the plan-side grant is validated,
declared in the plan's capabilities, Aljure-only, and absent from every earlier contract.
FIXTURES ONLY: no Docker, no model call, no network."""
import unittest

from benchmark import paired
from test_thesis_trajectory import CONFIG

BASE = {k: v for k, v in CONFIG.items() if k != 'trajectory'}
ONLY = {'aljure_only': {'disclosure': 'development benchmark; no Prime comparison is made'}}
GRANT = {'tools': [{'name': 'service_list'}, {'name': 'service_get', 'max_calls': 500},
                   {'name': 'service_update', 'max_calls': 200, 'approval': 'preapproved'}],
         'max_ops_per_program': 300, 'direct_tools': True}


class ProgramsSwitchTests(unittest.TestCase):
    def test_off_by_default_and_declared_when_on(self):
        self.assertNotIn('programs', paired.aljure_contract(BASE))
        self.assertNotIn('programs', paired.capabilities(BASE)['aljure'].get('execution_contract', {}))
        config = {**BASE, **ONLY, 'aljure_contract': {'programs': GRANT}}
        contract = paired.aljure_contract(config)
        self.assertEqual(contract['programs'], GRANT)
        text = paired.capabilities(config)['aljure']['execution_contract']['programs']
        self.assertIn('service_update (effect, at most 200 calls, preapproved)', text)
        self.assertIn('300 operations per program, 2000 per task', text)
        self.assertIn('program_run and direct one-operation tools', text)
        self.assertIn('Aljure-only', text)
        self.assertEqual(paired.harnesses(config), ('aljure',))

    def test_the_grant_refuses_unknown_tools_unapproved_effects_and_oversized_budgets(self):
        for bad, message in (({'tools': [{'name': 'shell'}]}, 'known tools'),
                             ({'tools': [{'name': 'service_update'}]}, 'preapproved'),
                             ({'tools': [{'name': 'service_get'}, {'name': 'service_get'}]}, 'distinct'),
                             ({'tools': [{'name': 'service_get', 'approval': 'ask'}]}, 'approval must be'),
                             ({'tools': [{'name': 'service_get'}], 'max_ops_per_task': 50000}, 'max_ops_per_task must be 1-20000'),
                             ({'tools': [{'name': 'service_get'}], 'program_tool': False}, 'program_tool and/or direct_tools'),
                             ({'tools': [{'name': 'service_get'}], 'shell': True}, 'programs takes'),
                             ({'tools': []}, 'must list')):
            with self.assertRaisesRegex(ValueError, message, msg=str(bad)):
                paired.programs_switch(bad)

    def test_programs_need_an_aljure_only_disclosure_and_no_trajectory(self):
        with self.assertRaisesRegex(ValueError, 'aljure_only'):
            paired.aljure_contract({**BASE, 'aljure_contract': {'programs': GRANT}})
        with self.assertRaisesRegex(ValueError, 'no programs'):
            paired.trajectory_spec({**CONFIG, **ONLY, 'aljure_contract': {'programs': GRANT}})

    def test_a_service_task_carries_its_pinned_fixture_and_a_plain_task_does_not(self):
        import json
        import tempfile
        from pathlib import Path
        from benchmark.oolong import digest
        with tempfile.TemporaryDirectory() as root:
            public = Path(root) / 'public'
            public.mkdir()
            (public / 'c.txt').write_text('Date: Jan 01, 2023 || User: 1 || Instance: x\n')
            fixture = {'collections': {'issues': {'i1': {'status': 'open'}}}, 'faults': {}}
            (public / 'f.json').write_text(json.dumps(fixture))
            task = {'task_id': 't', 'question': 'q', 'context_path': 'c.txt',
                    'context_sha256': digest((public / 'c.txt').read_bytes())}
            self.assertNotIn('service_fixture', paired.public_input(root, task))
            service = {**task, 'service_fixture_path': 'f.json', 'service_fixture_sha256': digest((public / 'f.json').read_bytes())}
            self.assertEqual(paired.public_input(root, service)['service_fixture'], fixture)
            with self.assertRaises(Exception):
                paired.public_input(root, {**service, 'service_fixture_sha256': '0' * 64})


if __name__ == '__main__':
    unittest.main()
