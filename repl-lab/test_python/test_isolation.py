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
    def test_preflight_identifies_and_records_each_failed_query(self):
        info = SimpleNamespace(returncode=0, stdout=json.dumps({"OSType": "linux", "MemoryLimit": True,
                               "SwapLimit": True, "CpuCfsQuota": True, "PidsLimit": True}))
        for stage, responses in [("docker-info", [subprocess.TimeoutExpired("docker", 5)]),
                                 ("image-inspect", [info, subprocess.TimeoutExpired("docker", 5)])]:
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as directory:
                with patch.object(isolation, "QUARANTINE", Path(directory) / "quarantine"), \
                     patch.dict(os.environ, {"REPL_LAB_WORKER_IMAGE": "sha256:" + "a" * 64,
                                             "REPL_LAB_WORKER_AUDIT_DIR": directory}), \
                     patch.object(isolation, "docker", side_effect=responses):
                    result = isolation.preflight()
                self.assertFalse(result["ready"])
                self.assertIn(stage, result["reason"])
                self.assertEqual(stage, result["queries"][-1]["stage"])
                self.assertEqual("TimeoutExpired", result["queries"][-1]["error_type"])
                self.assertGreaterEqual(result["queries"][-1]["elapsed_ms"], 0)
                self.assertEqual(result, json.loads(next((Path(directory) / "preflight").glob("*.json")).read_text()))

    def test_allocation_requires_specific_fatal_oom_and_worker_exit(self):
        original_popen = subprocess.Popen
        fatal = "Terminating due to java.lang.OutOfMemoryError: Java heap space"
        exited = "Isolation refused: Worker failed with exit 3"
        for output, error, code, expected in [(fatal, exited, 2, True),
                ("", "Isolation refused: Worker wall-time limit", 2, False),
                (fatal, "Isolation refused: Worker wall-time limit", 2, False),
                (fatal, exited, 3, False),  # Cleanup failure cannot pass.
                (fatal, exited, 0, False), (fatal, "", 2, False),
                ("OutOfMemoryError", exited, 2, False),
                ("{:error \"OutOfMemoryError\"}", exited, 2, False), ("", exited, 2, False)]:
            script = ("import sys; sys.stdin.readline(); print('{:value 42}',flush=True); "
                      "sys.stdin.readline(); print(" + repr(output) + "); print(" + repr(error) +
                      ",file=sys.stderr); raise SystemExit(" + str(code) + ")")
            def spawn(*args, **kwargs):
                return original_popen([sys.executable, "-c", script], stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
            with self.subTest(output=output, error=error, code=code), \
                 patch.object(isolation.subprocess, "Popen", side_effect=spawn):
                result = isolation.negative_case("allocation", "unexecuted")
                self.assertTrue(result["startup"])
                self.assertEqual(expected, result["passed"])
                if expected:
                    self.assertEqual("jvm-heap-exhausted", result["classification"])
                elif "wall-time" in error:
                    self.assertEqual("execution-deadline", result["classification"])

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

    def fixture_session(self, script, limits=None, language="clojure"):
        # Exercise real host pipes with a fixed Python fixture, not SCI or Docker.
        # This fixture never evaluates the supplied wire contents.
        read_fd, write_fd = os.pipe()
        os.write(write_fd, b'{:source "fixture" :bindings {}}\n')
        os.close(write_fd)
        output, errors, calls = io.BytesIO(), io.BytesIO(), []
        original_popen = subprocess.Popen
        def fixture_process(*args, **kwargs):
            return original_popen([sys.executable, "-c", script],
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
                 patch.object(isolation.sys, "stderr", SimpleNamespace(buffer=errors)), \
                 patch.dict(isolation.LIMITS, limits or {}):
                isolation.session(language)
        self.assertTrue(any(call[0] == "rm" for call in calls))
        return output.getvalue()

    # Each fixture answers the supervisor's readiness probe before the request.
    READY = "import sys, time; sys.stdin.buffer.readline(); "

    def test_transport_drains_final_output_after_process_exit(self):
        output = self.fixture_session(self.READY + "print('{:value 42}', flush=True); "
                                      "sys.stdin.buffer.read(); print('{:value nil}'); print('{:value 42}')")
        # The probe reply is never forwarded to the controller.
        self.assertEqual(b"{:value nil}\n{:value 42}\n", output)

    def test_slow_startup_does_not_consume_the_first_expression_limit(self):
        # Startup takes longer than an expression may run; the request still succeeds.
        output = self.fixture_session(self.READY + "time.sleep(0.6); print('{:value 42}', flush=True); "
                                      "sys.stdin.buffer.read(); print('{:value 7}')",
                                      {"wall_seconds": 0.3, "startup_seconds": 5})
        self.assertEqual(b"{:value 7}\n", output)

    def test_each_worker_language_gets_a_probe_in_its_own_wire_format(self):
        # The Python worker reads JSON; an EDN probe would fail its readiness.
        python = ("import sys, json; request = json.loads(sys.stdin.buffer.readline()); "
                  "assert request == {'source': '20 + 22', 'bindings': {}}; "
                  "print(json.dumps({'value': 42, 'printed': ''}, separators=(',', ':')), flush=True); "
                  "sys.stdin.buffer.read(); print('{\"value\":7,\"printed\":\"\"}')")
        self.assertEqual(b'{"value":7,"printed":""}\n', self.fixture_session(python, language="python"))
        with self.assertRaisesRegex(RuntimeError, "Worker readiness probe failed|Worker exited during startup"):
            self.fixture_session(python)

    def test_unready_worker_fails_at_the_startup_bound(self):
        for script in (self.READY + "time.sleep(5)", self.READY + "print('{:value 41}', flush=True); time.sleep(5)"):
            with self.assertRaisesRegex(RuntimeError, "Worker startup limit|Worker readiness probe failed"):
                self.fixture_session(script, {"startup_seconds": 0.5})

    def test_unconfirmed_cleanup_blocks_execution_until_removal(self):
        name = "repl-lab-" + "a" * 32
        with tempfile.TemporaryDirectory() as directory, patch.object(isolation, "QUARANTINE", Path(directory)):
            failed = SimpleNamespace(returncode=1, stdout="")
            with patch.object(isolation, "docker", return_value=failed), patch.object(isolation.time, "sleep"):
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

    def test_slow_daemon_answers_are_retried_before_quarantine(self):
        # A1 case 8: under load 21 the removal and its 5 s check timed out although
        # the container was gone, and the quarantine then failed cases 9 and 10.
        name = "repl-lab-" + "c" * 32
        slow = subprocess.TimeoutExpired("docker", 10)
        with tempfile.TemporaryDirectory() as directory, patch.object(isolation, "QUARANTINE", Path(directory)), \
             patch.object(isolation.time, "sleep"):
            with patch.object(isolation, "docker", side_effect=[slow, slow, SimpleNamespace(returncode=0, stdout="")]):
                evidence = isolation.cleanup(name)
            self.assertEqual(("verified-absence", 2), (evidence["method"], evidence["absence_checks"]))
            self.assertFalse((Path(directory) / (name + ".json")).exists())
            # Still listed on every check: removal is re-issued, then quarantine.
            listed = SimpleNamespace(returncode=0, stdout="abc123")
            with patch.object(isolation, "docker", side_effect=[slow] + [listed, listed] * isolation.CLEANUP_CHECKS) as docker:
                with self.assertRaisesRegex(RuntimeError, "quarantined"):
                    isolation.cleanup(name)
            self.assertEqual(1 + 2 * isolation.CLEANUP_CHECKS, docker.call_count)
            self.assertTrue((Path(directory) / (name + ".json")).exists())

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
            # Still listed: removal is retried on each check, then quarantine.
            listed = SimpleNamespace(returncode=0, stdout=name)
            with patch.object(isolation, "docker", side_effect=[subprocess.TimeoutExpired("docker", 5)] +
                              [listed, listed] * isolation.CLEANUP_CHECKS), patch.object(isolation.time, "sleep"):
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
