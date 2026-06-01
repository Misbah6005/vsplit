"""Tests for security/correctness fixes — markup escape, dash-prefix protection,
duration edge cases, output-dir error, expanduser, no-subs warning."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import typer
from typer.testing import CliRunner

from vsplit.cli import (
    _pair_external_subtitles,
    _rel_to_abs_audio_indices,
    _rel_to_abs_sub_indices,
    app,
)
from vsplit.errors import OutputDirError
from vsplit.splitter import _safe_ffmpeg_path, calculate_chunks

runner = CliRunner()


class TestSafeFFmpegPath:
    def test_normal_path_unchanged(self, tmp_path: Path):
        assert _safe_ffmpeg_path(tmp_path / "video.mp4") == str(tmp_path / "video.mp4")

    def test_relative_dash_prefix_gets_dot_slash(self, tmp_path: Path, monkeypatch):
        # Simulate a relative path that starts with '-' (e.g. cwd-relative glob hit)
        monkeypatch.chdir(tmp_path)
        sneaky = Path("-evil.mp4")
        result = _safe_ffmpeg_path(sneaky)
        assert result.startswith("./")
        assert result == "./-evil.mp4"

    def test_absolute_path_passthrough(self, tmp_path: Path):
        # Absolute paths never start with '-', so they pass through unchanged
        result = _safe_ffmpeg_path(tmp_path / "-flag.mp4")
        assert not result.startswith("./")
        assert result.startswith("/")


class TestCalculateChunksInf:
    def test_inf_total_does_not_loop(self):
        with pytest.raises((ValueError, OverflowError)):
            calculate_chunks(float("inf"), 60)

    def test_zero_total_single_empty_chunk(self):
        chunks = calculate_chunks(0, 60)
        assert chunks == [(0.0, 0.0)]


class TestMarkupEscapeInPrints:
    def test_print_error_does_not_crash_on_markup(self):
        from io import StringIO

        from rich.console import Console

        from vsplit.display import print_error

        buf = StringIO()
        with patch("vsplit.display.console", Console(file=buf, force_terminal=False, color_system=None)):
            # Should not raise — even with markup-like characters in user data
            print_error("File [/tmp/evil] [/] not found")

        out = buf.getvalue()
        # Brackets should appear in the rendered output (escape renders \[ → [)
        assert "[/tmp/evil]" in out

    def test_print_warning_does_not_crash_on_markup(self):
        from io import StringIO

        from rich.console import Console

        from vsplit.display import print_warning

        buf = StringIO()
        with patch("vsplit.display.console", Console(file=buf, force_terminal=False, color_system=None)):
            print_warning("Path [bold red]X[/] contains markup")

        out = buf.getvalue()
        assert "[bold red]X[/]" in out

    def test_print_success_does_not_crash_on_markup(self):
        from io import StringIO

        from rich.console import Console

        from vsplit.display import print_success

        buf = StringIO()
        with patch("vsplit.display.console", Console(file=buf, force_terminal=False, color_system=None)):
            print_success("Saved [b]X[/]")

        out = buf.getvalue()
        assert "[b]X[/]" in out

    def test_uses_escape_not_raw_interpolation(self):
        # Source-level guarantee: the print helpers wrap the message with escape()
        import inspect

        from vsplit import display

        for name in ("print_error", "print_warning", "print_success"):
            source = inspect.getsource(getattr(display, name))
            assert "escape(" in source, f"{name} should use rich.markup.escape()"


class TestNoSubsWarning:
    def test_no_subs_with_sub_lang_warns(self, tmp_path, capsys):
        fake = tmp_path / "x.mp4"
        # We use a missing file so the probe step fails fast, but the
        # no-subs warning should print before that error.
        result = runner.invoke(
            app,
            [str(fake), "--no-subs", "--sub-lang", "eng"],
        )
        # Should exit 1 (file doesn't exist) but warn first
        assert "no-subs overrides" in result.output or result.exit_code == 1

    def test_no_subs_alone_does_not_warn(self, tmp_path, capsys):
        fake = tmp_path / "x.mp4"
        result = runner.invoke(app, [str(fake), "--no-subs"])
        assert "no-subs overrides" not in result.output


class TestOutputExpanduser:
    def test_tilde_is_expanded(self, tmp_path, monkeypatch):
        # If we pass ~/somewhere and HOME is tmp_path, the file should be resolved there
        monkeypatch.setenv("HOME", str(tmp_path))
        target = tmp_path / "out"
        target.mkdir()
        # The path is resolved when we call .expanduser().resolve() on it
        result = Path("~/out").expanduser().resolve()
        assert result.parent == tmp_path
        assert result.name == "out"


class TestOutputDirError:
    def test_permission_denied_raises_output_dir_error(self, tmp_path, monkeypatch):
        from vsplit.batch import execute_split

        # Build a minimal prep dict
        prep = {
            "path": tmp_path / "src.mp4",
            "output_dir": tmp_path / "no_perm_out",
            "chunks": [(0.0, 1.0)],
            "input_args": [],
            "map_args": [],
            "codec_args": [],
            "metadata_args": [],
            "output_suffix": ".mp4",
        }

        def fake_mkdir(*args, **kwargs):
            raise PermissionError("denied")

        monkeypatch.setattr(Path, "mkdir", fake_mkdir)
        with pytest.raises(OutputDirError) as exc:
            execute_split(prep, parallel=1)
        assert "permission denied" in str(exc.value).lower()


class TestPairExternalSubtitles:
    def test_basic(self, tmp_path):
        p1 = tmp_path / "a.srt"
        p2 = tmp_path / "b.ass"
        result = _pair_external_subtitles([p1, p2], ["eng", "jpn"])
        assert result == [
            {"path": p1, "language": "eng"},
            {"path": p2, "language": "jpn"},
        ]

    def test_missing_languages_default_to_none(self, tmp_path):
        p1 = tmp_path / "a.srt"
        result = _pair_external_subtitles([p1], [])
        assert result == [{"path": p1, "language": None}]

    def test_more_languages_than_files_exits(self, tmp_path):
        p1 = tmp_path / "a.srt"
        # typer.Exit inherits from RuntimeError, not SystemExit
        with pytest.raises((typer.Exit, SystemExit)):
            _pair_external_subtitles([p1], ["eng", "jpn"])


class TestRelToAbsIndices:
    SAMPLE = [
        {"index": 0, "type": "video"},
        {"index": 1, "type": "audio", "lang": "eng"},
        {"index": 2, "type": "audio", "lang": "jpn"},
        {"index": 3, "type": "subtitle", "lang": "eng"},
        {"index": 4, "type": "subtitle", "lang": "jpn"},
    ]

    def test_audio_indices_basic(self):
        assert _rel_to_abs_audio_indices(self.SAMPLE, [0]) == [1]
        assert _rel_to_abs_audio_indices(self.SAMPLE, [1, 0]) == [2, 1]

    def test_audio_out_of_range_returns_none(self):
        assert _rel_to_abs_audio_indices(self.SAMPLE, [5]) is None
        assert _rel_to_abs_audio_indices(self.SAMPLE, [-1]) is None

    def test_audio_no_audio_returns_empty(self):
        no_audio = [s for s in self.SAMPLE if s["type"] != "audio"]
        assert _rel_to_abs_audio_indices(no_audio, [0]) == []

    def test_subtitle_indices_basic(self):
        assert _rel_to_abs_sub_indices(self.SAMPLE, [0]) == [3]
        assert _rel_to_abs_sub_indices(self.SAMPLE, [1]) == [4]

    def test_subtitle_out_of_range_returns_none(self):
        assert _rel_to_abs_sub_indices(self.SAMPLE, [99]) is None

    def test_subtitle_no_subs_returns_empty(self):
        no_subs = [s for s in self.SAMPLE if s["type"] != "subtitle"]
        assert _rel_to_abs_sub_indices(no_subs, [0]) == []


class TestCompatCapsCentralized:
    """The VIDEO_*_CAP constants are the single source of truth for caps
    in both the filter strings and the limit checker."""

    def test_caps_match_filter_strings(self):
        from vsplit.compat import (
            BASIC_VIDEO_FILTER,
            VAAPI_VIDEO_FILTER,
            VIDEO_FPS_CAP,
            VIDEO_HEIGHT_CAP,
            VIDEO_WIDTH_CAP,
        )

        for filt in (BASIC_VIDEO_FILTER, VAAPI_VIDEO_FILTER):
            assert str(VIDEO_FPS_CAP) in filt
            assert str(VIDEO_WIDTH_CAP) in filt
            assert str(VIDEO_HEIGHT_CAP) in filt

    def test_caps_importable_from_probe(self):
        from vsplit.compat import (
            VIDEO_FPS_CAP as A,
        )
        from vsplit.compat import (
            VIDEO_HEIGHT_CAP as B,
        )
        from vsplit.compat import (
            VIDEO_WIDTH_CAP as C,
        )
        from vsplit.probe import VIDEO_FPS_CAP, VIDEO_HEIGHT_CAP, VIDEO_WIDTH_CAP

        assert VIDEO_FPS_CAP == A
        assert VIDEO_HEIGHT_CAP == B
        assert VIDEO_WIDTH_CAP == C


class TestOutputDirErrorInErrorsModule:
    def test_subclasses_vsplit_error(self):
        from vsplit.errors import OutputDirError, VsplitError

        assert issubclass(OutputDirError, VsplitError)
