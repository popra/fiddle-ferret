from __future__ import annotations

import numpy as np

from song_lengthen.analyze import find_loop_candidates


def _tone(sr: int, seconds: float, freq: float = 220.0, amp: float = 0.25) -> np.ndarray:
    t = np.arange(int(sr * seconds), dtype=np.float32) / sr
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def test_repeated_steady_audio_produces_loop_candidate() -> None:
    sr = 22_050
    phrase = _tone(sr, 8.0)
    audio = np.concatenate([phrase, phrase, phrase])

    candidates = find_loop_candidates(
        audio,
        sr=sr,
        min_loop_seconds=6.0,
        max_loop_seconds=10.0,
        max_candidates=3,
    )

    assert candidates
    assert candidates[0].confidence > 0.5
    assert 6.0 <= candidates[0].duration_seconds <= 10.0


def test_silence_produces_no_loop_candidate() -> None:
    candidates = find_loop_candidates(
        np.zeros(22_050 * 20, dtype=np.float32),
        sr=22_050,
        min_loop_seconds=6.0,
        max_loop_seconds=10.0,
        max_candidates=3,
    )

    assert candidates == []
