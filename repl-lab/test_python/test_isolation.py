import importlib.util
import io
import json
import os
import subprocess
import sys
import threading
import time
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("isolation", Path(__file__).parents[1] / "scripts/isolation.py")
isolation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(isolation)


class IsolationConfigurationTests(unittest.TestCase):
    def test_negative_gate_rejects_startup_failure_and_requires_operation_error(self):
        original_popen = subprocess.Popen
        def run_fixture(program):
            def spawn(*args, **kwargs):
                return original_popen([sys.executable, "-c", program], stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
            return spawn
        with patch.object(isolation.subprocess, "Popen", side_effect=run_fixture("raise SystemExit(2)")):
            result = isolation.negative_case("process", "unexecuted")
            self.assertFalse(result["startup"])
            self.assertFalse(result["passed"])
        # Real pipes establish ordering: the second request is read only AFTER readiness.
        script = "import sys; sys.stdin.readline(); print('{:value 42}',flush=True); sys.stdin.readline(); print('{:error denied}',flush=True)"
        with patch.object(isolation.subprocess, "Popen", side_effect=run_fixture(script)):
            result = isolation.negative_case("process", "unexecuted")
            self.assertTrue(result["startup"])
            self.assertTrue(result["passed"])
        with patch.object(isolation.subprocess, "Popen", side_effect=run_fixture(script.replace("{:error denied}", "{:value 42}"))):
            self.assertFalse(isolation.negative_case("network", "unexecuted")["passed"])
        with patch.object(isolation.subprocess, "Popen", side_effect=run_fixture(script.replace("print('{:error denied}',flush=True)", "raise SystemExit(2)"))):
            self.assertFalse(isolation.negative_case("process", "unexecuted")["passed"])

    def test_opt_in_audit_preserves_failure_and_bounds_stderr(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"REPL_LAB_WORKER_AUDIT_DIR": directory}):
            audit = isolation.SessionAudit("repl-lab-" + "d" * 32)
            audit.event("supervisor-error", message="Worker wall-time limit")
            audit.stderr(b"x" * 20000)
            with patch.object(isolation, "docker", return_value=SimpleNamespace(returncode=0, stdout='{"OOMKilled":true,"ExitCode":137}')):
                audit.inspect(audit.data["container"])
            audit.save()
            data = json.loads(next(Path(directory).glob("*.json")).read_text())
            self.assertEqual(16384, len(data["stderr"]))
            self.assertTrue(data["state_before_cleanup"]["OOMKilled"])
            self.assertEqual("Worker wall-time limit", data["events"][0]["message"])
            self.assertFalse(data["cleanup_confirmed"])
            with self.assertRaises(FileExistsError):
                audit.save()

    def test_idle_worker_keeps_transport_open_between_model_requests(self):
        read_fd, write_fd = os.pipe()
        output, errors = io.BytesIO(), io.BytesIO()
        original_popen = subprocess.Popen
        def fixture_process(*args, **kwargs):
            return original_popen([sys.executable, "-c", "import sys\nfor line in sys.stdin: print('{:value 42}', flush=True)"],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
        def send_requests():
            try:
                os.write(write_fd, b"first fixture command\n")
                time.sleep(1)
                os.write(write_fd, b"second fixture command\n")
            finally:
                os.close(write_fd)
        sender = threading.Thread(target=send_requests)
        sender.start()
        with os.fdopen(read_fd, "rb", buffering=0) as source, tempfile.TemporaryDirectory() as directory:
            with patch.object(isolation, "QUARANTINE", Path(directory)), \
                 patch.dict(isolation.LIMITS, {"wall_seconds": 0.5, "session_seconds": 3}), \
                 patch.object(isolation, "preflight", return_value={"ready": True, "image": "sha256:" + "a" * 64}), \
                 patch.object(isolation, "verify_container"), \
                 patch.object(isolation, "docker", return_value=SimpleNamespace(returncode=0, stdout="[{}]")), \
                 patch.object(isolation.subprocess, "Popen", side_effect=fixture_process), \
                 patch.object(isolation.sys, "stdin", SimpleNamespace(buffer=source)), \
                 patch.object(isolation.sys, "stdout", SimpleNamespace(buffer=output)), \
                 patch.object(isolation.sys, "stderr", SimpleNamespace(buffer=errors)):
                isolation.session()
        sender.join(timeout=2)
        self.assertFalse(sender.is_alive())
        self.assertEqual(b"{:value 42}\n{:value 42}\n", output.getvalue())

    def test_task_deadline_can_shorten_but_not_extend_worker_lifetime(self):
        with patch.object(isolation.time, "time", return_value=10), patch.object(isolation.time, "monotonic", return_value=100):
            with patch.dict("os.environ", {"REPL_LAB_TASK_DEADLINE_MS": "10500"}):
                self.assertEqual(100.5, isolation.task_deadline())
            with patch.dict("os.environ", {"REPL_LAB_TASK_DEADLINE_MS": "999999999"}):
                self.assertEqual(220, isolation.task_deadline())
            with patch.dict("os.environ", {"REPL_LAB_TASK_DEADLINE_MS": "10000"}), patch.object(isolation, "preflight") as preflight:
                with self.assertRaisesRegex(RuntimeError, "Task wall-time limit"):
                    isolation.session()
                preflight.assert_not_called()

    def test_transport_drains_final_output_after_process_exit(self):
        # Exercise real host pipes with a fixed Python fixture, not SCI or Docker.
        # This fixture never evaluates the supplied wire contents.
        read_fd, write_fd = os.pipe()
        os.write(write_fd, b'{:source "fixture" :bindings {}}\n')
        os.close(write_fd)
        output, errors, calls = io.BytesIO(), io.BytesIO(), []
        original_popen = subprocess.Popen
        def fixture_process(*args, **kwargs):
            return original_popen([sys.executable, "-c", "import sys; sys.stdin.buffer.read(); print('{:value nil}'); print('{:value 42}')"],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
        def docker(*args, **kwargs):
            calls.append(args)
            return SimpleNamespace(returncode=0, stdout="[{}]" if args[0] == "inspect" else "")
        with os.fdopen(read_fd, "rb", buffering=0) as source, tempfile.TemporaryDirectory() as directory:
            with patch.object(isolation, "QUARANTINE", Path(directory)), \
                 patch.object(isolation, "preflight", return_value={"ready": True, "image": "sha256:" + "a" * 64}), \
                 patch.object(isolation, "verify_container"), patch.object(isolation, "docker", side_effect=docker), \
                 patch.object(isolation.subprocess, "Popen", side_effect=fixture_process), \
                 patch.object(isolation.sys, "stdin", SimpleNamespace(buffer=source)), \
                 patch.object(isolation.sys, "stdout", SimpleNamespace(buffer=output)), \
                 patch.object(isolation.sys, "stderr", SimpleNamespace(buffer=errors)):
                isolation.session()
        self.assertEqual(b"{:value nil}\n{:value 42}\n", output.getvalue())
        self.assertTrue(any(call[0] == "rm" for call in calls))

    def test_unconfirmed_cleanup_blocks_execution_until_removal(self):
        name = "repl-lab-" + "a" * 32
        with tempfile.TemporaryDirectory() as directory, patch.object(isolation, "QUARANTINE", Path(directory)):
            failed = SimpleNamespace(returncode=1, stdout="")
            with patch.object(isolation, "docker", return_value=failed):
                with self.assertRaisesRegex(RuntimeError, "quarantined"):
                    isolation.cleanup(name)
            marker = Path(directory) / (name + ".json")
            self.assertEqual(name, json.loads(marker.read_text())["container"])
            with patch.object(isolation, "docker") as docker:
                self.assertFalse(isolation.preflight()["ready"])
                docker.assert_not_called()
            with patch.object(isolation, "docker", return_value=SimpleNamespace(returncode=0, stdout=name)):
                isolation.cleanup(name)
            self.assertFalse(marker.exists())

    def test_cleanup_accepts_verified_absence_but_rejects_untrusted_target(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(isolation, "QUARANTINE", Path(directory)):
            with patch.object(isolation, "docker", side_effect=[SimpleNamespace(returncode=1, stdout=""),
                                                                 SimpleNamespace(returncode=0, stdout="")]) as docker:
                isolation.cleanup("repl-lab-" + "b" * 32)
                self.assertEqual(2, docker.call_count)
            with patch.object(isolation, "docker") as docker:
                with self.assertRaises(RuntimeError):
                    isolation.cleanup("some-other-container")
                docker.assert_not_called()

    def test_cleanup_timeout_is_quarantined(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(isolation, "QUARANTINE", Path(directory)):
            with patch.object(isolation, "docker", side_effect=isolation.subprocess.TimeoutExpired("docker", 5)):
                with self.assertRaises(RuntimeError):
                    isolation.cleanup("repl-lab-" + "c" * 32)
            self.assertEqual(1, len(list(Path(directory).glob("*.json"))))

    def test_removal_timeout_requires_independent_confirmed_absence(self):
        name = "repl-lab-" + "e" * 32
        with tempfile.TemporaryDirectory() as directory, patch.object(isolation, "QUARANTINE", Path(directory)):
            with patch.object(isolation, "docker", side_effect=[subprocess.TimeoutExpired("docker", 5),
                                                                  SimpleNamespace(returncode=0, stdout="")]):
                self.assertEqual("verified-absence", isolation.cleanup(name)["method"])
                self.assertEqual([], list(Path(directory).glob("*.json")))
            with patch.object(isolation, "docker", side_effect=[subprocess.TimeoutExpired("docker", 5),
                                                                  SimpleNamespace(returncode=0, stdout=name)]):
                with self.assertRaises(isolation.CleanupError): isolation.cleanup(name)
            self.assertEqual(1, len(list(Path(directory).glob("*.json"))))

    def test_no_implicit_image_or_download(self):
        with patch.dict("os.environ", {}, clear=True), patch.object(isolation, "docker") as docker:
            self.assertFalse(isolation.preflight()["ready"])
            docker.assert_not_called()

    def test_all_required_create_flags(self):
        args = isolation.create_args("sha256:" + "a" * 64, "fixture")
        for flag in ["--network", "--read-only", "--user", "--cap-drop", "--security-opt",
                     "--memory", "--memory-swap", "--cpus", "--pids-limit", "--tmpfs", "--log-driver"]:
            self.assertIn(flag, args)
        self.assertNotIn("--volume", args)
        self.assertNotIn("--privileged", args)
        self.assertNotIn("--env", args)

    def test_inspection_mismatch_fails_closed(self):
        host = {"NetworkMode": "none", "ReadonlyRootfs": True, "Memory": 256 * 1024**2,
                "MemorySwap": 256 * 1024**2, "NanoCpus": 1000000000, "PidsLimit": 32,
                "CapDrop": ["ALL"], "SecurityOpt": ["no-new-privileges:true"],
                "LogConfig": {"Type": "none"}, "Tmpfs": {"/tmp": "rw,noexec,nosuid,nodev,size=8m"}}
        meta = {"HostConfig": host, "Config": {"User": "65534:65534"}, "Mounts": []}
        isolation.verify_container(meta)
        for key, value in [("NetworkMode", "host"), ("Memory", 0), ("PidsLimit", 0),
                           ("Privileged", True), ("Binds", ["/host:/host"]), ("ReadonlyRootfs", False)]:
            changed = {**meta, "HostConfig": {**host, key: value}}
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                isolation.verify_container(changed)


if __name__ == "__main__":
    unittest.main()
