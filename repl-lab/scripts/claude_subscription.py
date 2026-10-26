#!/usr/bin/env python3
"""Bounded Claude Code subscription transport. Model text is never executed here.

The controller owns the shared reservation before invoking this process. This
transport rechecks the SCI gate and subscription auth, disables native tools,
preserves the CLI stream, and never retries an inference invocation.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import selectors
import shutil
import signal
import subprocess
import sys
import tempfile
import time

try:
    from . import isolation
except ImportError:
    import isolation

ROOT = Path(__file__).resolve().parents[1]
CLI_VERSION = "2.1.310 (Claude Code)"
MODEL = "claude-sonnet-5-5"
MAX_OUTPUT = 2048
MAX_INPUT_BYTES = 65536
MAX_STREAM_BYTES = 1048576
SYSTEM = ("You are the model for an external Clojure agent controller. The user input is a JSON "
          "conversation in chronological order. Follow its instructions and return only the next "
          "assistant response, as one EDN map. No markdown fences. Tools named in that conversation "
          "are controller protocol operations, not Claude Code tools. Emit their EDN; do not execute code.")
CASES = {"loop", "allocation", "oversized-result", "read", "write", "process", "network", "evaluator", "reader-eval"}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def safe_env(source=None):
    source = os.environ if source is None else source
    # Keep the operator's home and normal OAuth store. Do not copy or extract tokens.
    # No inherited API keys, cloud credentials, routing, debug hooks, or node preload.
    allowed = {"HOME", "USER", "LOGNAME", "SHELL", "PATH", "TMPDIR", "TMP", "TEMP",
               "LANG", "LC_ALL", "LC_CTYPE", "CLAUDE_CONFIG_DIR", "SSL_CERT_FILE", "SSL_CERT_DIR"}
    env = {key: value for key, value in source.items() if key in allowed}
    env.update({"CLAUDE_CODE_MAX_OUTPUT_TOKENS": str(MAX_OUTPUT), "CLAUDE_CODE_MAX_RETRIES": "0",
                "CLAUDE_CODE_RETRY_WATCHDOG": "0", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
                "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1", "DISABLE_AUTOUPDATER": "1",
                "DISABLE_PROMPT_CACHING": "1", "API_TIMEOUT_MS": "45000"})
    return env


def fixed_flags():
    return ["--safe-mode", "--restricted", "--setting-sources", "",
            "--settings", '{"disableAllHooks":true,"autoMemoryEnabled":false,"alwaysThinkingEnabled":false}',
            "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
            "--tools", "", "--disable-slash-commands", "--no-chrome",
            "--permission-mode", "dontAsk", "--permission-prompts", "none"]


def doctor():
    binary = shutil.which("claude")
    if not binary:
        return {"ready": False, "reason": "Claude Code is not installed", "model_calls": 0}
    try:
        env = safe_env()
        with tempfile.TemporaryDirectory(prefix="aljure-cli-check-") as cwd:
            version = subprocess.run([binary, "--version"], cwd=cwd, env=env,
                                     capture_output=True, text=True, timeout=10)
            auth = subprocess.run([binary, *fixed_flags(), "auth", "status", "--json"],
                                  cwd=cwd, env=env, capture_output=True, text=True, timeout=10)
        status = json.loads(auth.stdout)
        public = {key: status.get(key) for key in ("loggedIn", "authMethod", "apiProvider", "subscriptionType")}
        valid_auth = (auth.returncode == 0 and public["loggedIn"] is True and
                      public["authMethod"] == "claude.ai" and public["apiProvider"] == "firstParty" and
                      public["subscriptionType"] in ("pro", "max", "team", "enterprise"))
        valid_version = version.returncode == 0 and version.stdout.strip() == CLI_VERSION
        return {"ready": valid_auth and valid_version, "model_calls": 0, "auth": public,
                "cli_version": version.stdout.strip(), "cli_path": str(Path(binary).resolve()),
                "cli_sha256": hashlib.sha256(Path(binary).read_bytes()).hexdigest(),
                "reason": (None if valid_auth and valid_version else
                           "Pinned Claude Code version differs" if not valid_version else
                           "Subscription login is not visible to this process; use the logged-in host Terminal")}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {"ready": False, "reason": "Claude Code authentication preflight failed", "model_calls": 0}


def require_isolation():
    check = isolation.preflight()
    require(check.get("ready"), "Actual Docker isolation is unavailable in this process")
    proof = json.loads((ROOT / "var/isolation-proof.json").read_text())
    require(proof.get("status") == "TESTED" and proof.get("image") == check.get("image") and
            set(proof.get("results", {})) == CASES and all(v is True for v in proof["results"].values()),
            "SCI isolation proof is missing, incomplete, or refers to another image")


def command(binary, budget):
    return [binary, *fixed_flags(), "--print", "--output-format", "stream-json", "--verbose",
            "--include-partial-messages", "--no-session-persistence", "--max-turns", "1",
            "--prompt-suggestions", "false", "--model", MODEL, "--system-prompt", SYSTEM,
            "--max-budget-usd", str(budget)]


def validate_event(event):
    if event.get("type") == "system" and event.get("subtype") == "init":
        require(event.get("tools") == [] and event.get("mcp_servers") == [], "Native tool or MCP access is enabled")
        require(event.get("model") == MODEL, "CLI selected a different model")
    if event.get("type") == "assistant":
        require(event.get("parent_tool_use_id") is None, "Unexpected Claude Code subagent")
        require(all(block.get("type") in ("text", "thinking", "redacted_thinking")
                    for block in event.get("message", {}).get("content", [])), "Unexpected native tool request")
    if event.get("type") == "stream_event":
        require(event.get("parent_tool_use_id") is None, "Unexpected Claude Code subagent stream")
        block = event.get("event", {}).get("content_block", {})
        require(block.get("type") not in ("tool_use", "server_tool_use", "mcp_tool_use"), "Unexpected streamed native tool request")


def normalize(events):
    for event in events:
        validate_event(event)
    init = [e for e in events if e.get("type") == "system" and e.get("subtype") == "init"]
    assistants = [e["message"] for e in events if e.get("type") == "assistant"]
    results = [e for e in events if e.get("type") == "result"]
    require(len(init) == len(results) == 1 and assistants and len({a.get("id") for a in assistants}) == 1,
            "Expected exactly one model response and terminal receipt")
    message, result = assistants[0], results[0]
    require(all(a.get("model") == MODEL for a in assistants) and set(result.get("modelUsage", {})) == {MODEL},
            "Pinned model usage is missing or includes another model")
    require(isinstance(message.get("id"), str) and bool(message["id"]), "Missing provider message ID")
    usage = result.get("usage", {})
    per_model = result["modelUsage"][MODEL]
    fields = {"input_tokens": "inputTokens", "output_tokens": "outputTokens",
              "cache_read_input_tokens": "cacheReadInputTokens", "cache_creation_input_tokens": "cacheCreationInputTokens"}
    for field, other in fields.items():
        value = usage.get(field)
        require(type(value) is int and value >= 0 and per_model.get(other) == value,
                "Usage totals do not match the single provider receipt")
        # Assistant events arrive per completed content block. Their output token
        # count is a placeholder. Count their shared ID once; use terminal output.
        if field != "output_tokens":
            require(all(a.get("usage", {}).get(field, 0) == value for a in assistants),
                    "Input usage differs across the single provider response")
    require(result.get("num_turns") == 1, "Unexpected additional Claude Code turns")
    blocks = [block.get("text", "") for a in assistants for block in a.get("content", []) if block.get("type") == "text"]
    text = result.get("result")
    require(isinstance(text, str) and text in ("".join(blocks), "\n".join(blocks)), "Final text differs from the model receipt")
    wire = [e["event"] for e in events if e.get("type") == "stream_event"]
    starts = [e for e in wire if e.get("type") == "message_start"]
    deltas = [e for e in wire if e.get("type") == "message_delta"]
    require(len(starts) == 1 and starts[0].get("message", {}).get("id") == message["id"] and
            sum(e.get("type") == "message_stop" for e in wire) == 1 and deltas,
            "Missing complete provider stream boundaries")
    require(deltas[-1].get("usage", {}).get("output_tokens") == usage["output_tokens"],
            "Stream output usage differs from the terminal receipt")
    cost = result.get("total_cost_usd")
    require(type(cost) in (int, float) and math.isfinite(cost) and cost >= 0, "CLI cost estimate is missing")
    # Keep valid usage even when the response failed a completion/output/cache check.
    valid = (result.get("subtype") == "success" and result.get("is_error") is False and
             result.get("permission_denials", []) == [] and deltas[-1].get("delta", {}).get("stop_reason") == "end_turn" and
             usage["output_tokens"] <= MAX_OUTPUT and usage["cache_read_input_tokens"] == 0 and
             usage["cache_creation_input_tokens"] == 0)
    return {"model": MODEL, "provider_id": message["id"], "usage": usage, "text": text,
            "accepted": valid, "cli_reported_usd": cost, "transport_session_id": result.get("session_id"),
            "billing_basis": "subscription; actual charge unknown; standard-rate equivalent recorded separately"}


def invoke(spec):
    require(spec.get("model") == MODEL and spec.get("max_output_tokens") == MAX_OUTPUT, "Unapproved model or output cap")
    require(type(spec.get("reserved_usd")) in (int, float) and 0 < spec["reserved_usd"] <= 1,
            "Missing bounded controller reservation")
    trace = Path(spec["trace_dir"]).resolve()
    require(trace.is_relative_to((ROOT / "var/runs").resolve()), "Trace directory must be inside var/runs")
    prompt = json.dumps({"messages": spec["messages"]}, ensure_ascii=False, separators=(",", ":")).encode()
    require(len(prompt) <= MAX_INPUT_BYTES, "CLI prompt exceeds the transport input limit")
    require_isolation()
    check = doctor()
    require(check["ready"], check["reason"])
    require(check["cli_sha256"] == spec["cli_sha256"], "CLI binary changed after smoke preflight")
    remaining = min(60, spec["deadline_ms"] / 1000 - time.time())
    require(remaining > 0, "Task wall budget exhausted")
    trace.mkdir(parents=True, exist_ok=False)
    (trace / "request.json").write_bytes(prompt)
    (trace / "transport.json").write_text(json.dumps({"cli_sha256": check["cli_sha256"], "cli_version": CLI_VERSION,
                                                     "model": MODEL, "system_prompt": SYSTEM,
                                                     "reservation_usd": spec["reserved_usd"],
                                                     "budget_basis": "standard-rate-equivalent"}))
    events, process, failure = [], None, None
    try:
        with tempfile.TemporaryDirectory(prefix="aljure-model-") as cwd, \
                (trace / "request.json").open("rb") as request, \
                (trace / "stdout.jsonl").open("wb") as out, (trace / "stderr.log").open("wb") as err:
            process = subprocess.Popen(command(check["cli_path"], spec["reserved_usd"]), cwd=cwd, env=safe_env(),
                                       stdin=request, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
            deadline, used, pending = time.monotonic() + remaining, 0, b""
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ, out)
                selector.register(process.stderr, selectors.EVENT_READ, err)
                while selector.get_map():
                    require(time.monotonic() < deadline, "Claude Code timeout; outcome may be unknown")
                    for key, _ in selector.select(min(0.1, max(0, deadline - time.monotonic()))):
                        chunk = os.read(key.fileobj.fileno(), 65536)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            continue
                        used += len(chunk)
                        require(used <= MAX_STREAM_BYTES, "Claude Code output limit; outcome may be unknown")
                        key.data.write(chunk)
                        key.data.flush()
                        if key.data is out:
                            pending += chunk
                            while b"\n" in pending:
                                line, pending = pending.split(b"\n", 1)
                                if line.strip():
                                    event = json.loads(line)
                                    events.append(event)
                                    validate_event(event)
                require(not pending.strip(), "Incomplete CLI event stream")
            code = process.wait(timeout=max(0.01, deadline - time.monotonic()))
            response = normalize(events)
            response["accepted"] = response["accepted"] and code == 0
            return {"ok": True, "response": response, "trace_dir": str(trace)}
    except Exception:
        failure = "Transport failed; inspect preserved stream and retain the controller reservation"
        raise
    finally:
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)
            process.stdout.close()
            process.stderr.close()
        (trace / "completion.json").write_text(json.dumps({"transport_complete": failure is None,
                                                          "error": failure, "events_saved": len(events)}))


def main():
    if sys.argv[1:] == ["doctor"]:
        result = doctor()
    elif sys.argv[1:] == ["invoke"]:
        try:
            wire = sys.stdin.buffer.read(262145)
            require(len(wire) <= 262144, "Transport request too large")
            result = invoke(json.loads(wire))
        except Exception as error:
            # Exception bodies may come from the CLI. Preserve streams locally; do not echo them.
            result = {"ok": False, "error": "Subscription transport stopped", "error_type": type(error).__name__}
    else:
        raise SystemExit("Usage: claude_subscription.py doctor|invoke")
    print(json.dumps(result, allow_nan=False))
    return 0 if result.get("ok", result.get("ready", False)) else 1


if __name__ == "__main__":
    sys.exit(main())
