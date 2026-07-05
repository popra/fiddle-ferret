from __future__ import annotations

import numpy as np

from song_lengthen.render import _render_samples
from song_lengthen.types import LengthenPlan, LoopCandidate


def test_render_samples_repeats_loop_without_mutating_original_audio() -> None:
    sr = 10
    original = np.arange(100, dtype=np.float32)
    plan = LengthenPlan(
        input="in.wav",
        output="out.wav",
        requested_seconds=12.0,
        estimated_seconds=12.0,
        original_seconds=10.0,
        add_seconds=2.0,
        loop=LoopCandidate(
            rank=1,
            start_seconds=2.0,
            end_seconds=4.0,
            duration_seconds=2.0,
            confidence=0.8,
            reason="test",
        ),
        repeat_count=1,
        crossfade_seconds=0.0,
        warnings=[],
    )

    rendered = _render_samples(original, sr=sr, plan=plan)

    assert np.array_equal(original, np.arange(100, dtype=np.float32))
    assert rendered.size == 120
    assert np.array_equal(rendered[:100], original)
    assert np.array_equal(rendered[100:], original[20:40])
