from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class LoopCandidate:
    rank: int
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    confidence: float
    reason: str

    def to_dict(self) -> dict[str, float | int | str]:
        return asdict(self)


@dataclass(frozen=True)
class LengthenPlan:
    input: str
    output: str
    requested_seconds: float
    estimated_seconds: float
    original_seconds: float
    add_seconds: float
    loop: LoopCandidate
    repeat_count: int
    crossfade_seconds: float
    warnings: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "input": self.input,
            "output": self.output,
            "requested_seconds": self.requested_seconds,
            "estimated_seconds": self.estimated_seconds,
            "original_seconds": self.original_seconds,
            "add_seconds": self.add_seconds,
            "loop": self.loop.to_dict(),
            "repeat_count": self.repeat_count,
            "crossfade_seconds": self.crossfade_seconds,
            "warnings": self.warnings,
        }


@dataclass(frozen=True)
class SongLengthenError(Exception):
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}
