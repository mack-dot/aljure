"""Synthetic development invariants and fail-closed lifecycle gates; no model calls."""
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from benchmark import learning_development as development, paired
from benchmark.learning_report import minimal_acceptance
from benchmark.oolong import jsonl, read_suite
from test_thesis_trajectory import TrajectoryFixture, ROOT

CONFIG = json.loads((ROOT / 'config/learning-minimal-sonnet.json').read_text())


class MinimalDataTests(unittest.TestCase):
    def test_generator_is_deterministic_disjoint_and_tamper_evident(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'suite'
            manifest = development.prepare(root)
            self.assertEqual(development.verify(root), manifest)
            _, tasks, answers = read_suite(root)
            self.assertEqual(len(tasks), 6)
            novelty = json.loads((root / 'controller/novelty.json').read_text())
            self.assertTrue(novelty['texts_disjoint'] and novelty['features_disjoint'])
            for answer in answers.values():
                self.assertEqual(development.score(answer, 'Answer: ' + answer['answer'])['score'], 1)
                self.assertEqual(development.score(answer, 'Answer: ' + str(int(answer['answer']) + 1))['score'], 0)
            with self.assertRaisesRegex(ValueError, 'overlap'):
                development.novelty([{'id': 'a', 'items': [{'text': 'id=a x=1'}]},
                                     {'id': 'b', 'items': [{'text': 'id=b x=1'}]}])
            (root / 'controller/panel.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'differs'):
                development.verify(root)

    def test_gate_needs_correct_novel_reuse_refusal_and_unchanged_library(self):
        summary = {'lifecycle_pass': True, 'pre_restart_code_hashes': ['old'],
                   'post_restart_invocations': [{'position': n, 'code_hash': 'old', 'calls': 1, 'returns': 1,
                                                 'values': ['hold']} for n in (3, 4, 5)]}
        cases = [{'position': n, 'verified': True, 'refused': ['old'] if n == 6 else []} for n in range(1, 7)]
        rows = [{'position': n, 'learning_library_sha256': 'pin'} for n in range(1, 7)]
        ledger = [{'type': 'cold-restart', 'pin': 'pin'}]
        self.assertTrue(minimal_acceptance(summary, cases, rows, ledger))
        wrong = copy.deepcopy(cases); wrong[2]['verified'] = False
        self.assertFalse(minimal_acceptance(summary, wrong, rows, ledger))
        nil_only = copy.deepcopy(summary); nil_only['post_restart_invocations'][0]['values'] = []
        self.assertFalse(minimal_acceptance(nil_only, cases, rows, ledger))
        changed = copy.deepcopy(rows); changed[4]['learning_library_sha256'] = 'new'
        self.assertFalse(minimal_acceptance(summary, cases, changed, ledger))
        self.assertFalse(minimal_acceptance({**summary, 'post_restart_invocations': []}, cases, rows, ledger))
        wrong = copy.deepcopy(summary); wrong['post_restart_invocations'][0]['code_hash'] = 'new'
        self.assertFalse(minimal_acceptance(wrong, cases, rows, ledger))
        self.assertFalse(minimal_acceptance(summary, cases, rows, ledger + [{'type': 'promotion', 'position': 3}]))
        wrong = copy.deepcopy(cases); wrong[5]['refused'] = []
        self.assertFalse(minimal_acceptance(summary, wrong, rows, ledger))


class MinimalRunnerTests(TrajectoryFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.suite = self.root / 'new-development'
        development.prepare(self.suite)
        config = self.root / 'minimal.json'
        config.write_text(json.dumps(CONFIG))
        self.plan_path = self.root / 'minimal-plan.json'
        self.plan = paired.plan_trajectory(self.suite, config, self.plan_path)

    def test_only_acquisition_tasks_can_propose_and_resume_needs_a_new_process(self):
        self.assertEqual(self.plan['allocation']['task_runs'], 6)
        first = self.trajectory('ES-s101')
        self.assertEqual(first['status'], 'cold-restart-required')
        self.assertEqual(len(self.seen), 2)
        with self.assertRaisesRegex(ValueError, 'new runner process'):
            self.trajectory('ES-s101')
        with patch.object(paired.os, 'getpid', return_value=-1):
            self.trajectory('ES-s101')
        self.assertEqual(len(self.seen), 6)
        self.assertEqual(self.seen[2:], [first['pin']] * 4)
        out = self.out / 'ES-s101'
        self.assertEqual([r['position'] for r in paired.trajectory_ledger(out) if r['type'] == 'promotion'], [1, 2])
        for n in range(3, 7):
            self.assertFalse((out / f'{n:02}-aljure/agent/proposal.edn').exists())

    def test_disk_floor_stops_before_inference(self):
        with patch.object(paired.shutil, 'disk_usage', return_value=SimpleNamespace(free=0)):
            with self.assertRaisesRegex(ValueError, '6 GiB'):
                self.trajectory('ES-s101')
        self.assertEqual(self.seen, [])


if __name__ == '__main__':
    unittest.main()
