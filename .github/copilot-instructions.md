# GitHub Copilot instructions for the vsplit project.

## Project overview
vsplit is a Python CLI that wraps `ffmpeg` to split video files into equal-duration
chunks. Default mode is `ffmpeg -c copy` (stream-copy, no re-encode). The optional
`--compat` / `--re-encode` flag transcodes to a universal H.264/AAC MP4 with
capped resolution (1080p) and framerate (60fps), and prefers Intel VAAPI when
available. See `README.md` and `vsplit/compat.py` for the full design.

## Stack
- Python 3.9+ (uses PEP 604 union types sparingly, `from __future__ import annotations` is fine)
- `typer` for the CLI surface (`vsplit/cli.py`)
- `rich` for tables, panels, progress bars (`vsplit/display.py`)
- `ffmpeg` / `ffprobe` invoked as subprocesses
- `hatchling` build backend
- `pytest` for tests, `ruff` for lint+format

## Conventions
- Module-level docstring on every file.
- Pure helpers in `vsplit/utils.py`; ffmpeg/ffprobe wrappers in `vsplit/probe.py`
  and `vsplit/splitter.py`; CLI orchestration in `vsplit/cli.py`; interactive
  wizard in `vsplit/wizard.py` (kept separate so non-interactive paths stay light).
- Stream selection logic lives in `vsplit/streams.py`; compatibility / re-encode
  logic lives in `vsplit/compat.py`; batch orchestration in `vsplit/batch.py`.
- Custom exceptions are defined in `vsplit/errors.py` and inherit `VsplitError`.
- Tests live in `tests/`; integration tests that need real ffmpeg are gated by
  the `requires_ffmpeg` marker from `tests/conftest.py`.

## House style
- Format and lint with `ruff`. CI runs `ruff check vsplit/ tests/`.
- Keep public CLI flags in `vsplit/cli.py` terse and discoverable via `--help`.
- Prefer composing ffmpeg arg lists as plain `list[str]` (no abstraction layer).
- The `split_chunk` function in `vsplit/splitter.py` is the single place that
  actually invokes ffmpeg. Other code paths feed it args but never call it
  directly.
- Preserve user-facing error messages; they are shown verbatim in the terminal.

## What not to do
- Do not introduce third-party ffmpeg bindings (e.g. `ffmpeg-python`). The
  project intentionally uses `subprocess.run` with hand-built arg lists.
- Do not change the default behavior of `vsplit` from stream-copy to re-encode.
  Re-encoding must remain opt-in via `--compat` / `--re-encode`.
- Do not add a runtime dependency on `ffmpeg-python` or any other ffmpeg
  wrapper. ffmpeg is an external binary.
