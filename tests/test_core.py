from pathlib import Path
import tempfile
import unittest

from taatik.core import (
    TranscriptionError, conversion_command, parse_progress, transcription_command,
    unique_output_base, validate_input,
)


class CoreTests(unittest.TestCase):
    def test_conversion_is_mono_16khz_pcm(self):
        wav = Path("audio.wav")
        command = conversion_command(Path("ffmpeg.exe"), Path("lesson.mp4"), wav)
        self.assertEqual(
            command[-8:],
            ["-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)],
        )

    def test_transcription_forces_hebrew_and_writes_both_formats(self):
        command = transcription_command(
            Path("whisper-cli.exe"), Path("model.bin"), Path("audio.wav"), Path("result")
        )
        self.assertEqual(command[command.index("-l") + 1], "he")
        self.assertIn("-otxt", command)
        self.assertIn("-osrt", command)

    def test_parse_progress(self):
        self.assertEqual(parse_progress("whisper_print_progress: progress = 42%"), 42)
        self.assertIsNone(parse_progress("noise"))

    def test_output_names_do_not_overwrite_existing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "lesson.txt").write_text("old", encoding="utf-8")
            self.assertEqual(unique_output_base(Path("lesson.mp4"), output).name, "lesson (2)")

    def test_rejects_unsupported_input(self):
        with tempfile.TemporaryDirectory() as directory:
            bad = Path(directory) / "notes.pdf"
            bad.touch()
            with self.assertRaisesRegex(TranscriptionError, "not supported"):
                validate_input(bad)


if __name__ == "__main__":
    unittest.main()
