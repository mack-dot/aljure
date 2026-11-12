import json
import unittest

from benchmark import evidence as E

COMPARISON = ("In the above data, is label 'A' more common, less common, or the same frequency as label 'B'? "
              "Give your final answer in the form 'Answer: A is [X] B'")
COUNT = "In the above data, how many data points should be classified as label 'spam'? Give your final answer"
DATES = "In the above data, how many dates are represented exactly 2 times? Give your final answer"
PAIRS = "In the above data, list all pairs of user IDs (no duplicate pairs) where both users have at least one instance"


def step(source, result, ok=True):
    return {'source': source, 'ok': ok, 'result': result}


class TaskClassTest(unittest.TestCase):
    def test_classes_come_from_the_question_text_only(self):
        self.assertEqual(E.task_class(COMPARISON), 'label-comparison')
        self.assertEqual(E.task_class("Among instances occuring in December, is label 'contradiction' more common, less common, or the same frequency as label 'neutral'?"), 'label-comparison')
        self.assertEqual(E.task_class("In the above data, was label 'False' more common, less common, or the same frequency before 2022-10-02, as compared to after?"), 'label-comparison')
        self.assertEqual(E.task_class(COUNT), 'label-count')
        self.assertEqual(E.task_class(DATES), 'structural-count')
        self.assertEqual(E.task_class(PAIRS), 'pairs')
        self.assertEqual(E.task_class('What is the capital of France?'), 'unknown')
        self.assertEqual(E.task_class(None), 'unknown')


