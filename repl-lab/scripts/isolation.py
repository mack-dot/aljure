#!/usr/bin/env python3
"""Fail-closed Docker supervisor. No source is evaluated on the host.

The image must contain only the fixed worker and its pinned dependencies. This
runner never pulls images or mounts host paths. One invocation is one SCI session.
"""
import json
import hashlib
import os
import re
import selectors
import subprocess
import sys
import time
import uuid
from pathlib import Path

LIMITS = {"memory_mb": 256, "cpus": 1, "pids": 32, "scratch_mb": 8,
          "wall_seconds": 10, "output_bytes": 65536, "input_bytes": 65536,
          "session_seconds": 120, "startup_seconds": 30}
# Per-expression output bound. 64 KB is the default and the benchmark control;
# 1 MB only when explicitly configured, and it needs its own proof.
OUTPUT_BOUNDS = (65536, 1048576)


def apply_output_bound():
    value = os.environ.get("REPL_LAB_WORKER_OUTPUT_BYTES", "65536")
    if not value.isdigit() or int(value) not in OUTPUT_BOUNDS:
        raise RuntimeError("Unsupported worker output bound")
    LIMITS["output_bytes"] = int(value)
    # The oversized control must exceed the bound it proves (unchanged at 64 KB).
    NEGATIVE["oversized-result"] = '(apply str (repeat %d "x"))' % max(1000000, 2 * int(value))
    return int(value)


def proof_path():
    bound = LIMITS["output_bytes"]
    name = "isolation-proof.json" if bound == 65536 else f"isolation-proof-{bound}.json"
    return Path(__file__).resolve().parents[1] / "var" / name


# Fixed readiness probe the supervisor itself sends; it is never forwarded.
READY_PROBE, READY_REPLY = b'{:source "(+ 20 22)" :bindings {}}\n', b"{:value 42}"


QUARANTINE = Path(__file__).resolve().parents[1] / "var/isolation-quarantine"


class CleanupError(RuntimeError):
    """The controller must distinguish failed removal from a code/runtime error."""


class SessionAudit:
    """Opt-in host diagnostics. No source, environment, or credentials are logged."""
    def __init__(self, name):
        self.directory = os.environ.get("REPL_LAB_WORKER_AUDIT_DIR")
        self.started = time.monotonic()
        self.data = {"container": name, "supervisor_pid": os.getpid(), "events": [],
                     "stderr": "", "cleanup_confirmed": False}

    def event(self, kind, **fields):
        if self.directory and len(self.data["events"]) < 12000:
            self.data["events"].append({"event": kind, "elapsed_ms": round((time.monotonic() - self.started) * 1000, 3), **fields})

    def stderr(self, data):
        if self.directory:
            self.data["stderr"] = (self.data["stderr"] + data.decode("utf-8", errors="replace"))[:16384]

    def inspect(self, name):
        if self.directory:
            try:
                result = docker("inspect", "--format", "{{json .State}}", name)
                self.data["state_before_cleanup"] = json.loads(result.stdout) if result.returncode == 0 else None
            except (OSError, subprocess.TimeoutExpired, ValueError) as error:
                self.data["state_inspection_error"] = type(error).__name__

    def save(self):
        if self.directory:
            path = Path(self.directory)
            path.mkdir(parents=True, exist_ok=True)
            target = path / (self.data["container"] + ".json")
            with target.open("x") as output:
                json.dump(self.data, output, indent=2)


def docker(*args, timeout=5):
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)


