import ast
import json
import math
import tempfile
import unittest
from pathlib import Path

from benchmark import exploratory
from benchmark.oolong import PINS
from benchmark.vendor import longbench_pro as lbp
from benchmark.vendor import obliq_math as obliq

ROOT = Path(__file__).resolve().parent.parent
UPSTREAM_UTILS = ROOT / 'var/official-cache/reference-longbench-pro-utils.py'


class ObliqScorerTest(unittest.TestCase):
    def test_parse_keeps_order_first_occurrence_and_markers(self):
        out = '[Answer]\nID: american-math-monthly___2007___E 496\n- berkeley-quals___1984___Su2.2.32\n2. harvard-quals___2010___S10.9\nnot an id\nberkeley-quals___1984___Su2.2.32\nID: x___1___y || some text'
        self.assertEqual(obliq.parse_ranking(out), ['american-math-monthly___2007___E 496', 'berkeley-quals___1984___Su2.2.32', 'harvard-quals___2010___S10.9'])
        self.assertEqual(obliq.parse_ranking(''), [])
        self.assertEqual(obliq.parse_ranking(None), [])

    def test_ndcg_at_10_matches_trec_definition(self):
        gold = {f'd{i}___a___b': 2 for i in range(5)}
        perfect = '\n'.join(f'd{i}___a___b' for i in range(5))
        self.assertAlmostEqual(obliq.score(gold, {}, [], perfect)['score'], 1.0)
        # One relevant document at rank 1 only: DCG = 2/log2(2) = 2; IDCG = 2 * sum(1/log2(r+1), r=1..5)
        single = obliq.score(gold, {}, [], 'd0___a___b\nz___a___b')['score']
        idcg = sum(2 / math.log2(r + 1) for r in range(1, 6))
        self.assertAlmostEqual(single, 2 / idcg)
        # Rank 11 and beyond does not count.
        late = obliq.score(gold, {}, [], '\n'.join(['z%d___a___b' % i for i in range(10)] + ['d0___a___b']))['score']
        self.assertEqual(late, 0.0)
        self.assertEqual(obliq.score(gold, {}, [], 'nothing here')['parse_confidence'], 'no-id-found')

    def test_excluded_ids_are_dropped_from_ranking_and_gold(self):
        gold = {'a___1___x': 2, 'b___1___y': 2, 'e___1___z': 2}
        scored = obliq.score(gold, {'a___1___x': 2, 'p___1___q': 2}, ['e___1___z'], 'e___1___z\na___1___x\nb___1___y')
        self.assertAlmostEqual(scored['score'], 1.0)  # e is excluded on both sides, so a then b is perfect
        self.assertEqual(scored['hits_at_10'], 2)
        self.assertIsNotNone(scored['pooled_ndcg_at_10'])

    def test_split_is_seeded_disjoint_and_covers_every_query(self):
        ids = [f'q{i:05d}' for i in range(151)]
        dev = exploratory.split_obliq(ids, PINS['official_profiles']['obliq-math:dev:corpus'])
        held = exploratory.split_obliq(ids, PINS['official_profiles']['obliq-math:heldout:corpus'])
        self.assertEqual(len(dev), 10)
        self.assertEqual(len(held), 141)
        self.assertFalse(set(dev) & set(held))
        self.assertEqual(sorted(dev + held), ids)
        self.assertEqual(dev, exploratory.split_obliq(list(reversed(ids)), PINS['official_profiles']['obliq-math:dev:corpus']))


