import unittest

from benchmark.relay_fixture import ALJURE_TOOLS, Script

CONTRACT = {'tools': [{'name': name} for name in ALJURE_TOOLS[:-1]] + [{'name': ALJURE_TOOLS[-1], 'cache_control': {'type': 'ephemeral'}}],
            'tool_choice': {'type': 'auto', 'disable_parallel_tool_use': True}}
BASE = [{'role': 'user', 'content': 'base'}, {'role': 'user', 'content': 'task'}]
CALL = {'role': 'assistant', 'content': [{'type': 'thinking', 'thinking': 't', 'signature': 's'},
                                         {'type': 'tool_use', 'id': 'toolu_1', 'name': 'done', 'input': {}}]}
RESULT = {'role': 'user', 'content': [{'type': 'tool_result', 'tool_use_id': 'toolu_1', 'content': '{}'}]}


def marked(messages):
    # Aljure marks only the newest block of each request for prompt caching.
    *head, last = messages
    content = [{'type': 'text', 'text': last['content']}] if isinstance(last['content'], str) else last['content']
    return head + [{**last, 'content': content[:-1] + [{**content[-1], 'cache_control': {'type': 'ephemeral'}}]}]


class AljureToolHistoryTests(unittest.TestCase):
    def check(self, *requests, contract=CONTRACT, mark=True):
        script = Script('aljure')
        for messages in requests:
            script.check_aljure_tools({**contract, 'messages': marked(messages) if mark else messages}, 'root')
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
        for contract in ({}, {**CONTRACT, 'tool_choice': {'type': 'auto'}}, {**CONTRACT, 'tools': CONTRACT['tools'][:-1]},
                         {**CONTRACT, 'tools': [{'name': name} for name in ALJURE_TOOLS]}):
            with self.assertRaises(ValueError):
                self.check(BASE, contract=contract)

    def test_cache_breakpoint_must_mark_only_the_newest_block(self):
        with self.assertRaises(ValueError):
            self.check(BASE, mark=False)
        with self.assertRaises(ValueError):
            # A stale marker left on an earlier block makes two breakpoints.
            self.check(marked(BASE) + [CALL, RESULT])


if __name__ == '__main__':
    unittest.main()
