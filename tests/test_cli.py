from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile as sf
from typer.testing import CliRunner

from music_start.cli import app
from music_start.types import AnalysisResult, Candidate


runner = CliRunner()


def _write_sparse_intro(path: Path, sr: int = 22_050) -> None:
    silence = np.zeros(sr, dtype=np.float32)
    tone_t = np.arange(sr * 2, dtype=np.float32) / sr
    tone = (0.16 * np.sin(2 * np.pi * 440.0 * tone_t)).astype(np.float32)
    beat = np.zeros(sr * 3, dtype=np.float32)
    width = int(sr * 0.015)
    for start in range(0, len(beat), sr // 2):
        beat[start : start + width] = 0.9
    sf.write(path, np.concatenate([silence, tone, beat]), sr)


def _candidate(rank: int, seconds: float) -> Candidate:
    return Candidate(
        rank=rank,
        timestamp=f"0:{seconds:06.3f}",
        seconds=seconds,
        confidence=0.8,
        label=f"candidate {rank}",
        reason="test candidate",
    )


def _analysis_result(path: Path, seconds: list[float]) -> AnalysisResult:
    return AnalysisResult(
        file=str(path),
        target="main",
        max_seconds=120.0,
        candidates=[_candidate(rank, value) for rank, value in enumerate(seconds, start=1)],
    )


def test_cli_outputs_stable_json_schema(tmp_path: Path) -> None:
    audio_path = tmp_path / "song.wav"
    _write_sparse_intro(audio_path)

    result = runner.invoke(app, ["analyze", str(audio_path), "--target", "main"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["file"] == str(audio_path)
    assert payload["target"] == "main"
    assert payload["max_seconds"] == 120.0
    assert len(payload["candidates"]) == 3
    assert {
        "rank",
        "timestamp",
        "seconds",
        "confidence",
        "label",
        "reason",
    } <= set(payload["candidates"][0])


def test_cli_human_output_is_readable(tmp_path: Path) -> None:
    audio_path = tmp_path / "song.wav"
    _write_sparse_intro(audio_path)

    result = runner.invoke(app, ["analyze", str(audio_path), "--human"])

    assert result.exit_code == 0
    assert "Candidates for" in result.stdout
    assert "#1" in result.stdout
    assert "main" in result.stdout


def test_cli_explicit_json_output(tmp_path: Path) -> None:
    audio_path = tmp_path / "song.wav"
    _write_sparse_intro(audio_path)

    result = runner.invoke(app, ["analyze", str(audio_path), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["target"] == "main"
    assert payload["candidates"]


def test_cli_decode_error_returns_structured_json() -> None:
    result = runner.invoke(app, ["analyze", "missing.mp3"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "decode_error"
    assert "missing.mp3" in payload["error"]["message"]


def test_cli_returns_code_2_when_no_candidate(tmp_path: Path) -> None:
    audio_path = tmp_path / "silence.wav"
    sf.write(audio_path, np.zeros(22_050, dtype=np.float32), 22_050)

    result = runner.invoke(app, ["analyze", str(audio_path)])

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["candidates"] == []
    assert payload["error"]["code"] == "no_candidate"


def test_trim_start_writes_trimmed_copy_with_default_name(tmp_path: Path) -> None:
    audio_path = tmp_path / "song.wav"
    _write_sparse_intro(audio_path)

    def fake_run(command: list[str], check: bool) -> object:
        assert check is False
        assert "-ss" in command
        assert "-y" not in command
        assert "-n" in command
        assert command[-1] == str(tmp_path / "song.trimmed.wav")
        sf.write(command[-1], np.zeros(100, dtype=np.float32), 22_050)
        return type("Completed", (), {"returncode": 0})()

    with patch("music_start.cli.run_command", side_effect=fake_run):
        result = runner.invoke(app, ["trim-start", str(audio_path)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["input"] == str(audio_path)
    assert payload["output"] == str(tmp_path / "song.trimmed.wav")
    assert payload["candidate"]["seconds"] > 0
    assert audio_path.exists()
    assert (tmp_path / "song.trimmed.wav").exists()


def test_split_is_rejected_as_unknown_command(tmp_path: Path) -> None:
    audio_path = tmp_path / "song.wav"
    _write_sparse_intro(audio_path)

    result = runner.invoke(app, ["split", str(audio_path)])

    assert result.exit_code != 0
    assert "No such command" in result.stderr


def test_trim_start_refuses_existing_output_without_overwrite(tmp_path: Path) -> None:
    audio_path = tmp_path / "song.wav"
    output_path = tmp_path / "song.trimmed.wav"
    _write_sparse_intro(audio_path)
    output_path.write_bytes(b"existing")

    result = runner.invoke(app, ["trim-start", str(audio_path)])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "output_exists"


def test_trim_start_human_output_mentions_written_file(tmp_path: Path) -> None:
    audio_path = tmp_path / "song.wav"
    output_path = tmp_path / "custom.wav"
    _write_sparse_intro(audio_path)

    def fake_run(command: list[str], check: bool) -> object:
        sf.write(command[-1], np.zeros(100, dtype=np.float32), 22_050)
        return type("Completed", (), {"returncode": 0})()

    with patch("music_start.cli.run_command", side_effect=fake_run):
        result = runner.invoke(
            app,
            ["trim-start", str(audio_path), "--output", str(output_path), "--overwrite", "--human"],
        )

    assert result.exit_code == 0
    assert "Detected start:" in result.stdout
    assert f"Writing: {output_path}" in result.stdout


def test_analyze_min_remainder_filters_and_reranks_candidates(tmp_path: Path) -> None:
    audio_path = tmp_path / "song.wav"
    _write_sparse_intro(audio_path)

    with (
        patch("music_start.cli.decode_audio", return_value=(np.zeros(1, dtype=np.float32), 22_050)),
        patch("music_start.cli.analyze_audio", return_value=_analysis_result(audio_path, [10.0, 75.0])),
        patch("music_start.cli._probe_duration_seconds", return_value=100.0),
    ):
        result = runner.invoke(app, ["analyze", str(audio_path), "--min-remainder", "30"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert [item["seconds"] for item in payload["candidates"]] == [10.0]
    assert [item["rank"] for item in payload["candidates"]] == [1]


def test_trim_start_min_remainder_uses_first_qualifying_candidate(tmp_path: Path) -> None:
    audio_path = tmp_path / "song.wav"
    output_path = tmp_path / "song.trimmed.wav"
    _write_sparse_intro(audio_path)

    def fake_run(command: list[str], check: bool) -> object:
        assert command[command.index("-ss") + 1] == "20.0"
        sf.write(output_path, np.zeros(100, dtype=np.float32), 22_050)
        return type("Completed", (), {"returncode": 0})()

    with (
        patch("music_start.cli.decode_audio", return_value=(np.zeros(1, dtype=np.float32), 22_050)),
        patch("music_start.cli.analyze_audio", return_value=_analysis_result(audio_path, [80.0, 20.0])),
        patch("music_start.cli._probe_duration_seconds", return_value=100.0),
        patch("music_start.cli.run_command", side_effect=fake_run),
    ):
        result = runner.invoke(app, ["trim-start", str(audio_path), "--min-remainder", "30"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["candidate"]["seconds"] == 20.0
    assert payload["candidate"]["rank"] == 1


def test_trim_start_min_remainder_returns_no_candidate_when_all_filtered(tmp_path: Path) -> None:
    audio_path = tmp_path / "song.wav"
    _write_sparse_intro(audio_path)

    with (
        patch("music_start.cli.decode_audio", return_value=(np.zeros(1, dtype=np.float32), 22_050)),
        patch("music_start.cli.analyze_audio", return_value=_analysis_result(audio_path, [80.0])),
        patch("music_start.cli._probe_duration_seconds", return_value=100.0),
    ):
        result = runner.invoke(app, ["trim-start", str(audio_path), "--min-remainder", "30"])

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["candidates"] == []
    assert payload["error"]["code"] == "no_candidate"


def test_min_remainder_does_not_probe_duration_when_no_candidates(tmp_path: Path) -> None:
    audio_path = tmp_path / "song.wav"
    _write_sparse_intro(audio_path)

    with (
        patch("music_start.cli.decode_audio", return_value=(np.zeros(1, dtype=np.float32), 22_050)),
        patch("music_start.cli.analyze_audio", return_value=_analysis_result(audio_path, [])),
        patch("music_start.cli._probe_duration_seconds") as probe_duration,
    ):
        result = runner.invoke(app, ["analyze", str(audio_path), "--min-remainder", "30"])

    assert result.exit_code == 2
    probe_duration.assert_not_called()
    payload = json.loads(result.stdout)
    assert payload["candidates"] == []
    assert payload["error"]["code"] == "no_candidate"


def test_min_remainder_allows_exact_remaining_duration(tmp_path: Path) -> None:
    audio_path = tmp_path / "song.wav"
    _write_sparse_intro(audio_path)

    with (
        patch("music_start.cli.decode_audio", return_value=(np.zeros(1, dtype=np.float32), 22_050)),
        patch("music_start.cli.analyze_audio", return_value=_analysis_result(audio_path, [70.0])),
        patch("music_start.cli._probe_duration_seconds", return_value=100.0),
    ):
        result = runner.invoke(app, ["analyze", str(audio_path), "--min-remainder", "30"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["candidates"][0]["seconds"] == 70.0


def test_negative_min_remainder_is_rejected(tmp_path: Path) -> None:
    audio_path = tmp_path / "song.wav"
    _write_sparse_intro(audio_path)

    result = runner.invoke(app, ["analyze", str(audio_path), "--min-remainder", "-0.1"])

    assert result.exit_code != 0
    assert "Invalid value" in result.stderr
