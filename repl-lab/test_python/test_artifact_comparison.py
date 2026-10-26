import unittest

from benchmark.artifacts import verify_rows


class ArtifactScoringTests(unittest.TestCase):
    def test_stored_success_is_not_an_oracle(self):
        wrong = [{"input": 3, "output": 6, "expected": 6, "passed": True}]
        with self.assertRaises(ValueError):
            verify_rows(wrong, [3])
        correct = [{"input": 3, "output": 7, "expected": 7, "passed": True}]
        self.assertEqual(verify_rows(correct, [3]), [True])

    def test_missing_case_and_boolean_numeric_alias_are_rejected(self):
        with self.assertRaises(ValueError):
            verify_rows([], [3])
        with self.assertRaises(ValueError):
            verify_rows([{"input": 0, "output": True, "expected": 1, "passed": True}], [0])


if __name__ == "__main__":
    unittest.main()
