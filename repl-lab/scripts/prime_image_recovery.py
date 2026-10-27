#!/usr/bin/env python3
"""Archive/restore one pinned Prime build. No inference, credentials, or host-code execution.

The trusted manifest hash must come from the committed recovery record, not from
an untrusted archive. Restoration never selects an image for a live experiment.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile

from scripts import setup_prime

ROOT = Path(__file__).resolve().parents[1]
VERSION = "prime-image-recovery-v1"
FILES = {"image.tar", "build-inputs.tar"}


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest() if hasattr(hashlib, "file_digest") else _digest(stream)


def _digest(stream):
    result = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        result.update(block)
    return result.hexdigest()


def run(arguments, timeout=600):
    return subprocess.run(arguments, check=True, capture_output=True, timeout=timeout).stdout


def identity(image):
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
        raise ValueError("Immutable image identity required")
    meta = json.loads(run(["docker", "image", "inspect", image], timeout=10))[0]
    labels = meta["Config"].get("Labels", {})
    if (meta["Id"] != image or meta["Os"] != "linux" or
            labels.get("repl-lab.prime-native") != "true" or
            labels.get("repl-lab.prime-commit") != setup_prime.PIN):
        raise ValueError("Native image identity/source labels differ")
    # Config includes only build-time values. Refuse credential-shaped names.
    if any(re.search(r"API_KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL", value.split("=", 1)[0], re.I)
           for value in meta["Config"].get("Env", [])):
        raise ValueError("Credential-shaped image environment refused")
    return {key: meta[key] for key in ("Id", "Architecture", "Os", "RootFS", "Config")}


def seal(report_path, output):
    report_path, output = Path(report_path), Path(output)
    report = json.loads(report_path.read_text())
    if (report.get("status") != "BUILT / UNVERIFIED" or report.get("prime_commit") != setup_prime.PIN or
            report.get("rust_image") != setup_prime.RUST or report.get("python_image") != setup_prime.PYTHON):
        raise ValueError("Pinned successful build report required")
    context = (ROOT / report["context"]).resolve()
    if ROOT / "var/prime-build-contexts" not in context.parents:
        raise ValueError("Build context is outside the audited build directory")
    for name, key in [("Dockerfile", "dockerfile_sha256"), ("default-packages.lock", "default_packages_sha256")]:
        if digest(context / name) != report[key]:
            raise ValueError("Build input changed: " + name)
    meta = identity(report["image"])
    output.mkdir(parents=True, exist_ok=False)
    # Git archive contains only tracked source at the fixed commit, never .git or credentials.
    source_tar = output / "source.tar"
    source_tar.write_bytes(run(["git", "-C", str(ROOT / "var/upstream/prime-agent"),
                                "archive", "--format=tar", setup_prime.PIN], timeout=60))
    expected = {}
    with tarfile.open(source_tar) as archive:
        for member in archive:
            if member.isdir():
                continue
            if not member.isfile():
                raise ValueError("Unexpected upstream source entry")
            with archive.extractfile(member) as stream:
                expected[member.name] = _digest(stream)
    actual = {str(p.relative_to(context / "source")): digest(p)
              for p in (context / "source").rglob("*") if p.is_file()}
    if expected != actual:
        raise ValueError("Build context differs from pinned upstream source")
    with tarfile.open(output / "build-inputs.tar", "w") as archive:
        archive.add(source_tar, arcname="source.tar")
        archive.add(context / "Dockerfile", arcname="Dockerfile")
        archive.add(context / "default-packages.lock", arcname="default-packages.lock")
        archive.add(report_path, arcname="build-report.json")
    source_tar.unlink()
    run(["docker", "image", "save", "--output", str(output / "image.tar"), report["image"]])
    manifest = {"version": VERSION, "image": report["image"], "prime_commit": setup_prime.PIN,
                "identity": meta, "build_report": report, "source_files": expected,
                "files": {name: {"sha256": digest(output / name), "bytes": (output / name).stat().st_size}
                          for name in sorted(FILES)},
                "model_calls": 0, "isolation": "fresh native gate and relay required before live use"}
    path = output / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return {"manifest": str(path), "manifest_sha256": digest(path), "image": report["image"], "model_calls": 0}


def verify(path, trusted_hash):
    path = Path(path)
    if not re.fullmatch(r"[0-9a-f]{64}", trusted_hash) or digest(path) != trusted_hash:
        raise ValueError("Manifest does not match the independently trusted hash")
    manifest = json.loads(path.read_text())
    if (manifest.get("version") != VERSION or manifest.get("prime_commit") != setup_prime.PIN or
            set(manifest.get("files", {})) != FILES or
            not re.fullmatch(r"sha256:[0-9a-f]{64}", manifest.get("image", "")) or
            manifest.get("identity", {}).get("Id") != manifest["image"]):
        raise ValueError("Invalid recovery manifest")
    for name, record in manifest["files"].items():
        file = path.parent / name
        if (file.is_symlink() or not file.is_file() or file.stat().st_size != record["bytes"] or
                digest(file) != record["sha256"]):
            raise ValueError("Recovery artifact differs: " + name)
    return manifest


def restore(path, trusted_hash):
    manifest = verify(path, trusted_hash)  # Verify everything before mutating Docker.
    run(["docker", "image", "load", "--input", str(Path(path).parent / "image.tar")])
    if identity(manifest["image"]) != manifest["identity"]:
        raise ValueError("Restored image configuration or filesystem identity differs")
    return {"status": "RESTORED / ISOLATION STILL REQUIRED", "image": manifest["image"], "model_calls": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    command = commands.add_parser("seal")
    command.add_argument("--build-report", required=True, type=Path)
    command.add_argument("--out", required=True, type=Path)
    for action in ("verify", "restore"):
        command = commands.add_parser(action)
        command.add_argument("--manifest", required=True, type=Path)
        command.add_argument("--trusted-manifest-sha256", required=True)
    args = parser.parse_args()
    if args.action == "seal":
        result = seal(args.build_report, args.out)
    elif args.action == "restore":
        result = restore(args.manifest, args.trusted_manifest_sha256)
    else:
        manifest = verify(args.manifest, args.trusted_manifest_sha256)
        result = {"status": "ARCHIVES VERIFIED", "image": manifest["image"], "model_calls": 0}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
