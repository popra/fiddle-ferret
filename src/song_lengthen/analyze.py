from __future__ import annotations

import librosa
import numpy as np

from song_lengthen.types import LoopCandidate


def find_loop_candidates(
    audio: np.ndarray,
    sr: int,
    min_loop_seconds: float,
    max_loop_seconds: float,
    max_candidates: int = 5,
) -> list[LoopCandidate]:
    y = np.asarray(audio, dtype=np.float32)
    if y.ndim != 1:
        y = np.mean(y, axis=1).astype(np.float32)
    if y.size == 0 or float(np.max(np.abs(y))) < 0.001:
        return []

    duration = y.size / sr
    if duration < min_loop_seconds * 1.5:
        return []

    hop_seconds = 0.5
    frame_seconds = 1.0
    hop = max(1, int(sr * hop_seconds))
    frame = max(hop, int(sr * frame_seconds))
    starts = np.arange(0, max(1, y.size - frame), hop, dtype=np.int64)
    if starts.size < 2:
        return []

    fingerprints = np.vstack([_fingerprint(y[int(start) : int(start) + frame], sr) for start in starts])
    rms = np.asarray([_rms(y[int(start) : int(start) + frame]) for start in starts], dtype=np.float32)

    avoid_margin = duration * 0.10 if duration >= max_loop_seconds * 2 else 0.0
    min_frames = max(1, int(round(min_loop_seconds / hop_seconds)))
    max_frames = max(min_frames, int(round(max_loop_seconds / hop_seconds)))
    candidates: list[tuple[float, float, float, str]] = []

    for start_idx in range(0, len(starts) - min_frames):
        start_seconds = float(starts[start_idx] / sr)
        if avoid_margin and start_seconds < avoid_margin:
            continue
        for gap in range(min_frames, min(max_frames, len(starts) - start_idx - 1) + 1):
            end_idx = start_idx + gap
            end_seconds = float(starts[end_idx] / sr)
            if avoid_margin and end_seconds > duration - avoid_margin:
                continue

            boundary_similarity = _cosine_similarity(fingerprints[start_idx], fingerprints[end_idx])
            loudness_continuity = 1.0 - min(abs(float(rms[start_idx] - rms[end_idx])) / 0.25, 1.0)
            region = rms[start_idx : end_idx + 1]
            stability = 1.0 - min(float(np.std(region) / (np.mean(region) + 1e-6)), 1.0)
            length_score = min((end_seconds - start_seconds) / max(min_loop_seconds, 1e-6), 1.0)
            score = (
                0.45 * boundary_similarity
                + 0.25 * loudness_continuity
                + 0.20 * stability
                + 0.10 * length_score
            )
            if score >= 0.50:
                candidates.append((score, start_seconds, end_seconds, "similar loop boundary"))

    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
    deduped: list[tuple[float, float, float, str]] = []
    for item in candidates:
        _, start, end, _ = item
        if any(abs(start - old_start) < 1.0 and abs(end - old_end) < 1.0 for _, old_start, old_end, _ in deduped):
            continue
        deduped.append(item)
        if len(deduped) >= max_candidates:
            break

    return [
        LoopCandidate(
            rank=rank,
            start_seconds=round(start, 3),
            end_seconds=round(end, 3),
            duration_seconds=round(end - start, 3),
            confidence=round(float(min(max(score, 0.0), 1.0)), 3),
            reason=reason,
        )
        for rank, (score, start, end, reason) in enumerate(deduped, start=1)
    ]


def _fingerprint(audio: np.ndarray, sr: int) -> np.ndarray:
    if audio.size == 0:
        return np.zeros(14, dtype=np.float32)
    rms = np.asarray([_rms(audio)], dtype=np.float32)
    centroid = librosa.feature.spectral_centroid(y=audio, sr=sr)[0]
    flatness = librosa.feature.spectral_flatness(y=audio)[0]
    chroma = librosa.feature.chroma_stft(y=audio, sr=sr)
    return np.concatenate(
        [
            rms,
            np.asarray([float(np.mean(centroid)), float(np.mean(flatness))], dtype=np.float32),
            np.mean(chroma, axis=1).astype(np.float32),
        ]
    )


def _rms(audio: np.ndarray) -> float:
    if audio.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(audio, dtype=np.float32))))


def _cosine_similarity(left: np.ndarray, right: np.ndarray) -> float:
    denom = float(np.linalg.norm(left) * np.linalg.norm(right))
    if denom < 1e-9:
        return 0.0
    return float((np.dot(left, right) / denom + 1.0) / 2.0)
