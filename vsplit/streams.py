"""Stream parsing, language matching, and ffmpeg map building."""

from __future__ import annotations

from pathlib import Path

from vsplit.errors import NoAudioMatchError, NoSubtitleMatchError


def get_audio_streams(streams: list[dict]) -> list[dict]:
    """Filter to audio streams only."""
    return [s for s in streams if s["type"] == "audio"]


def get_video_streams(streams: list[dict]) -> list[dict]:
    """Filter to video streams only."""
    return [s for s in streams if s["type"] == "video"]


def get_subtitle_streams(streams: list[dict]) -> list[dict]:
    """Filter to subtitle streams only."""
    return [s for s in streams if s["type"] == "subtitle"]


def match_subtitle_by_lang(streams: list[dict], languages: list[str]) -> list[dict]:
    """Match subtitle streams by language code."""
    subtitles = get_subtitle_streams(streams)
    if not subtitles:
        return []

    languages_lower = [language.lower() for language in languages]
    return [
        stream
        for stream in subtitles
        if (stream.get("lang") or "").lower() in languages_lower
    ]


def match_subtitle_by_index(streams: list[dict], indices: list[int]) -> list[dict]:
    """Match subtitle streams by their absolute stream index."""
    subtitles = get_subtitle_streams(streams)
    return [s for s in subtitles if s["index"] in indices]


def match_audio_by_lang(streams: list[dict], languages: list[str]) -> list[dict]:
    """Match audio streams by language code.

    Args:
        streams: All streams from the file.
        languages: List of ISO 639 language codes (e.g. ["eng", "jpn"]).

    Returns:
        List of matching audio stream dicts.
    """
    audio = get_audio_streams(streams)
    if not audio:
        return []

    languages_lower = [lang.lower() for lang in languages]
    matched = []
    for s in audio:
        lang = (s.get("lang") or "").lower()
        if lang in languages_lower:
            matched.append(s)

    return matched


def match_audio_by_index(streams: list[dict], indices: list[int]) -> list[dict]:
    """Match audio streams by their absolute stream index.

    Args:
        streams: All streams from the file.
        indices: List of absolute stream indices.

    Returns:
        List of matching audio stream dicts.
    """
    audio = get_audio_streams(streams)
    return [s for s in audio if s["index"] in indices]


def select_audio(
    streams: list[dict],
    languages: list[str] | None = None,
    indices: list[int] | None = None,
    path: Path | None = None,
) -> list[dict]:
    """Select audio streams based on language or index.

    If both are None, returns all audio streams.
    If languages are provided, matches by language.
    If indices are provided, matches by index.
    """
    audio = get_audio_streams(streams)

    if not audio:
        return []

    if languages:
        matched = match_audio_by_lang(streams, languages)
        if not matched:
            available = list({s.get("lang", "unknown") for s in audio})
            raise NoAudioMatchError(path or Path("."), languages, available)
        return matched

    if indices:
        matched = match_audio_by_index(streams, indices)
        if not matched:
            available_indices = [s["index"] for s in audio]
            raise NoAudioMatchError(
                path or Path("."),
                [str(i) for i in indices],
                [str(i) for i in available_indices],
            )
        return matched

    return audio


def select_subtitles(
    streams: list[dict],
    languages: list[str] | None = None,
    indices: list[int] | None = None,
    include_subtitles: bool = True,
    path: Path | None = None,
) -> list[dict]:
    """Select subtitle streams based on language or index."""
    subtitles = get_subtitle_streams(streams)

    if not include_subtitles or not subtitles:
        return []

    if languages:
        matched = match_subtitle_by_lang(streams, languages)
        if not matched:
            available = list({s.get("lang", "unknown") for s in subtitles})
            raise NoSubtitleMatchError(path or Path("."), languages, available)
        return matched

    if indices:
        matched = match_subtitle_by_index(streams, indices)
        if not matched:
            available_indices = [s["index"] for s in subtitles]
            raise NoSubtitleMatchError(
                path or Path("."),
                [str(i) for i in indices],
                [str(i) for i in available_indices],
            )
        return matched

    return subtitles


def build_ffmpeg_maps(
    streams: list[dict],
    audio_selection: list[dict] | None = None,
    subtitle_selection: list[dict] | None = None,
    external_subtitles: list[dict] | None = None,
    include_attachments: bool = True,
) -> list[str]:
    """Build ffmpeg -map arguments from stream selection.

    Args:
        streams: All streams from the file.
        audio_selection: If provided, only map these audio streams.
                        If None, map all audio streams.

    Returns:
        List of ffmpeg -map args (without the -map prefix).
    """
    maps = []

    # Always map first video stream
    video = get_video_streams(streams)
    if video:
        maps.append("0:v:0")

    # Map audio
    if audio_selection is not None:
        all_audio = get_audio_streams(streams)
        for s in audio_selection:
            audio_relative = all_audio.index(s)
            maps.append(f"0:a:{audio_relative}")
    else:
        audio = get_audio_streams(streams)
        if audio:
            maps.append("0:a?")

    # Map internal subtitles
    if subtitle_selection is not None:
        all_subtitles = get_subtitle_streams(streams)
        for s in subtitle_selection:
            subtitle_relative = all_subtitles.index(s)
            maps.append(f"0:s:{subtitle_relative}")
    else:
        subs = get_subtitle_streams(streams)
        if subs:
            maps.append("0:s?")

    # Map external subtitles as extra inputs
    for input_index, _subtitle in enumerate(external_subtitles or [], start=1):
        maps.append(f"{input_index}:0")

    # Attachments are skipped for universal MP4 output because many devices reject them.
    if include_attachments:
        maps.append("0:t?")

    return maps
