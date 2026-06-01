"""Tests for vsplit.utils."""

from pathlib import Path

import pytest

from vsplit.utils import (
    DEFAULT_CHUNK_SECONDS,
    SUPPORTED_EXTENSIONS,
    SUPPORTED_SUBTITLE_EXTENSIONS,
    find_videos_in_dir,
    format_duration,
    format_duration_short,
    is_subtitle_file,
    is_video_file,
    parse_duration,
    sanitize_filename,
)


class TestParseDuration:
    def test_minutes_default(self):
        assert parse_duration("20") == 1200.0

    def test_minutes_explicit(self):
        assert parse_duration("20m") == 1200.0

    def test_seconds(self):
        assert parse_duration("30s") == 30.0

    def test_hours(self):
        assert parse_duration("1h") == 3600.0

    def test_fractional_hours(self):
        assert parse_duration("1.5h") == 5400.0

    def test_fractional_minutes(self):
        assert parse_duration("0.5m") == 30.0

    def test_whitespace_stripped(self):
        assert parse_duration("  20m  ") == 1200.0

    def test_uppercase_unit(self):
        assert parse_duration("20M") == 1200.0

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            parse_duration("")

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError):
            parse_duration("abc")

    def test_zero_raises(self):
        with pytest.raises(ValueError):
            parse_duration("0")

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            parse_duration("-5m")


class TestFormatDuration:
    def test_seconds_only(self):
        assert format_duration(45) == "45s"

    def test_minutes_seconds(self):
        assert format_duration(125) == "2m 5s"

    def test_hours_minutes_seconds(self):
        assert format_duration(3725) == "1h 2m 5s"

    def test_zero(self):
        assert format_duration(0) == "0s"

    def test_negative_clamped(self):
        assert format_duration(-5) == "0s"

    def test_fractional_seconds(self):
        result = format_duration(1.5)
        assert result == "1.5s"


class TestFormatDurationShort:
    def test_zero(self):
        assert format_duration_short(0) == "00:00:00.000"

    def test_seconds(self):
        assert format_duration_short(45) == "00:00:45.000"

    def test_minutes(self):
        assert format_duration_short(125) == "00:02:05.000"

    def test_hours(self):
        assert format_duration_short(3725) == "01:02:05.000"

    def test_fractional(self):
        assert format_duration_short(1.5) == "00:00:01.500"


class TestSanitizeFilename:
    def test_passes_safe(self):
        assert sanitize_filename("hello world") == "hello world"

    def test_replaces_slashes(self):
        assert sanitize_filename("a/b\\c") == "a_b_c"

    def test_replaces_specials(self):
        assert sanitize_filename('a*b?c:d"e<f>g|h') == "a_b_c_d_e_f_g_h"

    def test_collapses_underscores(self):
        assert sanitize_filename("a___b") == "a_b"

    def test_trims_separators(self):
        assert sanitize_filename("___hello___") == "hello"

    def test_truncates_long(self):
        long = "a" * 500
        assert len(sanitize_filename(long)) == 200

    def test_empty_fallback(self):
        assert sanitize_filename("") == "unnamed"
        assert sanitize_filename("___") == "unnamed"


class TestIsVideoFile:
    def test_supported_extensions(self, tmp_path: Path):
        for ext in [".mp4", ".mkv", ".avi", ".mov"]:
            f = tmp_path / f"movie{ext}"
            f.write_bytes(b"fake")
            assert is_video_file(f)

    def test_unsupported_extension(self, tmp_path: Path):
        f = tmp_path / "doc.txt"
        f.write_bytes(b"hi")
        assert not is_video_file(f)

    def test_directory(self, tmp_path: Path):
        assert not is_video_file(tmp_path)

    def test_case_insensitive(self, tmp_path: Path):
        f = tmp_path / "movie.MP4"
        f.write_bytes(b"fake")
        assert is_video_file(f)


class TestIsSubtitleFile:
    def test_supported(self, tmp_path: Path):
        for ext in [".srt", ".ass", ".ssa", ".vtt"]:
            f = tmp_path / f"sub{ext}"
            f.write_bytes(b"1\n00:00:00,000 --> 00:00:01,000\nhi")
            assert is_subtitle_file(f)

    def test_unsupported(self, tmp_path: Path):
        f = tmp_path / "sub.txt"
        f.write_bytes(b"hi")
        assert not is_subtitle_file(f)


class TestFindVideosInDir:
    def test_finds_videos(self, tmp_path: Path):
        (tmp_path / "a.mp4").write_bytes(b"x")
        (tmp_path / "b.mkv").write_bytes(b"x")
        (tmp_path / "c.txt").write_bytes(b"x")
        result = find_videos_in_dir(tmp_path)
        assert len(result) == 2
        assert all(p.suffix in SUPPORTED_EXTENSIONS for p in result)

    def test_sorted(self, tmp_path: Path):
        for name in ["c.mp4", "a.mp4", "b.mp4"]:
            (tmp_path / name).write_bytes(b"x")
        result = find_videos_in_dir(tmp_path)
        assert [p.name for p in result] == ["a.mp4", "b.mp4", "c.mp4"]

    def test_empty_dir(self, tmp_path: Path):
        assert find_videos_in_dir(tmp_path) == []

    def test_supported_extensions_match(self):
        assert ".mp4" in SUPPORTED_EXTENSIONS
        assert ".mkv" in SUPPORTED_EXTENSIONS
        assert ".srt" in SUPPORTED_SUBTITLE_EXTENSIONS


class TestDefaultChunk:
    def test_default_is_20_minutes(self):
        assert DEFAULT_CHUNK_SECONDS == 1200