def preflight(image_env="REPL_LAB_WORKER_IMAGE", label="repl-lab.worker"):
    timings = []
    stage = "configuration"

    def finish(result):
        result["queries"] = timings
        directory = os.environ.get("REPL_LAB_WORKER_AUDIT_DIR")
        if directory:
            path = Path(directory) / "preflight"
            path.mkdir(parents=True, exist_ok=True)
            with (path / (uuid.uuid4().hex + ".json")).open("x") as output:
                json.dump(result, output, indent=2)
        return result

    def query(*args):
        started = time.monotonic()
        record = {"stage": stage}
        try:
            result = docker(*args)
            record["returncode"] = result.returncode
            return result
        except (OSError, subprocess.TimeoutExpired) as error:
            record["error_type"] = type(error).__name__
            raise
        finally:
            record["elapsed_ms"] = round((time.monotonic() - started) * 1000, 3)
            timings.append(record)

    if QUARANTINE.exists() and any(QUARANTINE.iterdir()):
        return finish({"ready": False, "reason": "Worker cleanup is unconfirmed. Inspect var/isolation-quarantine and run make isolation-recover."})
    image = os.environ.get(image_env, "")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
        return finish({"ready": False, "reason": f"Set {image_env} to a local immutable sha256 image ID."})
    try:
        stage = "docker-info"
        info = query("info", "--format", "{{json .}}")
        if info.returncode:
            return finish({"ready": False, "reason": "Docker daemon is unavailable or denied."})
        info = json.loads(info.stdout)
        if info.get("OSType") != "linux" or not all(info.get(k) for k in ("MemoryLimit", "SwapLimit", "CpuCfsQuota", "PidsLimit")):
            return finish({"ready": False, "reason": "Required kernel resource controls are unavailable."})
        stage = "image-inspect"
        result = query("image", "inspect", image)
        if result.returncode:
            return finish({"ready": False, "reason": "Pinned worker image is not local. No automatic pull."})
        meta = json.loads(result.stdout)[0]
        if meta["Id"] != image or meta["Config"].get("Labels", {}).get(label) != "1":
            return finish({"ready": False, "reason": "Invalid worker image identity/label."})
        return finish({"ready": True, "image": image, "limits": LIMITS})
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError) as error:
        return finish({"ready": False, "reason": "Isolation preflight failed at " + stage + ": " + type(error).__name__})


def create_args(image, name):
    return ["create", "--name", name, "--interactive", "--network", "none", "--read-only",
            "--user", "65534:65534", "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
            "--memory", "256m", "--memory-swap", "256m", "--cpus", "1", "--pids-limit", "32",
            "--ulimit", "nofile=64:64", "--ulimit", "core=0:0", "--ulimit", "fsize=8388608:8388608",
            "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=8m", "--log-driver", "none", image]


def verify_container(meta):
    host, config = meta["HostConfig"], meta["Config"]
    checks = [host["NetworkMode"] == "none", host["ReadonlyRootfs"], config["User"] == "65534:65534",
              host["Memory"] == 256 * 1024**2, host["MemorySwap"] == 256 * 1024**2,
              host["NanoCpus"] == 1000000000, host["PidsLimit"] == 32,
              "ALL" in host["CapDrop"], "no-new-privileges:true" in host["SecurityOpt"],
              not host.get("Binds"), not host.get("Privileged"), not host.get("Devices"),
              host.get("LogConfig", {}).get("Type") == "none",
              host.get("Tmpfs", {}).get("/tmp") == "rw,noexec,nosuid,nodev,size=8m",
              all(m.get("Type") != "bind" for m in meta.get("Mounts", []))]
    if not all(checks):
        raise RuntimeError("Container isolation configuration mismatch")


def cleanup(name):
    # This name is generated here, never accepted from model code.
    if not re.fullmatch(r"repl-lab-[0-9a-f]{32}", name):
        raise RuntimeError("Invalid cleanup target")
    try:
        try:
            removed = docker("rm", "--force", name)
            confirmed = removed.returncode == 0
            removal = "success" if confirmed else "nonzero-exit"
        except (OSError, subprocess.TimeoutExpired) as error:
            # The daemon may have removed the container before the client timed out.
            # Do not retry execution/removal or assume success: verify absence.
            confirmed, removal = False, type(error).__name__
        if not confirmed:
            # A failed create can leave no container. Verify absence with a
            # successful daemon query; a failed inspect alone proves nothing.
            listed = docker("ps", "--all", "--filter", "name=^/" + name + "$", "--format", "{{.ID}}")
            if listed.returncode or listed.stdout.strip():
                raise RuntimeError("Worker removal unconfirmed")
        evidence = {"method": "docker-rm" if confirmed else "verified-absence", "removal": removal}
    except (OSError, subprocess.TimeoutExpired, RuntimeError) as error:
        QUARANTINE.mkdir(parents=True, exist_ok=True)
        (QUARANTINE / (name + ".json")).write_text(json.dumps({"container": name, "status": "cleanup-unconfirmed"}))
        raise CleanupError("Worker cleanup unconfirmed; generated-code execution is quarantined") from error
    marker = QUARANTINE / (name + ".json")
    marker.unlink(missing_ok=True)
    return evidence


