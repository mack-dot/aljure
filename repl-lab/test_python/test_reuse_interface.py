import copy
import json
import unittest
from unittest.mock import patch

from benchmark import reuse_interface as experiment
from benchmark.paired import aljure_contract


class ReuseInterfaceTest(unittest.TestCase):
    def test_new_cases_have_no_record_or_feature_overlap_and_changed_rules_are_discriminating(self):
        cases = experiment.generate()
        self.assertEqual(cases, experiment.generate())
        self.assertEqual(['eligible'] * 3 + ['parity', 'changed-rules'], [c['kind'] for c in cases])
        _, old = experiment.bundle()
        old_text = '\n'.join(v.decode() for k, v in old.items() if k.endswith('.txt')) + old['controller/panel.json'].decode()
        pattern = r'blocked=(yes|no) age_minutes=(\d+) attempts=(\d+)'
        known = set(experiment.re.findall(pattern, old_text))
        for case in cases:
            triples = experiment.re.findall(pattern, case['input']['context'])
            self.assertEqual(len(triples), len(set(triples)))
            self.assertFalse(set(triples) & known)
            known.update(triples)
            self.assertEqual({'context', 'task'}, set(case['input']))
        self.assertNotEqual(cases[-1]['answer'], cases[-1]['legacy_answer'])
        self.assertEqual(10, len(experiment.sequence(cases)))

    def test_opt_in_needs_existing_library_and_does_not_change_baseline_contract(self):
        base = aljure_contract({})
        self.assertNotIn('skill_interface', base)
        with self.assertRaises(ValueError):
            aljure_contract({'aljure_contract': {'skill_interface': 'inspect-v1'}})
        with self.assertRaises(ValueError):
            aljure_contract({'aljure_contract': {'skill_interface': True}})

    def test_no_paid_transport_without_new_exact_approval(self):
        with patch.object(experiment, 'read_plan', return_value=({'plan_sha256': 'new-plan'}, [])), \
             patch.object(experiment, 'preflight') as preflight, \
             patch.object(experiment, 'ClaudeSubscriptionTransport') as paid:
            for approval in (None, 'old-six-task-approval', ''):
                with self.assertRaises(ValueError):
                    experiment.run(None, None, None, approval)
            preflight.assert_not_called()
            paid.assert_not_called()

    def test_inspection_and_unloaded_hashes_do_not_count_as_invocation(self):
        events = [{'type': 'artifact-preloaded', 'payload': {'functions': [{'role': 'export', 'code-hash': 'approved'}]}},
                  {'type': 'tool-call', 'payload': {'command': {'op': 'skill/inspect'}}},
                  {'type': 'artifact-invoked', 'payload': {'origin': 'approved-external-library', 'code-hash': 'other'}}]
        self.assertFalse(experiment.observations(events)['source_attributed_invocation'])
        events.append({'type': 'artifact-invoked', 'payload': {'origin': 'approved-external-library',
                                                               'code-hash': 'approved', 'call-sequence': 8}})
        self.assertTrue(experiment.observations(events)['source_attributed_invocation'])

    def test_failure_unknown_cost_or_negative_transfer_prevents_acceptance(self):
        rows = []
        for arm in ('baseline', 'repaired'):
            for kind in ['eligible'] * 3 + ['parity', 'changed-rules']:
                rows.append({'arm': arm, 'kind': kind, 'correct': True, 'status': 'completed', 'safety_complete': True,
                             'source_attributed_invocation': arm == 'repaired' and kind == 'eligible', 'seconds': 1,
                             'usage': {'known_model_cost_usd': .01, 'accounting_complete': True}})
        self.assertEqual('PENDING-ATTRIBUTION-REVIEW', experiment.summarize(rows)['development_gate'])
        for key, value in [('correct', False), ('source_attributed_invocation', True),
                           ('safety_complete', False), ('status', 'error')]:
            changed = copy.deepcopy(rows)
            changed[-1][key] = value
            self.assertIn(experiment.summarize(changed)['development_gate'], ('NO-GO', 'INCOMPLETE'))
        changed = copy.deepcopy(rows)
        changed[-1]['usage']['accounting_complete'] = False
        self.assertEqual('INCOMPLETE', experiment.summarize(changed)['development_gate'])


if __name__ == '__main__':
    unittest.main()
