"""Disposable native Prime containers. No host mounts, credentials, or inference."""
import contextlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import selectors
import subprocess
import tarfile
import time
import uuid

from scripts import isolation

PIN = "c4c238ca025e382d96fb5f37e6328ca77fb82ef3"
WORK_TMPFS = "rw,nosuid,nodev,size=8m,uid=65534,gid=65534"
TASK_SECONDS = 120
INPUT_LIMIT = 65536
OUTPUT_LIMIT = 4 * 1024**2
ARCHIVE_LIMIT = 16 * 1024**2


def checked(args, timeout=10):
    result = isolation.docker(*args, timeout=timeout)
    if result.returncode:
        raise RuntimeError("Docker operation failed: " + args[0])
    return result.stdout


def doctor():
    if isolation.QUARANTINE.exists() and any(isolation.QUARANTINE.iterdir()):
        return {"ready": False, "reason": "Unconfirmed worker cleanup"}
    image = os.environ.get("REPL_LAB_PRIME_IMAGE", "")
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", image):
        return {"ready": False, "reason": "Source var/prime-worker.env after building the native image"}
    try:
        info = json.loads(checked(["info", "--format", "{{json .}}"] ))
        required = ("MemoryLimit", "SwapLimit", "CpuCfsQuota", "PidsLimit")
        if info.get("OSType") != "linux" or not all(info.get(k) for k in required):
            raise RuntimeError("Required Docker resource controls are unavailable")
        meta = json.loads(checked(["image", "inspect", image]))[0]
        labels = meta["Config"].get("Labels", {})
        if meta["Id"] != image or labels.get("repl-lab.prime-native") != "true" or labels.get("repl-lab.prime-commit") != PIN:
            raise RuntimeError("Native image source pin or identity differs")
        return {"ready": True, "image": image, "commit": PIN, "model_calls": 0,
                "limits": {"memory_mb": 256, "cpus": 1, "pids": 32, "scratch_mb": 8, "work_mb": 8,
                           "task_wall_seconds": TASK_SECONDS, "expression_wall_seconds": None,
                           "input_bytes": INPUT_LIMIT, "task_output_bytes": OUTPUT_LIMIT,
                           "archive_bytes": ARCHIVE_LIMIT},
                "note": "Preflight only; runtime isolation proof is separate"}
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
        return {"ready": False, "reason": str(error)}


@contextlib.contextmanager
def container(image, arguments, entrypoint=None):
    name = "repl-lab-" + uuid.uuid4().hex
    try:
        args = isolation.create_args(image, name)
        options = ["--tmpfs", "/work:" + WORK_TMPFS, "--workdir", "/work"]
        if entrypoint is not None:
            options.extend(["--entrypoint", entrypoint])
        checked(args[:-1] + options + [image] + list(arguments))
        meta = json.loads(checked(["inspect", name]))[0]
        isolation.verify_container(meta)
        if meta["HostConfig"].get("Tmpfs") != {"/tmp": "rw,noexec,nosuid,nodev,size=8m", "/work": WORK_TMPFS}:
            raise RuntimeError("Unexpected native scratch mounts")
        if any(m.get("Type") != "tmpfs" for m in meta.get("Mounts", [])):
            raise RuntimeError("Native fixture must not mount host or persistent data")
        yield name, meta
    finally:
        isolation.cleanup(name)


def bounded_process(arguments, payload=b"", *, seconds=TASK_SECONDS, max_output=OUTPUT_LIMIT, completion_type=None):
    """Bound both streams while draining; never trust a container to bound output."""
    begin = time.monotonic()
    process = subprocess.Popen(arguments, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    streams = {"stdout": bytearray(), "stderr": bytearray()}
    reason = None
    completion = None
    lines = bytearray()
    try:
        # Inputs are small controller-owned JSON, not generated shell commands.
        if len(payload) > INPUT_LIMIT:
            raise ValueError("Native request input limit")
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ, "stdout")
        selector.register(process.stderr, selectors.EVENT_READ, "stderr")
        sent = 0
        if payload:
            os.set_blocking(process.stdin.fileno(), False)
            selector.register(process.stdin, selectors.EVENT_WRITE, "stdin")
        else:
            process.stdin.close()
        while selector.get_map():
            if time.monotonic() - begin > seconds:
                reason = "wall-time-limit"
                break
            for key, _ in selector.select(0.1):
                if key.data == "stdin":
                    try:
                        sent += os.write(key.fd, payload[sent:sent + 4096])
                    except BlockingIOError:
                        continue
                    except BrokenPipeError:
                        sent = len(payload)
                    if sent == len(payload):
                        selector.unregister(key.fileobj)
                        process.stdin.close()
                    continue
                data = os.read(key.fd, 65536)
                if not data:
                    selector.unregister(key.fileobj)
                    continue
                if sum(map(len, streams.values())) + len(data) > max_output:
                    reason = "output-limit"
                    break
                streams[key.data].extend(data)
                if key.data == "stdout" and completion_type:
                    lines.extend(data)
                    while b'\n' in lines:
                        line, _, rest = lines.partition(b'\n')
                        lines = bytearray(rest)
                        try:
                            event = json.loads(line)
                        except (ValueError, UnicodeDecodeError):
                            continue
                        if isinstance(event, dict) and event.get('type') == completion_type:
                            completion = event
                            break
            if reason or completion:
                break
        selector.close()
        if reason or completion:
            # SIGKILL only the attach client. The context manager owns container
            # cleanup; the bootstrap keeps tmpfs alive for bounded collection.
            process.kill()
        try:
            code = process.wait(timeout=max(1, seconds - (time.monotonic() - begin)))
        except subprocess.TimeoutExpired:
            reason = "wall-time-limit"
            process.kill()
            code = process.wait(timeout=5)
        return {**{k: bytes(v) for k, v in streams.items()}, "exit_code": code,
                "failure": reason, "completion": completion, "wall_ms": (time.monotonic() - begin) * 1000}
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        process.stdout.close()
        process.stderr.close()
        if not process.stdin.closed:
            process.stdin.close()


def execute(name, payload=b"", **limits):
    return bounded_process(["docker", "start", "--attach", "--interactive", name], payload, **limits)


def snapshot(name):
    # Docker cp reads the root filesystem and can omit tmpfs contents. Archive
    # from inside the running mount namespace while the fixed bootstrap waits.
    source = "import sys,tarfile\nwith tarfile.open(fileobj=sys.stdout.buffer, mode='w|') as output:\n    output.add('/work', arcname='.')"
    result = bounded_process(["docker", "exec", name, "/opt/venv/bin/python", "-c", source], seconds=20, max_output=ARCHIVE_LIMIT)
    if result["failure"] or result["exit_code"]:
        raise RuntimeError("Native artifact collection failed or exceeded limits")
    return result["stdout"]


def regular_files(archive):
    """Read data only. Never restore symlinks, pickle snapshots, or executable state."""
    files = {}
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as stream:
        for member in stream:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("Unsafe native artifact path")
            if member.isdir():
                continue
            if not member.isfile() or member.size > 8 * 1024**2:
                raise ValueError("Unsafe native artifact type or size")
            name = str(path)
            if name in files:
                raise ValueError("Duplicate native artifact path")
            with stream.extractfile(member) as source:
                files[name] = source.read()
    return files
