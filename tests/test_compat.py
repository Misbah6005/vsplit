"""Tests for vsplit.compat."""

from vsplit.compat import (
    BASIC_OUTPUT_SUFFIX,
    filter_basic_subtitles,
)

SAMPLE_SUBS = [
    {"index": 0, "codec": "subrip", "lang": "eng"},
    {"index": 1, "codec": "ass", "lang": "jpn"},
    {"index": 2, "codec": "hdmv_pgs_subtitle", "lang": "eng"},
    {"index": 3, "codec": "dvd_subtitle", "lang": "fre"},
    {"index": 4, "codec": "mov_text", "lang": "spa"},
    {"index": 5, "codec": "webvtt", "lang": "ger"},
    {"index": 6, "codec": "", "lang": "ita"},
]


class TestBasicOutputSuffix:
    def test_is_mp4(self):
        assert BASIC_OUTPUT_SUFFIX == ".mp4"


class TestFilterBasicSubtitles:
    def test_keeps_text_subs(self):
        compatible, skipped = filter_basic_subtitles(SAMPLE_SUBS)
        kept_codecs = {s["codec"] for s in compatible}
        assert "subrip" in kept_codecs
        assert "ass" in kept_codecs
        assert "mov_text" in kept_codecs
        assert "webvtt" in kept_codecs

    def test_skips_image_subs(self):
        compatible, skipped = filter_basic_subtitles(SAMPLE_SUBS)
        skipped_codecs = {s["codec"] for s in skipped}
        assert "hdmv_pgs_subtitle" in skipped_codecs
        assert "dvd_subtitle" in skipped_codecs

    def test_total_count_preserved(self):
        compatible, skipped = filter_basic_subtitles(SAMPLE_SUBS)
        assert len(compatible) + len(skipped) == len(SAMPLE_SUBS)

    def test_empty_input(self):
        compatible, skipped = filter_basic_subtitles([])
        assert compatible == []
        assert skipped == []
