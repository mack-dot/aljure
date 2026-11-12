#!/usr/bin/env python3
"""Python worker gate using the same verified Docker supervisor as SCI.

Gate v2 (parity with scripts/isolation.py negative_tests): readiness confirmed in the
SAME worker before each negative request, the exact output boundary, the supervisor's
and this gate's hashes, and a positive control. Model calls: 0."""
import hashlib
import json
from pathlib import Path
import selectors
import subprocess
import sys
import time

try:
    from . import isolation
except ImportError:
    import isolation

ROOT = Path(__file__).resolve().parents[1]
NEGATIVE = {
    "loop": "while True: pass",
    "allocation": "bytearray(1024 * 1024 * 1024)",
    "oversized-result": "'x' * 1000000",
    "read": "open('/etc/passwd').read()",
    "write": "open('/tmp/escape', 'w').write('x')",
    "process": "import subprocess\nsubprocess.run(['id'])",
    "network": "import socket\nsocket.create_connection(('example.com', 443))",
    "evaluator": "import repl_lab.sim",
    "host-environment": "import os\nos.environ['ANTHROPIC_API_KEY']",
}
READY_REQUEST = '{"source": "20 + 22", "bindings": {}}\n'
READY_REPLY = '{"value":42,"printed":""}'
# A value of s characters replies {"value":"x...x","printed":""}: s + 25 bytes before the newline.
REPLY_OVERHEAD = 25


def doctor():
    return isolation.preflight("REPL_LAB_PYTHON_IMAGE", "repl-lab.python-worker")


def probe(sources):
    return subprocess.run([sys.executable, str(Path(__file__).resolve()), "session"],
                          input="".join(json.dumps({"source": s, "bindings": {}}) + "\n" for s in sources),
                          capture_output=True, text=True, timeout=isolation.LIMITS["startup_seconds"] + 30)


def request(source):
    return json.dumps({"source": source, "bindings": {}}) + "\n"


def negative_case(name, source):
    """Confirm readiness in the SAME worker, then send exactly one negative request
    (the Python counterpart of isolation.negative_case; JSON wire, Python outcomes)."""
    started = time.monotonic()
    with subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "session"], stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1) as proc:
        try:
            proc.stdin.write(READY_REQUEST)
            proc.stdin.flush()
            with selectors.DefaultSelector() as ready:
                ready.register(proc.stdout, selectors.EVENT_READ)
                if not ready.select(isolation.LIMITS["startup_seconds"] + 30):
                    raise subprocess.TimeoutExpired("worker readiness", isolation.LIMITS["startup_seconds"] + 30)
                first = proc.stdout.readline()
            startup_ms = (time.monotonic() - started) * 1000
            if first.strip() != READY_REPLY:
                out, err = proc.communicate(timeout=30)
                return {"startup": False, "passed": False, "stage": "startup",
                        "classification": "docker-preflight-failure" if "Isolation preflight failed" in err else "readiness-failure",
                        "stdout": (first + out)[:65536], "stderr": err[:16384], "startup_ms": startup_ms}
            # A separate write resets the existing per-request deadline. Do not pipeline.
            out, err = proc.communicate(input=request(source), timeout=30)
            rows = [json.loads(line) for line in out.splitlines() if line.strip()]
            errored = any("error" in row for row in rows)
            if name == "loop":
                passed = proc.returncode != 0 and "Worker wall-time limit" in err
            elif name == "allocation":
                # Either the interpreter refuses the allocation (MemoryError) or the container's
                # memory limit ends the worker; a deadline is not memory-limit evidence.
                passed = (proc.returncode == 0 and errored and "MemoryError" in out) or \
                         (proc.returncode != 0 and "Worker failed with exit" in err and "Worker wall-time limit" not in err)
            elif name == "oversized-result":
                # The worker refuses its own reply before the supervisor's bound: a recoverable error.
                passed = proc.returncode == 0 and errored and "Result limit" in out
            else:
                passed = proc.returncode == 0 and errored
            classification = ("memory-error" if name == "allocation" and passed and proc.returncode == 0 else
                              "container-memory-limit" if name == "allocation" and passed else
                              "execution-deadline" if "Worker wall-time limit" in err else
                              "expected-restriction" if passed else "missing-restriction-evidence")
            return {"startup": True, "passed": passed, "stage": "negative-operation", "classification": classification,
                    "stdout": out[:65536], "stderr": err[:16384], "returncode": proc.returncode,
                    "startup_ms": startup_ms, "total_ms": (time.monotonic() - started) * 1000}
        except subprocess.TimeoutExpired:
            isolation.QUARANTINE.mkdir(parents=True, exist_ok=True)
            (isolation.QUARANTINE / f"gate-supervisor-{proc.pid}.json").write_text(json.dumps(
                {"status": "cleanup-unconfirmed", "supervisor_pid": proc.pid,
                 "reason": "Gate supervisor timed out; inspect and remove its container before clearing this marker."}))
            proc.kill()
            proc.communicate()
            raise RuntimeError("Gate supervisor timeout; cleanup unconfirmed and quarantined")


