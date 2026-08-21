from __future__ import annotations

import os
from pathlib import Path
import platform
import subprocess
import sys
import unittest

from taatik.config import MODEL_FILENAME


ROOT = Path(__file__).resolve().parent.parent
BUILD_SCRIPT = ROOT / "scripts" / "build-macos.sh"


class MacBuildInterfaceTests(unittest.TestCase):
    def test_build_script_documents_outputs_and_optional_signing(self):
        result = subprocess.run(
            [str(BUILD_SCRIPT), "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Taatik.app", result.stdout)
        self.assertIn(".dmg", result.stdout)
        self.assertIn("TAATIK_SIGN_IDENTITY", result.stdout)
        self.assertIn("TAATIK_NOTARY_PROFILE", result.stdout)


@unittest.skipUnless(sys.platform == "darwin", "macOS artifact test")
class PackagedMacTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        configured = os.environ.get("TAATIK_MAC_APP")
        if not configured:
            raise unittest.SkipTest("TAATIK_MAC_APP is not set")
        cls.app = Path(configured).resolve()
        cls.executable = cls.app / "Contents" / "MacOS" / "Taatik"

    def test_app_has_expected_bundle_structure(self):
        self.assertTrue(self.executable.is_file())
        self.assertTrue((self.app / "Contents" / "Info.plist").is_file())

    def test_app_contains_native_ffmpeg_and_whisper(self):
        for name in ("ffmpeg", "whisper-cli"):
            matches = list((self.app / "Contents").rglob(f"bin/{name}"))
            self.assertTrue(matches, f"missing bundled {name}")
            architecture = subprocess.run(
                ["lipo", "-archs", str(matches[0])],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.split()
            self.assertIn(platform.machine(), architecture)

    def test_packaged_launcher_self_test_passes(self):
        result = subprocess.run([str(self.executable), "--self-test"], timeout=45)
        self.assertEqual(result.returncode, 0)

    def test_model_is_not_in_application_bundle(self):
        self.assertFalse(list(self.app.rglob(MODEL_FILENAME)))

    def test_https_root_certificates_are_bundled(self):
        self.assertTrue(list(self.app.rglob("cacert.pem")))

    def test_third_party_notices_are_bundled(self):
        self.assertTrue(list(self.app.rglob("THIRD_PARTY_NOTICES.md")))
        self.assertTrue(list(self.app.rglob("whisper.cpp-MIT.txt")))
        self.assertTrue(list(self.app.rglob("FFmpeg-LGPL-2.1.txt")))
        self.assertTrue(list(self.app.rglob("OpenSSL-Apache-2.0.txt")))
        self.assertTrue(list(self.app.rglob("XZ-Utils-COPYING.txt")))


if __name__ == "__main__":
    unittest.main()
