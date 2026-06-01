"""Tests for vsplit.streams."""

from pathlib import Path

import pytest

from vsplit.errors import NoAudioMatchError, NoSubtitleMatchError
from vsplit.streams import (
    build_ffmpeg_maps,
    get_audio_streams,
    get_subtitle_streams,
    get_video_streams,
    match_audio_by_index,
    match_audio_by_lang,
    match_subtitle_by_index,
    match_subtitle_by_lang,
    select_audio,
    select_subtitles,
)

SAMPLE_STREAMS = [
    {"index": 0, "type": "video", "codec": "h264"},
    {"index": 1, "type": "audio", "codec": "aac", "lang": "eng", "channels": 2},
    {"index": 2, "type": "audio", "codec": "aac", "lang": "jpn", "channels": 2},
    {"index": 3, "type": "subtitle", "codec": "subrip", "lang": "eng"},
    {"index": 4, "type": "subtitle", "codec": "ass", "lang": "jpn"},
    {"index": 5, "type": "attachment", "codec": "ttf"},
]


class TestFilters:
    def test_audio(self):
        audio = get_audio_streams(SAMPLE_STREAMS)
        assert len(audio) == 2
        assert all(s["type"] == "audio" for s in audio)

    def test_video(self):
        video = get_video_streams(SAMPLE_STREAMS)
        assert len(video) == 1
        assert video[0]["index"] == 0

    def test_subtitle(self):
        subs = get_subtitle_streams(SAMPLE_STREAMS)
        assert len(subs) == 2
        assert all(s["type"] == "subtitle" for s in subs)


class TestMatchAudioByLang:
    def test_single_match(self):
        result = match_audio_by_lang(SAMPLE_STREAMS, ["eng"])
        assert len(result) == 1
        assert result[0]["lang"] == "eng"

    def test_multiple_matches(self):
        result = match_audio_by_lang(SAMPLE_STREAMS, ["eng", "jpn"])
        assert len(result) == 2

    def test_case_insensitive(self):
        result = match_audio_by_lang(SAMPLE_STREAMS, ["ENG"])
        assert len(result) == 1

    def test_no_match_returns_empty(self):
        result = match_audio_by_lang(SAMPLE_STREAMS, ["fra"])
        assert result == []


class TestMatchAudioByIndex:
    def test_match(self):
        result = match_audio_by_index(SAMPLE_STREAMS, [1, 2])
        assert len(result) == 2
        assert {s["index"] for s in result} == {1, 2}

    def test_no_match(self):
        result = match_audio_by_index(SAMPLE_STREAMS, [99])
        assert result == []

    def test_ignores_non_audio(self):
        result = match_audio_by_index(SAMPLE_STREAMS, [0, 3])
        assert result == []


class TestMatchSubtitleByLang:
    def test_match(self):
        result = match_subtitle_by_lang(SAMPLE_STREAMS, ["jpn"])
        assert len(result) == 1
        assert result[0]["lang"] == "jpn"

    def test_no_match(self):
        assert match_subtitle_by_lang(SAMPLE_STREAMS, ["fra"]) == []


class TestMatchSubtitleByIndex:
    def test_match(self):
        result = match_subtitle_by_index(SAMPLE_STREAMS, [3, 4])
        assert len(result) == 2


class TestSelectAudio:
    def test_no_filter_returns_all(self):
        result = select_audio(SAMPLE_STREAMS)
        assert len(result) == 2

    def test_by_language(self):
        result = select_audio(SAMPLE_STREAMS, languages=["eng"])
        assert len(result) == 1
        assert result[0]["lang"] == "eng"

    def test_by_index(self):
        result = select_audio(SAMPLE_STREAMS, indices=[2])
        assert len(result) == 1
        assert result[0]["index"] == 2

    def test_no_match_raises(self):
        with pytest.raises(NoAudioMatchError):
            select_audio(SAMPLE_STREAMS, languages=["fra"])

    def test_empty_audio(self):
        no_audio = [s for s in SAMPLE_STREAMS if s["type"] != "audio"]
        assert select_audio(no_audio) == []


class TestSelectSubtitles:
    def test_no_filter_returns_all(self):
        result = select_subtitles(SAMPLE_STREAMS)
        assert len(result) == 2

    def test_by_language(self):
        result = select_subtitles(SAMPLE_STREAMS, languages=["jpn"])
        assert len(result) == 1
        assert result[0]["lang"] == "jpn"

    def test_by_index(self):
        result = select_subtitles(SAMPLE_STREAMS, indices=[3])
        assert len(result) == 1

    def test_no_subs_when_disabled(self):
        assert select_subtitles(SAMPLE_STREAMS, include_subtitles=False) == []

    def test_no_match_raises(self):
        with pytest.raises(NoSubtitleMatchError):
            select_subtitles(SAMPLE_STREAMS, languages=["fra"])


class TestBuildFFmpegMaps:
    def test_video_always_mapped(self):
        maps = build_ffmpeg_maps(SAMPLE_STREAMS)
        assert "0:v:0" in maps

    def test_default_audio_maps_all(self):
        maps = build_ffmpeg_maps(SAMPLE_STREAMS)
        # default maps audio as optional
        assert any(m.startswith("0:a") for m in maps)

    def test_specific_audio_selection(self):
        audio = [SAMPLE_STREAMS[1]]
        maps = build_ffmpeg_maps(SAMPLE_STREAMS, audio_selection=audio)
        assert "0:a:0" in maps
        assert "0:a:1" not in maps

    def test_subtitle_selection(self):
        subs = [SAMPLE_STREAMS[3]]
        maps = build_ffmpeg_maps(SAMPLE_STREAMS, subtitle_selection=subs)
        assert "0:s:0" in maps

    def test_external_subtitle_input_indices(self):
        external = [{"path": Path("a.srt"), "language": "eng"}]
        maps = build_ffmpeg_maps(SAMPLE_STREAMS, external_subtitles=external)
        assert "1:0" in maps

    def test_attachments_included_by_default(self):
        maps = build_ffmpeg_maps(SAMPLE_STREAMS, include_attachments=True)
        assert "0:t?" in maps

    def test_attachments_excluded(self):
        maps = build_ffmpeg_maps(SAMPLE_STREAMS, include_attachments=False)
        assert "0:t?" not in maps
