# fiddle-ferret

`fiddle-ferret` is a home for small audio and media command-line tools.

## music-start

`music-start` is useful for tracks with silence, ambience, drone, sparse intros,
pre-roll, or delayed drops. It supports two detection targets:

- `main`: the likely main groove, drop, or recognizable start of the song.
- `first-musical`: the earliest musically meaningful note, beat, or event.

The detector analyzes the opening portion of the file, defaulting to the first
120 seconds. It ranks candidates using classic DSP features including loudness,
energy changes, onset strength, beat regularity, spectral shape, and novelty.

## Requirements

- Python 3.12+
- `uv`
- `ffmpeg` and `ffprobe` available on `PATH`

Python dependencies are declared in `pyproject.toml`.

## Usage

Run directly from the GitHub repo with `uvx`:

```bash
uvx --from git+https://github.com/popra/fiddle-ferret.git music-start analyze path/to/song.mp3
```

Or clone the repo and run from the checkout:

```bash
git clone https://github.com/popra/fiddle-ferret.git
cd fiddle-ferret
uv run music-start analyze path/to/song.mp3
```

Run from the source checkout:

```bash
uv run music-start analyze path/to/song.mp3
```

Run as an installed/packaged tool from this repo:

```bash
uvx --from . music-start analyze path/to/song.mp3
```

The default output is JSON with the top 3 candidates:

```bash
uv run music-start analyze song.mp3
```

Example shape:

```json
{
  "file": "song.mp3",
  "target": "main",
  "max_seconds": 120.0,
  "candidates": [
    {
      "rank": 1,
      "timestamp": "0:14.512",
      "seconds": 14.512,
      "confidence": 0.812,
      "label": "likely main start",
      "reason": "strong energy rise, sustained loudness follows"
    }
  ]
}
```

Use text output for a more readable summary:

```bash
uv run music-start analyze song.mp3 --human
```

## Options

Choose the detection target:

```bash
uv run music-start analyze song.mp3 --target main
uv run music-start analyze song.mp3 --target first-musical
```

Return more or fewer candidates:

```bash
uv run music-start analyze song.mp3 --candidates 5
```

Limit the analyzed opening window:

```bash
uv run music-start analyze song.mp3 --max-seconds 60
```

Only return candidates that leave enough audio after the timestamp:

```bash
uv run music-start analyze song.mp3 --min-remainder 45
```

All CLI duration values are seconds and may be fractional.

Combine options:

```bash
uv run music-start analyze song.mp3 --target first-musical --candidates 1 --json
```

## Trimming Files

`music-start trim-start` detects the first candidate and writes a trimmed copy
starting at that timestamp.

```bash
uv run music-start trim-start song.mp3
uv run music-start trim-start song.mp3 --target first-musical --overwrite
uv run music-start trim-start song.mp3 --output song.trimmed.mp3
uv run music-start trim-start song.mp3 --min-remainder 45
```

The command leaves the original file untouched. By default it writes
`song.trimmed.mp3` next to the input. Existing output files are not overwritten
unless `--overwrite` is provided. Use `--min-remainder` to require at least
that many seconds of audio after the detected timestamp.

## Exit Codes

- `0`: candidates found
- `1`: decode or input error
- `2`: audio decoded successfully, but no confident candidate was found

Decode errors and no-candidate results are emitted as structured JSON when using
the default output format.

## Development

Install and run through `uv`:

```bash
uv run music-start --help
uv run music-start analyze --help
uv run music-start trim-start --help
```

Run tests and lint:

```bash
uv run pytest
uv run ruff check
```

Verify packaged execution:

```bash
uvx --from . music-start --help
```

## Notes

`music-start` uses classic signal processing rather than ML models. Results are
candidate timestamps, not authoritative edits. For workflows that create derived
files, inspect the timestamp first and keep the original file intact.
