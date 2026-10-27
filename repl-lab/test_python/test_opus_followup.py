"""Opus proposal controls. Scripted responses only; no credentials or network."""
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from benchmark.paired import ROOT, preflight, transport_contract, validate_config
from benchmark.relay_fixture import Script
from benchmark.subscription_protocol import PROVIDER, VERSION


class OpusFollowupTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / 'config/external-opus-subscription-proposal-v1.json').read_text())

    def test_exact_model_contract_and_original_sonnet_are_valid(self):
        validate_config(self.config)
        validate_config(json.loads((ROOT / 'config/external-subscription-proposal-v1.json').read_text()))
        for key, value in [('model', 'claude-opus-latest'), ('context_window', 128000),
                           ('max_output_tokens', 128001), ('rates', {'input': 2, 'output': 10, 'cache-read': .1,
                                                                  'cache-write-5m': 2.5, 'cache-write-1h': 4})]:
            with self.assertRaises(ValueError):
                validate_config({**self.config, key: value})
        self.assertEqual(self.config['usd_per_arm'], 12)
        self.assertEqual(self.config['total_usd'], 24)
        self.assertFalse(self.config['experiment']['approved'])

    def test_fixture_returns_and_requires_the_selected_model(self):
        script = Script('aljure', config=self.config)
        body = {'model': self.config['model'], 'messages': [{'role': 'user', 'content': 'fixture task'}],
                'max_tokens': 32768, **self.config['pinned_settings']}
        reply = json.loads(script(body, 10)['body'])
        self.assertEqual(reply['model'], 'claude-opus-5-5')
        with self.assertRaises(ValueError):
            script({**body, 'model': 'claude-sonnet-5-5'}, 10)

    def test_preflight_rejects_a_control_for_another_model_or_rates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'var').mkdir()
            (root / 'var/isolation-proof.json').write_text(json.dumps({'gate-version': 2, 'image': 'sci'}))
            plan = {'config': self.config, 'plan_sha256': 'fixture-plan', 'runtime_source': {'sha256': 'fixture-runtime'}}
            proof = {'evidence': 'FIXTURE', 'status': 'PASSED', 'runtime_source': plan['runtime_source'],
                     'prime_image': 'prime', 'sci_image': 'sci', 'provider': PROVIDER, 'subscription_protocol': VERSION,
                     'transport_contract': transport_contract(self.config),
                     'checks': dict.fromkeys(('native_root', 'native_child', 'native_tool', 'native_compaction',
                                             'native_refinement', 'native_signed_thinking', 'sci_context', 'shared_budget',
                                             'cleanup', 'oauth_protocol', 'command_correction',
                                             'rejected_fragment_not_executed'), True)}
            with patch('benchmark.paired.ROOT', root), patch('benchmark.paired.read_plan', return_value=(plan, {}, {})), \
                 patch('benchmark.paired.subprocess.run', return_value=SimpleNamespace(returncode=0)), \
                 patch('benchmark.prime.isolation.require_tested', return_value={'image': 'prime'}):
                path = root / 'var/subscription-relay-proof.json'
                path.write_text(json.dumps(proof))
                self.assertTrue(preflight('unused', 'unused')['ready'])
                for check in ('command_correction', 'rejected_fragment_not_executed'):
                    incomplete = copy.deepcopy(proof)
                    del incomplete['checks'][check]
                    path.write_text(json.dumps(incomplete))
                    self.assertFalse(preflight('unused', 'unused')['ready'])
                for key, value in [('model', 'claude-sonnet-5-5'), ('rates', {'input': 2}), ('usd_per_arm', 24)]:
                    wrong = copy.deepcopy(proof)
                    wrong['transport_contract'][key] = value
                    path.write_text(json.dumps(wrong))
                    result = preflight('unused', 'unused')
                    self.assertFalse(result['ready'])
                    self.assertIn('Relay model/settings/rates/budgets differ', result['blockers'][0])


if __name__ == '__main__':
    unittest.main()
