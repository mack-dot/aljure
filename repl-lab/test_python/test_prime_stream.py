"""The Prime adapter's task-output bound must measure output, not streaming repetition."""
import ast
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
KILLED = [ROOT / 'var/benchmarks/sci-ablation-control-2' / arm / 'stdout.jsonl' for arm in ('09-prime', '17-prime')]


def compact_event():
    source = (ROOT / 'benchmark/prime/relay_bootstrap.py').read_text()
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == 'compact_event')
    scope = {}
    exec(compile(ast.Module(body=[node], type_ignores=[]), 'relay_bootstrap', 'exec'), scope)
    return scope['compact_event']


class PrimeStreamTests(unittest.TestCase):
    def test_partial_message_updates_become_markers_and_final_messages_stay(self):
        compact = compact_event()
        update = {'type': 'message_update', 'message': {'content': [{'type': 'text', 'text': 'x' * 10000}]}}
        self.assertNotIn('message', compact(update))
        self.assertEqual('message_update', compact(update)['type'])
        final = {'type': 'message_end', 'message': {'content': [{'type': 'text', 'text': 'x' * 10000}]}}
        self.assertEqual(final, compact(final))
        self.assertEqual(['not', 'a', 'dict'], compact(['not', 'a', 'dict']))

    @unittest.skipUnless(all(path.exists() for path in KILLED), 'recorded 32K evidence absent')
    def test_the_two_arms_killed_at_4_mib_fit_once_updates_are_compacted(self):
        compact = compact_event()
        for path in KILLED:
            before = after = 0
            for line in path.read_bytes().splitlines(keepends=True):
                before += len(line)
                try:
                    frame = json.loads(line)
                except ValueError:  # The line being written when the arm was killed.
                    after += len(line)
                    continue
                if frame.get('type') == 'native_event':
                    frame['event'] = compact(frame['event'])
                after += len(json.dumps(frame).encode()) + 1
            self.assertGreater(before, 4 * 1024**2 - 200_000, path)
            self.assertLess(after, 2 * 1024**2, path)


if __name__ == '__main__':
    unittest.main()