def recover_cleanup():
    markers = list(QUARANTINE.glob("*.json")) if QUARANTINE.exists() else []
    for marker in markers:
        data = json.loads(marker.read_text())
        name = data["container"]
        if marker.name != name + ".json":
            raise RuntimeError("Invalid cleanup marker")
        cleanup(name)
    if QUARANTINE.exists() and any(QUARANTINE.iterdir()):
        raise RuntimeError("Unrecognized quarantine entry; inspect it before continuing")
    print(json.dumps({"status": "cleanup-confirmed", "containers": len(markers),
                      "isolation-tests": "still-required"}))


def task_deadline():
    remaining = LIMITS["session_seconds"]
    supplied = os.environ.get("REPL_LAB_TASK_DEADLINE_MS")
    if supplied is not None:
        if not re.fullmatch(r"[0-9]+", supplied):
            raise RuntimeError("Invalid task deadline")
        remaining = min(remaining, int(supplied) / 1000 - time.time())
    if remaining <= 0:
        raise RuntimeError("Task wall-time limit")
    return time.monotonic() + remaining


def session(language="clojure"):
    absolute_deadline = task_deadline()
    apply_output_bound()
    if language not in ("clojure", "python"):
        raise RuntimeError("Unknown execution language")
    check = preflight() if language == "clojure" else preflight("REPL_LAB_PYTHON_IMAGE", "repl-lab.python-worker")
    if not check["ready"]:
        raise RuntimeError(check["reason"])
    name = "repl-lab-" + uuid.uuid4().hex
    audit = SessionAudit(name)
    proc = None
    try:
        if time.monotonic() >= absolute_deadline:
            raise RuntimeError("Task wall-time limit")
        created = docker(*create_args(check["image"], name))
        audit.event("container-created", returncode=created.returncode)
        if created.returncode:
            raise RuntimeError("Cannot create isolated worker")
        inspect = docker("inspect", name)
        if inspect.returncode:
            raise RuntimeError("Cannot verify isolated worker")
        verify_container(json.loads(inspect.stdout)[0])
        audit.event("container-verified")
        if time.monotonic() >= absolute_deadline:
            raise RuntimeError("Task wall-time limit")
        proc = subprocess.Popen(["docker", "start", "--attach", "--interactive", name],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                bufsize=0)
        sel = selectors.DefaultSelector()
        sel.register(sys.stdin.buffer, selectors.EVENT_READ, "input")
        sel.register(proc.stdout, selectors.EVENT_READ, "output")
        sel.register(proc.stderr, selectors.EVENT_READ, "error")
        started = time.monotonic()
        audit.event("attach-started")
        # Container, JVM and SCI startup has its own bound. No controller request
        # is read until the worker answers the fixed probe, so each expression's
        # wall-time limit starts with a ready worker.
        ready_deadline = min(started + LIMITS["startup_seconds"], absolute_deadline)
        reply = b""
        with selectors.DefaultSelector() as startup:
            startup.register(proc.stdout, selectors.EVENT_READ, "output")
            startup.register(proc.stderr, selectors.EVENT_READ, "error")
            proc.stdin.write(READY_PROBE)
            while not reply.endswith(b"\n"):
                if time.monotonic() > ready_deadline:
                    raise RuntimeError("Worker startup limit")
                for key, _ in startup.select(0.1):
                    data = os.read(key.fd, 4096)
                    if not data:
                        raise RuntimeError("Worker exited during startup")
                    if key.data == "error":
                        audit.stderr(data)
                    else:
                        reply += data
                        if len(reply) > 4096:
                            raise RuntimeError("Worker readiness reply too large")
        if reply.strip() != READY_REPLY:
            raise RuntimeError("Worker readiness probe failed")
        audit.event("worker-ready", startup_ms=round((time.monotonic() - started) * 1000, 3))
        # Idle until the controller's first request; the task deadline still applies.
        deadline = absolute_deadline
        input_size = output_size = 0
        # Drain buffered stdout/stderr after process exit as well. A short-lived
        # positive control must not lose its final response at EOF.
        while proc.poll() is None or any(key.data in ("output", "error") for key in sel.get_map().values()):
            if time.monotonic() > min(deadline, absolute_deadline):
                raise RuntimeError("Worker wall-time limit")
            for key, _ in sel.select(0.1):
                data = os.read(key.fd, 4096)
                if not data:
                    sel.unregister(key.fileobj)
                    if key.data == "input":
                        proc.stdin.close()
                    continue
                if key.data == "input":
                    input_size += len(data)
                    if input_size > LIMITS["input_bytes"]:
                        raise RuntimeError("Worker input limit")
                    proc.stdin.write(data)
                    if b"\n" in data:
                        audit.event("request-written")
                        input_size = 0
                        deadline = time.monotonic() + LIMITS["wall_seconds"]
                else:
                    if key.data == "error":
                        audit.stderr(data)
                    output_size += len(data)
                    if output_size > LIMITS["output_bytes"]:
                        raise RuntimeError("Worker output limit")
                    target = sys.stdout.buffer if key.data == "output" else sys.stderr.buffer
                    target.write(data)
                    target.flush()
                    if b"\n" in data and key.data == "output":
                        audit.event("response-read")
                        # The controller sends one command at a time.
                        output_size = 0
                        # Keep idle bindings while the model is thinking. The
                        # absolute task/session deadline still bounds lifetime.
                        deadline = absolute_deadline
        if proc.returncode:
            raise RuntimeError("Worker failed with exit " + str(proc.returncode))
    except Exception as error:
        audit.event("supervisor-error", error_type=type(error).__name__, message=str(error))
        raise
    finally:
        audit.inspect(name)
        # Kill the execution unit, including descendants, before closing transport.
        try:
            audit.data["cleanup_evidence"] = cleanup(name)
            audit.data["cleanup_confirmed"] = True
        finally:
            if proc is not None and proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)
            audit.data["attach_exit_code"] = proc.returncode if proc is not None else None
            audit.event("cleanup-finished", confirmed=audit.data["cleanup_confirmed"])
            audit.save()


