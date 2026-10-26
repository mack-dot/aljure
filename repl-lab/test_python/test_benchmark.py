"""Synthetic protocol tests. These are not live benchmark or learning evidence."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from benchmark.oolong import PINS, account, compare, digest, encoded, prepare, read_suite, write_jsonl
from benchmark.vendor.oolong_synth import synth_process_response


MODEL = {"provider": "anthropic", "model": "claude-sonnet-5-5", "thinking": "provider-default",
         "temperature": "provider-default", "max_output_tokens": 2048}
PRICING = {"input_tokens": 2, "output_tokens": 10}


def call(call_id="root-1", session="root", *, unknown=False, cache=0):
    value = {"kind": "provider-call", "call_id": call_id, "session_id": session,
             "model": MODEL["model"], "status": "unknown" if unknown else "complete"}
    if unknown:
        return {**value, "reserved_usd": 0.1}
    return {**value, "provider_request_id": f"fixture-{call_id}", "input_tokens": 100,
            "output_tokens": 20, "cache_read_input_tokens": cache, "cache_creation_input_tokens": 0}


class BenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.raw = self.root / "raw.jsonl"
        self.data = [{"id": i, "dataset": "fixture-subset", "context_len": 131072,
                      "context_window_id": 7, "context_window_text": "External fixture records.",
                      "question": "Return the count.", "answer": "[997]", "answer_type": "ANSWER_TYPE.NUMERIC"}
                     for i in range(10)]
        write_jsonl(self.raw, self.data)
        self.suite = self.root / "suite"
        self.manifest = self.prepare(self.suite)

    def prepare(self, out):
        return prepare(self.raw, out, dataset_revision=PINS["oolong_dataset"]["revision"],
                       subset="fixture-subset", context_len=131072, count=10, seed=42, fixture=True)

    def pilot(self):
        _, tasks, _ = read_suite(self.suite)
        results = []
        for task_id, task in tasks.items():
            for harness in ("aljure", "prime"):
                prefix = f"{task_id}-{harness}"
                answer = self.root / f"{prefix}.txt"
                answer.write_text("Answer: 997" if harness == "aljure" else "Answer: 998")
                trace = self.root / f"{prefix}.trace.jsonl"
                write_jsonl(trace, [{"type": "fixture-only"}])
                usage = self.root / f"{prefix}.usage.jsonl"
                write_jsonl(usage, [call(prefix), call(prefix + "-child", "child")])
                results.append({"task_id": task_id, "harness": harness, "harness_revision": "fixture-1",
                                "suite_sha256": self.manifest["suite_sha256"], "task_sha256": task["task_sha256"],
                                "model_config": MODEL.copy(), "pricing_usd_per_m": PRICING.copy(),
                                "budget_usd": 1, "fresh_session": True, "provenance": "fixture",
                                "status": "completed", "wall_time_ms": 10,
                                "answer_path": answer.name, "answer_sha256": digest(answer.read_bytes()),
                                "trace_path": trace.name, "trace_sha256": digest(trace.read_bytes()),
                                "usage_path": usage.name, "usage_sha256": digest(usage.read_bytes()),
                                "score": -100})  # Must never influence independent scoring.
        return results

    def compare(self, results):
        path = self.root / "results.jsonl"
        write_jsonl(path, results)
        return compare(self.suite, path)

    def test_official_numeric_partial_credit_and_date_rules(self):
        row = self.data[0]
        self.assertEqual(synth_process_response(row, "Answer: 998", "blinded")["score"], 0.75)
        self.assertEqual(synth_process_response(row, "Answer: 999", "blinded")["score"], 0.5625)
        row = {**row, "answer": "[datetime.date(2026, 10, 19)]", "answer_type": "ANSWER_TYPE.DATE"}
        self.assertEqual(synth_process_response(row, "Date: October 19, 2026", "blinded")["score"], 1)

    def test_preparation_is_order_independent_and_hides_answers(self):
        write_jsonl(self.raw, list(reversed(self.data)))
        other = self.root / "other"
        second = self.prepare(other)
        self.assertEqual(self.manifest["task_ids"], second["task_ids"])
        self.assertEqual((self.suite / "public/tasks.jsonl").read_bytes(), (other / "public/tasks.jsonl").read_bytes())
        for file in (self.suite / "public").rglob("*"):
            if file.is_file():
                self.assertNotIn(b"997", file.read_bytes())
                self.assertNotIn(b"answer_type", file.read_bytes())
        self.assertEqual(self.manifest["input_provenance"], "fixture")

    def test_root_and_child_usage_are_counted_once(self):
        result = account([call(), call("child-1", "child")], PRICING)
        self.assertEqual(result["known_tokens"]["input_tokens"], 200)
        self.assertEqual(result["model_cost_usd"], 0.0008)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            account([call(), call()], PRICING)
        with self.assertRaisesRegex(ValueError, "individual provider"):
            account([{"kind": "child_usage_attributed", "aggregateUsage": {}}], PRICING)

    def test_unknown_calls_and_unpriced_cache_are_not_zero_cost(self):
        result = account([call(), call("child-1", "child", unknown=True)], PRICING)
        self.assertIsNone(result["model_cost_usd"])
        self.assertEqual(result["reserved_unknown_usd"], 0.1)
        result = account([call(cache=20)], PRICING)
        self.assertIsNone(result["model_cost_usd"])
        self.assertEqual(result["unpriced_calls"], 1)

    def test_ten_paired_fixtures_use_independent_scores_and_stay_fixtures(self):
        report = self.compare(self.pilot())
        self.assertEqual(report["mean_score"], {"aljure": 1, "prime": 0.75})
        self.assertEqual(report["paired_cases"], 10)
        self.assertEqual(report["independent_contexts"], 1)
        self.assertEqual(report["evidence"], "offline-fixture")
        self.assertFalse(report["paid_execution_ready"])
        self.assertFalse(report["learning_claim"])
        self.assertTrue(report["accounting_complete"])

    def test_failures_remain_in_the_paired_denominator(self):
        results = self.pilot()
        results[0]["status"] = "timeout"
        results[0].pop("answer_path")
        report = self.compare(results)
        self.assertEqual(report["paired_cases"], 10)
        self.assertAlmostEqual(report["mean_score"]["aljure"], 0.9)

    def test_partial_duplicate_and_unmatched_pilots_are_rejected(self):
        results = self.pilot()
        mutations = [results[:-1], results + [results[0]]]
        for field, value in (("budget_usd", 2), ("fresh_session", False),
                             ("task_sha256", "bad"), ("harness_revision", "different")):
            changed = copy.deepcopy(results)
            changed[-1][field] = value
            mutations.append(changed)
        changed = copy.deepcopy(results)
        changed[-1]["model_config"]["thinking"] = "high"
        mutations.append(changed)
        for index, value in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.compare(value)

    def test_modified_inputs_answers_and_escaped_paths_are_rejected(self):
        results = self.pilot()
        changed = copy.deepcopy(results)
        changed[0]["answer_sha256"] = "bad"
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            self.compare(changed)
        changed = copy.deepcopy(results)
        changed[0]["trace_path"] = "../outside.jsonl"
        with self.assertRaisesRegex(ValueError, "escapes"):
            self.compare(changed)
        context = next((self.suite / "public/contexts").glob("*.txt"))
        context.write_text("tampered")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            self.compare(results)

    def test_child_model_change_and_receipt_reuse_are_rejected(self):
        results = self.pilot()
        path = self.root / results[0]["usage_path"]
        receipts = [call("unique"), {**call("unique-child", "child"), "model": "other-model"}]
        write_jsonl(path, receipts)
        results[0]["usage_sha256"] = digest(path.read_bytes())
        with self.assertRaisesRegex(ValueError, "child used a different model"):
            self.compare(results)
        results = self.pilot()
        results[1]["usage_path"] = results[0]["usage_path"]
        results[1]["usage_sha256"] = results[0]["usage_sha256"]
        with self.assertRaisesRegex(ValueError, "reused across"):
            self.compare(results)

    def test_unresolved_reservations_cannot_hide_a_budget_overrun(self):
        results = self.pilot()
        path = self.root / results[0]["usage_path"]
        write_jsonl(path, [call("unique"), {**call("pending", "child", unknown=True), "reserved_usd": 1}])
        results[0]["usage_sha256"] = digest(path.read_bytes())
        with self.assertRaisesRegex(ValueError, "retained reservations exceeded"):
            self.compare(results)


if __name__ == "__main__":
    unittest.main()
