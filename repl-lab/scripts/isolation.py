#!/usr/bin/env python3
"""Fail-closed Docker supervisor. No source is evaluated on the host.

The image must contain only the fixed worker and its pinned dependencies. This
runner never pulls images or mounts host paths. One invocation is one SCI session.
"""
import json
import os
import re
import selectors
import subprocess
import sys
import time
import uuid

LIMITS = {"memory_mb": 256, "cpus": 1, "pids": 32, "scratch_mb": 8,
          "wall_seconds": 10, "output_bytes": 65536, "input_bytes": 65536,
          "session_seconds": 120}


def docker(*args, timeout=5):
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)


def preflight():
    image = os.environ.get("REPL_LAB_WORKER_IMAGE", "")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
        return {"ready": False, "reason": "Set REPL_LAB_WORKER_IMAGE to a local immutable sha256 image ID."}
    try:
        info = docker("info", "--format", "{{json .}}")
        if info.returncode:
            return {"ready": False, "reason": "Docker daemon is unavailable or denied."}
        info = json.loads(info.stdout)
        if info.get("OSType") != "linux" or not all(info.get(k) for k in ("MemoryLimit", "SwapLimit", "CpuCfsQuota", "PidsLimit")):
            return {"ready": False, "reason": "Required kernel resource controls are unavailable."}
        result = docker("image", "inspect", image)
        if result.returncode:
            return {"ready": False, "reason": "Pinned worker image is not local. No automatic pull."}
        meta = json.loads(result.stdout)[0]
        if meta["Id"] != image or meta["Config"].get("Labels", {}).get("repl-lab.worker") != "1":
            return {"ready": False, "reason": "Invalid worker image identity/label."}
        return {"ready": True, "image": image, "limits": LIMITS}
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError) as error:
        return {"ready": False, "reason": "Isolation preflight failed: " + type(error).__name__}


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


def session():
    check = preflight()
    if not check["ready"]:
        raise RuntimeError(check["reason"])
    name = "repl-lab-" + uuid.uuid4().hex
    proc = None
    try:
        created = docker(*create_args(check["image"], name))
        if created.returncode:
            raise RuntimeError("Cannot create isolated worker")
        inspect = docker("inspect", name)
        if inspect.returncode:
            raise RuntimeError("Cannot verify isolated worker")
        verify_container(json.loads(inspect.stdout)[0])
        proc = subprocess.Popen(["docker", "start", "--attach", "--interactive", name],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                bufsize=0)
        sel = selectors.DefaultSelector()
        sel.register(sys.stdin.buffer, selectors.EVENT_READ, "input")
        sel.register(proc.stdout, selectors.EVENT_READ, "output")
        sel.register(proc.stderr, selectors.EVENT_READ, "error")
        started = time.monotonic()
        deadline = started + LIMITS["wall_seconds"]
        input_size = output_size = 0
        while proc.poll() is None:
            if time.monotonic() > min(deadline, started + LIMITS["session_seconds"]):
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
                        input_size = 0
                        deadline = time.monotonic() + LIMITS["wall_seconds"]
                else:
                    output_size += len(data)
                    if output_size > LIMITS["output_bytes"]:
                        raise RuntimeError("Worker output limit")
                    target = sys.stdout.buffer if key.data == "output" else sys.stderr.buffer
                    target.write(data)
                    target.flush()
                    if b"\n" in data and key.data == "output":
                        # The controller sends one command at a time.
                        output_size = 0
                        deadline = time.monotonic() + LIMITS["wall_seconds"]
        if proc.returncode:
            raise RuntimeError("Worker failed with exit " + str(proc.returncode))
    finally:
        # Kill the execution unit, including descendants, before closing transport.
        docker("rm", "--force", name)
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)


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


def negative_tests():
    check = preflight()
    if not check["ready"]:
        print(json.dumps({"status": "UNVERIFIED", "reason": check["reason"], "tests": list(NEGATIVE)}))
        return 2
    # A positive control ensures failures are not merely broken worker startup.
    positive = subprocess.run([sys.executable, __file__, "session"],
                              input='{:source "(+ 1 2)" :bindings {}}\n', text=True,
                              capture_output=True, timeout=30)
    if positive.returncode or ':value 3' not in positive.stdout:
        raise RuntimeError("Worker positive control failed")
    results = {}
    for name, source in NEGATIVE.items():
        wire = '{:source ' + json.dumps(source) + ' :bindings {}}\n'
        result = subprocess.run([sys.executable, __file__, "session"], input=wire, text=True,
                                capture_output=True, timeout=30)
        results[name] = result.returncode != 0 or ":error" in result.stdout
    report = {"status": "TESTED" if all(results.values()) else "FAILED", "results": results, "image": check["image"]}
    if all(results.values()):
        from pathlib import Path
        Path("var").mkdir(exist_ok=True)
        Path("var/isolation-proof.json").write_text(json.dumps(report))
    print(json.dumps(report))
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    try:
        action = sys.argv[1] if len(sys.argv) > 1 else "doctor"
        if action == "doctor":
            print(json.dumps(preflight()))
        elif action == "session":
            session()
        elif action == "test":
            sys.exit(negative_tests())
        else:
            raise RuntimeError("Unknown isolation command")
    except Exception as error:
        print("Isolation refused: " + str(error), file=sys.stderr)
        sys.exit(2)
