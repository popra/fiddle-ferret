from __future__ import annotations

from collections.abc import Iterable

import numpy as np

from music_start.features import AudioFeatures, compute_features
from music_start.types import AnalysisResult, Candidate, Target


def analyze_audio(
    audio: np.ndarray,
    sr: int,
    target: Target,
    max_candidates: int = 3,
    file: str | None = None,
    max_seconds: float = 120.0,
) -> AnalysisResult:
    features = compute_features(audio, sr=sr)
    if features.times.size == 0 or float(np.max(features.rms)) < 0.001:
        return AnalysisResult(file=file, target=target, max_seconds=max_seconds, candidates=[])

    ranked = _rank_candidates(features, target=target)
    candidates: list[Candidate] = []
    for rank, (idx, score) in enumerate(ranked[:max_candidates], start=1):
        seconds = round(float(features.times[idx]), 3)
        confidence = round(float(min(max(score, 0.0), 1.0)), 3)
        candidates.append(
            Candidate(
                rank=rank,
                timestamp=_format_timestamp(seconds),
                seconds=seconds,
                confidence=confidence,
                label=_label(target, rank),
                reason=_reason(features, idx, target),
            )
        )
    return AnalysisResult(file=file, target=target, max_seconds=max_seconds, candidates=candidates)


def _rank_candidates(features: AudioFeatures, target: Target) -> list[tuple[int, float]]:
    if target == "first-musical":
        score = (
            0.40 * features.rms_rise
            + 0.30 * features.onset
            + 0.20 * features.rms
            + 0.10 * features.novelty
        )
        threshold = 0.18
        candidates = _candidate_indices(features, score, threshold)
        candidates.sort(key=lambda item: (item[0], -item[1]))
        return _dedupe(candidates, min_gap_seconds=0.65, times=features.times)

    score = (
        0.30 * features.sustained
        + 0.25 * features.rms_rise
        + 0.20 * features.onset
        + 0.15 * features.beat
        + 0.10 * features.novelty
    )
    threshold = 0.22
    candidates = _candidate_indices(features, score, threshold)
    if candidates:
        max_score = max(score for _, score in candidates)
        decisive_floor = max(threshold, max_score - 0.12)
        candidates = [
            (idx, item_score)
            for idx, item_score in candidates
            if item_score >= decisive_floor
            or features.rms_rise[idx] >= 0.50
            or features.onset[idx] >= 0.50
            or features.beat[idx] >= 0.30
        ]
    if candidates:
        max_score = max(score for _, score in candidates)
        top_band = max(threshold, max_score - 0.25)
        candidates.sort(
            key=lambda item: (
                item[1] < top_band,
                float(features.times[item[0]]) if item[1] >= top_band else -item[1],
            )
        )
    return _dedupe(candidates, min_gap_seconds=1.0, times=features.times)


def _candidate_indices(
    features: AudioFeatures,
    score: np.ndarray,
    threshold: float,
) -> list[tuple[int, float]]:
    seeds = set(_local_peaks(score, threshold=threshold))
    seeds.update(_local_peaks(features.rms_rise, threshold=0.20))
    seeds.update(_local_peaks(features.onset, threshold=0.25))
    seeds.update(_local_peaks(features.novelty, threshold=0.25))

    transitions = np.where((features.rms_rise >= 0.20) & (features.sustained >= 0.20))[0]
    seeds.update(int(idx) for idx in transitions)

    ranked = [(idx, float(score[idx])) for idx in sorted(seeds) if float(score[idx]) >= threshold]
    if ranked:
        return ranked

    best = int(np.argmax(score)) if score.size else 0
    if score.size and float(score[best]) >= threshold:
        return [(best, float(score[best]))]
    return []


def _local_peaks(values: np.ndarray, threshold: float) -> list[int]:
    if values.size == 0:
        return []
    if values.size == 1:
        return [0] if float(values[0]) >= threshold else []
    peaks: list[int] = []
    for idx in range(values.size):
        left = values[idx - 1] if idx > 0 else -np.inf
        right = values[idx + 1] if idx < values.size - 1 else -np.inf
        if values[idx] >= threshold and values[idx] >= left and values[idx] >= right:
            peaks.append(idx)
    return peaks


def _dedupe(
    candidates: Iterable[tuple[int, float]],
    min_gap_seconds: float,
    times: np.ndarray,
) -> list[tuple[int, float]]:
    kept: list[tuple[int, float]] = []
    for idx, score in candidates:
        if any(abs(float(times[idx] - times[old_idx])) < min_gap_seconds for old_idx, _ in kept):
            continue
        kept.append((idx, score))
    return kept


def _format_timestamp(seconds: float) -> str:
    whole = int(seconds)
    millis = int(round((seconds - whole) * 1000))
    minutes, secs = divmod(whole, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d}.{millis:03d}"
    return f"{minutes:d}:{secs:02d}.{millis:03d}"


def _label(target: Target, rank: int) -> str:
    if target == "first-musical":
        return "earliest musical event" if rank == 1 else "alternate early event"
    return "likely main start" if rank == 1 else "alternate main start"


def _reason(features: AudioFeatures, idx: int, target: Target) -> str:
    parts: list[str] = []
    if features.rms_rise[idx] >= 0.35:
        parts.append("strong energy rise")
    if features.onset[idx] >= 0.35:
        parts.append("clear onset")
    if features.sustained[idx] >= 0.35:
        parts.append("sustained loudness follows")
    if features.beat[idx] >= 0.35:
        parts.append("repeated beat structure")
    if not parts:
        parts.append("combined novelty and energy evidence")
    if target == "main" and "sustained loudness follows" not in parts:
        parts.append("sustained section evidence")
    return ", ".join(parts)
