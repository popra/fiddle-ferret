from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


Target = Literal["main", "first-musical"]
OutputFormat = Literal["json", "human"]


@dataclass(frozen=True)
class Candidate:
    rank: int
    timestamp: str
    seconds: float
    confidence: float
    label: str
    reason: str

    def to_dict(self) -> dict[str, int | float | str]:
        return asdict(self)


@dataclass(frozen=True)
class AnalysisResult:
    file: str | None
    target: Target
    max_seconds: float
    candidates: list[Candidate]

    def to_dict(self) -> dict[str, object]:
        return {
            "file": self.file,
            "target": self.target,
            "max_seconds": self.max_seconds,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }


@dataclass(frozen=True)
class MusicStartError(Exception):
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


class DecodeError(MusicStartError):
    def __init__(self, message: str) -> None:
        super().__init__("decode_error", message)
