import subprocess
import sys

from taatik.app import main
from taatik.config import bundled_tool, diarization_models, diarization_ready


def self_test() -> int:
    for name, argument in (("ffmpeg", "-version"), ("whisper-cli", "--help")):
        tool = bundled_tool(name)
        if not tool.is_file():
            print(f"Missing bundled component: {tool}", file=sys.stderr)
            return 1
        result = subprocess.run(
            [str(tool), argument], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=30,
        )
        if result.returncode != 0:
            print(f"Bundled component failed its self-check: {name}", file=sys.stderr)
            return 1
    # The speaker-separation engine is optional but, when its models ship, its
    # native ONNX libraries must load in the packaged environment.
    if diarization_ready():
        try:
            import numpy  # noqa: F401
            import soundfile  # noqa: F401
            import sherpa_onnx  # noqa: F401
        except Exception as exc:  # pragma: no cover - packaging guard
            print(f"Speaker separation engine failed to load: {exc}", file=sys.stderr)
            return 1
    return 0


def diar_self_test(wav: str) -> int:
    from taatik.diarization import diarize

    segmentation, embedding = diarization_models()
    segments = diarize(wav, segmentation, embedding, num_speakers=0)
    print(f"diarization produced {len(segments)} segments")
    return 0 if segments else 1


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        raise SystemExit(self_test())
    if "--diar-self-test" in sys.argv:
        raise SystemExit(diar_self_test(sys.argv[sys.argv.index("--diar-self-test") + 1]))
    raise SystemExit(main())
