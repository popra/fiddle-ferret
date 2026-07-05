from __future__ import annotations

from pathlib import Path
from subprocess import PIPE, run as run_command

import numpy as np

from song_lengthen.types import SongLengthenError


DEFAULT_SAMPLE_RATE = 22_050


def decode_analysis_audio(
    path: Path,
    sr: int = DEFAULT_SAMPLE_RATE,
    max_seconds: float | None = None,
) -> tuple[np.ndarray, int]:
    if not path.exists():
        raise SongLengthenError("decode_error", f"Audio file not found: {path}")

    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
    ]
    if max_seconds is not None:
        command.extend(["-t", str(float(max_seconds))])
    command.extend(
        [
            "-i",
            str(path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(sr),
            "-f",
            "f32le",
            "pipe:1",
        ]
    )
    try:
        completed = run_command(command, check=False, stdout=PIPE, stderr=PIPE)
    except OSError as exc:
        raise SongLengthenError("decode_error", f"Could not run ffmpeg: {exc}") from exc

    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise SongLengthenError("decode_error", f"ffmpeg could not decode {path}: {detail}")

    audio = np.frombuffer(completed.stdout, dtype=np.float32).copy()
    if audio.size == 0:
        raise SongLengthenError("decode_error", f"Decoded audio was empty: {path}")
    return audio, sr


def probe_duration_seconds(path: Path) -> float:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        completed = run_command(command, check=False, stdout=PIPE, stderr=PIPE, text=True)
    except OSError as exc:
        raise SongLengthenError("duration_error", f"Could not run ffprobe: {exc}") from exc

    if completed.returncode != 0:
        detail = completed.stderr.strip()
        message = f"ffprobe could not read duration for {path}"
        if detail:
            message = f"{message}: {detail}"
        raise SongLengthenError("duration_error", message)

    try:
        return float(completed.stdout.strip())
    except ValueError as exc:
        raise SongLengthenError(
            "duration_error",
            f"ffprobe returned an invalid duration for {path}: {completed.stdout.strip()}",
        ) from exc
