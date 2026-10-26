import json
import unittest
from benchmark.prime.usage import audit_transcripts


def usage(value):
    return dict.fromkeys(('input', 'output', 'cacheRead', 'cacheWrite'), value)


def transcript(session, value, extra=()):
    rows = [{'type': 'session', 'id': session},
            {'type': 'message', 'id': 'call', 'message': {'role': 'assistant', 'provider': 'faux',
                                                        'model': 'faux-1', 'usage': usage(value)}}]
    return b'\n'.join(json.dumps(row).encode() for row in rows + list(extra))


class NativeUsageTests(unittest.TestCase):
    def test_child_aggregate_does_not_double_count_original_calls(self):
        attributed = {'type': 'child_usage_attributed', 'id': 'fold', 'targetId': 'call',
                      'origin': 'spawn_task', 'childUsage': usage(3), 'aggregateUsage': usage(5)}
        files = {'parent.jsonl': transcript('parent', 2, [attributed]), 'child.jsonl': transcript('child', 3)}
        result = audit_transcripts(files)
        self.assertEqual(result['distinct_assistant_row_counters'], usage(5))
        self.assertEqual(len(result['assistant_rows']), 2)
        self.assertEqual(len(result['child_attributions']), 1)
        self.assertFalse(result['trusted_provider_accounting'])
        self.assertIsNone(result['provider_billing_usd'])

    def test_bad_attribution_and_duplicate_identity_fail(self):
        bad = {'type': 'child_usage_attributed', 'id': 'fold', 'targetId': 'call',
               'childUsage': usage(3), 'aggregateUsage': usage(2)}
        with self.assertRaises(ValueError):
            audit_transcripts({'parent.jsonl': transcript('parent', 2, [bad])})
        with self.assertRaises(ValueError):
            audit_transcripts({'a.jsonl': transcript('same', 2), 'b.jsonl': transcript('same', 2)})

    def test_faux_without_attribution_is_not_live_accounting_evidence(self):
        result = audit_transcripts({'parent.jsonl': transcript('parent', 2), 'child.jsonl': transcript('child', 3)})
        self.assertEqual(result['evidence'], 'FIXTURE')
        self.assertFalse(result['trusted_provider_accounting'])
        self.assertEqual(result['child_attributions'], [])


if __name__ == '__main__':
    unittest.main()
