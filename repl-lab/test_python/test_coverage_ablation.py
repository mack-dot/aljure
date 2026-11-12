import collections
import json
import unittest
from pathlib import Path

from benchmark import coverage_ablation as ca
from benchmark import headtohead as h
from benchmark import official
from benchmark import paired
from benchmark import verification_ablation as v

ROOT = Path(__file__).resolve().parent.parent


def fake_suites():
    primary = [f'p{i}' for i in range(12)]
    structural, known = ['s0', 's1', 's2'], ['k0', 'k1']
    ids = primary + structural + known
    contexts = {**{t: str(i) for i, t in enumerate(primary)}, 's0': '0', 's1': '1', 's2': '2', 'k0': '100', 'k1': '101'}
    lengths = {t: (4096 if i % 2 else 32768) for i, t in enumerate(ids)}
    manifest = {'selection': {'strata': {'label-judgement': primary, 'structural': structural, 'audit-correct': known}, 'lengths': lengths}}
    return {'coverage': {'path': 'x', 'suite_sha256': 'x' * 64, 'suite': 'oolong-synth', 'rule': 'all', 'exposure': 't',
                         'task_ids': ids, 'contexts': contexts, '_manifest': manifest}}


def fake_rows(seq, suites, score_fn, work_fn=lambda e: {}):
    rows = []
    for e in seq:
        extra = {'cost': 0.03 if e['harness'] == 'aljure' else 0.06, 'calls': 3, 'out': 500, 'tools': 3, 'seen': 0.5, **work_fn(e)}
        rows.append({**e, 'suite_sha256': 'x' * 64, 'context_window_id': suites['coverage']['contexts'][e['task_id']], 'status': 'completed',
                     'failure': None, 'score': score_fn(e), 'wall_time_ms': 20000.0,
                     'usage': {'calls': extra['calls'], 'known_model_cost_usd': extra['cost'], 'reserved_unknown_usd': 0.0, 'accounting_complete': True,
                               'known_tokens': {'input_tokens': 10, 'output_tokens': extra['out'], 'cache_read_input_tokens': 1000, 'cache_creation_input_tokens': 2000}},
                     'measures': {'agent_wall_ms': 18000.0, 'tool_calls': extra['tools'], 'tool_errors': 0, 'http_errors': 0},
                     'coverage': {'seen_fraction': extra['seen'], 'full_fraction': extra['seen'] / 2, 'output_chars': 4000}})
    return rows


def fake_value(suites, seq):
    strata, lengths = ca.strata_of(suites)
    return {'plan_sha256': 'h', 'sequence': seq, 'arms': ca.ARMS, 'contrasts': ca.CONTRASTS, 'primary': ca.PRIMARY, 'primary_stratum': ca.PRIMARY_STRATUM,
            'mechanism_control': ca.MECHANISM, 'go_rule': ca.GO, 'strata': strata, 'lengths': lengths,
            'suites': {'coverage': {'contexts': suites['coverage']['contexts']}}, 'analysis': {'claim': 'dev'}}


