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
    return ["python3", "scripts/clj.py", "-m", "repl-lab.crash-probe", op, str(root), *extra]


def run(op, root):
    result = subprocess.run(command(op, root), cwd=ROOT, capture_output=True, text=True, timeout=25)
    if result.returncode:
        raise AssertionError(result.stderr)
    return result.stdout


class ProcessRecoveryTests(unittest.TestCase):
    def test_kill_before_and_after_promotion_commit(self):
        for point in ["after-artifact-write", "before-promotion-commit", "after-promotion-commit"]:
            with self.subTest(point=point), tempfile.TemporaryDirectory(prefix="repl-lab-crash-") as path:
                root = Path(path)
                run("prepare", root)
                proc = subprocess.Popen(command("promote", root, point), cwd=ROOT,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
                try:
                    deadline = time.monotonic() + 25
                    while not (root / "ready-to-kill").exists():
                        if proc.poll() is not None:
                            self.fail(proc.communicate()[1].decode())
                        if time.monotonic() > deadline:
                            self.fail("Crash point was not reached")
                        time.sleep(.05)
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.communicate(timeout=5)
                finally:
                    if proc.poll() is None:
                        os.killpg(proc.pid, signal.SIGKILL)
                        proc.communicate(timeout=5)
                recovered = json.loads(run("recover", root))
                committed = point == "after-promotion-commit"
                self.assertEqual(recovered["active"], recovered["candidate" if committed else "initial"])
                self.assertEqual(recovered["promotions"], int(committed))
                if committed:
                    run("rollback", root)
                    rolled = json.loads(run("recover", root))
                    self.assertEqual(rolled["active"], rolled["initial"])


if __name__ == "__main__":
    unittest.main()
