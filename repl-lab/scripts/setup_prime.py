#!/usr/bin/env python3
"""Build unmodified pinned Prime in Docker. No model calls or host-code execution."""
import json
import hashlib
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
PIN = "c4c238ca025e382d96fb5f37e6328ca77fb82ef3"
RUST = "rust@sha256:93ce27a88655056a51dbdd8f5f2d7ddc071c7b0070fb288a37b5a285fc83971e"
PYTHON = "python@sha256:fd95fa221297a88e1cf49c55ec1828edd7c5a428187e67b5d1805692d11588db"


def run(args, *, capture=False, timeout=1800):
    print("> " + " ".join(str(a) for a in args), flush=True)
    return subprocess.run([str(a) for a in args], cwd=ROOT, capture_output=capture,
                          text=True, check=True, timeout=timeout)


def extract_source(archive, destination):
    destination.mkdir()
    with tarfile.open(archive) as stream:
        for member in stream:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or not (member.isdir() or member.isfile()):
                raise ValueError("Unexpected source archive path or link")
            target = destination.joinpath(*path.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with stream.extractfile(member) as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output)
                target.chmod(member.mode & 0o777)


def setup():
    checkout = ROOT / "var/upstream/prime-agent"
    report = {"status": "INCOMPLETE", "model_calls": 0, "prime_commit": PIN,
              "rust_image": RUST, "python_image": PYTHON, "runtime_lock": "prime-agent-runtime/uv.lock"}
    reports = ROOT / "var/prime-builds"
    reports.mkdir(parents=True, exist_ok=True)
    output = reports / (str(time.time_ns()) + ".json")
    try:
        commit = run(["git", "-C", checkout, "rev-parse", "HEAD"], capture=True).stdout.strip()
        dirty = run(["git", "-C", checkout, "status", "--porcelain"], capture=True).stdout.strip()
        if commit != PIN or dirty:
            raise ValueError("Prime checkout must be clean and match the source pin")
        run(["docker", "info", "--format", "{{.ServerVersion}}"], capture=True, timeout=20)
        build_root = ROOT / "var/prime-build-contexts"
        build_root.mkdir(exist_ok=True)
        context = Path(tempfile.mkdtemp(prefix="native-", dir=build_root))
        report["context"] = str(context.relative_to(ROOT))
        archive = context / "source.tar"
        run(["git", "-C", checkout, "archive", "--format=tar", "-o", archive, PIN], timeout=60)
        extract_source(archive, context / "source")
        archive.unlink()
        shutil.copyfile(ROOT / "benchmark/prime/Dockerfile", context / "Dockerfile")
        shutil.copyfile(ROOT / "benchmark/prime/default-packages.lock", context / "default-packages.lock")
        report["dockerfile_sha256"] = hashlib.sha256((context / "Dockerfile").read_bytes()).hexdigest()
        report["default_packages_sha256"] = hashlib.sha256((context / "default-packages.lock").read_bytes()).hexdigest()
        run(["docker", "build", "--build-arg", "RUST_IMAGE=" + RUST,
             "--build-arg", "PYTHON_IMAGE=" + PYTHON, "--build-arg", "PRIME_COMMIT=" + PIN,
             "-t", "repl-lab-prime-native", context])
        image = run(["docker", "image", "inspect", "--format", "{{.Id}}", "repl-lab-prime-native"], capture=True).stdout.strip()
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
            raise ValueError("Invalid image digest")
        report.update(status="BUILT / UNVERIFIED", image=image,
                      note="Runtime isolation and native adapter tests are still required before model execution")
        (ROOT / "var/prime-worker.env").write_text("export REPL_LAB_PRIME_IMAGE=" + image + "\n")
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        output.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({"report": str(output.relative_to(ROOT)), **report}), flush=True)


if __name__ == "__main__":
    setup()