NEGATIVE = {
    "loop": "(loop [] (recur))",
    "allocation": "(vec (range 1000000000))",
    "oversized-result": "(apply str (repeat 1000000 \"x\"))",
    "read": '(slurp "/etc/passwd")',
    "write": '(spit "/tmp/escape" "x")',
    "process": '(java.lang.Runtime/getRuntime)',
    "network": '(slurp "https://example.com")',
    "evaluator": '(require (quote repl-lab.sim))',
    "reader-eval": '#=(System/exit 0)',
}


def negative_case(name, source):
    """Confirm readiness in the SAME worker, then send exactly one negative request."""
    started = time.monotonic()
    with subprocess.Popen([sys.executable, __file__, "session"], stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1) as proc:
        try:
            proc.stdin.write('{:source "(+ 20 22)" :bindings {}}\n')
            proc.stdin.flush()
            with selectors.DefaultSelector() as ready:
                ready.register(proc.stdout, selectors.EVENT_READ)
                # The supervisor's own startup bound comes first.
                if not ready.select(LIMITS["startup_seconds"] + 30):
                    raise subprocess.TimeoutExpired("worker readiness", LIMITS["startup_seconds"] + 30)
                first = proc.stdout.readline()
            startup_ms = (time.monotonic() - started) * 1000
            if first.strip() != "{:value 42}":
                out, err = proc.communicate(timeout=30)
                return {"startup": False, "passed": False, "stage": "startup",
                        "classification": "docker-preflight-failure" if "Isolation preflight failed" in err else "readiness-failure",
                        "stdout": (first + out)[:65536], "stderr": err[:16384], "startup_ms": startup_ms}
            # A separate write resets the existing per-request deadline. Do not pipeline.
            wire = '{:source ' + json.dumps(source) + ' :bindings {}}\n'
            out, err = proc.communicate(input=wire, timeout=30)
            if name == "loop":
                passed = proc.returncode != 0 and "Worker wall-time limit" in err
            elif name == "allocation":
                # This fixed probe must exhaust the JVM heap AFTER readiness.
                # ExitOnOutOfMemoryError emits this fatal line and exits 3.
                # A deadline, arbitrary nonzero exit, or quoted error is not OOM proof.
                passed = (proc.returncode == 2
                          and "Terminating due to java.lang.OutOfMemoryError: Java heap space" in (out + err).splitlines()
                          and "Isolation refused: Worker failed with exit 3" in err.splitlines()
                          and "Worker wall-time limit" not in err)
            elif name == "oversized-result":
                passed = proc.returncode != 0 and "Worker output limit" in err
            else:
                passed = proc.returncode == 0 and ":error" in out
            classification = ("jvm-heap-exhausted" if name == "allocation" and passed else
                              "execution-deadline" if "Worker wall-time limit" in err else
                              "expected-restriction" if passed else "missing-restriction-evidence")
            return {"startup": True, "passed": passed, "stage": "negative-operation", "classification": classification,
                    "stdout": out[:65536], "stderr": err[:16384], "returncode": proc.returncode,
                    "startup_ms": startup_ms, "total_ms": (time.monotonic() - started) * 1000}
        except subprocess.TimeoutExpired:
            # An unresponsive supervisor cannot prove container removal. Block all work.
            QUARANTINE.mkdir(parents=True, exist_ok=True)
            (QUARANTINE / f"gate-supervisor-{proc.pid}.json").write_text(json.dumps(
                {"status": "cleanup-unconfirmed", "supervisor_pid": proc.pid,
                 "reason": "Gate supervisor timed out; inspect and remove its container before clearing this marker."}))
            proc.kill()
            proc.communicate()
            raise RuntimeError("Gate supervisor timeout; cleanup unconfirmed and quarantined")


