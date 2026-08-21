"""Offline speaker diarization and merging with the transcript.

Uses sherpa-onnx (ONNX, no PyTorch) to segment the audio by speaker, then
labels each transcript cue with the speaker who overlaps it most. Heavy
dependencies are imported lazily so the rest of the app runs without them.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from .core import TranscriptionCancelled, TranscriptionError

# Distance threshold for automatic clustering when the speaker count is unknown.
_AUTO_THRESHOLD = 0.6
# Ignore clusters with less than this much total speech when auto-detecting.
_MIN_SPEAKER_SECONDS = 8.0


def diarize(
    wav: Path,
    segmentation: Path,
    embedding: Path,
    num_speakers: int = 0,
    progress: Callable[[int], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> list[dict]:
    """Return speaker segments [{start, end, speaker}] sorted by start time."""
    try:
        import numpy as np
        import soundfile as sf
        import sherpa_onnx
    except ImportError as exc:  # pragma: no cover - packaging guard
        raise TranscriptionError(f"Speaker separation is unavailable: {exc}") from exc

    config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(model=str(segmentation)),
        ),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(embedding)),
        # Always cluster in automatic mode. Forcing a fixed num_clusters makes
        # sherpa-onnx collapse everything into one dominant speaker and peel off
        # only tiny scraps for the rest. The requested speaker count is applied
        # afterwards in label_transcript, by keeping the top-K speakers.
        clustering=sherpa_onnx.FastClusteringConfig(num_clusters=-1, threshold=_AUTO_THRESHOLD),
        min_duration_on=0.3,
        min_duration_off=0.5,
    )
    if not config.validate():
        raise TranscriptionError("Speaker separation models could not be loaded.")

    sd = sherpa_onnx.OfflineSpeakerDiarization(config)
    audio, sample_rate = sf.read(str(wav), dtype="float32", always_2d=False)
    if getattr(audio, "ndim", 1) > 1:
        audio = audio[:, 0]
    audio = np.ascontiguousarray(audio)
    if sample_rate != sd.sample_rate:
        raise TranscriptionError("Audio sample rate does not match the speaker models.")

    last = -1

    def on_progress(done: int, total: int) -> int:
        nonlocal last
        if is_cancelled and is_cancelled():
            raise TranscriptionCancelled()
        pct = int(done / total * 100) if total else 0
        if progress and pct != last:
            last = pct
            progress(pct)
        return 0

    result = sd.process(audio, callback=on_progress).sort_by_start_time()
    return [{"start": s.start, "end": s.end, "speaker": s.speaker} for s in result]


def _label_map(segments: list[dict], num_speakers: int) -> tuple[list[dict], dict]:
    """Pick the real speakers and map them to Speaker 1..N by first appearance."""
    totals: dict[int, float] = {}
    for s in segments:
        totals[s["speaker"]] = totals.get(s["speaker"], 0.0) + s["end"] - s["start"]
    if num_speakers and num_speakers > 0:
        keep = sorted(totals, key=totals.get, reverse=True)[:num_speakers]
    else:
        keep = [spk for spk, tot in totals.items() if tot >= _MIN_SPEAKER_SECONDS] or list(totals)
    kept = set(keep)
    main = [s for s in segments if s["speaker"] in kept]
    order: list[int] = []
    for s in sorted(main, key=lambda s: s["start"]):
        if s["speaker"] not in order:
            order.append(s["speaker"])
    return main, {spk: i + 1 for i, spk in enumerate(order)}


def _assign(diar: list[dict], start: float, end: float) -> int:
    best, best_overlap = None, 0.0
    for d in diar:
        overlap = min(end, d["end"]) - max(start, d["start"])
        if overlap > best_overlap:
            best_overlap, best = overlap, d["speaker"]
    if best is not None:
        return best
    mid = (start + end) / 2
    nearest = min(diar, key=lambda d: min(abs(mid - d["start"]), abs(mid - d["end"])))
    return nearest["speaker"]


_SRT_TIME = re.compile(r"(\d\d):(\d\d):(\d\d),(\d+)")


def _parse_srt_time(text: str) -> float:
    h, m, s, ms = _SRT_TIME.match(text).groups()
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def parse_srt(content: str) -> list[tuple[float, float, str]]:
    cues = []
    for block in re.split(r"\n\s*\n", content.strip()):
        lines = block.splitlines()
        if len(lines) < 2:
            continue
        arrow = re.search(r"(\d\d:\d\d:\d\d,\d+)\s*-->\s*(\d\d:\d\d:\d\d,\d+)", lines[1])
        if not arrow:
            continue
        text = " ".join(part.strip() for part in lines[2:]).strip()
        cues.append((_parse_srt_time(arrow.group(1)), _parse_srt_time(arrow.group(2)), text))
    return cues


def _clock(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 60}:{total % 60:02d}"


def _srt_time(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def label_transcript(srt_content: str, diar: list[dict], num_speakers: int) -> tuple[str, str]:
    """Return (txt, srt) content with 'Speaker N' labels applied to each cue."""
    main, labels = _label_map(diar, num_speakers)
    cues = parse_srt(srt_content)
    tagged = [(start, end, labels[_assign(main, start, end)], text) for start, end, text in cues if text]

    # Speaker-labelled SRT: prefix each cue's text.
    srt_lines = []
    for i, (start, end, spk, text) in enumerate(tagged, start=1):
        srt_lines.append(f"{i}\n{_srt_time(start)} --> {_srt_time(end)}\nSpeaker {spk}: {text}\n")
    srt_out = "\n".join(srt_lines) + "\n"

    # Plain text: merge consecutive cues from the same speaker into a turn.
    turns: list[list] = []
    for start, _end, spk, text in tagged:
        if turns and turns[-1][1] == spk:
            turns[-1][2] += " " + text
        else:
            turns.append([start, spk, text])
    txt_out = "".join(f"[{_clock(start)}] Speaker {spk}:\n{text}\n\n" for start, spk, text in turns)
    return txt_out, srt_out
