import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("isolation", Path(__file__).parents[1] / "scripts/isolation.py")
isolation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(isolation)


class IsolationConfigurationTests(unittest.TestCase):
    def test_no_implicit_image_or_download(self):
        with patch.dict("os.environ", {}, clear=True), patch.object(isolation, "docker") as docker:
            self.assertFalse(isolation.preflight()["ready"])
            docker.assert_not_called()

    def test_all_required_create_flags(self):
        args = isolation.create_args("sha256:" + "a" * 64, "fixture")
        for flag in ["--network", "--read-only", "--user", "--cap-drop", "--security-opt",
                     "--memory", "--memory-swap", "--cpus", "--pids-limit", "--tmpfs", "--log-driver"]:
            self.assertIn(flag, args)
        self.assertNotIn("--volume", args)
        self.assertNotIn("--privileged", args)
        self.assertNotIn("--env", args)

    def test_inspection_mismatch_fails_closed(self):
        host = {"NetworkMode": "none", "ReadonlyRootfs": True, "Memory": 256 * 1024**2,
                "MemorySwap": 256 * 1024**2, "NanoCpus": 1000000000, "PidsLimit": 32,
                "CapDrop": ["ALL"], "SecurityOpt": ["no-new-privileges:true"],
                "LogConfig": {"Type": "none"}, "Tmpfs": {"/tmp": "rw,noexec,nosuid,nodev,size=8m"}}
        meta = {"HostConfig": host, "Config": {"User": "65534:65534"}, "Mounts": []}
        isolation.verify_container(meta)
        for key, value in [("NetworkMode", "host"), ("Memory", 0), ("PidsLimit", 0),
                           ("Privileged", True), ("Binds", ["/host:/host"]), ("ReadonlyRootfs", False)]:
            changed = {**meta, "HostConfig": {**host, key: value}}
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                isolation.verify_container(changed)


if __name__ == "__main__":
    unittest.main()