def negative_tests():
    apply_output_bound()
    path = proof_path()
    if path.exists():
        path.replace(path.with_name(f"{path.stem}-before-test-{time.time_ns()}.json"))
    check = preflight()
    if not check["ready"]:
        print(json.dumps({"status": "UNVERIFIED", "reason": check["reason"], "tests": list(NEGATIVE)}))
        return 2
    # A positive control ensures failures are not merely broken worker startup.
    positive = subprocess.run([sys.executable, __file__, "session"],
                              input='{:source "(do (def offset 2) nil)" :bindings {}}\n'
                                    '{:source "(+ offset 40)" :bindings {}}\n', text=True,
                              capture_output=True, timeout=30)
    if positive.returncode or ':value nil' not in positive.stdout or ':value 42' not in positive.stdout:
        raise RuntimeError("Worker positive control failed")
    # Exact output boundary: a reply line (with its newline) of exactly the bound
    # passes; one byte more stops the worker.
    bound, boundary = LIMITS["output_bytes"], {}
    for name, size in (("at-bound", bound - 12), ("over-bound", bound - 11)):
        run = subprocess.run([sys.executable, __file__, "session"], text=True, capture_output=True, timeout=90,
                             input='{:source "(apply str (repeat %d \\"x\\"))" :bindings {}}\n' % size)
        line = run.stdout.splitlines()[0] if run.stdout else ""
        boundary[name] = ((run.returncode == 0 and len(line.encode()) + 1 == bound) if name == "at-bound"
                          else (run.returncode != 0 and "Worker output limit" in run.stderr))
    outcomes = {}
    for name, source in NEGATIVE.items():
        outcomes[name] = negative_case(name, source)
        if not outcomes[name]["startup"] or (QUARANTINE.exists() and any(QUARANTINE.iterdir())):
            break
    results = {name: outcomes.get(name, {}).get("passed", False) for name in NEGATIVE}
    startup = {name: outcomes.get(name, {}).get("startup", False) for name in NEGATIVE}
    passed = all(results.values()) and all(startup.values()) and all(boundary.values()) and preflight()["ready"]
    report = {"status": "TESTED" if passed else "FAILED", "gate-version": 2,
              "results": results, "startup": startup, "outcomes": outcomes, "image": check["image"],
              "output-bytes": LIMITS["output_bytes"], "boundary": boundary,
              "supervisor-sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    if passed:
        Path("var").mkdir(exist_ok=True)
        path.write_text(json.dumps(report))
    print(json.dumps(report))
    return 0 if passed else 1


if __name__ == "__main__":
    try:
        action = sys.argv[1] if len(sys.argv) > 1 else "doctor"
        apply_output_bound()
        if action == "doctor":
            print(json.dumps(preflight()))
        elif action == "session":
            session()
        elif action == "test":
            sys.exit(negative_tests())
        elif action == "recover":
            recover_cleanup()
        else:
            raise RuntimeError("Unknown isolation command")
    except Exception as error:
        print("Isolation refused: " + str(error), file=sys.stderr)
        sys.exit(3 if isinstance(error, CleanupError) else 2)