class ArmsTest(unittest.TestCase):
    def test_arms_differ_only_in_the_declared_contracts(self):
        cfgs = ca.configs_of()
        self.assertEqual(list(cfgs), ['A0', 'AU', 'AC', 'AUC', 'P0', 'PC'])
        base = cfgs['A0']
        for label, c in cfgs.items():
            paired.validate_config(c)
            stripped = {k: val for k, val in c.items() if k not in ('aljure_contract', 'prime_contract')}
            self.assertEqual(stripped, {k: val for k, val in base.items() if k not in ('aljure_contract', 'prime_contract')}, label)
        # The baseline is the existing audit contract, byte for byte the A1 arm of the verification ablation.
        self.assertEqual(cfgs['AU']['aljure_contract'], v.ARMS['A1']['aljure_contract'])
        self.assertEqual(cfgs['A0']['aljure_contract'], v.ARMS['A0']['aljure_contract'])
        self.assertEqual(cfgs['AC']['aljure_contract'], {'terminal_text_answer': 'text-answer-v2', 'evidence_coverage': True})
        self.assertEqual(cfgs['AUC']['aljure_contract'], {**cfgs['AU']['aljure_contract'], 'evidence_coverage': True})
        self.assertNotIn('prime_contract', cfgs['P0'])
        self.assertEqual(cfgs['PC']['prime_contract'], {'coverage_prompt': True})
        # Trigger v1 and the evidence gate are in no arm.
        self.assertFalse(any(paired.aljure_contract(c)['targeted_review'] for c in cfgs.values()))
        self.assertEqual(paired.capabilities(cfgs['P0'])['prime'], paired.capabilities(cfgs['A0'])['prime'])
        self.assertIn('coverage_prompt', paired.capabilities(cfgs['PC'])['prime']['execution_contract'])
        self.assertIn('evidence_coverage', paired.capabilities(cfgs['AC'])['aljure']['execution_contract'])
        self.assertNotIn('evidence_coverage', paired.capabilities(cfgs['AU'])['aljure']['execution_contract'])

    def test_the_coverage_instruction_is_the_same_text_in_both_harnesses_up_to_harness_terms(self):
        aljure = (ROOT / 'resources/evidence-coverage.txt').read_text().strip()
        prime = (ROOT / 'resources/prime-evidence-coverage.txt').read_text().strip()
        terms = [(', even though you otherwise read only what you need', ''), ('in SCI first; then display', 'with code first; then print'),
                 ('page by page when a result is truncated', 'in pieces when the output is truncated'), ('compute it in SCI', 'compute it with code')]
        rewritten = aljure
        for a, b in terms:
            self.assertIn(a, rewritten)
            rewritten = rewritten.replace(a, b)
        self.assertEqual(rewritten, prime)
        cfgs = ca.configs_of()
        self.assertEqual(paired.prime_prompt(cfgs['PC'], 'Q'), paired.PRIME_PROMPT + '\n\n' + prime + '\n\nQ')
        self.assertEqual(paired.prime_prompt(cfgs['P0'], 'Q'), paired.PRIME_PROMPT + '\n\nQ')
        both = paired.prime_prompt({**cfgs['P0'], 'prime_contract': {'verification_prompt': True, 'coverage_prompt': True}}, 'Q')
        self.assertLess(both.index('record one label per item'), both.index(prime))
        with self.assertRaises(ValueError):
            paired.prime_contract({**cfgs['P0'], 'prime_contract': {'coverage_prompt': 'yes'}})
        with self.assertRaises(ValueError):
            paired.aljure_contract({'aljure_contract': {'evidence_coverage': 'yes'}})
        with self.assertRaises(ValueError):      # the text names SCI: not offered on the Python surface
            paired.validate_config({**cfgs['AC'], 'execution_language': 'python'})


class BudgetTest(unittest.TestCase):
    def test_four_concurrent_reservations_fit_the_per_arm_cap_and_the_ceiling_holds(self):
        config = ca.configs_of()['P0']
        self.assertAlmostEqual(h.reservation_usd(config), 4.32768)             # the conservative reservation is unchanged
        self.assertEqual(config['concurrent_requests'], ca.CONCURRENCY)
        self.assertEqual(h.admitted_concurrency(config), 4)
        self.assertEqual(h.admitted_concurrency({**config, 'usd_per_arm': config['usd_per_arm'] - 0.02}), 3)
        h.check_reservation_policy(config)
        with self.assertRaises(ValueError):
            h.check_reservation_policy({**config, 'concurrent_requests': 5})
        suites = fake_suites()
        seq = ca.sequence(suites)
        plan = ca.budget(config, seq, ca.strata_of(suites)[1])
        est = plan['estimate']
        self.assertAlmostEqual(est['high_usd'], round(ca.HIGH_MULTIPLIER * sum(est['expected_by_arm_usd'].values()), 2), delta=0.02)
        self.assertAlmostEqual(plan['required_ceiling_usd'], round(est['high_usd'] + config['usd_per_arm'], 2))
        self.assertEqual(plan['max_spend_usd'], ca.MAX_SPEND_USD)
        self.assertEqual(plan['maximum_reservation_exposure_usd'], ca.MAX_SPEND_USD)
        # An arm starts only while spend + unknown reservations + one per-arm cap fits: exposure can never pass the ceiling.
        self.assertAlmostEqual(plan['run_can_spend_until_usd'] + config['usd_per_arm'], ca.MAX_SPEND_USD)
        self.assertEqual(config['total_usd'], ca.MAX_SPEND_USD)

    def test_the_real_suite_fits_the_proposed_ceiling(self):
        if not (ROOT / 'var/official/coverage-dev/manifest.json').exists():
            self.skipTest('coverage-dev suite not built on this machine')
        suites = h.load_suites(ca.SUITES)
        seq = ca.sequence(suites)
        plan = ca.budget(ca.configs_of()['A0'], seq, ca.strata_of(suites)[1])
        self.assertEqual(len(seq), 120)
        self.assertLessEqual(plan['required_ceiling_usd'], ca.MAX_SPEND_USD)


