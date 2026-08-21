import subprocess
import sys

from taatik.app import main
from taatik.config import bundled_tool


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
    return 0


if __name__ == "__main__":
    raise SystemExit(self_test() if "--self-test" in sys.argv else main())
