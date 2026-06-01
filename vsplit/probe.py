"""ffprobe wrappers for video inspection."""

import json
import subprocess
from pathlib import Path

from vsplit.errors import (
    CorruptFileError,
    EmptyFileError,
    NoVideoStreamError,
    ProbeError,
)


def probe_file(path: Path) -> dict:
    """Run ffprobe and return raw JSON data."""
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired as e:
        raise ProbeError(path, "ffprobe timed out (file may be corrupted)") from e

    if result.returncode != 0:
        raise CorruptFileError(path)

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise CorruptFileError(path) from e


def get_duration(path: Path) -> float:
    """Get video duration in seconds."""
    if not path.exists():
        raise ProbeError(path, "File does not exist")
    if path.stat().st_size == 0:
        raise EmptyFileError(path)

    data = probe_file(path)

    # Try format duration first
    duration = data.get("format", {}).get("duration")
    if duration:
        try:
            return float(duration)
        except (ValueError, TypeError):
            pass

    # Fallback: max stream duration
    max_duration = 0.0
    for stream in data.get("streams", []):
        d = stream.get("duration")
        if d:
            try:
                max_duration = max(max_duration, float(d))
            except (ValueError, TypeError):
                pass

    if max_duration > 0:
        return max_duration

    raise ProbeError(path, "Could not determine duration")


def list_streams(path: Path) -> list[dict]:
    """List all streams in a video file.

    Returns list of dicts with keys:
        index: int — stream index (e.g. 0, 1, 2)
        type: str — "video", "audio", "subtitle", "attachment", etc.
        codec: str — codec name (e.g. "h264", "aac")
        lang: str or None — language code
        title: str or None — stream title
        width: int or None — video width
        height: int or None — video height
        channels: int or None — audio channel count
        sample_rate: str or None — audio sample rate
    """
    if not path.exists():
        raise ProbeError(path, "File does not exist")
    if path.stat().st_size == 0:
        raise EmptyFileError(path)

    data = probe_file(path)
    streams = data.get("streams", [])

    if not any(s.get("codec_type") == "video" for s in streams):
        raise NoVideoStreamError(path)

    result = []
    for s in streams:
        info = {
            "index": s.get("index", 0),
            "type": s.get("codec_type", "unknown"),
            "codec": s.get("codec_name", "unknown"),
            "lang": s.get("tags", {}).get("language"),
            "title": s.get("tags", {}).get("title"),
            "width": s.get("width"),
            "height": s.get("height"),
            "channels": s.get("channels"),
            "sample_rate": s.get("sample_rate"),
        }
        result.append(info)

    return result


def get_format_info(path: Path) -> dict:
    """Get format-level info (container format, size, etc.)."""
    data = probe_file(path)
    fmt = data.get("format", {})
    return {
        "format": fmt.get("format_long_name", "unknown"),
        "size": int(fmt.get("size", 0)),
        "bit_rate": fmt.get("bit_rate"),
        "duration": fmt.get("duration"),
    }


VIDEO_WIDTH_CAP = 1920
VIDEO_HEIGHT_CAP = 1080
VIDEO_FPS_CAP = 60


def exceeds_compatibility_limits(path: Path) -> tuple[bool, str]:
    """Check if video exceeds compatibility limits.

    Returns (True, reason) if caps needed, (False, "") if stream-copy OK.
    """
    streams = list_streams(path)

    for stream in streams:
        if stream["type"] != "video":
            continue

        width = stream.get("width") or 0
        height = stream.get("height") or 0

        if width > VIDEO_WIDTH_CAP or height > VIDEO_HEIGHT_CAP:
            return True, f"resolution {width}x{height} exceeds {VIDEO_WIDTH_CAP}x{VIDEO_HEIGHT_CAP}"

    data = probe_file(path)
    for stream in data.get("streams", []):
        if stream.get("codec_type") != "video":
            continue

        r_frame_rate = stream.get("r_frame_rate", "0/1")
        if "/" in r_frame_rate:
            try:
                num, denom = r_frame_rate.split("/")
                fps = float(num) / float(denom)
            except (ValueError, ZeroDivisionError):
                fps = 0
        else:
            try:
                fps = float(r_frame_rate)
            except ValueError:
                fps = 0

        if fps > VIDEO_FPS_CAP:
            return True, f"fps {fps:.1f} exceeds {VIDEO_FPS_CAP}"

    return False, ""
