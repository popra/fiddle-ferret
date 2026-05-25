from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

from music_start.types import DecodeError


DEFAULT_SAMPLE_RATE = 22_050


def decode_audio(path: Path, max_seconds: float, sr: int = DEFAULT_SAMPLE_RATE) -> tuple[np.ndarray, int]:
    if not path.exists():
        raise DecodeError(f"Audio file not found: {path}")
    if max_seconds <= 0:
        raise DecodeError("--max-seconds must be greater than 0")

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return _decode_with_soundfile(path, max_seconds=max_seconds, sr=sr)

    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-t",
        str(float(max_seconds)),
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
    try:
        completed = subprocess.run(
            command,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise DecodeError(f"Could not run ffmpeg: {exc}") from exc

    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise DecodeError(f"ffmpeg could not decode {path}: {detail}")

    audio = np.frombuffer(completed.stdout, dtype=np.float32).copy()
    if audio.size == 0:
        raise DecodeError(f"Decoded audio was empty: {path}")
    return audio, sr


def _decode_with_soundfile(path: Path, max_seconds: float, sr: int) -> tuple[np.ndarray, int]:
    try:
        data, file_sr = sf.read(path, dtype="float32", always_2d=True)
    except RuntimeError as exc:
        raise DecodeError(f"ffmpeg is not on PATH and soundfile could not read {path}: {exc}") from exc

    max_samples = int(max_seconds * file_sr)
    mono = data[:max_samples].mean(axis=1)
    if file_sr != sr:
        import librosa

        mono = librosa.resample(mono, orig_sr=file_sr, target_sr=sr)
    if mono.size == 0:
        raise DecodeError(f"Decoded audio was empty: {path}")
    return mono.astype(np.float32, copy=False), sr
