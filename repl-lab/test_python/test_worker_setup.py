"""Setup control-flow tests. Docker and SCI execution are mocked here."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/setup_worker.py"
SPEC = importlib.util.spec_from_file_location("setup_worker", SCRIPT)
setup_worker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup_worker)
IMAGE = "sha256:" + "1" * 64
BASE = "clojure@sha256:" + "2" * 64


class WorkerSetupTests(unittest.TestCase):
    def invoke(self, root, *, unavailable=False, fail_tests=False, invalid_proof=False):
        calls = []

        def fake_run(argv, cwd, *, capture=False, env=None):
            calls.append(argv)
            output = ""
            if argv[1] == "info":
                if unavailable:
                    raise subprocess.CalledProcessError(1, argv)
                output = "fixture-docker-version\n"
            elif "{{json .RepoDigests}}" in argv:
                output = json.dumps([BASE])
            elif "{{.Id}}" in argv:
                output = IMAGE + "\n"
            elif "scripts/isolation.py" in argv:
                self.assertEqual(env["REPL_LAB_WORKER_IMAGE"], IMAGE)
                if fail_tests:
                    raise subprocess.CalledProcessError(2, argv)
                proof = {"status": "TESTED", "image": IMAGE, "results": dict.fromkeys(setup_worker.CASES, True)}
                if invalid_proof:
                    proof["results"]["network"] = False
                (root / "var/isolation-proof.json").write_text(json.dumps(proof))
            return subprocess.CompletedProcess(argv, 0, stdout=output)

        with patch.object(setup_worker, "run", side_effect=fake_run), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            try:
                result = setup_worker.setup(root)
            except (RuntimeError, subprocess.CalledProcessError) as error:
                return calls, error
            return calls, result

    def test_denied_docker_stops_before_pull_or_build(self):
        with tempfile.TemporaryDirectory() as path:
            root = Path(path)
            calls, result = self.invoke(root, unavailable=True)
            self.assertIsInstance(result, subprocess.CalledProcessError)
            self.assertEqual(len(calls), 1)
            report = json.loads((root / "var/worker-setup.json").read_text())
            self.assertEqual((report["status"], report["stage"]), ("FAILED", "docker-access"))
            self.assertFalse((root / "var/worker.env").exists())

    def test_build_pins_digest_and_publishes_selection_only_after_proof(self):
        with tempfile.TemporaryDirectory() as path:
            root = Path(path)
            calls, report = self.invoke(root)
            build = next(call for call in calls if call[1] == "build")
            self.assertIn("BASE_IMAGE=" + BASE, build)
            self.assertEqual(report["status"], "TESTED")
            self.assertEqual(report["model_calls"], 0)
            self.assertEqual((root / "var/worker.env").read_text(), "export REPL_LAB_WORKER_IMAGE=" + IMAGE + "\n")

    def test_failed_isolation_archives_old_proof_and_does_not_select_worker(self):
        with tempfile.TemporaryDirectory() as path:
            root = Path(path)
            (root / "var").mkdir()
            (root / "var/isolation-proof.json").write_text('{"old": true}')
            _, result = self.invoke(root, fail_tests=True)
            self.assertIsInstance(result, subprocess.CalledProcessError)
            self.assertFalse((root / "var/isolation-proof.json").exists())
            archived = list((root / "var").glob("isolation-proof-before-setup-*.json"))
            self.assertEqual(len(archived), 1)
            self.assertEqual(json.loads(archived[0].read_text()), {"old": True})
            self.assertFalse((root / "var/worker.env").exists())

    def test_successful_process_without_complete_proof_does_not_pass(self):
        with tempfile.TemporaryDirectory() as path:
            root = Path(path)
            _, result = self.invoke(root, invalid_proof=True)
            self.assertIsInstance(result, RuntimeError)
            self.assertFalse((root / "var/worker.env").exists())
            self.assertEqual(json.loads((root / "var/worker-setup.json").read_text())["status"], "FAILED")


if __name__ == "__main__":
    unittest.main()