def boundary_tests():
    """The exact output boundary. At the bound, a reply line with its newline of exactly the
    supervisor's bound passes. One byte more is refused by the worker itself (Result limit) as a
    recoverable error, and the same worker answers the next request: the Python worker never
    reaches the supervisor's bound, where the SCI worker would be stopped."""
    bound = isolation.LIMITS["output_bytes"]
    results = {}
    at = probe(["'x' * %d" % (bound - 1 - REPLY_OVERHEAD)])
    line = at.stdout.splitlines()[0] if at.stdout else ""
    results["at-bound"] = at.returncode == 0 and len(line.encode()) + 1 == bound and '"error"' not in line
    over = probe(["'x' * %d" % (bound - REPLY_OVERHEAD), "20 + 22"])
    rows = [json.loads(s) for s in over.stdout.splitlines() if s.strip()]
    results["over-bound"] = (over.returncode == 0 and len(rows) == 2 and "Result limit" in rows[0].get("error", "")
                             and rows[1].get("value") == 42)
    return results


def negative_tests():
    path = ROOT / "var/python-isolation-proof.json"
    if path.exists():
        path.replace(path.with_name(f"python-isolation-proof-before-{time.time_ns()}.json"))
    check = doctor()
    if not check.get("ready"):
        print(json.dumps({"status": "UNVERIFIED", "reason": check.get("reason"), "tests": list(NEGATIVE)}))
        return 2
    positive = probe(["offset = 2", "offset + 40"])
    rows = [json.loads(s) for s in positive.stdout.splitlines()]
    if positive.returncode or [r.get("value") for r in rows] != [None, 42] or any("error" in r for r in rows):
        raise RuntimeError("Python positive control failed")
    boundary = boundary_tests()
    outcomes = {}
    for name, source in NEGATIVE.items():
        outcomes[name] = negative_case(name, source)
        if not outcomes[name]["startup"] or (isolation.QUARANTINE.exists() and any(isolation.QUARANTINE.iterdir())):
            break
    results = {name: outcomes.get(name, {}).get("passed", False) for name in NEGATIVE}
    startup = {name: outcomes.get(name, {}).get("startup", False) for name in NEGATIVE}
    # A new interpreter must not inherit a prior session's binding.
    reset = probe(["offset"])
    results["session-reset"] = reset.returncode == 0 and "NameError" in reset.stdout
    startup["session-reset"] = reset.returncode == 0
    passed = all(results.values()) and all(startup.values()) and all(boundary.values()) and doctor()["ready"]
    report = {"status": "TESTED" if passed else "FAILED", "gate-version": 2, "image": check["image"],
              "results": results, "startup": startup, "outcomes": outcomes, "boundary": boundary,
              "output-bytes": isolation.LIMITS["output_bytes"], "positive_control": True, "model_calls": 0,
              "supervisor-sha256": hashlib.sha256((ROOT / "scripts/isolation.py").read_bytes()).hexdigest(),
              "gate-sha256": hashlib.sha256(Path(__file__).resolve().read_bytes()).hexdigest()}
    if passed:
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "outcomes"}))
    return 0 if passed else 2


if __name__ == "__main__":
    try:
        action = sys.argv[1] if len(sys.argv) == 2 else "doctor"
        if action == "doctor":
            print(json.dumps(doctor()))
        elif action == "session":
            isolation.session("python")
        elif action == "test":
            sys.exit(negative_tests())
        else:
            raise RuntimeError("Unknown Python isolation command")
    except Exception as error:
        print("Python isolation refused: " + str(error), file=sys.stderr)
        sys.exit(3 if isinstance(error, isolation.CleanupError) else 2)
