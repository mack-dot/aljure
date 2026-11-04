import collections
import json
import unittest
from pathlib import Path

from benchmark import headtohead as h
from benchmark import paired
from benchmark import verification_ablation as v

ROOT = Path(__file__).resolve().parent.parent


def fake_suites():
    return {'verify8': {'path': 'x', 'suite_sha256': 'x' * 64, 'suite': 'oolong-synth', 'rule': 'all', 'exposure': 't',
                        'task_ids': [f'a{i}' for i in range(12)], 'contexts': {f'a{i}': str(i // 2) for i in range(12)}},
            'verify32': {'path': 'y', 'suite_sha256': 'y' * 64, 'suite': 'oolong-synth', 'rule': 'all', 'exposure': 't',
                         'task_ids': [f'b{i}' for i in range(8)], 'contexts': {f'b{i}': str(10 + i // 2) for i in range(8)}}}


def fake_rows(seq, suites, score_fn, cost_fn=lambda e: 0.03 if e['harness'] == 'aljure' else 0.06):
    return [{**e, 'suite_sha256': 'x' * 64, 'context_window_id': suites[e['suite']]['contexts'][e['task_id']], 'status': 'completed',
             'failure': None, 'score': score_fn(e), 'wall_time_ms': 20000.0,
             'usage': {'calls': 3, 'known_model_cost_usd': cost_fn(e), 'reserved_unknown_usd': 0.0, 'accounting_complete': True,
                       'known_tokens': {'input_tokens': 1, 'output_tokens': 1, 'cache_read_input_tokens': 0, 'cache_creation_input_tokens': 0}},
             'measures': {'agent_wall_ms': 18000.0, 'tool_calls': 3, 'tool_errors': 0, 'http_errors': 0}} for e in seq]


class ArmsAndSequenceTest(unittest.TestCase):
    def test_configs_differ_only_in_the_declared_contracts_and_all_validate(self):
        cfgs = v.configs_of()
        self.assertEqual(set(cfgs), set(v.ARMS))
        base = cfgs['A0']
        self.assertEqual(base['aljure_contract'], {'terminal_text_answer': 'text-answer-v2'})
        self.assertEqual(cfgs['A2']['aljure_contract'], {})
        self.assertTrue(cfgs['A1']['aljure_contract']['uncertainty_audit'] and not cfgs['A1']['aljure_contract'].get('targeted_review'))
        self.assertTrue(cfgs['A3']['aljure_contract']['targeted_review'])
        self.assertEqual(cfgs['P1']['prime_contract'], {'verification_prompt': True})
        self.assertNotIn('prime_contract', cfgs['P0'])
        for label, c in cfgs.items():
            paired.validate_config(c)
            self.assertGreaterEqual(h.spend_allowance_usd(c), h.MIN_ALLOWANCE_USD)
            stripped = {k: val for k, val in c.items() if k not in ('aljure_contract', 'prime_contract')}
            self.assertEqual(stripped, {k: val for k, val in base.items() if k not in ('aljure_contract', 'prime_contract')}, label)
        self.assertNotEqual(paired.capabilities(cfgs['P1']), paired.capabilities(cfgs['P0']))
        self.assertEqual(paired.capabilities(cfgs['P0'])['prime'], paired.capabilities(cfgs['A0'])['prime'])

    def test_prime_prompt_carries_the_contract_only_when_enabled(self):
        cfgs = v.configs_of()
        text = (ROOT / 'resources/prime-verification.txt').read_text().strip()
        self.assertIn(text, paired.prime_prompt(cfgs['P1'], 'Q'))
        self.assertNotIn(text, paired.prime_prompt(cfgs['P0'], 'Q'))
        self.assertTrue(paired.prime_prompt(cfgs['P0'], 'Q').endswith('\n\nQ'))
        with self.assertRaises(ValueError):
            paired.prime_contract({**cfgs['P0'], 'prime_contract': {'verification_prompt': 'yes'}})
        for name in ('structured-labels', 'uncertainty-audit', 'targeted-review'):
            self.assertTrue((ROOT / f'resources/{name}.txt').exists())

    def test_sequence_runs_six_arms_per_item_with_balanced_first_positions(self):
        suites = fake_suites()
        seq = v.sequence(suites)
        self.assertEqual(seq, v.sequence(suites))
        self.assertEqual(len(seq) % 6, 0)
        items = len(seq) // 6
        self.assertEqual(items, 20 + round(0.2 * 20))
        for i in range(items):
            block = seq[6 * i:6 * i + 6]
            self.assertEqual(len({e['task_id'] for e in block}), 1)
            self.assertEqual({e['arm'] for e in block}, set(v.ARMS))
            self.assertEqual([e['position'] for e in block], list(range(1, 7)))
        firsts = collections.Counter(e['arm'] for e in seq if e['position'] == 1)
        self.assertLessEqual(max(firsts.values()) - min(firsts.values()), 1)
        self.assertEqual([e['index'] for e in seq], list(range(len(seq))))


class SummaryTest(unittest.TestCase):
    def test_contrasts_go_rule_and_harness_specific_effect(self):
        suites = fake_suites()
        seq = v.sequence(suites)
        value = {'plan_sha256': 'p' * 64, 'sequence': seq, 'suites': suites, 'arms': v.ARMS, 'contrasts': v.CONTRASTS, 'primary': v.PRIMARY,
                 'go_rule': v.GO, 'analysis': {'claim': 'test'}}
        # A1 gains 0.2 over A0 on every task; P1 gains 0.05 over P0; A2 equals A0; A3 equals A1.
        base = {'A0': 0.6, 'A1': 0.8, 'A2': 0.6, 'A3': 0.8, 'P0': 0.7, 'P1': 0.75}
        rows = fake_rows(seq, suites, lambda e: base[e['arm']])
        report = v.summarize(value, rows)
        self.assertTrue(report['complete'])
        c = report['contrasts']
        self.assertAlmostEqual(c['verification_in_aljure']['context_weighted_mean_difference'], 0.2)
        self.assertAlmostEqual(c['text_channel']['context_weighted_mean_difference'], 0.0)
        self.assertAlmostEqual(c['evidence_gate']['context_weighted_mean_difference'], 0.0)
        self.assertAlmostEqual(c['verification_in_prime']['context_weighted_mean_difference'], 0.05)
        self.assertAlmostEqual(c['prime_vs_aljure_base']['context_weighted_mean_difference'], -0.1)
        self.assertEqual(c['verification_in_aljure']['independent_contexts'], 10)
        self.assertAlmostEqual(report['harness_specific_verification_effect']['estimate'], 0.15)
        self.assertTrue(report['go_rule']['go'])
        self.assertAlmostEqual(report['go_rule']['aljure_cost_ratio_to_prime'], 0.5)
        # NO-GO when the gain is below 0.10 even if cheap.
        rows = fake_rows(seq, suites, lambda e: {**base, 'A1': 0.65}[e['arm']])
        self.assertFalse(v.summarize(value, rows)['go_rule']['go'])
        # NO-GO when the verified Aljure arm costs more than half of Prime's.
        rows = fake_rows(seq, suites, lambda e: base[e['arm']], cost_fn=lambda e: 0.05 if e['arm'] == 'A1' else (0.03 if e['harness'] == 'aljure' else 0.06))
        self.assertFalse(v.summarize(value, rows)['go_rule']['go'])

    def test_plan_constants_survive_a_json_round_trip(self):
        for value in (v.ARMS, v.CONTRASTS, v.GO):
            self.assertEqual(json.loads(json.dumps(value)), value)

    def test_lockfile_profiles_for_the_verification_suites(self):
        from benchmark.oolong import PINS
        for cl in (8192, 32768):
            p = PINS['official_profiles'][f'oolong-synth:dev-verification:{cl}']
            self.assertEqual(p['selection'], 'dev-verification-v1')
            self.assertEqual(p['answer_types'], ['COMPARISON', 'NUMERIC'])
            self.assertTrue(p['exclude_ids'])
        held = PINS['official_profiles']['oolong-synth:independent-heldout:32768']['windows']
        dev = PINS['official_profiles']['oolong-synth:dev-verification:32768']['windows']
        self.assertFalse({tuple(w) for w in held} & {tuple(w) for w in dev})


if __name__ == '__main__':
    unittest.main()
