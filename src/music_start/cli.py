from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from subprocess import PIPE, run as run_command
from typing import Annotated

import typer

from music_start.decode import decode_audio
from music_start.detect import analyze_audio
from music_start.types import AnalysisResult, Candidate, DecodeError, MusicStartError, OutputFormat, Target


app = typer.Typer(no_args_is_help=True, help="Find likely music start timestamps in audio files.")


@app.callback()
def main() -> None:
    """Find likely music start timestamps in audio files."""


@app.command()
def analyze(
    path: Annotated[Path, typer.Argument(help="Local audio file to analyze.")],
    target: Annotated[Target, typer.Option(help="Timestamp target profile.")] = "main",
    candidates: Annotated[int, typer.Option("--candidates", min=1, max=20)] = 3,
    json_output: Annotated[
        bool,
        typer.Option("--json/--human", help="Emit JSON or human-readable text."),
    ] = True,
    max_seconds: Annotated[
        float,
        typer.Option("--max-seconds", min=1.0, help="Only analyze this many seconds."),
    ] = 120.0,
    min_remainder: Annotated[
        float,
        typer.Option(
            "--min-remainder",
            min=0.0,
            help="Only include candidates with at least this many seconds after them.",
        ),
    ] = 0.0,
) -> None:
    output_format: OutputFormat = "json" if json_output else "human"
    try:
        audio, sr = decode_audio(path, max_seconds=max_seconds)
        result = analyze_audio(
            audio,
            sr=sr,
            target=target,
            max_candidates=20 if min_remainder > 0 else candidates,
            file=str(path),
            max_seconds=max_seconds,
        )
        result = _filter_by_min_remainder(result, path=path, min_remainder=min_remainder)
    except DecodeError as exc:
        _emit_error(exc, output_format)
        raise typer.Exit(1) from exc
    except MusicStartError as exc:
        _emit_error(exc, output_format)
        raise typer.Exit(1) from exc

    if min_remainder > 0:
        result = replace(result, candidates=result.candidates[:candidates])

    if not result.candidates:
        payload = result.to_dict()
        payload["error"] = MusicStartError(
            "no_candidate",
            "No confident music start candidate was found.",
        ).to_dict()
        _emit_payload(payload, output_format)
        raise typer.Exit(2)

    _emit_payload(result.to_dict(), output_format)


@app.command()
def trim_start(
    path: Annotated[Path, typer.Argument(help="Local audio file to trim.")],
    target: Annotated[Target, typer.Option(help="Timestamp target profile.")] = "main",
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output path for the trimmed copy."),
    ] = None,
    overwrite: Annotated[
        bool,
        typer.Option("--overwrite", "-y", help="Overwrite output if it exists."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json/--human", help="Emit JSON or human-readable text."),
    ] = True,
    max_seconds: Annotated[
        float,
        typer.Option("--max-seconds", min=1.0, help="Only analyze this many seconds."),
    ] = 120.0,
    min_remainder: Annotated[
        float,
        typer.Option(
            "--min-remainder",
            min=0.0,
            help="Only use candidates with at least this many seconds after them.",
        ),
    ] = 0.0,
) -> None:
    output_format: OutputFormat = "json" if json_output else "human"
    output_path = output or _default_trim_output(path)
    if output_path.exists() and not overwrite:
        _emit_error(
            MusicStartError(
                "output_exists",
                f"Output file already exists: {output_path}. Use --overwrite to replace it.",
            ),
            output_format,
        )
        raise typer.Exit(1)

    try:
        audio, sr = decode_audio(path, max_seconds=max_seconds)
        result = analyze_audio(
            audio,
            sr=sr,
            target=target,
            max_candidates=20 if min_remainder > 0 else 1,
            file=str(path),
            max_seconds=max_seconds,
        )
        result = _filter_by_min_remainder(result, path=path, min_remainder=min_remainder)
    except DecodeError as exc:
        _emit_error(exc, output_format)
        raise typer.Exit(1) from exc
    except MusicStartError as exc:
        _emit_error(exc, output_format)
        raise typer.Exit(1) from exc

    if not result.candidates:
        payload = result.to_dict()
        payload["error"] = MusicStartError(
            "no_candidate",
            "No confident music start candidate was found.",
        ).to_dict()
        _emit_payload(payload, output_format)
        raise typer.Exit(2)

    candidate = result.candidates[0]
    command = [
        "ffmpeg",
        "-y" if overwrite else "-n",
        "-ss",
        str(candidate.seconds),
        "-i",
        str(path),
        "-map",
        "0",
        "-c",
        "copy",
        str(output_path),
    ]
    completed = run_command(command, check=False)
    if completed.returncode != 0:
        _emit_error(
            MusicStartError("trim_error", f"ffmpeg failed with exit code {completed.returncode}."),
            output_format,
        )
        raise typer.Exit(1)

    payload = {
        "input": str(path),
        "output": str(output_path),
        "target": target,
        "max_seconds": max_seconds,
        "candidate": candidate.to_dict(),
    }
    _emit_payload(payload, output_format)