class LongBenchScorerTest(unittest.TestCase):
    def test_metrics_follow_upstream_definitions(self):
        self.assertEqual(lbp.Accuracy(['Paris'], 'thinking...\n[Answer]\nparis'), 1.0)
        self.assertEqual(lbp.Accuracy(['Paris'], '[Answer]\nLondon\nParis'), 0.0)
        self.assertAlmostEqual(lbp.F1_Score(['a', 'b', 'c'], '[Answer]\na\nb\nd'), 2 * (2 / 3) * (2 / 3) / (4 / 3))
        self.assertAlmostEqual(lbp.SubEM(['a', 'b'], '[Answer]\nb\nz'), 0.5)
        self.assertAlmostEqual(lbp.Pairwise_Accuracy(['A', 'B', 'C'], '[Answer]\nA\nC\nB'), 2 / 3)
        self.assertEqual(lbp.Pairwise_Accuracy(['A'], '[Answer]\nA\nB'), 0.0)
        self.assertEqual(lbp.score('T3.1 Multi-Doc Integration QA', ['x'], ''), 0.0)
        self.assertEqual(lbp.score('T4.1 Global-Coverage Constrained Summary', ['x'], 'x'), 0.0)  # not ported

    def test_ndcg_reimplements_trec_ndcg_cut_with_upstream_gains(self):
        # answers define gains 3, 2, 1 and k = 3; a perfect ranking scores 1.
        self.assertAlmostEqual(lbp.NDCG(['x', 'y', 'z'], '[Answer]\nx\ny\nz'), 1.0)
        # reversed ranking: DCG = 1/log2(2) + 2/log2(3) + 3/log2(4); IDCG = 3/log2(2) + 2/log2(3) + 1/log2(4)
        dcg = 1 / math.log2(2) + 2 / math.log2(3) + 3 / math.log2(4)
        idcg = 3 / math.log2(2) + 2 / math.log2(3) + 1 / math.log2(4)
        self.assertAlmostEqual(lbp.NDCG(['x', 'y', 'z'], '[Answer]\nz\ny\nx'), dcg / idcg)
        # only the first k ranked items count; unjudged items contribute nothing
        self.assertAlmostEqual(lbp.NDCG(['x', 'y'], '[Answer]\nq\nr\nx\ny'), 0.0)
        self.assertEqual(lbp.NDCG([], 'x'), 0.0)

    def test_port_agrees_with_the_pinned_upstream_on_a_probe_set_when_present(self):
        """Behavioural equivalence: the upstream pure functions (no jieba, rouge or pytrec_eval) are extracted from
        the pinned utils.py by AST and executed beside the port on the same probes."""
        if not UPSTREAM_UTILS.exists():
            self.skipTest('pinned upstream utils.py not in the cache (license unverified; not vendored)')
        import hashlib
        self.assertEqual(hashlib.sha256(UPSTREAM_UTILS.read_bytes()).hexdigest(), PINS['longbench_pro_scorer']['source_sha256'])
        tree = ast.parse(UPSTREAM_UTILS.read_text())
        wanted = {'get_answer_area', 'lower', 'split_by_new_line', 'fix_space', 'normalize_answers', 'normalize_prediction',
                  'Accuracy', 'F1_Score', 'SubEM', 'Pairwise_Accuracy'}
        module = ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in wanted], type_ignores=[])
        from itertools import combinations
        from typing import Dict, List, Set
        upstream = {'List': List, 'Dict': Dict, 'Set': Set, 'combinations': combinations}
        exec(compile(module, str(UPSTREAM_UTILS), 'exec'), upstream)
        probes = [(['Paris'], 'x\n[Answer]\nparis'), (['Paris'], '[Answer]\nLondon\nParis'), (['a', 'b', 'c'], '[Answer]\na\nb\nd'),
                  (['a', 'b'], '[Answer]\nb\nz'), (['A', 'B', 'C'], '[Answer]\nA\nC\nB'), (['A'], '[Answer]\nA\nB'),
                  (['1 rule 1001', '2 rule 9011'], '[答案]\n1  rule 1001\n2 rule  9011'), (['x'], ''), ([], 'x'),
                  (['a', 'b'], 'no marker\na\nb'), (['K1', 'K2'], 'thinking [Answer] early\n[Answer]\nk2\nk1')]
        for name in ('Accuracy', 'F1_Score', 'SubEM', 'Pairwise_Accuracy'):
            for answers, prediction in probes:
                self.assertAlmostEqual(upstream[name](answers, prediction), getattr(lbp, name)(answers, prediction), msg=f'{name} {answers} {prediction!r}')
        for answers, prediction in probes:
            self.assertEqual(upstream['normalize_prediction'](prediction), lbp.normalize_prediction(prediction))
            self.assertEqual(upstream['normalize_answers'](answers), lbp.normalize_answers(answers))


class ProvenanceTest(unittest.TestCase):
    def test_pins_are_complete_and_profiles_disjoint(self):
        for key in ('obliq_math_dataset', 'obliq_math_scorer', 'longbench_pro_dataset', 'longbench_pro_scorer'):
            self.assertIn(key, PINS)
        self.assertEqual(PINS['longbench_pro_scorer']['license'][:10], 'unverified')
        self.assertEqual(PINS['obliq_math_dataset']['license'], 'cc-by-4.0')
        self.assertEqual(PINS['longbench_pro_dataset']['license'], 'apache-2.0')
        for name in PINS['official_profiles']['obliq-math:dev:corpus']['artifacts'] + ['longbench_pro.json']:
            pin = PINS['official_artifacts'][name]
            self.assertEqual(len(pin['sha256']), 64)
            self.assertGreater(pin['size'], 0)
        dev, held = PINS['official_profiles']['longbench-pro:dev:mixed'], PINS['official_profiles']['longbench-pro:heldout:mixed']
        self.assertEqual(dev['seed'], held['seed'])
        self.assertEqual(sum(dev['per_length'].values()), 10)
        self.assertEqual(sum(held['per_length'].values()), 60)

    def test_prepared_suites_are_sealed_and_disjoint_when_present(self):
        base = ROOT / 'var/official'
        pairs = [('obliq-math-dev', 'obliq-math-heldout'), ('longbench-pro-dev', 'longbench-pro-heldout')]
        for dev, held in pairs:
            if not (base / dev).exists() or not (base / held).exists():
                self.skipTest('suites not prepared')
            d, h = json.loads((base / dev / 'manifest.json').read_text()), json.loads((base / held / 'manifest.json').read_text())
            self.assertFalse(set(d['task_ids']) & set(h['task_ids']))
            self.assertEqual(oct((base / held / 'controller/answers.jsonl').stat().st_mode)[-3:], '600')
            if dev.startswith('longbench'):
                dc = {json.loads(l)['context_window_id'] for l in (base / dev / 'controller/answers.jsonl').read_text().splitlines() if l}
                hc = {json.loads(l)['context_window_id'] for l in (base / held / 'controller/answers.jsonl').read_text().splitlines() if l}
                self.assertFalse(dc & hc)


if __name__ == '__main__':
    unittest.main()
