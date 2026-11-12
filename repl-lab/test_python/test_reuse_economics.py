import copy
import json
import re
import unittest
from unittest.mock import patch

from benchmark import reuse_causal
from benchmark import reuse_economics as experiment
from benchmark.paired import aljure_contract, capabilities


DOMAIN = [(b, a, t) for b in ('yes', 'no') for a in range(120) for t in range(10)]


class ReuseEconomicsTest(unittest.TestCase):
    def test_long_statement_equals_the_retained_rule_and_changed_rules_differ(self):
        self.assertTrue(all(experiment.long_v1(*x) == reuse_causal.v1(*x) for x in DOMAIN))
        self.assertTrue(any(experiment.long_v2(*x) != reuse_causal.v1(*x) for x in DOMAIN))
        for text in (experiment.LONG, experiment.LONG_CHANGED):
            for literal in ('blocked=', "'hold'", 'age_minutes>=60 means expedite'):
                self.assertIn(literal, text)
            for word in ('library', 'artifact', 'tool', 'function', 'route-hold-rules', 'summary'):
                self.assertNotIn(word, text)
            self.assertEqual(6, len(re.findall(r'\(\d\)', text)))
        self.assertNotIn('otherwise attempts>=3 means retry; otherwise hold', experiment.LONG)

    def test_cases_are_disjoint_from_every_earlier_development_record(self):
        cases = experiment.generate()
        self.assertEqual(cases, experiment.generate())
        self.assertEqual([c['kind'] for c in cases], ['eligible'] * 6 + ['parity', 'changed-rules'])
        pattern = r'blocked=(yes|no) age_minutes=(\d+) attempts=(\d+)'
        known = experiment.prior_tuples()
        self.assertTrue(known)
        for case in cases:
            triples = re.findall(pattern, case['input']['context'])
            self.assertEqual(len(triples), len(set(triples)))
            self.assertFalse(set(triples) & known)
            known.update(triples)
            self.assertEqual({'context', 'task'}, set(case['input']))
            self.assertEqual(case['records'], len(case['input']['context'].splitlines()) - 2)
            if case['kind'] == 'eligible':
                self.assertTrue(case['input']['context'].startswith(experiment.LONG))
                self.assertEqual(case['answer'], case['legacy_answer'])
                self.assertNotEqual(case['answer'], '0')
            if case['kind'] == 'changed-rules':
                self.assertTrue(case['input']['context'].startswith(experiment.LONG_CHANGED))
                self.assertNotEqual(case['answer'], case['legacy_answer'])
        codes = [int(c) for case in cases if case['kind'] == 'parity' for c in re.findall(r'code=(\d+)', case['input']['context'])]
        self.assertTrue(codes and all(60000 <= c < 61000 for c in codes))
        # Records never appear in another suite's text.
        for other in reuse_causal.generate():
            self.assertNotIn('reuse-economics', other['input']['context'])

    def test_sequence_rotates_three_arms_over_eight_cases(self):
        cases = experiment.generate()
        order = experiment.sequence(cases)
        self.assertEqual(24, len(order))
        self.assertEqual(['A', 'B', 'BN', 'B', 'BN', 'A', 'BN', 'A', 'B'], [e['arm'] for e in order[:9]])
        for case in cases:
            self.assertEqual({'A', 'B', 'BN'}, {e['arm'] for e in order if e['task_id'] == case['task_id']})
        self.assertEqual(experiment.ARMS, json.loads(json.dumps(experiment.ARMS)))
        self.assertEqual(experiment.ATTEMPTS, 24)

    def test_names_only_interface_is_accepted_only_with_the_pinned_library(self):
        self.assertNotIn('skill_interface', aljure_contract({'aljure_contract': {}}))
        for interface in ('inspect-v1', 'inspect-v1-names'):
            with self.assertRaises(ValueError):
                aljure_contract({'aljure_contract': {'skill_interface': interface}})
        with self.assertRaises(ValueError):
            aljure_contract({'aljure_contract': {'skill_interface': 'inspect-v2', 'artifacts': {'library': 'x', 'library_sha256': 'y'}}})

    def test_names_only_capability_text_declares_the_withheld_summaries(self):
        base = json.loads((experiment.ROOT / 'config/learning-minimal-sonnet.json').read_text())
        library = {'library': 'research/evidence/learning-minimal-results-20261102/runs/ES-s101/library',
                   'library_sha256': 'f273cf89770402469f31d549a51c7c25a5d955940706b202565fdd3adc5b2c88'}
        def contract(interface):
            config = {**base, 'aljure_contract': {'artifacts': library, 'skill_interface': interface}}
            with patch('benchmark.paired.artifact_library', return_value=library):
                return aljure_contract(config)
        self.assertEqual('inspect-v1-names', contract('inspect-v1-names')['skill_interface'])
        self.assertEqual('inspect-v1', contract('inspect-v1')['skill_interface'])
        with patch('benchmark.paired.artifact_library', return_value=library):
            shown = capabilities({**base, 'aljure_contract': {'artifacts': library, 'skill_interface': 'inspect-v1'}})
            withheld = capabilities({**base, 'aljure_contract': {'artifacts': library, 'skill_interface': 'inspect-v1-names'}})
        self.assertIn('summaries withheld', withheld['aljure']['execution_contract']['skill_interface'])
        self.assertNotIn('withheld', shown['aljure']['execution_contract']['skill_interface'])
        self.assertEqual({k: v for k, v in shown['aljure']['execution_contract'].items() if k != 'skill_interface'},
                         {k: v for k, v in withheld['aljure']['execution_contract'].items() if k != 'skill_interface'})

    def test_no_paid_transport_without_new_exact_approval(self):
        with patch.object(experiment, 'read_plan', return_value=({'plan_sha256': 'new-plan'}, [])), \
             patch.object(experiment, 'preflight') as preflight, \
             patch.object(experiment, 'ClaudeSubscriptionTransport') as paid:
            for approval in (None, '1d5a4db2f5f730eed81664700a4efad64f58daba326a6aa47d2a055b2b0e4546', ''):
                with self.assertRaises(ValueError):
                    experiment.run(None, None, None, approval)
            preflight.assert_not_called()
            paid.assert_not_called()

    def test_evaluation_counts_come_from_tool_results(self):
        events = [{'type': 'tool-result', 'payload': {'op': 'repl/eval', 'status': 'ok'}},
                  {'type': 'tool-result', 'payload': {'op': 'repl/eval', 'status': 'error'}},
                  {'type': 'tool-result', 'payload': {'op': 'skill/inspect', 'status': 'ok'}},
                  {'type': 'tool-result', 'payload': {'op': 'artifact/call', 'status': 'ok'}},
                  {'type': 'tool-call', 'payload': {'command': {'op': 'repl/eval'}}}]
        self.assertEqual({'evaluations': 2, 'evaluation_errors': 1, 'inspections': 1, 'artifact_calls': 1}, experiment.evaluations(events))

    def rows(self):
        cases = experiment.generate()
        rows = []
        for entry in experiment.sequence(cases):
            kind = next(c['kind'] for c in cases if c['task_id'] == entry['task_id'])
            rows.append({**entry, 'kind': kind, 'correct': True, 'status': 'completed', 'safety_complete': True, 'seconds': 1,
                         'usage': {'known_model_cost_usd': .01, 'accounting_complete': True, 'calls': 3},
                         'prompt': {'first_request_tokens': 3000, 'tools_bytes': 2000},
                         'computation': {'evaluations': 1, 'evaluation_errors': 0, 'inspections': 0, 'artifact_calls': 0},
                         'attribution': {'level': 'admitted' if entry['arm'] != 'A' else 'no-library', 'useful_reuse': False,
                                         'flags': {'executed': False, 'inspected': False}}})
        return rows

    def test_frozen_outcome_patterns(self):
        rows = self.rows()
        self.assertEqual('INCOMPLETE', experiment.summarize(rows[:-1])['development_gate'])
        report = experiment.summarize(rows)
        self.assertEqual('COMPLETE-PENDING-ATTRIBUTION-REVIEW', report['development_gate'])
        self.assertEqual('reimplementation-regardless-of-length', report['outcome_pattern'])
        self.assertEqual('none', report['summary_effect'])
        self.assertEqual(6, report['endpoints']['A_eligible_correct'])
        self.assertEqual(6, report['endpoints']['A_eligible_evaluations'])
        def with_(mutate):
            changed = copy.deepcopy(rows)
            for r in changed:
                mutate(r)
            return experiment.summarize(changed)
        def used(arm, count):
            seen = {'n': 0}
            def mutate(r):
                if r['arm'] == arm and r['kind'] == 'eligible' and seen['n'] < count:
                    seen['n'] += 1
                    r['attribution'] = {'level': 'used', 'useful_reuse': True, 'flags': {'executed': True, 'inspected': True}}
            return mutate
        self.assertEqual('occasional-reuse-under-long-rules', with_(used('B', 2))['outcome_pattern'])
        self.assertEqual('summary-mediated', with_(used('B', 2))['summary_effect'])
        self.assertEqual('reuse-under-long-rules', with_(used('B', 3))['outcome_pattern'])
        b_three, bn_three = used('B', 3), used('BN', 3)
        def both(r):
            b_three(r)
            bn_three(r)
        both_report = with_(both)
        self.assertEqual('execution-independent-of-summary', both_report['summary_effect'])
        self.assertEqual(3, both_report['endpoints']['BN_eligible_inspected'])
        self.assertEqual(3, both_report['endpoints']['B_eligible_used_correct'])
        bn_report = with_(used('BN', 1))
        self.assertEqual('reimplementation-regardless-of-length', bn_report['outcome_pattern'])
        self.assertEqual('execution-independent-of-summary', bn_report['summary_effect'])
        self.assertEqual(1, bn_report['endpoints']['BN_eligible_used_correct'])
        # A used-but-wrong B task does not count toward the primary endpoint.
        b_all = used('B', 6)
        def used_wrong(r):
            b_all(r)
            if r['arm'] == 'B' and r['kind'] == 'eligible':
                r['correct'] = False
        self.assertEqual(0, with_(used_wrong)['endpoints']['B_eligible_used_correct'])
        def negative(r):
            if r['arm'] == 'BN' and r['kind'] == 'changed-rules':
                r['attribution'] = {'level': 'executed', 'useful_reuse': False, 'flags': {'executed': True, 'inspected': False}}
        self.assertEqual('NEGATIVE-CONTROL-FAILURE', with_(negative)['development_gate'])
        def wrong_control(r):
            if r['arm'] == 'B' and r['kind'] == 'parity':
                r['correct'] = False
        self.assertEqual('NEGATIVE-CONTROL-FAILURE', with_(wrong_control)['development_gate'])
        def wrong_stateless_control(r):
            if r['arm'] == 'A' and r['kind'] == 'parity':
                r['correct'] = False
        self.assertEqual('COMPLETE-PENDING-ATTRIBUTION-REVIEW', with_(wrong_stateless_control)['development_gate'])
        def unknown_cost(r):
            r['usage']['accounting_complete'] = False
        self.assertEqual('INCOMPLETE', with_(unknown_cost)['development_gate'])


if __name__ == '__main__':
    unittest.main()
