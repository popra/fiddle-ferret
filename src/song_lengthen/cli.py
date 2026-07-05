from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from song_lengthen.decode import probe_duration_seconds
from song_lengthen.plan import create_lengthen_plan
from song_lengthen.render import render_lengthened_audio
from song_lengthen.types import SongLengthenError


app = typer.Typer(no_args_is_help=True, help="Automatically lengthen songs with looped sections.")


@app.callback()
def main() -> None:
    """Automatically lengthen songs with looped sections."""


@app.command()
def lengthen(
    path: Annotated[Path, typer.Argument(help="Local audio file to lengthen.")],
    target_seconds: Annotated[
        float | None,
        typer.Option("--target-seconds", min=0.001, help="Desired approximate output duration."),
    ] = None,
    add_seconds: Annotated[
        float | None,
        typer.Option("--add-seconds", min=0.001, help="Seconds to add to the input duration."),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output path for the lengthened copy."),
    ] = None,
    overwrite: Annotated[
        bool,
        typer.Option("--overwrite", "-y", help="Overwrite output if it exists."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json/--human", help="Emit JSON or human-readable text."),
    ] = True,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Analyze and print the edit plan without writing audio."),
    ] = False,
    crossfade_seconds: Annotated[
        float,
        typer.Option("--crossfade-seconds", min=0.0, help="Crossfade duration at loop joins."),
    ] = 3.0,
    min_loop_seconds: Annotated[
        float,
        typer.Option("--min-loop-seconds", min=1.0, help="Minimum loop candidate duration."),
    ] = 8.0,
    max_loop_seconds: Annotated[
        float,
        typer.Option("--max-loop-seconds", min=1.0, help="Maximum loop candidate duration."),
    ] = 45.0,
    candidates: Annotated[
        int,
        typer.Option("--candidates", min=1, max=20, help="Loop candidates to consider."),
    ] = 5,
) -> None:
    output_format = "json" if json_output else "human"
    output_path = output or _default_output(path)

    try:
        if (target_seconds is None) == (add_seconds is None):
            raise SongLengthenError(
                "invalid_options",
                "Exactly one of --target-seconds or --add-seconds is required.",
            )
        if max_loop_seconds < min_loop_seconds:
            raise SongLengthenError(
                "invalid_options",
                "--max-loop-seconds must be greater than or equal to --min-loop-seconds.",
            )
        if output_path.exists() and not overwrite and not dry_run:
            raise SongLengthenError(
                "output_exists",
                f"Output file already exists: {output_path}. Use --overwrite to replace it.",
            )

        requested_seconds = target_seconds
        if requested_seconds is None:
            requested_seconds = probe_duration_seconds(path) + float(add_seconds)

        plan = create_lengthen_plan(
            path=path,
            output=output_path,
            requested_seconds=float(requested_seconds),
            crossfade_seconds=crossfade_seconds,
            min_loop_seconds=min_loop_seconds,
            max_loop_seconds=max_loop_seconds,
            max_candidates=candidates,
        )
        if not dry_run:
            render_lengthened_audio(plan, overwrite=overwrite)
    except SongLengthenError as exc:
        _emit_error(exc, output_format)
        raise typer.Exit(2 if exc.code == "no_loop" else 1) from exc
    except RuntimeError as exc:
        _emit_error(SongLengthenError("render_error", str(exc)), output_format)
        raise typer.Exit(1) from exc

    _emit_payload(plan.to_dict(), output_format)


def _default_output(path: Path) -> Path:
    suffix = path.suffix
    if suffix:
        return path.with_name(f"{path.stem}.lengthened{suffix}")
    return path.with_name(f"{path.name}.lengthened")


def _emit_error(error: SongLengthenError, output_format: str) -> None:
    _emit_payload({"error": error.to_dict()}, output_format)


def _emit_payload(payload: dict[str, object], output_format: str) -> None:
    if output_format == "json":
        typer.echo(json.dumps(payload, indent=2))
        return
    typer.echo(_format_text(payload))


def _format_text(payload: dict[str, object]) -> str:
    if "error" in payload:
        error = payload["error"]
        if isinstance(error, dict):
            return f"Error [{error.get('code')}]: {error.get('message')}"
        return "Error"

    loop = payload.get("loop")
    if isinstance(loop, dict):
        return "\n".join(
            [
                f"Lengthened file: {payload.get('output')}",
                "Loop: {start:.3f}s to {end:.3f}s ({duration:.3f}s), confidence={confidence:.3f}".format(
                    start=float(loop.get("start_seconds", 0.0)),
                    end=float(loop.get("end_seconds", 0.0)),
                    duration=float(loop.get("duration_seconds", 0.0)),
                    confidence=float(loop.get("confidence", 0.0)),
                ),
                f"Repeats: {payload.get('repeat_count')}",
                f"Estimated duration: {payload.get('estimated_seconds')} seconds",
            ]
        )
    return json.dumps(payload, indent=2)
