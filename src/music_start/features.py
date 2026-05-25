from __future__ import annotations

from dataclasses import dataclass

import librosa
import numpy as np


@dataclass(frozen=True)
class AudioFeatures:
    times: np.ndarray
    rms: np.ndarray
    rms_rise: np.ndarray
    onset: np.ndarray
    beat: np.ndarray
    centroid: np.ndarray
    flatness: np.ndarray
    novelty: np.ndarray
    sustained: np.ndarray


def compute_features(audio: np.ndarray, sr: int, hop_length: int = 512) -> AudioFeatures:
    y = np.asarray(audio, dtype=np.float32)
    if y.ndim != 1:
        y = np.mean(y, axis=1).astype(np.float32)

    frame_length = 2048
    rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
    onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop_length)
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=hop_length)[0]
    flatness = librosa.feature.spectral_flatness(y=y, hop_length=hop_length)[0]

    length = min(len(rms), len(onset), len(centroid), len(flatness))
    rms = rms[:length]
    onset = onset[:length]
    centroid = centroid[:length]
    flatness = flatness[:length]
    times = librosa.frames_to_time(np.arange(length), sr=sr, hop_length=hop_length)

    rms_norm = _normalize(rms)
    onset_norm = _normalize(onset)
    centroid_norm = _normalize(centroid)
    flatness_norm = _normalize(flatness)
    rms_rise = _normalize(np.maximum(np.diff(rms_norm, prepend=rms_norm[0]), 0.0))
    beat = _beat_stability(onset_norm, sr=sr, hop_length=hop_length)
    sustained = _forward_sustained_energy(rms_norm, window=max(4, int(1.5 * sr / hop_length)))
    novelty = _normalize(
        0.35 * onset_norm
        + 0.25 * rms_rise
        + 0.20 * _normalize(np.maximum(np.diff(centroid_norm, prepend=centroid_norm[0]), 0.0))
        + 0.20 * (1.0 - flatness_norm)
    )

    return AudioFeatures(
        times=times,
        rms=rms_norm,
        rms_rise=rms_rise,
        onset=onset_norm,
        beat=beat,
        centroid=centroid_norm,
        flatness=flatness_norm,
        novelty=novelty,
        sustained=sustained,
    )


def _normalize(values: np.ndarray) -> np.ndarray:
    arr = np.nan_to_num(np.asarray(values, dtype=np.float32), copy=False)
    if arr.size == 0:
        return arr
    lo = float(np.min(arr))
    hi = float(np.max(arr))
    if hi - lo < 1e-9:
        return np.zeros_like(arr)
    return (arr - lo) / (hi - lo)


def _forward_sustained_energy(rms: np.ndarray, window: int) -> np.ndarray:
    if rms.size == 0:
        return rms
    result = np.zeros_like(rms)
    for idx in range(rms.size):
        result[idx] = float(np.mean(rms[idx : min(rms.size, idx + window)]))
    return _normalize(result)


def _beat_stability(onset: np.ndarray, sr: int, hop_length: int) -> np.ndarray:
    if onset.size == 0:
        return onset
    frame_seconds = hop_length / sr
    min_gap = max(1, int(0.25 / frame_seconds))
    peaks = _peak_indices(onset, min_distance=min_gap, threshold=0.25)
    stability = np.zeros_like(onset)
    if len(peaks) < 3:
        return stability
    gaps = np.diff(peaks)
    for peak_pos in range(2, len(peaks)):
        recent = gaps[max(0, peak_pos - 4) : peak_pos]
        if recent.size < 2:
            continue
        regularity = 1.0 - min(float(np.std(recent) / (np.mean(recent) + 1e-6)), 1.0)
        stability[peaks[peak_pos] :] = np.maximum(stability[peaks[peak_pos] :], regularity)
    return stability


def _peak_indices(values: np.ndarray, min_distance: int, threshold: float) -> list[int]:
    peaks: list[int] = []
    for idx in range(1, max(1, len(values) - 1)):
        if values[idx] < threshold:
            continue
        if values[idx] >= values[idx - 1] and values[idx] >= values[idx + 1]:
            if peaks and idx - peaks[-1] < min_distance:
                if values[idx] > values[peaks[-1]]:
                    peaks[-1] = idx
            else:
                peaks.append(idx)
    return peaks
