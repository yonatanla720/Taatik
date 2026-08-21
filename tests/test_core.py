from pathlib import Path
import os
import tempfile
import unittest

from taatik.core import (
    TranscriptionError, conversion_command, format_duration, parse_duration, parse_progress,
    transcription_command, output_file, transcribe, unique_output_base, validate_input,
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

    def test_parse_duration_reads_ffmpeg_summary(self):
        line = "  Duration: 00:58:24.20, start: 0.000000, bitrate: 128 kb/s"
        self.assertAlmostEqual(parse_duration(line), 3504.2, places=1)
        self.assertIsNone(parse_duration("no duration here"))

    def test_format_duration(self):
        self.assertEqual(format_duration(75), "1:15")
        self.assertEqual(format_duration(3504), "58:24")
        self.assertEqual(format_duration(3661), "1:01:01")

    def test_output_names_do_not_overwrite_existing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "lesson.txt").write_text("old", encoding="utf-8")
            self.assertEqual(unique_output_base(Path("lesson.mp4"), output).name, "lesson (2)")

    def test_output_extension_preserves_dots_in_recording_name(self):
        self.assertEqual(output_file(Path("lesson.part1"), ".txt"), Path("lesson.part1.txt"))

    def test_rejects_unsupported_input(self):
        with tempfile.TemporaryDirectory() as directory:
            bad = Path(directory) / "notes.pdf"
            bad.touch()
            with self.assertRaisesRegex(TranscriptionError, "not supported"):
                validate_input(bad)

    @unittest.skipIf(os.name == "nt", "uses POSIX test executables")
    def test_transcription_pipeline_generates_both_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "recording.wav"
            source.touch()
            model = root / "model.bin"
            model.touch()
            ffmpeg = root / "ffmpeg"
            ffmpeg.write_text(
                '#!/bin/sh\nfor output do :; done\nprintf "wav" > "$output"\n',
                encoding="utf-8",
            )
            whisper = root / "whisper-cli"
            whisper.write_text(
                "#!/bin/sh\n"
                "while [ \"$#\" -gt 0 ]; do\n"
                "  if [ \"$1\" = \"-of\" ]; then base=$2; fi\n"
                "  shift\n"
                "done\n"
                'printf "שלום\\n" > "$base.txt"\n'
                'printf "1\\n00:00:00,000 --> 00:00:01,000\\nשלום\\n" > "$base.srt"\n',
                encoding="utf-8",
            )
            ffmpeg.chmod(0o755)
            whisper.chmod(0o755)

            txt, srt = transcribe(
                source,
                root / "output",
                model,
                ffmpeg,
                whisper,
                root / "temporary.wav",
                lambda _value, _message: None,
            )

            self.assertEqual(txt.read_text(encoding="utf-8"), "שלום\n")
            self.assertIn("00:00:00,000 --> 00:00:01,000", srt.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
