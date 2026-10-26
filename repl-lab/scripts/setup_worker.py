#!/usr/bin/env python3
"""Build and test the local worker. Never calls a model or changes Docker permissions."""
import datetime
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
BASE_TAG = "clojure:temurin-21-tools-deps-1.12.6.1673-bookworm-slim"
CASES = {"loop", "allocation", "oversized-result", "read", "write", "process", "network", "evaluator", "reader-eval"}


def run(argv, root, *, capture=False, env=None):
    print("> " + shlex.join(map(str, argv)), flush=True)
    return subprocess.run(argv, cwd=root, env=env, check=True, text=True,
                          stdout=subprocess.PIPE if capture else None)


def write_json(path, data):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n")
    temporary.replace(path)


def setup(root=ROOT):
    root = Path(root)
    output = root / "var"
    output.mkdir(parents=True, exist_ok=True)
    report_path = output / "worker-setup.json"
    report = {"status": "INCOMPLETE", "stage": "docker-access", "base_tag": BASE_TAG,
              "started": datetime.datetime.now(datetime.timezone.utc).isoformat(), "model_calls": 0}

    def stage(name):
        report["stage"] = name
        write_json(report_path, report)

    try:
        stage("docker-access")
        version = run(["docker", "info", "--format", "{{.ServerVersion}}"], root, capture=True).stdout.strip()
        if not version:
            raise RuntimeError("Docker returned no server version")
        report["docker_server_version"] = version
        stage("pull-base")
        run(["docker", "pull", BASE_TAG], root)
        digests = json.loads(run(["docker", "image", "inspect", "--format", "{{json .RepoDigests}}", BASE_TAG],
                                 root, capture=True).stdout)
        pinned = next((d for d in (digests or []) if re.fullmatch(r"(?:docker.io/library/)?clojure@sha256:[0-9a-f]{64}", d)), None)
        if not pinned:
            raise RuntimeError("The official base image has no immutable repository digest")
        report["base_image"] = pinned
        stage("build-worker")
        run(["docker", "build", "-f", "worker/Dockerfile", "--build-arg", "BASE_IMAGE=" + pinned,
             "-t", "repl-lab-worker", "."], root)
        image = run(["docker", "image", "inspect", "--format", "{{.Id}}", "repl-lab-worker"],
                    root, capture=True).stdout.strip()
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
            raise RuntimeError("Invalid local worker image ID")
        report["worker_image"] = image
        stage("isolation-tests")
        proof_path = output / "isolation-proof.json"
        # Keep earlier evidence without allowing a failed rerun to reuse its pass.
        if proof_path.exists():
            archive = output / ("isolation-proof-before-setup-" + str(time.time_ns()) + ".json")
            proof_path.replace(archive)
        environment = dict(os.environ, REPL_LAB_WORKER_IMAGE=image)
        run([sys.executable, "scripts/isolation.py", "test"], root, env=environment)
        proof = json.loads(proof_path.read_text())
        if (proof.get("status") != "TESTED" or proof.get("image") != image
                or set(proof.get("results", {})) != CASES
                or not all(value is True for value in proof["results"].values())):
            raise RuntimeError("The isolation proof is incomplete or does not match this worker")
        # Safe to source: the only value is the validated immutable image ID.
        (output / "worker.env").write_text("export REPL_LAB_WORKER_IMAGE=" + image + "\n")
        report.update(status="TESTED", stage="complete", isolation_proof=str(proof_path))
        write_json(report_path, report)
        print("Worker built. Positive control and all nine negative isolation tests passed.", flush=True)
        print("Use this image in the same terminal: source var/worker.env", flush=True)
        print("Model calls: 0. Paid execution still requires separate approval and private credentials.", flush=True)
        return report
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        report.update(status="FAILED", error=str(error))
        write_json(report_path, report)
        if report["stage"] == "docker-access":
            print("Docker is unavailable to this process. Start Docker Desktop and run make worker-setup in your Mac Terminal.", file=sys.stderr)
        raise


if __name__ == "__main__":
    try:
        setup()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print("Worker setup stopped: " + str(error), file=sys.stderr)
        sys.exit(2)
