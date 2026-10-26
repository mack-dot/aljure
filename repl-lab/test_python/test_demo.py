"""Schema tests use labeled synthetic data, never fabricated model measurements."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("demo", Path(__file__).resolve().parents[1] / "scripts/demo.py")
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


class DashboardSchemaTests(unittest.TestCase):
    def load(self, report, events=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "report.json").write_text(json.dumps(report))
            if events is not None:
                (root / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events))
            return demo.load_dashboard(root)

    def test_missing_costs_stay_unknown_and_failure_rows_remain(self):
        record = {"arm": "test-fixture", "metrics": {"status": "execution-failure"}}
        output = self.load({"provenance": "synthetic-fixture", "raw-cases": [record], "claims": {}})
        self.assertEqual("SYNTHETIC FIXTURE", output["report"]["label"])
        self.assertEqual([record], output["report"]["raw-cases"])
        self.assertIsNone(output["report"]["cost-view"]["acquisition"]["usd"])

    def test_nested_ledger_costs_and_rejection(self):
        output = self.load({"provenance": "synthetic-fixture", "raw-frozen": [], "raw-evolving": [],
                            "costs": {"evaluation": {"spent": {"calls": 2, "tokens": 7, "usd": 0},
                                                      "reserved-unknown": {"usd": 0.1}}}},
                           [{"type": "candidate-decision", "payload": {"status": "rejected", "evidence": {"approved": False}}}])
        self.assertEqual(0, output["report"]["cost-view"]["evaluation"]["usd"])
        self.assertEqual({"usd": 0.1}, output["report"]["cost-view"]["evaluation"]["reserved"])
        self.assertFalse(output["report"]["rejection"]["approved"])

    def test_unknown_provenance_is_refused(self):
        with self.assertRaises(ValueError):
            self.load({"provenance": "unlabeled"})
