import random
import unittest
import json
from pathlib import Path
import tempfile

from benchmark.language import evaluate_case, compare_languages
from scripts import isolation, python_isolation
from unittest.mock import patch


class LanguageEvaluatorTests(unittest.TestCase):
    def test_failed_pilot_gate_cannot_be_reported_as_passing(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "report.json").write_text(json.dumps({"evidence": "FIXTURE", "action": "pilot",
                "model-calls": 0, "learning-claim": False, "passed": False, "rows": [{"score": 1}]}))
            with self.assertRaisesRegex(ValueError, "Pilot gate failed"):
                compare_languages(directory)

    def test_wrong_semantics_and_unchanged_program_do_not_pass(self):
        nodes = [{"op": "add", "value": 3}, {"op": "add", "value": 5}]
        self.assertTrue(evaluate_case("transform", nodes, [{"op": "add", "value": 8}]))
        for wrong in (nodes, [], [{"op": "mul", "value": 8}], [{"op": "add", "value": 9}],
                      [{"op": "add", "value": 8, "unknown": True}]):
            self.assertFalse(evaluate_case("transform", nodes, wrong))

    def test_affine_oracle_on_generated_compositions(self):
        rng = random.Random(9921)
        for _ in range(100):
            a, b, c = (rng.randint(-20, 20) for _ in range(3))
            original = [{"op": "add", "value": a}, {"op": "add", "value": b}, {"op": "mul", "value": c}]
            transformed = ([] if a+b == 0 else [{"op": "add", "value": a+b}]) + ([] if c == 1 else [{"op": "mul", "value": c}])
            self.assertTrue(evaluate_case("transform", original, transformed))

    def test_python_gate_uses_its_own_image_identity(self):
        with patch.object(isolation, "preflight", return_value={"ready": False}) as preflight:
            self.assertFalse(python_isolation.doctor()["ready"])
            preflight.assert_called_once_with("REPL_LAB_PYTHON_IMAGE", "repl-lab.python-worker")


if __name__ == "__main__":
    unittest.main()
