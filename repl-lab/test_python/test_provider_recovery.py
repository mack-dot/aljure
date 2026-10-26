"""Actual controller SIGKILL with a fixed, non-network provider transport."""
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


def command(op, root, *extra):
    return ["python3", "scripts/clj.py", "-m", "repl-lab.provider-crash-probe", op, str(root), *extra]


class ProviderProcessRecoveryTests(unittest.TestCase):
    def test_provider_crash_boundaries_preserve_costs_without_retry(self):
        points = ["after-reservation", "request-dispatched", "before-response-commit", "after-response-commit"]
        for caller in ["root", "child"]:
            for point in points:
                with self.subTest(caller=caller, point=point), tempfile.TemporaryDirectory(prefix="repl-lab-provider-crash-") as path:
                    root = Path(path)
                    proc = subprocess.Popen(command("invoke", root, point, caller), cwd=ROOT,
                                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
                    try:
                        deadline = time.monotonic() + 30
                        while not (root / "ready-to-kill").exists():
                            if proc.poll() is not None:
                                self.fail(proc.communicate()[1].decode())
                            if time.monotonic() > deadline:
                                self.fail("Provider crash boundary was not reached")
                            time.sleep(.05)
                        self.assertEqual((root / "ready-to-kill").read_text(), point)
                        os.killpg(proc.pid, signal.SIGKILL)
                        proc.communicate(timeout=5)
                        self.assertEqual(proc.returncode, -signal.SIGKILL)
                    finally:
                        if proc.poll() is None:
                            os.killpg(proc.pid, signal.SIGKILL)
                            proc.communicate(timeout=5)

                    transport = root / "transport.jsonl"
                    dispatched = transport.read_text() if transport.exists() else ""
                    events = [json.loads(line)["path"] for line in dispatched.splitlines()]
                    self.assertEqual(events, [] if point == "after-reservation" else ["messages/count_tokens", "messages"])

                    recovered = subprocess.run(command("recover", root), cwd=ROOT, capture_output=True, text=True, timeout=30)
                    self.assertEqual(recovered.returncode, 0, recovered.stderr)
                    result = json.loads(recovered.stdout)
                    self.assertEqual(result["provenance"], "synthetic-fixture")
                    self.assertTrue(result["idempotent"])
                    self.assertEqual(result["checkpoint-status"], "checkpointed")
                    self.assertEqual(result["episode-status"], "execution-failure")
                    self.assertEqual(result["replayed"], 1)
                    self.assertEqual(transport.read_text() if transport.exists() else "", dispatched)

                    committed = point == "after-response-commit"
                    before, after = result["before"], result["after"]
                    self.assertEqual(len(after["requests"]), 1)
                    self.assertEqual(after["spent"], before["spent"])
                    self.assertEqual(after["reserved"], before["reserved"])
                    self.assertEqual(after["spent"]["calls"], int(committed))
                    self.assertEqual(after["reserved"]["calls"], int(not committed))
                    self.assertEqual(after["unknown-events"], int(not committed))
                    request = next(iter(after["requests"].values()))
                    self.assertEqual(request["session"], caller)
                    self.assertEqual(request["status"], "complete" if committed else "unknown")
                    self.assertEqual(after["sessions"]["root"]["status"], "cancelled")
                    if caller == "child":
                        self.assertEqual(after["sessions"]["child"]["parent"], "root")
                        self.assertEqual(after["sessions"]["child"]["status"], "cancelled")
                    if committed:
                        self.assertEqual(after["spent"]["tokens"], 15)
                        self.assertAlmostEqual(after["spent"]["usd"], .000018)
                        self.assertEqual(after["reserved"], {"calls": 0, "tokens": 0, "usd": 0.0})
                        self.assertEqual(result["playback"], {"entries": 1})
                    else:
                        self.assertEqual(after["spent"]["tokens"], 0)
                        self.assertGreater(after["reserved"]["tokens"], 0)
                        self.assertGreater(after["reserved"]["usd"], 0)
                        self.assertNotIn("response", request)
                        self.assertEqual(result["playback"], {"unknown-outcome": True})


if __name__ == "__main__":
    unittest.main()
