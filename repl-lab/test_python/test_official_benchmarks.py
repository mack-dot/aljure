"""FIXTURE controls for pinned official import and independently scored answers."""
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from benchmark import official
from benchmark.oolong import encoded, jsonl


class OfficialScoringTests(unittest.TestCase):
    def test_official_pairs_metrics_order_dedup_and_thinking(self):
        answer = {"answer": "(1, 2)\n(3, 4)"}
        scored = official.score_answer("oolong-pairs", answer,
                                       "<think>(90,91)</think> (2,1), (1,2), (5,6)")
        self.assertEqual((scored["precision"], scored["recall"], scored["score"]), (0.5, 0.5, 0.5))
        self.assertEqual(official.score_answer("oolong-pairs", answer, "invalid")["score"], 0)
        self.assertEqual(official.score_answer("oolong-pairs", {"answer": "[]"}, "[]")["score"], 1)

    def test_official_synth_partial_credit_unchanged(self):
        answer = {"id": 1, "context_window_id": 0, "dataset": "fixture",
                  "answer": "[5]", "answer_type": "ANSWER_TYPE.NUMERIC"}
        self.assertEqual(official.score_answer("oolong-synth", answer, "4")["score"], 0.75)

    def test_unknown_suite_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            official.suite_pins("approximate-oolong")


class OfficialDownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cache = Path(self.temp.name)
        self.data = b"fixture upstream bytes"
        self.pin = {"repository": "https://huggingface.co/datasets/test/fixture",
                    "revision": "f" * 40, "path": "data/test.bin", "size": len(self.data),
                    "sha256": hashlib.sha256(self.data).hexdigest()}
        self.mock_pins = {**official.PINS, "official_artifacts": {"test.bin": self.pin}}
        self.patch = patch.object(official, "PINS", self.mock_pins)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_download_uses_exact_pin_and_offline_cache(self):
        with patch.object(official.urllib.request, "urlopen", return_value=io.BytesIO(self.data)) as request:
            path = official.fetch_artifact("test.bin", self.cache)
        self.assertIn("/resolve/" + "f" * 40 + "/data/test.bin", request.call_args.args[0])
        self.assertEqual(path.read_bytes(), self.data)
        with patch.object(official.urllib.request, "urlopen", side_effect=AssertionError("network")):
            self.assertEqual(official.fetch_artifact("test.bin", self.cache, download=False), path)

    def test_corrupt_cache_is_not_silently_repaired(self):
        path = self.cache / (self.pin["sha256"] + "-test.bin")
        path.write_bytes(b"x" * len(self.data))
        with patch.object(official.urllib.request, "urlopen", side_effect=AssertionError("network")):
            with self.assertRaisesRegex(ValueError, "Corrupt"):
                official.fetch_artifact("test.bin", self.cache)

    def test_download_hash_failure_preserves_no_partial_artifact(self):
        with patch.object(official.urllib.request, "urlopen", return_value=io.BytesIO(b"x" * len(self.data))):
            with self.assertRaisesRegex(ValueError, "does not match"):
                official.fetch_artifact("test.bin", self.cache)
        self.assertEqual(list(self.cache.iterdir()), [])

    def test_unknown_or_missing_artifact_fails_without_network(self):
        with self.assertRaisesRegex(ValueError, "Unknown"):
            official.fetch_artifact("caller-claimed-revision", self.cache)
        with self.assertRaisesRegex(ValueError, "Missing verified cache"):
            official.fetch_artifact("test.bin", self.cache, download=False)


