"""Tests for vsplit.errors."""


from vsplit.errors import (
    CorruptFileError,
    DiskFullError,
    EmptyFileError,
    FFmpegNotFoundError,
    NoAudioMatchError,
    NoSubtitleMatchError,
    ProbeError,
    SplitError,
    SubtitleFileError,
    VsplitError,
    format_error,
)


class TestHierarchy:
    def test_all_inherit_from_base(self):
        for cls in [
            FFmpegNotFoundError,
            CorruptFileError,
            EmptyFileError,
            NoAudioMatchError,
            NoSubtitleMatchError,
            SubtitleFileError,
        ]:
            assert issubclass(cls, VsplitError)

    def test_probe_subtypes_inherit_probe(self):
        for cls in [CorruptFileError, EmptyFileError]:
            assert issubclass(cls, ProbeError)

    def test_disk_full_inherits_split(self):
        assert issubclass(DiskFullError, SplitError)


class TestMessages:
    def test_probe_error_includes_path(self, tmp_path):
        e = ProbeError(tmp_path, "bad stream")
        assert str(tmp_path) in str(e)
        assert "bad stream" in str(e)

    def test_no_audio_match_includes_languages(self, tmp_path):
        e = NoAudioMatchError(tmp_path, ["eng", "jpn"], ["eng", "fra"])
        assert "eng" in str(e)
        assert "jpn" in str(e)

    def test_no_subtitle_match(self, tmp_path):
        e = NoSubtitleMatchError(tmp_path, ["eng"], ["jpn"])
        assert "eng" in str(e)

    def test_split_error_includes_chunk_index(self):
        e = SplitError(chunk_index=3, message="boom")
        assert "3" in str(e)
        assert "boom" in str(e)

    def test_disk_full_inherits_message(self):
        e = DiskFullError(chunk_index=7)
        assert "7" in str(e)
        assert "full" in str(e).lower()

    def test_empty_file_error(self, tmp_path):
        e = EmptyFileError(tmp_path)
        assert "empty" in str(e).lower()


class TestFormatError:
    def test_formats_vsplit_error(self):
        e = FFmpegNotFoundError("missing")
        out = format_error(e)
        assert "Error" in out
        assert "missing" in out

    def test_formats_unknown(self):
        out = format_error(ValueError("weird"))
        assert "Unexpected" in out or "Error" in out
