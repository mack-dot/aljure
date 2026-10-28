import unittest

from benchmark.relay_fixture import ALJURE_TOOLS, Script

CONTRACT = {'tools': [{'name': name} for name in ALJURE_TOOLS],
            'tool_choice': {'type': 'auto', 'disable_parallel_tool_use': True}}
BASE = [{'role': 'user', 'content': 'base'}, {'role': 'user', 'content': 'task'}]
CALL = {'role': 'assistant', 'content': [{'type': 'thinking', 'thinking': 't', 'signature': 's'},
                                         {'type': 'tool_use', 'id': 'toolu_1', 'name': 'done', 'input': {}}]}
RESULT = {'role': 'user', 'content': [{'type': 'tool_result', 'tool_use_id': 'toolu_1', 'content': '{}'}]}


class AljureToolHistoryTests(unittest.TestCase):
    def check(self, *requests, contract=CONTRACT):
        script = Script('aljure')
        for messages in requests:
            script.check_aljure_tools({**contract, 'messages': messages}, 'root')
        return script

    def test_answered_append_only_tool_history_is_accepted(self):
        script = self.check(BASE, BASE + [CALL, RESULT], BASE + [CALL, RESULT, {'role': 'user', 'content': 'feedback'}])
        self.assertEqual(script.tool_results, 1)

    def test_provider_invalid_shapes_are_refused(self):
        wrong_id = {'role': 'user', 'content': [{**RESULT['content'][0], 'tool_use_id': 'toolu_2'}]}
        for requests in ([BASE + [CALL]], [BASE + [CALL, {'role': 'user', 'content': 'text'}]],
                         [BASE + [CALL, wrong_id]], [BASE + [RESULT]],
                         # Dropping an earlier turn edits history; thinking blocks would be invalid.
                         [BASE + [CALL, RESULT], [BASE[0], CALL, RESULT]]):
            with self.assertRaises(ValueError):
                self.check(*requests)
        for contract in ({}, {**CONTRACT, 'tool_choice': {'type': 'auto'}}, {**CONTRACT, 'tools': CONTRACT['tools'][:-1]}):
            with self.assertRaises(ValueError):
                self.check(BASE, contract=contract)


if __name__ == '__main__':
    unittest.main()