class SequenceTest(unittest.TestCase):
    def test_six_arms_per_item_repeats_from_the_primary_stratum_only(self):
        suites = fake_suites()
        seq = ca.sequence(suites)
        self.assertEqual(len(seq), (17 + ca.REPEATS) * 6)
        self.assertEqual([e['index'] for e in seq], list(range(len(seq))))
        for i in range(0, len(seq), 6):
            block = seq[i:i + 6]
            self.assertEqual({e['arm'] for e in block}, set(ca.ARMS))
            self.assertEqual(len({(e['task_id'], e['trial']) for e in block}), 1)
            self.assertEqual([e['position'] for e in block], [1, 2, 3, 4, 5, 6])
        repeated = {e['task_id'] for e in seq if e['trial'] == 1}
        self.assertEqual(len(repeated), ca.REPEATS)
        self.assertTrue(all(t.startswith('p') for t in repeated))
        first = collections.Counter(e['arm'] for e in seq if e['position'] == 1)
        self.assertLessEqual(max(first.values()) - min(first.values()), 1)
        self.assertEqual(seq, ca.sequence(suites))
        self.assertNotEqual(seq, ca.sequence(suites, seed=1))
        self.assertEqual({e['stratum'] for e in seq}, set(ca.STRATA))

    def test_plan_constants_survive_a_json_round_trip(self):
        for constant in (ca.ARMS, ca.CONTRASTS, ca.MECHANISM, ca.GO, ca.SUITES):
            self.assertEqual(json.loads(json.dumps(constant)), constant)
        self.assertEqual(ca.CONTRASTS[ca.PRIMARY], ['AC', 'AU'])


