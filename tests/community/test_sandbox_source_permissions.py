"""Non-root sandbox copies stay readable without widening operator permissions."""
import os
import stat
import tempfile
import unittest
from pathlib import Path

from community.remediation import Sandbox


class SandboxSourcePermissionTests(unittest.TestCase):
    def test_private_tree_is_staged_readably_without_git_or_symlink_target_chmod(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            repo.mkdir(mode=0o700)
            (repo / "app.py").write_text("print('owned')\n")
            (repo / "app.py").chmod(0o600)
            (repo / "script").write_text("#!/bin/sh\nexit 0\n")
            (repo / "script").chmod(0o700)
            (repo / ".git").mkdir()
            (repo / ".git" / "config").write_text("PRIVATE-GIT-METADATA")
            target = root / "outside"
            target.write_text("private outside")
            target.chmod(0o600)
            (repo / "link").symlink_to(target)
            seen = []
            def run(argv, timeout):
                if argv[:2] == ["docker", "run"]:
                    mount = argv[argv.index("--mount") + 1]
                    source = Path(mount.split("src=", 1)[1].split(",dst=", 1)[0])
                    seen.append(source)
                    self.assertNotEqual(source, repo)
                    self.assertEqual(stat.S_IMODE(source.parent.stat().st_mode), 0o700)
                    self.assertEqual(stat.S_IMODE(source.stat().st_mode), 0o755)
                    self.assertEqual(stat.S_IMODE((source / "app.py").stat().st_mode), 0o644)
                    self.assertEqual(stat.S_IMODE((source / "script").stat().st_mode), 0o755)
                    self.assertFalse((source / ".git").exists())
                    self.assertTrue((source / "link").is_symlink())
                    self.assertEqual(os.readlink(source / "link"), str(target))
                    self.assertIn("--user=65534:65534", argv)
                    self.assertIn("--network=none", argv)
                    self.assertIn("--read-only", argv)
                    self.assertTrue(mount.endswith(",readonly"))
                return {"exit_code": 0, "output": "owned", "timed_out": False}
            result = Sandbox("owned:fixture", run=run).probe(repo, {"argv": ["python", "app.py"]})
            self.assertFalse(result["infrastructure_error"])
            self.assertFalse(seen[0].exists())
            self.assertEqual(stat.S_IMODE(repo.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE((repo / "app.py").stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)

    def test_staging_is_removed_when_container_execution_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            source = None
            def run(argv, timeout):
                nonlocal source
                if argv[:2] == ["docker", "run"]:
                    source = Path(argv[argv.index("--mount") + 1].split("src=", 1)[1].split(",dst=", 1)[0])
                    raise RuntimeError("Owned engine failure")
                return {"exit_code": 0}
            with self.assertRaises(RuntimeError):
                Sandbox("owned:fixture", run=run).probe(directory, {"argv": ["true"]})
            self.assertFalse(source.exists())