class TriggerV1Test(unittest.TestCase):
    def a(self, question, steps, language='clojure'):
        return E.assess(question, steps, language)

    def test_o3_missing_aggregation_triggers(self):
        r = self.a(COMPARISON, [step('(subs external-context 0 1500)', 'The following lines contain 438 pairs')])
        self.assertEqual((r['state'], r['trigger'], r['facts']['observables']), ('missing', True, ['O3-missing-aggregation']))
        self.assertTrue(self.a(COUNT, [])['trigger'])
        self.assertIn('item-level record', E.corrective_request(r))

    def test_o2_narrow_margin_triggers_and_wide_margin_does_not(self):
        narrow = self.a(COMPARISON, [step('(let [f (fn [re] (count (filter #(re-find re %) ls)))] [(f #"a") (f #"b")])', '[43 30]')])
        self.assertEqual((narrow['state'], narrow['trigger'], narrow['facts']['observables']), ('approximation', True, ['O2-narrow-margin']))
        wide = self.a(COMPARISON, [step('(let [f (fn [re] (count (filter #(re-find re %) ls)))] [(f #"a") (f #"b")])', '[120, 12]')])
        self.assertEqual((wide['state'], wide['trigger']), ('approximation', False))
        self.assertIsNone(E.corrective_request(wide))
        # A single label count cannot form a margin: recorded as an approximation, never a trigger by itself.
        single = self.a(COUNT, [step('(count (filter #(re-find #"(?i)free|win" %) ls))', '31')])
        self.assertEqual((single['state'], single['trigger']), ('approximation', False))

    def test_o1_contradiction_triggers(self):
        r = self.a(COMPARISON, [step('(c1)', '[43 30]'), step('(c2)', '[27 45]')])
        self.assertEqual((r['state'], r['facts']['observables']), ('contradictory', ['O1-contradiction']))
        self.assertIn('opposite directions', E.corrective_request(r))

    def test_complete_record_is_supported_and_incomplete_record_triggers(self):
        full = self.a(COMPARISON, [step('(def M #{1 2 3 4 5 6 7 8 9 10 11 12})', "#'user/M"), step('[(count M) (- 30 (count M))]', '[12 18]')])
        self.assertEqual((full['state'], full['trigger']), ('supported', False))
        few = self.a(COMPARISON, [step('(def M #{1 2 3})', "#'user/M")])
        self.assertEqual((few['state'], few['facts']['observables']), ('incomplete', ['O4-incomplete-coverage']))
        shown = '\n'.join(f'{i} item text' for i in range(40))
        short = self.a(COMPARISON, [step('(show)', shown), step('(def l "NCEECNENCCNENEN")', "#'user/l")])
        self.assertEqual(short['state'], 'incomplete')
        covered = self.a(COMPARISON, [step('(show)', shown), step('(def l "' + 'NCEN' * 10 + '")', "#'user/l")])
        self.assertEqual(covered['state'], 'supported')
        interrupted = self.a(COMPARISON, [step('(def M #{1 2 3 4 5 6 7 8 9 10})', "#'user/M"), step('(count (', 'unreadable', ok=False)])
        self.assertEqual(interrupted['state'], 'incomplete')

    def test_structural_counts_and_unknown_tasks(self):
        self.assertEqual(self.a(DATES, [step('(count (filter #(= 2 (val %)) (frequencies ds)))', '7')])['trigger'], False)
        self.assertEqual(self.a(DATES, [step('(subs external-context 0 100)', 'text')])['facts']['observables'], ['O3-missing-aggregation'])
        unknown = self.a('Summarize the document in one sentence.', [])
        self.assertEqual((unknown['state'], unknown['trigger']), ('undeterminable', False))

    def test_fabricated_or_malformed_evidence_does_not_count_as_a_record(self):
        # Claims in a result or in prose are not records; only literal label data in executed source is.
        claim = self.a(COMPARISON, [step('"audit complete: all 438 items labelled"', '"audit complete: all 438 items labelled"')])
        self.assertTrue(claim['trigger'])
        fake_map = self.a(COMPARISON, [step('{:aljure/evidence :sufficient :record 438}', '{:aljure/evidence :sufficient, :record 438}')])
        self.assertTrue(fake_map['trigger'])
        failed = self.a(COMPARISON, [step('(def M #{1 2 3 4 5 6 7 8 9 10 11 12})', 'error', ok=False)])
        self.assertTrue(failed['trigger'])          # a record in a step that did not run is not evidence
        computed = self.a(COMPARISON, [step('(def M (set (range 400)))', "#'user/M")])
        self.assertTrue(computed['trigger'])        # a computed collection is not a typed-in judgement
        prose = self.a(COMPARISON, [step('(def note "the quick brown fox jumps over the lazy dog")', "#'user/note")])
        self.assertTrue(prose['trigger'])           # prose is not a label string
        garbage = E.assess(COMPARISON, [None, 5, {'source': None, 'ok': True, 'result': None}], 'clojure')
        self.assertIn(garbage['state'], ('missing', 'undeterminable'))
        self.assertEqual(E.assess(COMPARISON, 'not a list')['state'], 'undeterminable')   # fail-safe, no trigger
        self.assertFalse(E.assess(COMPARISON, 'not a list')['trigger'])

    def test_python_ledgers_use_the_same_rule(self):
        narrow = self.a(COMPARISON, [step("print(len(re.findall('a', t)), len(re.findall('b', t)))", '(43, 30)')], 'python')
        self.assertEqual(narrow['state'], 'approximation')
        rec = self.a(COMPARISON, [step('inf={0,1,2,3,6,10,14,15,21,23,24,25}\nprint(len(inf))', '12')], 'python')
        self.assertEqual((rec['state'], rec['trigger']), ('supported', False))
        dict_rec = self.a(COMPARISON, [step("m={0:'N',1:'E',2:'C',3:'N',4:'E',5:'C',6:'N',7:'E',8:'C'}", '')], 'python')
        self.assertEqual(dict_rec['state'], 'supported')

    def test_no_score_or_gold_is_an_input(self):
        import inspect
        self.assertEqual(list(inspect.signature(E.assess).parameters), ['question', 'steps', 'language'])
        self.assertNotIn('score', inspect.getsource(E.assess))
        self.assertNotIn('gold', inspect.getsource(E.assess))

    def test_ledger_readers(self):
        events = [{'type': 'tool-call', 'sequence': 7, 'payload': {'session': 'root', 'command': {'op': 'repl/eval', 'source': '(+ 1 2)'}}},
                  {'type': 'tool-result', 'payload': {'session': 'root', 'call-sequence': 7, 'op': 'repl/eval', 'status': 'ok', 'result': {'value': 3}}},
                  {'type': 'tool-call', 'sequence': 9, 'payload': {'session': 'child', 'command': {'op': 'repl/eval', 'source': '(def M #{1 2 3 4 5 6 7 8 9})'}}},
                  {'type': 'tool-result', 'payload': {'session': 'child', 'call-sequence': 9, 'op': 'repl/eval', 'status': 'ok', 'result': {'value': 1}}}]
        self.assertEqual(E.aljure_steps(events), [{'source': '(+ 1 2)', 'ok': True, 'result': '3'}])   # root session only
        lines = [json.dumps({'message': {'role': 'assistant', 'content': [{'type': 'toolCall', 'id': 'a', 'arguments': {'code': 'print(1)'}}]}}),
                 json.dumps({'message': {'role': 'toolResult', 'toolCallId': 'a', 'content': [{'type': 'text', 'text': '1'}], 'details': {'status': 'ok'}}}), 'not json']
        self.assertEqual(E.prime_steps(lines), [{'source': 'print(1)', 'ok': True, 'result': '1'}])


if __name__ == '__main__':
    unittest.main()
