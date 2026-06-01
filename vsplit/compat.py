"""Universal media compatibility settings for vsplit outputs."""

from __future__ import annotations

import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

BASIC_OUTPUT_SUFFIX = ".mp4"
VIDEO_WIDTH_CAP = 1920
VIDEO_HEIGHT_CAP = 1080
VIDEO_FPS_CAP = 60
BASIC_VIDEO_FILTER = (
    f"fps=fps='min({VIDEO_FPS_CAP},source_fps)',"
    f"scale=w='min({VIDEO_WIDTH_CAP},iw)':h='min({VIDEO_HEIGHT_CAP},ih)':"
    "force_original_aspect_ratio=decrease:force_divisible_by=2,format=yuv420p"
)
VAAPI_RENDER_DEVICE = Path("/dev/dri/renderD128")
VAAPI_VIDEO_FILTER = (
    f"fps=fps='min({VIDEO_FPS_CAP},source_fps)',"
    f"scale=w='min({VIDEO_WIDTH_CAP},iw)':h='min({VIDEO_HEIGHT_CAP},ih)':"
    "force_original_aspect_ratio=decrease:force_divisible_by=2,format=nv12,hwupload"
)


@lru_cache(maxsize=1)
def has_h264_vaapi() -> bool:
    """Return whether this machine can use Intel/VAAPI H.264 encoding."""
    if not VAAPI_RENDER_DEVICE.exists() or not shutil.which("ffmpeg"):
        return False

    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False

    return result.returncode == 0 and "h264_vaapi" in result.stdout


def basic_encoder_name() -> str:
    """Name the encoder selected for compatibility mode."""
    return "h264_vaapi" if has_h264_vaapi() else "libx264"


VIDEO_BITRATE = "1500k"
VIDEO_MAXRATE = "1750k"
VIDEO_QP = "28"


def build_basic_codec_args(
    subtitle_selection: list[dict] | None = None,
    external_subtitles: list[dict] | None = None,
) -> list[str]:
    """Build ffmpeg codec args for old-device-compatible MP4 output."""
    if has_h264_vaapi():
        args = [
            "-vaapi_device",
            str(VAAPI_RENDER_DEVICE),
            "-vf",
            VAAPI_VIDEO_FILTER,
            "-c:v",
            "h264_vaapi",
            "-profile:v",
            "constrained_baseline",
            "-level",
            "40",
            "-bf",
            "0",
            "-qp",
            VIDEO_QP,
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ac",
            "2",
            "-ar",
            "44100",
        ]
    else:
        args = [
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-tune",
            "fastdecode",
            "-profile:v",
            "baseline",
            "-level",
            "4.0",
            "-vf",
            BASIC_VIDEO_FILTER,
            "-b:v",
            VIDEO_BITRATE,
            "-maxrate",
            VIDEO_MAXRATE,
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ac",
            "2",
            "-ar",
            "44100",
        ]

    subtitle_count = len(subtitle_selection or []) + len(external_subtitles or [])
    if subtitle_count:
        args.extend(["-c:s", "copy"])

    return args


def filter_basic_subtitles(
    subtitle_selection: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Keep only text-based subtitles that work on TVs."""
    text_codecs = {"subrip", "srt", "text", "ass", "ssa", "webvtt", "mov_text"}
    compatible = []
    skipped = []
    for subtitle in subtitle_selection:
        codec = (subtitle.get("codec") or "").lower()
        if codec in text_codecs:
            compatible.append(subtitle)
        else:
            skipped.append(subtitle)
    return compatible, skipped
