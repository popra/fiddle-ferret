from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile as sf
from typer.testing import CliRunner

from song_lengthen.cli import app
from song_lengthen.types import LengthenPlan, LoopCandidate, SongLengthenError


runner = CliRunner()


def _write_loopable_audio(path: Path, sr: int = 22_050) -> None:
    t = np.arange(sr * 8, dtype=np.float32) / sr
    phrase = (0.25 * np.sin(2 * np.pi * 220.0 * t)).astype(np.float32)
    audio = np.concatenate([phrase, phrase, phrase])
    sf.write(path, audio, sr)


def _candidate() -> LoopCandidate:
    return LoopCandidate(
        rank=1,
        start_seconds=2.0,
        end_seconds=10.0,
        duration_seconds=8.0,
        confidence=0.82,
        reason="similar loop boundary",
    )


def _plan(path: Path) -> LengthenPlan:
    return LengthenPlan(
        input=str(path),
        output=str(path.with_name(f"{path.stem}.lengthened{path.suffix}")),
        requested_seconds=30.0,
        estimated_seconds=32.0,
        original_seconds=24.0,
        add_seconds=6.0,
        loop=_candidate(),
        repeat_count=1,
        crossfade_seconds=3.0,
        warnings=[],
    )


def test_cli_requires_exactly_one_duration_mode(tmp_path: Path) -> None:
    audio_path = tmp_path / "song.wav"
    _write_loopable_audio(audio_path)

    missing = runner.invoke(app, ["lengthen", str(audio_path)])
    conflicting = runner.invoke(
        app,
        [
            "lengthen",
            str(audio_path),
            "--target-seconds",
            "30",
            "--add-seconds",
            "10",
        ],
    )

    assert missing.exit_code == 1
    assert conflicting.exit_code == 1
    assert json.loads(missing.stdout)["error"]["code"] == "invalid_options"
    assert json.loads(conflicting.stdout)["error"]["code"] == "invalid_options"


def test_dry_run_outputs_json_plan_and_does_not_render(tmp_path: Path) -> None:
    audio_path = tmp_path / "song.wav"
    _write_loopable_audio(audio_path)
    plan = _plan(audio_path)

    with (
        patch("song_lengthen.cli.create_lengthen_plan", return_value=plan),
        patch("song_lengthen.cli.render_lengthened_audio") as render,
    ):
        result = runner.invoke(
            app,
            ["lengthen", str(audio_path), "--target-seconds", "30", "--dry-run"],
        )

    assert result.exit_code == 0
    render.assert_not_called()
    payload = json.loads(result.stdout)
    assert payload["input"] == str(audio_path)
    assert payload["output"] == str(audio_path.with_name("song.lengthened.wav"))
    assert payload["loop"]["start_seconds"] == 2.0
    assert payload["repeat_count"] == 1


def test_human_output_mentions_output_and_loop(tmp_path: Path) -> None:
    audio_path = tmp_path / "song.wav"
    _write_loopable_audio(audio_path)
    plan = _plan(audio_path)

    with (
        patch("song_lengthen.cli.create_lengthen_plan", return_value=plan),
        patch("song_lengthen.cli.render_lengthened_audio"),
    ):
        result = runner.invoke(
            app,
            ["lengthen", str(audio_path), "--target-seconds", "30", "--human"],
        )

    assert result.exit_code == 0
    assert "Lengthened file:" in result.stdout
    assert "Loop: 2.000s to 10.000s" in result.stdout


def test_existing_output_is_refused_without_overwrite(tmp_path: Path) -> None:
    audio_path = tmp_path / "song.wav"
    output_path = tmp_path / "song.lengthened.wav"
    _write_loopable_audio(audio_path)
    output_path.write_bytes(b"existing")

    result = runner.invoke(app, ["lengthen", str(audio_path), "--target-seconds", "30"])

    assert result.exit_code == 1
    assert json.loads(result.stdout)["error"]["code"] == "output_exists"


def test_render_failure_returns_structured_json(tmp_path: Path) -> None:
    audio_path = tmp_path / "song.wav"
    _write_loopable_audio(audio_path)
    plan = _plan(audio_path)

    with (
        patch("song_lengthen.cli.create_lengthen_plan", return_value=plan),
        patch("song_lengthen.cli.render_lengthened_audio", side_effect=RuntimeError("ffmpeg failed")),
    ):
        result = runner.invoke(app, ["lengthen", str(audio_path), "--target-seconds", "30"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "render_error"
    assert "ffmpeg failed" in payload["error"]["message"]


def test_no_loop_returns_exit_code_2(tmp_path: Path) -> None:
    audio_path = tmp_path / "song.wav"
    _write_loopable_audio(audio_path)

    with patch(
        "song_lengthen.cli.create_lengthen_plan",
        side_effect=SongLengthenError("no_loop", "No acceptable loop candidate was found."),
    ):
        result = runner.invoke(app, ["lengthen", str(audio_path), "--target-seconds", "30"])

    assert result.exit_code == 2
    assert json.loads(result.stdout)["error"]["code"] == "no_loop"


def test_add_seconds_uses_probed_duration(tmp_path: Path) -> None:
    audio_path = tmp_path / "song.wav"
    _write_loopable_audio(audio_path)

    with (
        patch("song_lengthen.cli.probe_duration_seconds", return_value=24.0),
        patch("song_lengthen.cli.create_lengthen_plan") as create_plan,
        patch("song_lengthen.cli.render_lengthened_audio"),
    ):
        create_plan.return_value = _plan(audio_path)
        result = runner.invoke(app, ["lengthen", str(audio_path), "--add-seconds", "6"])

    assert result.exit_code == 0
    assert create_plan.call_args.kwargs["requested_seconds"] == 30.0
