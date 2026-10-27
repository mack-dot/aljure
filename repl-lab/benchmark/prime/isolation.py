"""Actual negative controls for the native Prime image; no provider calls."""
import json
import hashlib
from pathlib import Path
import time

from .container import container, doctor, execute, checked

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


def gate_digest():
    files = [Path(__file__), Path(__file__).with_name('container.py'), ROOT / 'scripts/isolation.py']
    return hashlib.sha256(b''.join(p.read_bytes() for p in files)).hexdigest()


def probe(image, source, seconds=10):
    # The negative operation cannot run before the host observes readiness in
    # THIS container. A dead interpreter or transport is never a security pass.
    ready = []
    program = "import json,sys; print(json.dumps({'type':'probe_ready'}),flush=True); assert input() == 'go'\n" + source
    def handshake(event, remaining):
        if event.get('type') == 'probe_ready' and not ready:
            ready.append(True)
            return b'go\n'
        return None
    with container(image, ["-c", program], entrypoint="/opt/venv/bin/python") as (name, _):
        result = execute(name, seconds=seconds, max_output=65536, event_handler=handshake)
        state = json.loads(checked(['inspect', '--format', '{{json .State}}', name]))
    stdout = result['stdout'].decode(errors='replace')
    lines = stdout.splitlines(keepends=True)
    if ready and lines:
        lines = lines[1:]
    return {"exit_code": result["exit_code"], "failure": result["failure"], "wall_ms": result["wall_ms"],
            "startup_ready": bool(ready), "container_state": state,
            "stdout": ''.join(lines), "stderr": result["stderr"].decode(errors="replace")}


def denied(name, item):
    if not item.get('startup_ready'):
        return False
    if name == 'loop':
        return item['failure'] == 'wall-time-limit'
    if name == 'oversized-output':
        return item['failure'] == 'output-limit'
    if name == 'allocation':
        return (item['failure'] is None and item['exit_code'] != 0 and
                ('MemoryError' in item['stderr'] or
                 (item['exit_code'] == 137 and item.get('container_state', {}).get('OOMKilled') is True)))
    if name == 'root-write':
        return bool(item['exit_code']) and item['failure'] is None and (
            'PermissionError' in item['stderr'] or 'OSError: [Errno 30] Read-only file system' in item['stderr'])
    errors = {'host-read': 'FileNotFoundError',
              'network': 'OSError', 'evaluator': 'FileNotFoundError'}
    return bool(item['exit_code']) and item['failure'] is None and errors[name] in item['stderr']


def test():
    if PROOF.exists():
        PROOF.rename(PROOF.with_name("prime-isolation-before-test-" + str(time.time_ns()) + ".json"))
    check = doctor()
    if not check["ready"]:
        raise RuntimeError(check["reason"])
    image = check["image"]
    positive = probe(image, "from pathlib import Path; import os; Path('/work/marker').write_text('42'); print(6 * 7); print(any('API_KEY' in k or 'TOKEN' in k for k in os.environ))")
    if not positive['startup_ready'] or positive["exit_code"] or positive["failure"] or positive["stdout"].strip() != "42\nFalse":
        PROOF.with_name('prime-isolation-failed-' + str(time.time_ns()) + '.json').write_text(json.dumps(
            {'status': 'FAILED', 'gate_version': 2, 'image': image, 'positive': positive,
             'classification': 'infrastructure-positive-control', 'model_calls': 0}, indent=2))
        raise RuntimeError("Native worker positive control failed")
    evidence = {name: probe(image, source) for name, source in NEGATIVE.items()}
    non_oom_kill = probe(image, 'import os,signal; os.kill(os.getpid(), signal.SIGKILL)')
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
    passed = {name: denied(name, item) for name, item in evidence.items()}
    passed["session-reset"] = reset["startup_ready"] and reset["exit_code"] == 0 and reset["failure"] is None and reset["stdout"].strip() == "False"
    passed["process-limit"] = process_limit["startup_ready"] and process_limit["exit_code"] == 0 and process_limit["failure"] is None and process_limit["stdout"].strip() == "pids-limited"
    passed['non-oom-kill-rejected'] = (non_oom_kill['startup_ready'] and non_oom_kill['exit_code'] == 137 and
                                      non_oom_kill['container_state'].get('OOMKilled') is False and
                                      not denied('allocation', non_oom_kill))
    report = {"status": "TESTED" if all(passed.values()) else "FAILED", "gate_version": 3,
              "gate_sha256": gate_digest(), "image": image,
              "results": passed, "positive": positive, "negative": evidence, "reset": reset,
              "process_limit": process_limit, "non_oom_kill": non_oom_kill, "model_calls": 0,
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
    if (proof.get("status") != "TESTED" or proof.get("gate_version") != 3
            or proof.get("gate_sha256") != gate_digest()
            or proof.get("image") != check["image"]
            or not all(proof.get('negative', {}).get(name, {}).get('startup_ready') is True for name in NEGATIVE)
            or not denied('allocation', proof.get('negative', {}).get('allocation', {}))
            or set(proof.get("results", {})) != set(NEGATIVE) | {"session-reset", "process-limit", "non-oom-kill-rejected"}
            or not all(v is True for v in proof["results"].values())):
        raise RuntimeError("Native isolation proof is incomplete or stale")
    return check


if __name__ == "__main__":
    report = test()
    print(json.dumps({k: report[k] for k in ("status", "image", "results", "model_calls")}, indent=2))
