from __future__ import annotations

import shutil
import subprocess
import threading
from collections.abc import Iterable, Iterator


def resample_s16le_mono_stream(
    chunks: Iterable[bytes],
    input_rate: int = 24000,
    output_rate: int = 16000,
    read_size: int = 3200,
) -> Iterator[bytes]:
    """Resample raw signed-16-bit mono PCM chunks with ffmpeg."""

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found. Install ffmpeg before streaming to the robot.")

    process = subprocess.Popen(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "s16le",
            "-ar",
            str(input_rate),
            "-ac",
            "1",
            "-i",
            "pipe:0",
            "-f",
            "s16le",
            "-ar",
            str(output_rate),
            "-ac",
            "1",
            "pipe:1",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    def feed() -> None:
        try:
            assert process.stdin is not None
            for chunk in chunks:
                if chunk:
                    process.stdin.write(chunk)
                    process.stdin.flush()
        except BrokenPipeError:
            pass
        finally:
            if process.stdin:
                try:
                    process.stdin.close()
                except BrokenPipeError:
                    pass

    feeder = threading.Thread(target=feed, daemon=True)
    feeder.start()

    assert process.stdout is not None
    try:
        while True:
            data = process.stdout.read(read_size)
            if not data:
                break
            yield data
    finally:
        feeder.join(timeout=3)
        return_code = process.wait(timeout=10)
        if return_code != 0:
            stderr = b""
            if process.stderr:
                stderr = process.stderr.read()
            raise RuntimeError(f"ffmpeg resampler failed with code {return_code}: {stderr.decode(errors='replace')}")

