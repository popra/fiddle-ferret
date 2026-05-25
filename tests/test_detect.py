from __future__ import annotations

import numpy as np

from music_start.detect import analyze_audio


def _tone(sr: int, seconds: float, freq: float = 440.0, amp: float = 0.5) -> np.ndarray:
    t = np.arange(int(sr * seconds), dtype=np.float32) / sr
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def _click_track(sr: int, seconds: float, bpm: float = 120.0, amp: float = 0.9) -> np.ndarray:
    y = np.zeros(int(sr * seconds), dtype=np.float32)
    step = int(sr * 60.0 / bpm)
    width = max(1, int(sr * 0.015))
    for start in range(0, len(y), step):
        y[start : start + width] = amp
    return y


def test_first_musical_finds_earliest_note_before_main_groove() -> None:
    sr = 22_050
    audio = np.concatenate(
        [
            np.zeros(sr, dtype=np.float32),
            _tone(sr, 2.0, amp=0.18),
            _click_track(sr, 4.0, amp=0.9),
        ]
    )

    first = analyze_audio(audio, sr=sr, target="first-musical", max_candidates=3)
    main = analyze_audio(audio, sr=sr, target="main", max_candidates=3)

    assert first.candidates
    assert main.candidates
    assert 0.85 <= first.candidates[0].seconds <= 1.25
    assert main.candidates[0].seconds >= 2.75
    assert main.candidates[0].seconds > first.candidates[0].seconds


def test_main_ignores_drone_and_prefers_sustained_beat() -> None:
    sr = 22_050
    drone = _tone(sr, 4.0, freq=110.0, amp=0.08)
    beat = _click_track(sr, 5.0, amp=0.8)
    audio = np.concatenate([drone, beat])

    result = analyze_audio(audio, sr=sr, target="main", max_candidates=3)

    assert result.candidates
    assert 3.7 <= result.candidates[0].seconds <= 4.3
    assert "sustained" in result.candidates[0].reason.lower()


def test_silence_has_no_confident_candidate() -> None:
    sr = 22_050
    result = analyze_audio(np.zeros(sr * 3, dtype=np.float32), sr=sr, target="main")

    assert result.candidates == []
