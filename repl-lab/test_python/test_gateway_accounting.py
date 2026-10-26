"""Independent accounting tests for the shared gateway receipt format."""
import unittest
from benchmark.oolong import account


class GatewayAccountingTests(unittest.TestCase):
    def row(self):
        return {'kind': 'provider-call', 'call_id': 'fixture-call', 'session_id': 'request-id',
                'provider_request_id': 'fixture-receipt', 'model': 'fixture-model', 'status': 'complete',
                'input_tokens': 12, 'output_tokens': 3, 'cache_read_input_tokens': 5,
                'cache_creation_input_tokens': 10,
                'cache_creation': {'ephemeral_5m_input_tokens': 6, 'ephemeral_1h_input_tokens': 4}}

    def test_cache_durations_have_separate_explicit_prices(self):
        pricing = {'input_tokens': 2, 'output_tokens': 10, 'cache_read_input_tokens': 0.2,
                   'cache_creation_5m_input_tokens': 2.5, 'cache_creation_1h_input_tokens': 4}
        result = account([self.row()], pricing)
        self.assertEqual(result['model_cost_usd'], 0.000086)
        self.assertTrue(result['accounting_complete'])
        del pricing['cache_creation_1h_input_tokens']
        pricing['cache_creation_input_tokens'] = 2.5  # Must not substitute a generic rate.
        result = account([self.row()], pricing)
        self.assertIsNone(result['model_cost_usd'])
        self.assertEqual(result['unpriced_calls'], 1)

    def test_inconsistent_cache_totals_are_rejected_even_when_total_is_zero(self):
        for total in (0, 11):
            row = self.row()
            row['cache_creation_input_tokens'] = total
            with self.assertRaises(ValueError):
                account([row], {})


if __name__ == '__main__':
    unittest.main()
