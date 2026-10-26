#!/usr/bin/env python3
"""Build, pin, and test Python isolation without model inference."""
import json
import os
import re
import sys
from setup_worker import ROOT, run, write_json
from python_isolation import NEGATIVE

BASE_TAG = "python:3.12.10-slim-bookworm"


def setup():
    output = ROOT / "var"
    output.mkdir(exist_ok=True)
    report = {"status": "INCOMPLETE", "base_tag": BASE_TAG, "model_calls": 0}
    try:
        run(["docker", "info", "--format", "{{.ServerVersion}}"], ROOT)
        run(["docker", "pull", BASE_TAG], ROOT)
        digests = json.loads(run(["docker", "image", "inspect", "--format", "{{json .RepoDigests}}", BASE_TAG], ROOT, capture=True).stdout)
        base = next(d for d in digests if re.fullmatch(r"(?:docker.io/library/)?python@sha256:[0-9a-f]{64}", d))
        report["base_image"] = base
        run(["docker", "build", "-f", "worker/Python.Dockerfile", "--build-arg", "BASE_IMAGE=" + base,
             "-t", "repl-lab-python-worker", "."], ROOT)
        image = run(["docker", "image", "inspect", "--format", "{{.Id}}", "repl-lab-python-worker"], ROOT, capture=True).stdout.strip()
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
            raise RuntimeError("Invalid Python worker identity")
        report["worker_image"] = image
        run([sys.executable, "scripts/python_isolation.py", "test"], ROOT, env=dict(os.environ, REPL_LAB_PYTHON_IMAGE=image))
        proof = json.loads((output / "python-isolation-proof.json").read_text())
        if (proof.get("status") != "TESTED" or proof.get("image") != image or
                set(proof.get("results", {})) != set(NEGATIVE) | {"session-reset"} or
                not all(v is True for v in proof["results"].values())):
            raise RuntimeError("Python isolation proof is incomplete")
        (output / "python-worker.env").write_text("export REPL_LAB_PYTHON_IMAGE=" + image + "\n")
        report["status"] = "TESTED"
        print("Python worker tested. Run: source var/python-worker.env. Model calls: 0.")
    finally:
        write_json(output / "python-worker-setup.json", report)


if __name__ == "__main__":
    setup()
