import unittest

from taatik.diarization import _srt_time, label_transcript, parse_srt


SRT = """1
00:00:00,000 --> 00:00:05,000
hello there

2
00:00:06,000 --> 00:00:10,000
general kenobi
"""


class DiarizationMergeTests(unittest.TestCase):
    def test_parse_srt(self):
        cues = parse_srt(SRT)
        self.assertEqual(len(cues), 2)
        self.assertEqual(cues[0], (0.0, 5.0, "hello there"))
        self.assertEqual(cues[1][2], "general kenobi")

    def test_srt_time_roundtrip_format(self):
        self.assertEqual(_srt_time(3661.5), "01:01:01,500")
        self.assertEqual(_srt_time(0), "00:00:00,000")

    def test_label_transcript_assigns_by_overlap(self):
        # Speaker 0 owns the first cue, speaker 1 the second; both above the
        # min-speech threshold so both are kept and relabelled 1 and 2.
        diar = [
            {"start": 0.0, "end": 5.5, "speaker": 0},
            {"start": 5.5, "end": 12.0, "speaker": 1},
            {"start": 25.0, "end": 30.0, "speaker": 1},
            {"start": 30.0, "end": 40.0, "speaker": 0},
        ]
        txt, srt = label_transcript(SRT, diar, num_speakers=0)
        self.assertIn("Speaker 1: hello there", srt)
        self.assertIn("Speaker 2: general kenobi", srt)
        # Two different speakers -> two turns in the text output.
        self.assertEqual(txt.count("] Speaker"), 2)

    def test_label_transcript_top_k_caps_speakers(self):
        diar = [
            {"start": 0.0, "end": 5.0, "speaker": 0},
            {"start": 6.0, "end": 10.0, "speaker": 7},  # minor cluster
        ]
        # Cap to a single speaker: everything collapses to Speaker 1.
        _txt, srt = label_transcript(SRT, diar, num_speakers=1)
        self.assertIn("Speaker 1:", srt)
        self.assertNotIn("Speaker 2:", srt)


if __name__ == "__main__":
    unittest.main()
