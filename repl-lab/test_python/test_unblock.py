"""Pilots 1 and 2 of research/UNBLOCK_ACQUISITION.md: the seeded-library positive control, Aljure-only
plans without a Prime counterpart, the acquisition modes and arms, and the reuse-pilot importer.
FIXTURES ONLY: no Docker, no model call, no network."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from benchmark import official, paired
from benchmark.oolong import jsonl
from test_thesis_trajectory import CONFIG, PROFILE, SuiteFixture

PIN = 'a' * 64
BASE = {k: v for k, v in CONFIG.items() if k != 'trajectory'}


class SupplyAndAljureOnlyTests(unittest.TestCase):
    def test_the_positive_control_is_off_by_default_and_declared_when_on(self):
        library = {'library': 'research/evidence/reuse-pilot-seed/library', 'library_sha256': PIN}
        d = {**BASE, 'aljure_contract': {'artifacts': library}}
        p = {**BASE, 'aljure_contract': {'artifacts': {**library, 'supply': 'applied'}}}
        self.assertNotIn('supply', paired.aljure_contract(d)['artifacts'])
        contract_d = paired.capabilities(d)['aljure']['execution_contract']
        contract_p = paired.capabilities(p)['aljure']['execution_contract']
        self.assertNotIn('artifacts_supply', contract_d)
        self.assertEqual(contract_p['artifacts_supply'], paired.SUPPLY_CAPABILITY)
        self.assertEqual({k: v for k, v in contract_p.items() if k != 'artifacts_supply'}, contract_d)
        with self.assertRaisesRegex(ValueError, 'artifacts must be'):
            paired.aljure_contract({**BASE, 'aljure_contract': {'artifacts': {**library, 'supply': 'always'}}})

    def test_aljure_only_needs_its_disclosure_and_excludes_a_prime_reference(self):
        good = {**BASE, 'aljure_only': {'disclosure': 'Pilot 1 measures library value; no Prime comparison is made.'}}
        self.assertEqual(paired.harnesses(good), ('aljure',))
        self.assertEqual(paired.harnesses(BASE), ('aljure', 'prime'))
        with self.assertRaisesRegex(ValueError, 'aljure_only needs'):
            paired.harnesses({**BASE, 'aljure_only': {'disclosure': 'Aljure only.'}})
        with self.assertRaisesRegex(ValueError, 'aljure_only needs'):
            paired.aljure_only({**good, 'prime_reference': {}})


class AcquisitionModeTests(unittest.TestCase):
    def test_modes_are_arm_e_only_and_the_optional_text_is_unchanged(self):
        artifacts = {'library': 'var/x', 'library_sha256': PIN}
        for mode in ('optional', 'structured', 'capture'):
            paired.aljure_contract({**BASE, 'aljure_contract': {'artifacts': artifacts, 'acquisition': {'arm': 'E', 'mode': mode}}})
        for bad in ({'arm': 'C', 'mode': 'capture'}, {'arm': 'E', 'mode': 'forced'}):
            with self.assertRaisesRegex(ValueError, 'acquisition must be'):
                paired.aljure_contract({**BASE, 'aljure_contract': {'artifacts': artifacts, 'acquisition': bad}})
        self.assertEqual(paired.acquisition_capability({'arm': 'E'}), paired.ACQUISITION_CAPABILITY.format(arm='E'))
        structured = paired.acquisition_capability({'arm': 'E', 'mode': 'structured'})
        self.assertIn(paired.ACQUISITION_MODES['structured'], structured)
        self.assertNotIn(paired.ACQUISITION_MODES['optional'], structured)

    def test_pilot_two_arms_map_onto_arm_e_with_their_mode(self):
        config = copy.deepcopy(CONFIG)
        config['trajectory']['arms'] = ['A', 'E', 'ES', 'EX']
        spec = paired.trajectory_spec(config)
        self.assertEqual([paired.arm_acquisition(a) for a in ('E', 'ES', 'EX')],
                         [{'arm': 'E'}, {'arm': 'E', 'mode': 'structured'}, {'arm': 'E', 'mode': 'capture'}])
        contract = paired.trajectory_contract(config, 'EX', 'var/lib', PIN)['aljure_contract']
        self.assertEqual(contract['acquisition'], {'arm': 'E', 'mode': 'capture'})
        caps = paired.trajectory_capabilities(config, 'ES', spec)['trajectory']
        self.assertIn('promotion', caps)
        self.assertIn('same order for arms A, E, ES and EX', caps['order'])
        # The thesis pilot's capability text is unchanged.
        thesis = paired.trajectory_capabilities(CONFIG, 'E', paired.trajectory_spec(CONFIG))['trajectory']
        self.assertTrue(thesis['order'].endswith('same order for arms A, C and E'))
        config['trajectory']['arms'] = ['A', 'ES']
        with self.assertRaisesRegex(ValueError, 'Arms A, C and E'):
            paired.trajectory_spec(config)


REUSE = {**copy.deepcopy(PROFILE), 'selection': 'reuse-pilot-v1', 'count': 18}
REUSE['families']['F1'] = {**REUSE['families']['F1'], 'per_window': 2, 'numeric': 2}


class ReuseImporterTests(SuiteFixture, unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_the_reuse_profile_takes_two_numeric_questions_per_window_and_keeps_the_thesis_path(self):
        pins, cache = self.build_suite(self.root)
        pins['official_profiles']['oolong-synth:reuse-pilot:validation'] = REUSE
        with patch.object(official, 'PINS', pins):
            manifest = official.prepare_thesis_pilot(self.root / 'reuse', cache=cache, download=False, exposed=set(), name='reuse-pilot')
            thesis = official.prepare_thesis_pilot(self.root / 'thesis', cache=cache, download=False, exposed=set())
            with self.assertRaisesRegex(ValueError, 'not pinned'):
                official.prepare_thesis_pilot(self.root / 'other', cache=cache, download=False, exposed=set(), name='other')
        self.assertEqual((manifest['selection']['method'], manifest['selection']['dataset']), ('reuse-pilot-v1', 'reuse-pilot'))
        answers = list(jsonl(self.root / 'reuse/controller/answers.jsonl'))
        for window in [w for _, w in PROFILE['families']['F1']['windows']]:
            # Both NUMERIC_ONE_CLASS rows of the window (ids x0 and x1), never the other types.
            self.assertEqual(sorted(a['id'] % 10 for a in answers if a['context_window_id'] == window), [0, 1])
        self.assertEqual(thesis['selection']['method'], 'thesis-pilot-v1')
        self.assertTrue((self.root / 'reuse/controller/task-items.json').is_file())


if __name__ == '__main__':
    unittest.main()
