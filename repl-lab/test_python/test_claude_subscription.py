"""Offline transport tests. The child executable emits fixtures and makes no API calls."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from scripts import claude_subscription as cli


def events():
    usage = {"input_tokens": 100, "output_tokens": 20, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
    message = {"id": "fixture-message", "model": cli.MODEL, "usage": {**usage, "output_tokens": 1},
               "content": [{"type": "text", "text": "{:op :done :summary 42}"}], "stop_reason": None}
    return [
        {"type": "system", "subtype": "init", "model": cli.MODEL, "tools": [], "mcp_servers": []},
        {"type": "stream_event", "event": {"type": "message_start", "message": {"id": message["id"]}}},
        {"type": "assistant", "message": message},
        {"type": "stream_event", "event": {"type": "message_delta", "delta": {"stop_reason": "end_turn"},
                                           "usage": {"output_tokens": 20}}},
        {"type": "stream_event", "event": {"type": "message_stop"}},
        {"type": "result", "subtype": "success", "is_error": False, "num_turns": 1,
         "result": "{:op :done :summary 42}", "total_cost_usd": 0.0004, "usage": usage,
         "session_id": "fixture-session", "permission_denials": [],
         "modelUsage": {cli.MODEL: {"inputTokens": 100, "outputTokens": 20,
                                   "cacheReadInputTokens": 0, "cacheCreationInputTokens": 0}}}]


class SubscriptionTransportTests(unittest.TestCase):
    def test_environment_and_flags_keep_native_tools_and_api_credentials_out(self):
        env = cli.safe_env({"HOME": "/operator-home", "PATH": "/bin", "ANTHROPIC_API_KEY": "fixture-secret",
                            "ANTHROPIC_AUTH_TOKEN": "fixture-token", "ANTHROPIC_BASE_URL": "fixture-url",
                            "CLAUDE_CODE_OAUTH_TOKEN": "fixture-token", "NODE_OPTIONS": "fixture-inject",
                            "AWS_SECRET_ACCESS_KEY": "fixture-secret", "CLAUDE_CODE_USE_BEDROCK": "1"})
        self.assertEqual(env["HOME"], "/operator-home")
        self.assertFalse(any(k in env for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
                                                "CLAUDE_CODE_OAUTH_TOKEN", "AWS_SECRET_ACCESS_KEY", "NODE_OPTIONS")))
        self.assertEqual(env["CLAUDE_CODE_MAX_RETRIES"], "0")
        self.assertEqual(env["DISABLE_PROMPT_CACHING"], "1")
        argv = cli.command("claude", 0.1)
        self.assertIn("--safe-mode", argv)
        self.assertIn("--restricted", argv)
        self.assertNotIn("--bare", argv)  # Bare disables subscription authentication.
        self.assertNotIn("--dangerously-skip-permissions", argv)
        self.assertEqual(argv[argv.index("--tools") + 1], "")
        self.assertEqual(argv[argv.index("--max-turns") + 1], "1")
        self.assertIn("--strict-mcp-config", argv)

    def test_output_placeholder_and_repeated_content_blocks_are_not_double_counted(self):
        stream = events()
        thought = copy.deepcopy(stream[2])
        thought["message"]["content"] = [{"type": "thinking", "thinking": "Fixture reasoning"}]
        stream.insert(2, thought)
        response = cli.normalize(stream)
        self.assertTrue(response["accepted"])
        self.assertEqual(response["usage"]["input_tokens"], 100)
        self.assertEqual(response["usage"]["output_tokens"], 20)
        self.assertEqual(response["text"], "{:op :done :summary 42}")

    def test_native_tools_extra_model_calls_and_ambiguous_usage_are_rejected(self):
        changes = []
        stream = events(); stream[0]["tools"] = ["Bash"]; changes.append(stream)
        stream = events(); stream[0]["mcp_servers"] = [{"name": "fixture"}]; changes.append(stream)
        stream = events(); stream[2]["message"]["model"] = "other"; changes.append(stream)
        stream = events(); stream[-1]["modelUsage"]["other"] = {}; changes.append(stream)
        stream = events(); stream[-1]["usage"]["input_tokens"] = 200; changes.append(stream)
        stream = events(); stream[-1]["num_turns"] = 2; changes.append(stream)
        stream = events(); stream[3]["event"]["usage"]["output_tokens"] = 21; changes.append(stream)
        stream = events(); stream.insert(3, {"type": "assistant", "message": {**stream[2]["message"], "id": "extra"}}); changes.append(stream)
        stream = events(); stream.insert(3, {"type": "stream_event", "event": {"content_block": {"type": "tool_use"}}}); changes.append(stream)
        for i, stream in enumerate(changes):
            with self.subTest(case=i), self.assertRaises(RuntimeError):
                cli.normalize(stream)

    def test_failed_completion_retains_known_usage(self):
        stream = events()
        stream[-1]["is_error"] = True
        response = cli.normalize(stream)
        self.assertFalse(response["accepted"])
        self.assertEqual(response["usage"]["output_tokens"], 20)

    def test_isolation_rejects_incomplete_and_different_image_proofs(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(cli, "ROOT", Path(directory)), \
                patch.object(cli.isolation, "preflight", return_value={"ready": True, "image": "fixture-image"}):
            path = Path(directory) / "var/isolation-proof.json"
            path.parent.mkdir()
            valid = {"status": "TESTED", "image": "fixture-image", "results": dict.fromkeys(cli.CASES, True)}
            for bad in ({**valid, "image": "different"}, {**valid, "results": {"loop": True}},
                        {**valid, "results": {**valid["results"], "network": False}}):
                path.write_text(json.dumps(bad))
                with self.assertRaises(RuntimeError): cli.require_isolation()
            path.write_text(json.dumps(valid))
            cli.require_isolation()

    def test_doctor_requires_subscription_and_never_prints_account_details(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "fixture-cli"
            binary.write_text("fixture; not an executable")
            for auth_method, ready in (("api_key", False), ("claude.ai", True)):
                auth = {"loggedIn": True, "authMethod": auth_method, "subscriptionType": "max",
                        "apiProvider": "firstParty", "email": "fixture-private", "apiKey": "fixture-secret"}
                outputs = [subprocess.CompletedProcess([], 0, cli.CLI_VERSION, ""),
                           subprocess.CompletedProcess([], 0, json.dumps(auth), "")]
                with patch.object(cli.shutil, "which", return_value=str(binary)), patch.object(cli.subprocess, "run", side_effect=outputs):
                    result = cli.doctor()
                    self.assertEqual(result["ready"], ready)
                    self.assertEqual(result["model_calls"], 0)
                    self.assertNotIn("fixture-private", json.dumps(result))
                    self.assertNotIn("fixture-secret", json.dumps(result))

    def run_child(self, directory, *, tail="", deadline=5, area="var/runs"):
        root = Path(directory)
        binary = root / "fixture-cli"
        binary.write_text(f"#!{sys.executable}\nimport json,sys,time\nsys.stdin.read()\n" +
                          "\n".join(f"print({json.dumps(json.dumps(e))}, flush=True)" for e in events()) + "\n" + tail)
        binary.chmod(0o700)
        trace = root / area / "smoke-test/transport/request"
        spec = {"model": cli.MODEL, "max_output_tokens": cli.MAX_OUTPUT, "reserved_usd": 0.1,
                "messages": [{"role": "user", "content": "fixture"}], "trace_dir": str(trace),
                "cli_sha256": "fixture-sha", "deadline_ms": (time.time() + deadline) * 1000}
        check = {"ready": True, "reason": None, "cli_path": str(binary), "cli_sha256": "fixture-sha"}
        with patch.object(cli, "ROOT", root), patch.object(cli, "require_isolation"), patch.object(cli, "doctor", return_value=check):
            return cli.invoke(spec)

    def test_actual_pipe_transport_preserves_stream_and_uses_empty_workdir(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_child(directory)
            self.assertTrue(result["response"]["accepted"])
            trace = Path(result["trace_dir"])
            self.assertEqual(len((trace / "stdout.jsonl").read_text().splitlines()), len(events()))
            self.assertTrue(json.loads((trace / "completion.json").read_text())["transport_complete"])
            self.assertTrue((trace / "request.json").is_file())

    def test_actual_pipe_timeout_preserves_partial_evidence_and_kills_child(self):
        with tempfile.TemporaryDirectory() as directory:
            start = time.monotonic()
            with self.assertRaisesRegex(RuntimeError, "timeout"):
                self.run_child(directory, tail="time.sleep(30)", deadline=0.2)
            self.assertLess(time.monotonic() - start, 3)
            trace = Path(directory) / "var/runs/smoke-test/transport/request"
            self.assertFalse(json.loads((trace / "completion.json").read_text())["transport_complete"])
            self.assertTrue((trace / "stdout.jsonl").exists())

    def test_learning_evaluation_trace_root_and_traversal_check(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_child(directory, area='var/evaluations')
            self.assertTrue(result['response']['accepted'])
            self.assertIn('/var/evaluations/', result['trace_dir'])
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, 'Trace directory'):
                self.run_child(directory, area='var/evaluations/../../outside')

    def test_failed_isolation_never_launches_claude(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(cli, "ROOT", Path(directory)), \
                patch.object(cli, "require_isolation", side_effect=RuntimeError("fixture gate closed")), \
                patch.object(cli, "doctor") as doctor, patch.object(cli.subprocess, "Popen") as start:
            spec = {"model": cli.MODEL, "max_output_tokens": cli.MAX_OUTPUT, "reserved_usd": 0.1,
                    "messages": [], "trace_dir": str(Path(directory) / "var/runs/fixture")}
            with self.assertRaisesRegex(RuntimeError, "gate closed"):
                cli.invoke(spec)
            doctor.assert_not_called()
            start.assert_not_called()


if __name__ == "__main__":
    unittest.main()