class OfficialImportTests(unittest.TestCase):
    def setUp(self):
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError:
            self.skipTest("Install benchmark/requirements-official.txt for Parquet import controls")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cache = self.root / "cache"
        self.cache.mkdir()
        self.pins = copy.deepcopy(official.PINS)
        self.pins["official_artifacts"] = {}
        self.pins["official_profiles"] = {}
        # IDs deliberately descend. First-N must follow official source row order.
        for suite, subset, filename in [("oolong-synth", "negation", "test.parquet"),
                                         ("oolong-pairs", "trec_coarse", "context.parquet")]:
            rows = [{"id": 100 - i, "context_window_id": 7, "dataset": subset,
                     "context_len": 32768, "context_window_text": "PUBLIC unlabelled context",
                     "context_window_text_with_labels": "SECRET labels never exported",
                     "question": "Fixture question " + str(i), "answer": "[987654321]",
                     "answer_type": "ANSWER_TYPE.NUMERIC"} for i in range(20)]
            path = self.root / filename
            pq.write_table(pa.Table.from_pylist(rows), path, row_group_size=3)
            self._cache_fixture(filename, path.read_bytes())
            names = [filename]
            if suite == "oolong-pairs":
                name = "pairs.json"
                questions = [{"id": str(i + 1), "question": "Pair fixture " + str(i),
                              "answer": ["(88771, 99882)"], "type": "pairs"} for i in range(20)]
                self._cache_fixture(name, encoded(questions))
                names.append(name)
            self.pins["official_profiles"][f"{suite}:{subset}:32768"] = {
                "split": "test" if suite == "oolong-synth" else "validation", "artifacts": names}
        self.patch = patch.object(official, "PINS", self.pins)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def _cache_fixture(self, name, data):
        pin = {"repository": "https://huggingface.co/datasets/test/fixture", "revision": "f" * 40,
               "path": "data/" + name, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
        self.pins["official_artifacts"][name] = pin
        (self.cache / (pin["sha256"] + "-" + name)).write_bytes(data)

    def test_both_suites_first_one_is_prefix_of_first_ten(self):
        for suite in ("oolong-synth", "oolong-pairs"):
            one, ten = self.root / (suite + "-one"), self.root / (suite + "-ten")
            first = official.prepare_official(one, suite=suite, cache=self.cache, count=1, download=False)
            larger = official.prepare_official(ten, suite=suite, cache=self.cache, count=10, download=False)
            self.assertEqual(first["task_ids"], larger["task_ids"][:1])
            self.assertEqual(list(jsonl(one / "public/tasks.jsonl")), list(jsonl(ten / "public/tasks.jsonl"))[:1])
            self.assertEqual(larger["selection"]["method"], "first-n-in-pinned-upstream-order")
            self.assertEqual(len(larger["task_ids"]), 10)
            self.assertEqual(len(larger["source_artifacts"]), 1 if suite == "oolong-synth" else 2)

    def test_public_material_excludes_labels_gold_and_scorer_metadata(self):
        for suite in ("oolong-synth", "oolong-pairs"):
            output = self.root / suite
            official.prepare_official(output, suite=suite, cache=self.cache, count=10, download=False)
            public = b"\n".join(path.read_bytes() for path in (output / "public").rglob("*") if path.is_file())
            for secret in (b"SECRET", b"987654321", b"88771", b"99882", b"answer_type", b"with_labels"):
                self.assertNotIn(secret, public)
            self.assertEqual((output / "controller").stat().st_mode & 0o777, 0o700)
            self.assertEqual((output / "controller/answers.jsonl").stat().st_mode & 0o777, 0o600)

    def test_manifest_pins_and_selection_are_enforced(self):
        manifest = official.prepare_official(self.root / "out", cache=self.cache, download=False)
        official.validate_provenance(manifest)
        for mutate in (lambda m: m["selection"].update(seed=4),
                       lambda m: m["source_artifacts"][0].update(revision="caller-claim"),
                       lambda m: m.update(input_provenance="unverified-local-export")):
            changed = copy.deepcopy(manifest)
            mutate(changed)
            with self.assertRaises(ValueError):
                official.validate_provenance(changed)

    def test_unknown_profile_seed_and_count_do_not_create_output(self):
        for config in ({"context_len": 99}, {"seed": 1}, {"count": 2}):
            with self.assertRaises(ValueError):
                official.prepare_official(self.root / "missing", cache=self.cache, download=False, **config)
            self.assertFalse((self.root / "missing").exists())

    def test_previous_evidence_is_not_overwritten(self):
        output = self.root / "existing"
        official.prepare_official(output, cache=self.cache, download=False)
        before = (output / "manifest.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "Output exists"):
            official.prepare_official(output, cache=self.cache, download=False)
        self.assertEqual((output / "manifest.json").read_bytes(), before)

    def test_cache_change_during_decode_is_rejected(self):
        original = official._parquet_rows

        def changed(path, *args, **kwargs):
            rows = original(path, *args, **kwargs)
            path.write_bytes(b"changed after decoding")
            return rows

        with patch.object(official, "_parquet_rows", side_effect=changed):
            with self.assertRaisesRegex(ValueError, "changed during"):
                official.prepare_official(self.root / "changed", cache=self.cache, download=False)
        self.assertFalse((self.root / "changed").exists())


if __name__ == "__main__":
    unittest.main()
