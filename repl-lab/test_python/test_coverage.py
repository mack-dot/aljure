import json
import tempfile
import unittest
from pathlib import Path

from benchmark import coverage as C

CONTEXT = ("The following lines contain 4 reviews.\n\n"
           "Date: Jan 05, 2024 || User: 111 || Instance: The battery lasts all day and the screen is bright enough outdoors\n"
           "Date: Feb 11, 2024 || User: 222 || Instance: Stopped working after a week, \"support\" never answered my emails\n"
           "Date: Jan 20, 2023 || User: 111 || Instance: Fine for the price but the hinge feels loose after a month of use\n"
           "Date: Mar 02, 2024 || User: 333 || Instance: Great\n")
WHOLE = "In the above data, is label 'positive' more common, less common, or the same frequency as label 'negative'?"
MONTH = "For the following question, only consider the subset of instances that occur in January of any year. Among instances occuring in January, which of the labels is the most common?"
USERS = "For the following question, only consider the subset of instances that are associated with user IDs 222, 333. Among instances associated with these users, how many data points should be classified as label 'negative'?"
SPLIT = "In the above data, was label 'positive' more common, less common, or the same frequency before 2024-02-01, as compared to after 2024-02-01?"


class RelevantRecordsTest(unittest.TestCase):
    def test_the_question_filter_selects_the_relevant_records(self):
        self.assertEqual(len(C.records(CONTEXT)), 4)
        self.assertEqual(len(C.relevant(WHOLE, CONTEXT)), 4)
        self.assertEqual([r[1] for r in C.relevant(MONTH, CONTEXT)], ['111', '111'])
        self.assertEqual([r[1] for r in C.relevant(USERS, CONTEXT)], ['222', '333'])
        self.assertEqual(len(C.relevant(SPLIT, CONTEXT)), 4)        # a before/after question concerns every record
        self.assertEqual(C.relevant(WHOLE, 'no records here'), [])


class CoverageTest(unittest.TestCase):
    def test_seen_and_full_are_counted_over_the_relevant_records(self):
        nothing = C.coverage(WHOLE, CONTEXT, [])
        self.assertEqual((nothing['relevant'], nothing['seen'], nothing['full'], nothing['seen_fraction']), (4, 0, 0, 0.0))
        cut = C.coverage(WHOLE, CONTEXT, ['0 The battery lasts all day and the scr\n1 Stopped working after a week, "sup'])
        self.assertEqual((cut['seen'], cut['full']), (2, 0))          # displayed, but cut short
        everything = C.coverage(WHOLE, CONTEXT, [CONTEXT])
        self.assertEqual((everything['seen'], everything['full'], everything['full_fraction']), (4, 4, 1.0))
        # An EDN or JSON printed value escapes quotes and newlines; the record still counts.
        escaped = C.coverage(USERS, CONTEXT, ['["Stopped working after a week, \\"support\\" never answered my emails" "Great"]'])
        self.assertEqual((escaped['relevant'], escaped['full']), (2, 2))
        january = C.coverage(MONTH, CONTEXT, ['Fine for the price but the hinge feels loose after a month of use'])
        self.assertEqual((january['relevant'], january['full'], january['full_fraction']), (2, 1, 0.5))
        self.assertIsNone(C.coverage(WHOLE, 'no records', ['x'])['seen_fraction'])

    def test_a_count_or_a_claim_is_not_coverage(self):
        claimed = C.coverage(WHOLE, CONTEXT, ['[3 1]', 'I read all 4 reviews', '{:positive 3 :negative 1}'])
        self.assertEqual((claimed['seen'], claimed['full']), (0, 0))

    def test_trace_readers_take_every_session_of_an_arm(self):
        with tempfile.TemporaryDirectory() as tmp:
            arm = Path(tmp)
            (arm / 'agent').mkdir()
            (arm / 'public-input.json').write_text(json.dumps({'task': {'task_id': 't', 'question': WHOLE}, 'context': CONTEXT}))
            events = [{'type': 'tool-call', 'payload': {'session': 'root'}},
                      {'type': 'tool-result', 'payload': {'session': 'root', 'result': {'value': 'The battery lasts all day and the screen is bright enough outdoors'}}},
                      {'type': 'tool-result', 'payload': {'session': 'child-1', 'result': {'value': ['Great']}}}]
            (arm / 'agent/events.jsonl').write_text('\n'.join(json.dumps(e) for e in events) + '\nnot json\n')
            self.assertEqual(C.measure(arm, 'aljure')['full'], 2)
            sub = arm / 'native/agent/session-artifacts/s/sub-1'
            sub.mkdir(parents=True)
            (arm / 'native/sessions').mkdir(parents=True)
            line = lambda text: json.dumps({'message': {'role': 'toolResult', 'content': [{'type': 'text', 'text': text}]}})
            (arm / 'native/sessions/root.jsonl').write_text(line('Stopped working after a week, "support" never answered my emails') + '\n')
            (sub / 'child.jsonl').write_text(line('Fine for the price but the hinge feels loose after a month of use') + '\n')
            (sub / 'semantic-edges.jsonl').write_text(line('Great') + '\n')       # not a session log
            self.assertEqual(C.measure(arm, 'prime')['full'], 2)
            self.assertIsNone(C.measure(arm / 'missing', 'prime'))


if __name__ == '__main__':
    unittest.main()
