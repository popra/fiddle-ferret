# Agent Instructions

## Repo-Specific Context

`fiddle-ferret` is the repository name. `music_start` is only the first tool
package in the repo; do not treat it as the long-term top-level project name.
Future tools may be added beside it.

## Interface Decisions To Preserve

`music-start analyze` uses `--json` and `--human` for output selection, with
JSON as the default. Do not bring back `--format` unless it is intentionally
added as a backward-compatible alias with tests.

The trim command is `music-start trim-start`. Do not bring back `split` unless
it is intentionally added as a backward-compatible alias with tests.

All CLI duration flags use seconds, including fractional seconds.

Keep structured JSON error output stable for automation.

## Audio Safety

The CLI itself must remain read-only: it reports timestamps and must not modify
input files or control playback.

Subcommands that create derived files should leave originals untouched by
default. Overwriting should require an explicit user flag.

## Documentation Preference

README examples should use Bash syntax and Unix-style paths. Mention PowerShell
only for Windows-specific behavior.
