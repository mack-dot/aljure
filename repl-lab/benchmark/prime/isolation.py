"""Actual negative controls for the native Prime image; no provider calls."""
import json
from pathlib import Path
import time

from .container import container, doctor, execute

ROOT = Path(__file__).resolve().parents[2]
PROOF = ROOT / "var/prime-isolation-proof.json"
NEGATIVE = {
    "loop": "while True: pass",
    "allocation": "x = bytearray(1024**3)",
    "oversized-output": "print('x' * 1000000)",
    "host-read": "open('/Users/mackianni/aljure/repl-lab/config/experiment.edn').read()",
    "root-write": "open('/escape', 'w').write('x')",
    "network": "import socket; socket.create_connection(('1.1.1.1', 443), timeout=2)",
    "evaluator": "open('/work/hidden-evaluator.json').read()",
}


def probe(image, source, seconds=10):
    with container(image, ["-c", source], entrypoint="/opt/venv/bin/python") as (name, _):
        result = execute(name, seconds=seconds, max_output=65536)
    return {"exit_code": result["exit_code"], "failure": result["failure"], "wall_ms": result["wall_ms"],
            "stdout": result["stdout"].decode(errors="replace"), "stderr": result["stderr"].decode(errors="replace")}


def test():
    if PROOF.exists():
        PROOF.rename(PROOF.with_name("prime-isolation-before-test-" + str(time.time_ns()) + ".json"))
    check = doctor()
    if not check["ready"]:
        raise RuntimeError(check["reason"])
    image = check["image"]
    positive = probe(image, "from pathlib import Path; import os; Path('/work/marker').write_text('42'); print(6 * 7); print(any('API_KEY' in k or 'TOKEN' in k for k in os.environ))")
    if positive["exit_code"] or positive["failure"] or positive["stdout"].strip() != "42\nFalse":
        raise RuntimeError("Native worker positive control failed")
    evidence = {name: probe(image, source) for name, source in NEGATIVE.items()}
    reset = probe(image, "from pathlib import Path; print(Path('/work/marker').exists())")
    process_limit = probe(image, """import errno, subprocess
children = []
try:
    for _ in range(64):
        children.append(subprocess.Popen(['/bin/sleep', '30']))
except OSError as error:
    print('pids-limited' if error.errno == errno.EAGAIN else 'unexpected-error')
finally:
    for child in children:
        child.terminate()
    for child in children:
        child.wait()
""")
    passed = {name: bool(item["exit_code"] or item["failure"]) for name, item in evidence.items()}
    passed["session-reset"] = reset["exit_code"] == 0 and reset["failure"] is None and reset["stdout"].strip() == "False"
    passed["process-limit"] = process_limit["exit_code"] == 0 and process_limit["failure"] is None and process_limit["stdout"].strip() == "pids-limited"
    report = {"status": "TESTED" if all(passed.values()) else "FAILED", "image": image,
              "results": passed, "positive": positive, "negative": evidence, "reset": reset,
              "process_limit": process_limit, "model_calls": 0,
              "limitations": ["Native Python may read image files and execute tools inside the container",
                              "PID/CPU/memory controls are inspected; no arbitrary-code security proof",
                              "Native task watchdog bounds whole task, not each Python expression"]}
    destination = PROOF if all(passed.values()) else PROOF.with_name("prime-isolation-failed-" + str(time.time_ns()) + ".json")
    destination.write_text(json.dumps(report, indent=2) + "\n")
    if not all(passed.values()):
        raise RuntimeError("Native isolation negative controls failed")
    return report


def require_tested():
    check = doctor()
    if not check["ready"]:
        raise RuntimeError(check["reason"])
    proof = json.loads(PROOF.read_text())
    if (proof.get("status") != "TESTED" or proof.get("image") != check["image"]
            or set(proof.get("results", {})) != set(NEGATIVE) | {"session-reset", "process-limit"}
            or not all(v is True for v in proof["results"].values())):
        raise RuntimeError("Native isolation proof is incomplete or stale")
    return check


if __name__ == "__main__":
    report = test()
    print(json.dumps({k: report[k] for k in ("status", "image", "results", "model_calls")}, indent=2))
