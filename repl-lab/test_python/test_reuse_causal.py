import copy
import json
import re
import unittest
from unittest.mock import patch

from benchmark import reuse_causal as experiment
from benchmark import reuse_interface
from benchmark.paired import aljure_contract


def events_for(loaded_hash, name, *extra):
    return [{'type': 'artifact-library-loaded', 'payload': {'library-sha256': 'pin', 'approved': 1}},
            {'type': 'artifact-applicability', 'payload': {'artifact': 'a', 'code-hash': loaded_hash, 'decision': 'preload', 'reason': 'applicable'}},
            {'type': 'artifact-preloaded', 'payload': {'worker': 0, 'functions': [{'name': name, 'arity': 1, 'hash': 'a', 'code-hash': loaded_hash, 'role': 'export'}]}},
            *extra]


def call(session, seq, op, command, value, status='ok'):
    return [{'type': 'tool-call', 'payload': {'session': session, 'command': {'op': op, **command}}},
            {'type': 'tool-result', 'payload': {'session': session, 'call-sequence': seq, 'op': op, 'status': status, 'result': {'value': value}}}]


REQUEST = {'messages': [{'role': 'user', 'content': '{:task {} :approved-functions {:functions []}}'}]}


class ReuseCausalTest(unittest.TestCase):
    def test_cases_are_disjoint_from_every_earlier_development_record_and_withheld_cases_need_the_rule(self):
        cases = experiment.generate()
        self.assertEqual(cases, experiment.generate())
        self.assertEqual([c['kind'] for c in cases], ['eligible'] * 3 + ['parity', 'changed-rules', 'withheld', 'withheld', 'sufficient', 'parity', 'changed-rules'])
        pattern = r'blocked=(yes|no) age_minutes=(\d+) attempts=(\d+)'
        _, old = reuse_interface.bundle()
        old_text = '\n'.join(v.decode() for k, v in old.items() if k.endswith('.txt')) + old['controller/panel.json'].decode()
        known = set(re.findall(pattern, old_text))
        for case in reuse_interface.generate():
            known.update(re.findall(pattern, case['input']['context']))
        for case in cases:
            triples = re.findall(pattern, case['input']['context'])
            self.assertEqual(len(triples), len(set(triples)))
            self.assertFalse(set(triples) & known)
            known.update(triples)
            self.assertEqual({'context', 'task'}, set(case['input']))
            if case['kind'] in ('withheld', 'sufficient'):
                context = case['input']['context']
                # The retained predicate's three literals are present; the retry rule is not.
                for literal in ('blocked=', "'hold'", 'age_minutes>=60 means expedite'):
                    self.assertIn(literal, context)
                self.assertNotIn('attempts>=3', context)
                for word in ('library', 'artifact', 'tool', 'function', 'route-hold-rules'):
                    self.assertNotIn(word, context.split('\n')[0])
            if case['kind'] == 'withheld':
                self.assertNotIn(case['answer'], case['without_rule_answers'])
                self.assertNotEqual(case['answer'], '0')
        for case in cases:
            if case['kind'] == 'changed-rules':
                self.assertNotEqual(case['answer'], case['legacy_answer'])
        self.assertEqual(20, len(experiment.sequence(cases)))
        order = experiment.sequence(cases)
        self.assertEqual(['A', 'B', 'B', 'A', 'A', 'B', 'B', 'A', 'A', 'B'], [e['arm'] for e in order[:10]])
        self.assertEqual(['C0', 'C', 'C', 'C0', 'C0', 'C', 'C', 'C0', 'C0', 'C'], [e['arm'] for e in order[10:]])
        self.assertEqual(['reuse-causal-6'] * 2, [e['task_id'] for e in order[10:12]])

    def test_stateless_contract_has_no_library_and_library_contract_needs_the_interface(self):
        self.assertNotIn('artifacts', aljure_contract({'aljure_contract': {}}))
        self.assertNotIn('skill_interface', aljure_contract({'aljure_contract': {}}))
        with self.assertRaises(ValueError):
            aljure_contract({'aljure_contract': {'skill_interface': 'inspect-v1'}})

    def test_no_paid_transport_without_new_exact_approval(self):
        with patch.object(experiment, 'read_plan', return_value=({'plan_sha256': 'new-plan'}, [])), \
             patch.object(experiment, 'preflight') as preflight, \
             patch.object(experiment, 'ClaudeSubscriptionTransport') as paid:
            for approval in (None, '40db9df9422121aa53779bb27461076858530f18078fe1510803b0dd85f45ce4', ''):
                with self.assertRaises(ValueError):
                    experiment.run(None, None, None, approval)
            preflight.assert_not_called()
            paid.assert_not_called()

    def test_attribution_levels_separate_exposure_inspection_probe_execution_and_decision_use(self):
        question = "How many data points should be classified as label 'retry'? Return only Answer: N."
        h, name = 'c' * 64, 'route-hold-rules'
        # No library at all.
        self.assertEqual('no-library', experiment.attribution(call('root', 3, 'repl/eval', {'source': '(count context-lines)'}, 40), 'Answer: 7', question, {'messages': []})['level'])
        # Inventory shown, nothing used.
        base = experiment.attribution(events_for(h, name), 'Answer: 7', question, REQUEST)
        self.assertEqual('admitted', base['level'])
        self.assertFalse(base['useful_reuse'])
        # Inspection alone.
        inspected = experiment.attribution(events_for(h, name, *call('root', 3, 'skill/inspect', {'hash': 'a', 'section': 'function'}, {})), 'Answer: 7', question, REQUEST)
        self.assertEqual('inspected', inspected['level'])
        # A nil probe: executed, not useful, not used (run-3 baseline task 1).
        probe = call('root', 7, 'repl/eval', {'source': '(route-hold-rules (first context-lines))'}, None)
        probe_log = {'type': 'artifact-invocations', 'payload': {'session': 'root', 'op': 'repl/eval', 'call-sequence': 7,
                     'invocations': [{'code-hash': h, 'calls': 1, 'returns': 1, 'nils': 1, 'values': [], 'name': name}]}}
        probed = experiment.attribution(events_for(h, name, *probe, probe_log), 'Answer: 7', question, REQUEST)
        self.assertEqual('executed', probed['level'])
        self.assertTrue(probed['flags']['attempted'] and probed['flags']['executed'])
        self.assertFalse(probed['flags']['useful'] or probed['useful_reuse'])
        # Legacy traces without the nils field: a nil probe records no values and stays not useful.
        legacy_log = copy.deepcopy(probe_log)
        del legacy_log['payload']['invocations'][0]['nils']
        self.assertFalse(experiment.attribution(events_for(h, name, *probe, legacy_log), 'Answer: 7', question, REQUEST)['flags']['useful'])
        # Useful execution whose value did not reach the answer.
        counted = call('root', 9, 'repl/eval', {'source': '(route-hold-rules (nth context-lines 3))'}, 'retry')
        counted_log = {'type': 'artifact-invocations', 'payload': {'session': 'root', 'op': 'repl/eval', 'call-sequence': 9,
                       'invocations': [{'code-hash': h, 'calls': 1, 'returns': 1, 'nils': 0, 'values': ['retry'], 'name': name}]}}
        useful = experiment.attribution(events_for(h, name, *counted, counted_log), 'Answer: 7', question, REQUEST)
        self.assertEqual('useful', useful['level'])
        self.assertFalse(useful['useful_reuse'])
        # The evaluation that executed the export returned the delivered number: decision use.
        decided = call('root', 12, 'repl/eval', {'source': '(count (filter #(= "retry" (route-hold-rules %)) context-lines))'}, 7)
        decided_log = {'type': 'artifact-invocations', 'payload': {'session': 'root', 'op': 'repl/eval', 'call-sequence': 12,
                       'invocations': [{'code-hash': h, 'calls': 40, 'returns': 40, 'nils': 1, 'values': ['hold', 'retry', 'expedite'], 'name': name}]}}
        used = experiment.attribution(events_for(h, name, *decided, decided_log), 'Answer: 7', question, REQUEST)
        self.assertEqual('used', used['level'])
        self.assertTrue(used['useful_reuse'])
        # The same trace with a different delivered number is not decision use.
        self.assertFalse(experiment.attribution(events_for(h, name, *decided, decided_log), 'Answer: 8', question, REQUEST)['useful_reuse'])
        # An unloaded code hash never counts, nor does a textual mention without execution.
        other_log = copy.deepcopy(decided_log)
        other_log['payload']['invocations'][0]['code-hash'] = 'd' * 64
        mention = experiment.attribution(events_for(h, name, *decided, other_log), 'Answer: 7', question, REQUEST)
        self.assertEqual('attempted', mention['level'])
        self.assertFalse(mention['useful_reuse'])
        # artifact_call values for the asked label counting to the answer are decision use; nil values are not useful.
        invoked = [{'type': 'artifact-invoked', 'payload': {'session': 'root', 'origin': 'approved-external-library', 'code-hash': h,
                                                             'call-sequence': 20 + i, 'value': v}} for i, v in enumerate(['retry', 'hold', 'retry'])]
        via_call = experiment.attribution(events_for(h, name, *invoked), 'Answer: 2', question, REQUEST)
        self.assertTrue(via_call['useful_reuse'])
        self.assertFalse(experiment.attribution(events_for(h, name, *invoked), 'Answer: 3', question, REQUEST)['useful_reuse'])
        nil_call = [{'type': 'artifact-invoked', 'payload': {'session': 'root', 'origin': 'approved-external-library', 'code-hash': h, 'call-sequence': 20, 'value': None}}]
        self.assertEqual('executed', experiment.attribution(events_for(h, name, *nil_call), 'Answer: 0', question, REQUEST)['level'])

    def rows(self):
        rows = []
        for entry in experiment.sequence(experiment.generate()):
            kind = next(c['kind'] for c in experiment.generate() if c['task_id'] == entry['task_id'])
            rows.append({**entry, 'kind': kind, 'correct': True, 'status': 'completed', 'safety_complete': True, 'seconds': 1,
                         'usage': {'known_model_cost_usd': .01, 'accounting_complete': True, 'calls': 3},
                         'prompt': {'first_request_tokens': 3000, 'tools_bytes': 2000},
                         'attribution': {'level': 'admitted' if entry['arm'] in ('B', 'C') else 'no-library', 'useful_reuse': False,
                                         'flags': {'executed': False}}})
        return rows

    def test_frozen_outcome_patterns(self):
        rows = self.rows()
        self.assertEqual('INCOMPLETE', experiment.summarize(rows[:-1])['development_gate'])
        # All correct everywhere with no execution: the rule was recoverable without the library.
        report = experiment.summarize(rows)
        self.assertEqual('COMPLETE-PENDING-ATTRIBUTION-REVIEW', report['development_gate'])
        self.assertEqual('rule-recoverable-without-library', report['outcome_pattern'])
        def with_(mutate):
            changed = copy.deepcopy(rows)
            for r in changed:
                mutate(r)
            return experiment.summarize(changed)
        def c0_wrong(r):
            if r['arm'] == 'C0' and r['kind'] == 'withheld':
                r['correct'] = False
        self.assertEqual('knowledge-reuse-without-execution', with_(c0_wrong)['outcome_pattern'])
        def c_used(r):
            c0_wrong(r)
            if r['arm'] == 'C' and r['kind'] == 'withheld':
                r['attribution'] = {'level': 'used', 'useful_reuse': True, 'flags': {'executed': True}}
        self.assertEqual('reuse-only-when-necessary', with_(c_used)['outcome_pattern'])
        def b_used(r):
            c_used(r)
            if r['arm'] == 'B' and r['kind'] == 'eligible':
                r['attribution'] = {'level': 'used', 'useful_reuse': True, 'flags': {'executed': True}}
        self.assertEqual('voluntary-useful-reuse', with_(b_used)['outcome_pattern'])
        def nobody(r):
            if r['kind'] == 'withheld':
                r['correct'] = False
        self.assertEqual('no-reuse-even-when-necessary', with_(nobody)['outcome_pattern'])
        def negative(r):
            if r['arm'] == 'C' and r['kind'] == 'changed-rules':
                r['attribution'] = {'level': 'executed', 'useful_reuse': False, 'flags': {'executed': True}}
        self.assertEqual('NEGATIVE-CONTROL-FAILURE', with_(negative)['development_gate'])
        def unknown_cost(r):
            r['usage']['accounting_complete'] = False
        self.assertEqual('INCOMPLETE', with_(unknown_cost)['development_gate'])
        # A B-arm useful reuse with a wrong answer does not satisfy the primary endpoint.
        def b_used_wrong(r):
            if r['arm'] == 'B' and r['kind'] == 'eligible':
                r['attribution'] = {'level': 'used', 'useful_reuse': True, 'flags': {'executed': True}}
                r['correct'] = False
        self.assertEqual(0, with_(b_used_wrong)['endpoints']['B_eligible_useful_reuse_correct'])


if __name__ == '__main__':
    unittest.main()
