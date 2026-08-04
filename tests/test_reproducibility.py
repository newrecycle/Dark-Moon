#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import re
import unittest

REPO = Path(__file__).resolve().parents[1]


class ReproducibilityTests(unittest.TestCase):
    def test_mcp_image_requires_hash_locked_dependencies(self) -> None:
        dockerfile = (REPO / "Dockerfile.mcp").read_text(encoding="utf-8")
        self.assertRegex(dockerfile.splitlines()[0], r"^FROM python:3\.12-slim@sha256:[0-9a-f]{64}$")
        self.assertIn("--require-hashes", dockerfile)
        self.assertIn("--requirement requirements.lock", dockerfile)

    def test_every_locked_requirement_has_at_least_one_hash(self) -> None:
        lock = (REPO / "mcp" / "requirements.lock").read_text(encoding="utf-8")
        starts = list(re.finditer(r"(?m)^([A-Za-z0-9][A-Za-z0-9_.-]*==[^\s\\]+)(?:\s*\\)?$", lock))
        self.assertGreater(len(starts), 25)
        for index, match in enumerate(starts):
            end = starts[index + 1].start() if index + 1 < len(starts) else len(lock)
            block = lock[match.start():end]
            with self.subTest(requirement=match.group(1)):
                self.assertIn("--hash=sha256:", block)

    def test_lock_inputs_are_exact_direct_pins(self) -> None:
        lines = [
            line.strip()
            for line in (REPO / "mcp" / "requirements.in").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        self.assertGreaterEqual(len(lines), 5)
        self.assertTrue(all(re.fullmatch(r"[A-Za-z0-9_.-]+==[^=<>!~\s]+", line) for line in lines))


if __name__ == "__main__":
    unittest.main(verbosity=2)
