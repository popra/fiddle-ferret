from __future__ import annotations

from math import ceil
from pathlib import Path

from song_lengthen.analyze import find_loop_candidates
from song_lengthen.decode import decode_analysis_audio, probe_duration_seconds
from song_lengthen.types import LengthenPlan, SongLengthenError


def create_lengthen_plan(
    path: Path,
    output: Path,
    requested_seconds: float,
    crossfade_seconds: float,
    min_loop_seconds: float,
    max_loop_seconds: float,
    max_candidates: int,
) -> LengthenPlan:
    original_seconds = probe_duration_seconds(path)
    if requested_seconds <= original_seconds:
        raise SongLengthenError(
            "invalid_options",
            "--target-seconds must be greater than the input duration.",
        )

    audio, sr = decode_analysis_audio(path)
    candidates = find_loop_candidates(
        audio,
        sr=sr,
        min_loop_seconds=min_loop_seconds,
        max_loop_seconds=max_loop_seconds,
        max_candidates=max_candidates,
    )
    if not candidates:
        raise SongLengthenError("no_loop", "No acceptable loop candidate was found.")

    loop = candidates[0]
    add_seconds = requested_seconds - original_seconds
    effective_loop = max(loop.duration_seconds - crossfade_seconds, 0.001)
    repeat_count = max(1, int(ceil(add_seconds / effective_loop)))
    estimated_seconds = original_seconds + repeat_count * effective_loop
    warnings: list[str] = []
    if loop.confidence < 0.65:
        warnings.append("Low-confidence loop; inspect the output before using it.")
    if abs(estimated_seconds - requested_seconds) > max(2.0, loop.duration_seconds):
        warnings.append("Estimated output duration is approximate.")

    return LengthenPlan(
        input=str(path),
        output=str(output),
        requested_seconds=round(requested_seconds, 3),
        estimated_seconds=round(estimated_seconds, 3),
        original_seconds=round(original_seconds, 3),
        add_seconds=round(add_seconds, 3),
        loop=loop,
        repeat_count=repeat_count,
        crossfade_seconds=round(crossfade_seconds, 3),
        warnings=warnings,
    )
