#!/usr/bin/env python3
"""Python worker gate using the same verified Docker supervisor as SCI."""
import json
from pathlib import Path
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


def doctor():
    return isolation.preflight("REPL_LAB_PYTHON_IMAGE", "repl-lab.python-worker")


def probe(sources):
    return subprocess.run([sys.executable, str(Path(__file__).resolve()), "session"],
                          input="".join(json.dumps({"source": s, "bindings": {}}) + "\n" for s in sources),
                          capture_output=True, text=True, timeout=35)


def negative_tests():
    path = ROOT / "var/python-isolation-proof.json"
    if path.exists():
        path.replace(path.with_name(f"python-isolation-proof-before-{time.time_ns()}.json"))
    check = doctor()
    if not check.get("ready"):
        raise RuntimeError(check.get("reason"))
    positive = probe(["offset = 2", "offset + 40"])
    rows = [json.loads(s) for s in positive.stdout.splitlines()]
    if positive.returncode or [r.get("value") for r in rows] != [None, 42] or any("error" in r for r in rows):
        raise RuntimeError("Python positive control failed")
    results = {}
    for name, source in NEGATIVE.items():
        result = probe([source])
        results[name] = result.returncode != 0 or any("error" in json.loads(s) for s in result.stdout.splitlines())
    # A new interpreter must not inherit a prior session's binding.
    reset = probe(["offset"])
    results["session-reset"] = reset.returncode == 0 and "NameError" in reset.stdout
    report = {"status": "TESTED" if all(results.values()) else "FAILED", "image": check["image"],
              "results": results, "positive_control": True, "model_calls": 0}
    if all(results.values()):
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    return 0 if all(results.values()) else 2


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
