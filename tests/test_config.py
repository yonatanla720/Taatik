import os
from pathlib import Path
import unittest
from unittest.mock import patch

from taatik.config import MIN_MODEL_BYTES, data_dir, model_is_ready


class DataDirectoryTests(unittest.TestCase):
    def test_macos_uses_application_support(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("taatik.config.sys.platform", "darwin"),
            patch.object(Path, "home", return_value=Path("/Users/example")),
        ):
            self.assertEqual(
                data_dir(),
                Path("/Users/example/Library/Application Support/Taatik"),
            )

    def test_windows_keeps_local_app_data_location(self):
        with (
            patch.dict(os.environ, {"LOCALAPPDATA": r"C:\Users\example\AppData\Local"}, clear=True),
            patch("taatik.config.sys.platform", "win32"),
        ):
            self.assertEqual(
                data_dir(),
                Path(r"C:\Users\example\AppData\Local") / "Taatik",
            )

    def test_model_is_ready_only_after_complete_download(self):
        with patch("taatik.config.Path.is_file", return_value=True):
            incomplete = unittest.mock.Mock()
            incomplete.st_size = MIN_MODEL_BYTES - 1
            complete = unittest.mock.Mock()
            complete.st_size = MIN_MODEL_BYTES
            with patch("taatik.config.Path.stat", return_value=incomplete):
                self.assertFalse(model_is_ready(Path("model.bin")))
            with patch("taatik.config.Path.stat", return_value=complete):
                self.assertTrue(model_is_ready(Path("model.bin")))


if __name__ == "__main__":
    unittest.main()
