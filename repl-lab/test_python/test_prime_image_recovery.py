"""Offline recovery and image-pin controls. No Docker or model requests."""
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import prime_image_recovery as recovery
from benchmark import paired

IMAGE = "sha256:" + "a" * 64
OTHER = "sha256:" + "b" * 64


class PrimeImageRecoveryTests(unittest.TestCase):
    def fixture(self, root):
        for name in recovery.FILES:
            (root / name).write_bytes(b"FIXTURE ARCHIVE; not a Docker image")
        manifest = {"version": recovery.VERSION, "prime_commit": recovery.setup_prime.PIN,
                    "image": IMAGE, "identity": {"Id": IMAGE},
                    "files": {name: {"bytes": (root / name).stat().st_size,
                                     "sha256": recovery.digest(root / name)} for name in recovery.FILES}}
        path = root / "manifest.json"
        path.write_text(json.dumps(manifest))
        return path, recovery.digest(path)

    def test_tampered_manifest_and_archives_never_reach_docker(self):
        for target in ["manifest.json", "image.tar", "build-inputs.tar"]:
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); path, trusted = self.fixture(root)
                with (root / target).open("ab") as stream: stream.write(b"changed")
                with patch.object(recovery, "run") as run, self.assertRaises(ValueError):
                    recovery.restore(path, trusted)
                run.assert_not_called()

    def test_unexpected_file_paths_and_symlinks_are_rejected(self):
        for mode in ("path", "symlink"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); path, trusted = self.fixture(root)
                if mode == "path":
                    data = json.loads(path.read_text()); data["files"]["../outside"] = data["files"].pop("image.tar")
                    path.write_text(json.dumps(data)); trusted = recovery.digest(path)
                else:
                    (root / "image.tar").unlink(); (root / "image.tar").symlink_to(root / "build-inputs.tar")
                with patch.object(recovery, "run") as run, self.assertRaises(ValueError):
                    recovery.restore(path, trusted)
                run.assert_not_called()

    def test_restore_requires_same_image_identity_after_load(self):
        with tempfile.TemporaryDirectory() as directory:
            path, trusted = self.fixture(Path(directory))
            with patch.object(recovery, "run") as run, patch.object(recovery, "identity", return_value={"Id": IMAGE}):
                result = recovery.restore(path, trusted)
                self.assertEqual(result["image"], IMAGE)
                self.assertIn("ISOLATION STILL REQUIRED", result["status"])
                self.assertEqual(run.call_args.args[0], ["docker", "image", "load", "--input", str(path.parent / "image.tar")])
            with patch.object(recovery, "run"), patch.object(recovery, "identity", return_value={"Id": OTHER}):
                with self.assertRaisesRegex(ValueError, "identity differs"): recovery.restore(path, trusted)

    def test_identity_rejects_wrong_source_and_credential_environment(self):
        meta = {"Id": IMAGE, "Os": "linux", "Architecture": "arm64", "RootFS": {},
                "Config": {"Labels": {"repl-lab.prime-native": "true", "repl-lab.prime-commit": recovery.setup_prime.PIN}, "Env": []}}
        with patch.object(recovery, "run", return_value=json.dumps([meta]).encode()):
            self.assertEqual(recovery.identity(IMAGE), meta)
        credential, wrong_source = copy.deepcopy(meta), copy.deepcopy(meta)
        credential["Config"]["Env"] = ["ANTHROPIC_API_KEY=FIXTURE"]
        wrong_source["Config"]["Labels"]["repl-lab.prime-commit"] = "wrong"
        for changed in [credential, wrong_source]:
            with patch.object(recovery, "run", return_value=json.dumps([changed]).encode()), self.assertRaises(ValueError):
                recovery.identity(IMAGE)

    def test_preflight_rejects_changed_images_even_with_matching_new_proofs(self):
        config = json.loads((paired.ROOT / "config/external-subscription-proposal-v7.json").read_text())
        config["execution_images"] = {"sci": IMAGE, "prime": IMAGE}
        paired.validate_config(config)
        for bad in [{"sci": IMAGE}, {"sci": "latest", "prime": IMAGE}, {"sci": IMAGE, "prime": True}]:
            with self.assertRaises(ValueError): paired.validate_config({**config, "execution_images": bad})
        for changed_arm in (None, "sci", "prime"):
            with self.subTest(changed_arm=changed_arm), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); (root / "var").mkdir()
                images = {"sci": IMAGE, "prime": IMAGE}
                if changed_arm: images[changed_arm] = OTHER
                (root / "var/isolation-proof.json").write_text(json.dumps({"gate-version": 2, "image": images["sci"]}))
                proof = {"evidence": "FIXTURE", "status": "PASSED", "runtime_source": {},
                         "transport_contract": paired.transport_contract(config),
                         "sci_image": images["sci"], "prime_image": images["prime"],
                         "provider": config["provider"], "subscription_protocol": config["subscription_protocol"],
                         "checks": dict.fromkeys(["native_root", "native_child", "native_tool", "native_compaction",
                             "native_refinement", "native_signed_thinking", "sci_context", "shared_budget", "cleanup",
                             "command_correction", "rejected_fragment_not_executed", "oauth_protocol"], True)}
                (root / "var/subscription-relay-proof.json").write_text(json.dumps(proof))
                value = {"config": config, "runtime_source": {}, "plan_sha256": "fixture"}
                with patch.object(paired, "ROOT", root), patch.object(paired, "read_plan", return_value=(value, {}, {})), \
                     patch("benchmark.prime.isolation.require_tested", return_value={"image": images["prime"]}), \
                     patch.object(paired.subprocess, "run", return_value=SimpleNamespace(returncode=0)):
                    result = paired.preflight("unused", "unused")
                self.assertEqual(result["ready"], changed_arm is None)
                if changed_arm: self.assertIn("image differs from frozen plan", " ".join(result["blockers"]))


if __name__ == "__main__":
    unittest.main()