def _filter_by_min_remainder(
    result: AnalysisResult,
    path: Path,
    min_remainder: float,
) -> AnalysisResult:
    if min_remainder <= 0 or not result.candidates:
        return result

    duration_seconds = _probe_duration_seconds(path)
    candidates = [
        candidate
        for candidate in result.candidates
        if duration_seconds - candidate.seconds >= min_remainder
    ]
    return replace(result, candidates=_rerank(candidates))


def _rerank(candidates: list[Candidate]) -> list[Candidate]:
    return [replace(candidate, rank=rank) for rank, candidate in enumerate(candidates, start=1)]


def _probe_duration_seconds(path: Path) -> float:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        completed = run_command(command, check=False, stdout=PIPE, stderr=PIPE, text=True)
    except OSError as exc:
        raise MusicStartError("duration_error", f"Could not run ffprobe: {exc}") from exc

    if completed.returncode != 0:
        detail = completed.stderr.strip()
        message = f"ffprobe could not read duration for {path}"
        if detail:
            message = f"{message}: {detail}"
        raise MusicStartError("duration_error", message)

    try:
        return float(completed.stdout.strip())
    except ValueError as exc:
        raise MusicStartError(
            "duration_error",
            f"ffprobe returned an invalid duration for {path}: {completed.stdout.strip()}",
        ) from exc


def _emit_error(error: MusicStartError, output_format: OutputFormat) -> None:
    _emit_payload({"error": error.to_dict()}, output_format)


def _emit_payload(payload: dict[str, object], output_format: OutputFormat) -> None:
    if output_format == "json":
        typer.echo(json.dumps(payload, indent=2))
        return
    typer.echo(_format_text(payload))


def _format_text(payload: dict[str, object]) -> str:
    if "error" in payload and "candidates" not in payload:
        error = payload["error"]
        if isinstance(error, dict):
            return f"Error [{error.get('code')}]: {error.get('message')}"
        return "Error"

    if "candidate" in payload and "output" in payload:
        candidate = payload["candidate"]
        if isinstance(candidate, dict):
            return "\n".join(
                [
                    "Detected start: {timestamp} ({seconds} seconds)".format(
                        timestamp=candidate.get("timestamp", "?"),
                        seconds=candidate.get("seconds", "?"),
                    ),
                    f"Writing: {payload.get('output')}",
                ]
            )

    target = payload.get("target", "main")
    file = payload.get("file", "<unknown>")
    lines = [f"Candidates for {file} ({target})"]
    candidates = payload.get("candidates", [])
    if isinstance(candidates, list) and candidates:
        for item in candidates:
            if not isinstance(item, dict):
                continue
            lines.append(
                "#{rank}  {timestamp}  confidence={confidence:.3f}  {label} - {reason}".format(
                    rank=item.get("rank", "?"),
                    timestamp=item.get("timestamp", "?"),
                    confidence=float(item.get("confidence", 0.0)),
                    label=item.get("label", "candidate"),
                    reason=item.get("reason", ""),
                )
            )
    else:
        lines.append("No confident candidate found.")
    if "error" in payload:
        error = payload["error"]
        if isinstance(error, dict):
            lines.append(f"Error [{error.get('code')}]: {error.get('message')}")
    return "\n".join(lines)


def _default_trim_output(path: Path) -> Path:
    suffix = path.suffix
    if suffix:
        return path.with_name(f"{path.stem}.trimmed{suffix}")
    return path.with_name(f"{path.name}.trimmed")
