"""The Python worker's display and answer requests, run on the host interpreter (the worker
file is plain Python); its container boundary is proved by scripts/python_isolation.py."""
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / 'worker/src/repl_lab/python_worker.py'
DISPLAY = {'limit': 60000, 'preview': 24000}


def worker(requests):
    lines = ''.join(json.dumps(r) + '\n' for r in requests)
    run = subprocess.run([sys.executable, '-I', str(WORKER)], input=lines, capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr
    return [json.loads(line) for line in run.stdout.splitlines()]


def shown(source, **extra):
    return {'source': source, 'bindings': {}, 'display': DISPLAY, **extra}


def prelude_and_context_lines():
    """The prelude and the context_lines binding exactly as external_task.clj sends them."""
    source = (ROOT / 'src/repl_lab/external_task.clj').read_text()
    match = re.search(r'\(str "(context_lines = [^"]*)"\s*\n\s*"([^"]*)"\)', source)
    binding = (match.group(1) + match.group(2)).encode().decode('unicode_escape')
    return (ROOT / 'resources/python-prelude.py').read_text(), binding


class DisplayRequestTests(unittest.TestCase):
    def test_printed_output_then_the_final_expression_repr(self):
        values = [r['value'] for r in worker([shown("print('hi'); x = 3\nx + 1"), shown('{1, 2}'), shown('y = 5'),
                                              shown('last_result'), shown('None'), shown("print('a')\nNone"),
                                              shown("print('b')"), shown("'s'")])]
        self.assertEqual(['hi\n4', '{1, 2}', '(no output)', '{1, 2}', '(no output)', 'a', 'b', "'s'"], values)

    def test_plain_requests_keep_the_readiness_wire_format(self):
        self.assertEqual([{'value': 42, 'printed': ''}], worker([{'source': '20 + 22', 'bindings': {}}]))

    def test_oversized_results_become_previews_and_keep_the_worker(self):
        prelude, _ = prelude_and_context_lines()
        rows = worker([{'source': prelude, 'bindings': {}},
                       shown("'x' * 100000"), shown('len(full_result)'), shown('page(full_result, 99998, 10)'),
                       shown('list(range(20000))'), shown("print('z' * 2000000)"), shown('len(full_result)')])[1:]
        big = rows[0]['value']
        self.assertTrue(big['aljure/truncated'])
        self.assertEqual((100002, 24000, None, 'string'), (big['total-chars'], big['shown-chars'], big['items'], big['kind']))
        self.assertEqual("'" + 'x' * 23999, big['preview'])
        self.assertEqual('100002', rows[1]['value'])
        self.assertEqual('"xxx\'"', rows[2]['value'])
        self.assertEqual((20000, 'sequence'), (rows[3]['value']['items'], rows[3]['value']['kind']))
        self.assertIn('Printed output limit', rows[4]['error'])
        self.assertEqual('128890', rows[5]['value'])  # full_result is unchanged by the refused print

    def test_escaped_text_is_measured_on_the_wire(self):
        row = worker([shown("'é\U0001F600' * 30000")])[0]['value']
        self.assertTrue(row['aljure/truncated'])
        self.assertLess(len(json.dumps(row['preview']).encode()), DISPLAY['limit'] // 2 + 1)

    def test_invalid_display_and_answer_requests_are_refused(self):
        rows = worker([{'source': '1', 'bindings': {}, 'display': {'limit': 0, 'preview': 1}},
                       {'source': '1', 'bindings': {}, 'display': {'limit': 10}},
                       {'source': '1', 'bindings': {}, 'answer': 1},
                       {'source': '1', 'bindings': {}, 'other': True}])
        self.assertTrue(all('error' in r for r in rows), rows)


class AnswerRequestTests(unittest.TestCase):
    def test_answers_stay_in_the_worker_with_a_code_point_checksum(self):
        # 96354 and 131519 are the 31-polynomial values the controller recomputes (runtime_test).
        rows = worker([{'source': "'abc'", 'bindings': {}, 'answer': True},
                       {'source': "'a\U0001F600'", 'bindings': {}, 'answer': True},
                       {'source': 'aljure_answer[0:1]', 'bindings': {}},
                       {'source': '42', 'bindings': {}, 'answer': True}])
        self.assertEqual([[3, 96354], [2, 131519], 'a', 'aljure/not-a-string'], [r['value'] for r in rows])

    def test_checksum_is_signed_32_bit(self):
        row = worker([{'source': "'z' * 50", 'bindings': {}, 'answer': True}])[0]['value']
        self.assertEqual(50, row[0])
        self.assertTrue(-2**31 <= row[1] < 2**31)


class PreludeTests(unittest.TestCase):
    def test_page_and_context_lines_match_the_clojure_worker(self):
        prelude, binding = prelude_and_context_lines()
        context = 'a\r\nb\n\nc\n\n'
        rows = worker([{'source': 'external_context = chunk', 'bindings': {'chunk': context}},
                       {'source': prelude, 'bindings': {}}, {'source': binding, 'bindings': {}},
                       shown('context_lines'), shown("page('abcdef', 2, 3)"), shown('page([1, 2, 3], 0, 4)'),
                       shown("page('abc', 10, 5)"), shown('(last_result, full_result)')])
        # clojure.string/split-lines: split on \r?\n, trailing empty strings dropped, inner kept.
        self.assertEqual("['a', 'b', '', 'c']", rows[3]['value'])
        self.assertEqual(["'cde'", "'[1, '", "''"], [r['value'] for r in rows[4:7]])
        self.assertEqual("('', None)", rows[7]['value'])


if __name__ == '__main__':
    unittest.main()