class AnalysisTest(unittest.TestCase):
    def test_the_primary_uses_only_the_label_judgement_stratum(self):
        suites = fake_suites()
        seq = ca.sequence(suites)
        # Coverage (AC) fixes four label-judgement tasks the audit (AU) misses; on controls AC is worse. The primary must not see the controls.
        def score(e):
            if e['stratum'] != 'label-judgement':
                return 0.0 if e['arm'] == 'AC' else 1.0
            if e['arm'] in ('AC', 'AUC', 'PC'):
                return 1.0
            return 0.0 if e['task_id'] in ('p0', 'p1', 'p2', 'p3') else 1.0
        report = ca.summarize(fake_value(suites, seq), fake_rows(seq, suites, score))
        primary = report['primary']
        self.assertEqual((primary['name'], primary['stratum'], primary['tasks'], primary['independent_contexts']), ('coverage_vs_audit', 'label-judgement', 12, 12))
        self.assertAlmostEqual(primary['context_weighted_mean_difference'], 4 / 12)
        self.assertEqual(primary['decision'], 'superior')
        self.assertAlmostEqual(report['contrasts']['coverage_in_prime']['context_weighted_mean_difference'], 4 / 12)
        self.assertAlmostEqual(report['mechanism_control']['estimate'], 0.0)        # the same lift in both harnesses
        self.assertEqual(report['per_arm']['structural']['AC']['deadline_aware_mean_score'], 0.0)
        self.assertTrue(report['complete'])

    def test_negative_controls_report_added_work_and_the_go_rule_needs_gain_and_cost(self):
        suites = fake_suites()
        seq = ca.sequence(suites)
        def work(e):
            if e['arm'] in ('AC', 'AUC', 'PC'):
                return {'cost': 0.05 if e['harness'] == 'aljure' else 0.09, 'calls': 5, 'out': 900, 'tools': 5, 'seen': 0.9}
            return {}
        rows = fake_rows(seq, suites, lambda e: 1.0, work)
        report = ca.summarize(fake_value(suites, seq), rows)
        for name, tasks in (('structural', 3), ('audit-correct', 2), ('fresh-audit-already-correct', 12)):
            block = report['negative_controls'][name]
            self.assertEqual(block['tasks'], tasks)
            added = block['work_difference']['coverage_added_to_audit']
            self.assertAlmostEqual(added['cost_usd'], 0.02)
            self.assertAlmostEqual(added['model_calls'], 2)
            self.assertAlmostEqual(added['coverage_seen'], 0.4)
            self.assertAlmostEqual(added['score'], 0.0)
        self.assertIn('regression to the mean', report['negative_controls']['fresh-audit-already-correct']['note'])
        go = report['go_rule']['results']
        self.assertFalse(go['AC']['go'])                 # no gain
        self.assertTrue(go['AC']['primary_endpoint'] and not go['AUC']['primary_endpoint'])
        # A gain of 4/12 with a clear interval passes only if the cost stays within half of Prime's.
        lift = lambda e: 1.0 if e['arm'] in ('AC', 'AUC', 'PC') or e['task_id'] not in ('p0', 'p1', 'p2', 'p3') else 0.0
        cheap = ca.summarize(fake_value(suites, seq), fake_rows(seq, suites, lift))
        self.assertTrue(cheap['go_rule']['results']['AC']['go'])
        costly = ca.summarize(fake_value(suites, seq), fake_rows(seq, suites, lift, work))
        self.assertFalse(costly['go_rule']['results']['AC']['go'])          # 0.05 / 0.06 of Prime's cost
        self.assertGreater(costly['go_rule']['results']['AC']['cost_ratio_to_prime'], 0.5)

    def test_an_incomplete_run_is_reported_as_incomplete(self):
        suites = fake_suites()
        seq = ca.sequence(suites)
        rows = fake_rows(seq[:30], suites, lambda e: 1.0)
        rows[-1] = {**rows[-1], 'status': 'not-attempted', 'failure': 'BudgetCeiling', 'score': 0.0}
        report = ca.summarize(fake_value(suites, seq), rows)
        self.assertFalse(report['complete'])
        self.assertEqual(report['stopped_by'], 'BudgetCeiling')


