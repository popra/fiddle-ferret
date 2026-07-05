from __future__ import annotations

import tempfile
from pathlib import Path
from subprocess import PIPE, run as run_command

import numpy as np
import soundfile as sf

from song_lengthen.decode import decode_analysis_audio
from song_lengthen.types import LengthenPlan, SongLengthenError


def render_lengthened_audio(plan: LengthenPlan, overwrite: bool) -> None:
    input_path = Path(plan.input)
    output_path = Path(plan.output)
    audio, sr = decode_analysis_audio(input_path, sr=44_100)
    rendered = _render_samples(audio, sr=sr, plan=plan)

    with tempfile.TemporaryDirectory(prefix="song-lengthen-") as temp_dir:
        temp_wav = Path(temp_dir) / "lengthened.wav"
        sf.write(temp_wav, rendered, sr)
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y" if overwrite else "-n",
            "-i",
            str(temp_wav),
            str(output_path),
        ]
        try:
            completed = run_command(command, check=False, stdout=PIPE, stderr=PIPE, text=True)
        except OSError as exc:
            raise SongLengthenError("render_error", f"Could not run ffmpeg: {exc}") from exc

    if completed.returncode != 0:
        detail = completed.stderr.strip()
        message = f"ffmpeg failed with exit code {completed.returncode}."
        if detail:
            message = f"{message} {detail}"
        raise SongLengthenError("render_error", message)


def _render_samples(audio: np.ndarray, sr: int, plan: LengthenPlan) -> np.ndarray:
    start = max(0, int(round(plan.loop.start_seconds * sr)))
    end = min(audio.size, int(round(plan.loop.end_seconds * sr)))
    loop = audio[start:end]
    if loop.size == 0:
        raise SongLengthenError("render_error", "Loop region was empty.")

    result = audio.copy()
    for _ in range(plan.repeat_count):
        result = _append_with_crossfade(result, loop, int(round(plan.crossfade_seconds * sr)))
    return result


def _append_with_crossfade(base: np.ndarray, addition: np.ndarray, crossfade_samples: int) -> np.ndarray:
    fade = min(crossfade_samples, base.size, addition.size)
    if fade <= 0:
        return np.concatenate([base, addition])

    angle = np.linspace(0.0, np.pi / 2.0, fade, dtype=np.float32)
    out_curve = np.cos(angle)
    in_curve = np.sin(angle)
    blended = base[-fade:] * out_curve + addition[:fade] * in_curve
    return np.concatenate([base[:-fade], blended, addition[fade:]])
