"""The Python isolation gate v2 (scripts/python_isolation.py) on fixture supervisors: no Docker,
no worker. The real gate runs against the pinned image with make python-isolation-test."""
import json
import subprocess
import sys
import unittest
from unittest.mock import patch

from scripts import isolation, python_isolation

READY = python_isolation.READY_REPLY


def supervisor(reply, stderr="", code=0):
    """A fake supervisor: answers the readiness probe, then the one negative request."""
    script = ("import sys; sys.stdin.readline(); print(" + repr(READY) + ", flush=True); sys.stdin.readline(); "
              "print(" + repr(reply) + "); print(" + repr(stderr) + ", file=sys.stderr); raise SystemExit(" + str(code) + ")")
    original = subprocess.Popen
    return lambda *a, **k: original([sys.executable, "-c", script], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, text=True, bufsize=1)


class NegativeCaseTests(unittest.TestCase):
    def outcome(self, name, reply, stderr="", code=0):
        with patch.object(python_isolation.subprocess, "Popen", side_effect=supervisor(reply, stderr, code)):
            return python_isolation.negative_case(name, "unexecuted")

    def test_readiness_is_confirmed_in_the_same_worker_before_the_negative_request(self):
        original = subprocess.Popen
        script = "import sys; sys.stdin.readline(); print('{\"value\":41,\"printed\":\"\"}', flush=True); sys.stdin.readline()"
        with patch.object(python_isolation.subprocess, "Popen",
                          side_effect=lambda *a, **k: original([sys.executable, "-c", script], stdin=subprocess.PIPE,
                                                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)):
            result = python_isolation.negative_case("read", "unexecuted")
        self.assertEqual((False, False, "readiness-failure"), (result["startup"], result["passed"], result["classification"]))

    def test_each_case_needs_its_own_evidence(self):
        error = json.dumps({"error": "PermissionError: denied"})
        self.assertTrue(self.outcome("read", error)["passed"])
        self.assertFalse(self.outcome("read", json.dumps({"value": "root:x", "printed": ""}))["passed"])
        self.assertTrue(self.outcome("loop", "", "Isolation refused: Worker wall-time limit", 2)["passed"])
        self.assertFalse(self.outcome("loop", error)["passed"])
        # A deadline is not memory-limit evidence; MemoryError or a container exit is.
        self.assertFalse(self.outcome("allocation", "", "Isolation refused: Worker wall-time limit", 2)["passed"])
        self.assertEqual("memory-error", self.outcome("allocation", json.dumps({"error": "MemoryError: "}))["classification"])
        self.assertEqual("container-memory-limit", self.outcome("allocation", "", "Isolation refused: Worker failed with exit 137", 2)["classification"])
        self.assertTrue(self.outcome("oversized-result", json.dumps({"error": "ValueError: Result limit"}))["passed"])
        self.assertFalse(self.outcome("oversized-result", "", "Isolation refused: Worker output limit", 2)["passed"])
        self.assertEqual("missing-restriction-evidence", self.outcome("network", json.dumps({"value": 1, "printed": ""}))["classification"])


class BoundaryTests(unittest.TestCase):
    def test_reply_overhead_matches_the_worker_wire_format(self):
        wire = json.dumps({"value": "x" * 10, "printed": ""}, separators=(",", ":"))
        self.assertEqual(10 + python_isolation.REPLY_OVERHEAD, len(wire.encode()))

    def test_boundary_needs_an_exact_line_and_a_surviving_worker(self):
        bound = isolation.LIMITS["output_bytes"]
        exact = json.dumps({"value": "x" * (bound - 1 - python_isolation.REPLY_OVERHEAD), "printed": ""}, separators=(",", ":"))
        refused = json.dumps({"error": "ValueError: Result limit"}) + "\n" + READY
        runs = iter([subprocess.CompletedProcess([], 0, exact + "\n", ""), subprocess.CompletedProcess([], 0, refused + "\n", "")])
        with patch.object(python_isolation, "probe", side_effect=lambda sources: next(runs)):
            self.assertEqual({"at-bound": True, "over-bound": True}, python_isolation.boundary_tests())
        runs = iter([subprocess.CompletedProcess([], 0, exact[:-1] + "\n", ""),
                     subprocess.CompletedProcess([], 2, "", "Isolation refused: Worker output limit")])
        with patch.object(python_isolation, "probe", side_effect=lambda sources: next(runs)):
            self.assertEqual({"at-bound": False, "over-bound": False}, python_isolation.boundary_tests())


if __name__ == "__main__":
    unittest.main()