class SuiteSelectionTest(unittest.TestCase):
    PROFILE = {'seed': 7, 'windows': [['a', 4096, 1], ['b', 4096, 2], ['c', 8192, 3], ['d', 16384, 4], ['e', 32768, 5], ['f', 8192, 6]],
               'structural_lengths': [[4096], [8192], [16384, 32768]], 'audit_correct': [['z', 8192, 9, 900]]}

    def rows(self):
        out, n = {}, 0
        for dataset, length, window in self.PROFILE['windows']:
            found = []
            for group, task, kind in (('counting', 'TASK_TYPE.RELATIVE_FREQ', 'ANSWER_TYPE.COMPARISON'), ('counting', 'TASK_TYPE.NUMERIC_ONE_CLASS', 'ANSWER_TYPE.NUMERIC'),
                                      ('counting', 'TASK_TYPE.MOST_FREQ', 'ANSWER_TYPE.LABEL'), ('timeline', 'TASK_TYPE.NUMERIC_ONE_CLASS', 'ANSWER_TYPE.NUMERIC'),
                                      ('user', 'TASK_TYPE.RELATIVE_FREQ', 'ANSWER_TYPE.COMPARISON'), ('timeline', 'TASK_TYPE.LEAST_FREQ', 'ANSWER_TYPE.LABEL'),
                                      ('user', 'TASK_TYPE.MOST_FREQ', 'ANSWER_TYPE.USER'), ('timeline', 'TASK_TYPE.REPRESENTED_N_TIMES', 'ANSWER_TYPE.NUMERIC'),
                                      ('user', 'TASK_TYPE.RELATIVE_FREQ', 'ANSWER_TYPE.USER')):
                for _ in range(2):
                    n += 1
                    found.append({'id': n, 'task_group': group, 'task': task, 'answer_type': kind})     # no question, no answer
            out[(dataset, length, window)] = found
        return out

    def test_selection_uses_metadata_only_and_balances_the_cells(self):
        rows = self.rows()
        chosen = official.coverage_selection(rows, self.PROFILE)
        self.assertEqual(chosen, official.coverage_selection(rows, self.PROFILE))
        by_id = {r['id']: (w, r) for w, found in rows.items() for r in found}
        self.assertEqual(len(chosen['label-judgement']), 6)
        self.assertEqual({by_id[i][0] for i in chosen['label-judgement']}, set(rows))                      # one per window
        cells = [official.coverage_cell(by_id[i][1]) for i in chosen['label-judgement']]
        self.assertEqual(sorted(cells), sorted(official.COVERAGE_CELLS))                                    # each cell once over six windows
        self.assertEqual(len(chosen['structural']), 3)
        self.assertEqual(sorted(by_id[i][0][1] in bucket for i, bucket in zip(chosen['structural'], self.PROFILE['structural_lengths'])), [True] * 3)
        for i in chosen['structural']:
            self.assertIsNone(official.coverage_cell(by_id[i][1]))
        self.assertEqual(chosen['audit-correct'], [900])
        self.assertNotEqual(chosen['label-judgement'], official.coverage_selection(rows, {**self.PROFILE, 'seed': 8})['label-judgement'])

    def test_cells_exclude_structural_and_user_answers(self):
        cell = lambda g, t, k: official.coverage_cell({'task_group': g, 'task': t, 'answer_type': k})
        self.assertEqual(cell('counting', 'TASK_TYPE.RELATIVE_FREQ', 'ANSWER_TYPE.COMPARISON'), ['whole', 'COMPARISON'])
        self.assertEqual(cell('timeline', 'TASK_TYPE.NUMERIC_ONE_CLASS', 'ANSWER_TYPE.NUMERIC'), ['filtered', 'NUMERIC'])
        self.assertIsNone(cell('timeline', 'TASK_TYPE.REPRESENTED_N_TIMES', 'ANSWER_TYPE.NUMERIC'))
        self.assertIsNone(cell('user', 'TASK_TYPE.MOST_FREQ', 'ANSWER_TYPE.USER'))
        self.assertIsNone(cell('timeline', 'TASK_TYPE.MOST_FREQ', 'ANSWER_TYPE.DATE'))

    def test_the_pinned_profile_keeps_a_reserve_apart_from_the_development_windows(self):
        pins = json.loads((ROOT / 'benchmark/upstream.lock.json').read_text())
        profile = pins['official_profiles']['oolong-synth:dev-coverage:mixed']
        dev = {tuple(w) for w in profile['windows']}
        reserve = {tuple(w) for w in profile['reserve']}
        controls = {tuple(c[:3]) for c in profile['audit_correct']}
        self.assertEqual((len(dev), len(controls)), (12, 2))
        self.assertFalse(dev & reserve or controls & reserve or dev & controls)
        self.assertEqual(profile['count'], len(dev) + len(profile['structural_lengths']) + len(controls))
        self.assertTrue(all(length <= 32768 for _, length, _ in dev))
        self.assertTrue(any(length >= 65536 for _, length, _ in reserve))
        self.assertTrue(all(name in pins['official_artifacts'] for name in profile['artifacts']))
        # No development or reserve window belongs to an earlier pinned profile.
        earlier = set()
        for key, other in pins['official_profiles'].items():
            if key != 'oolong-synth:dev-coverage:mixed' and key.startswith('oolong-synth:') and isinstance(other.get('windows'), list):
                length = key.split(':')[-1]
                earlier |= {(w[0], int(length), w[1]) for w in other['windows'] if length.isdigit() and len(w) == 2}
        self.assertFalse((dev | reserve) & earlier)
        self.assertTrue(controls <= earlier)


if __name__ == '__main__':
    unittest.main()
