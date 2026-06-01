"""Utility functions for vsplit."""

import re
from pathlib import Path

DEFAULT_CHUNK_SECONDS = 1200

SUPPORTED_EXTENSIONS = {
    ".mp4",
    ".mkv",
    ".avi",
    ".mov",
    ".webm",
    ".flv",
    ".wmv",
    ".ts",
    ".m4v",
    ".mpg",
    ".mpeg",
    ".vob",
    ".3gp",
}

SUPPORTED_SUBTITLE_EXTENSIONS = {
    ".srt",
    ".ass",
    ".ssa",
    ".vtt",
}


def parse_duration(text: str) -> float:
    """Parse a duration string into seconds.

    Accepted formats:
        "20"   → 20 minutes (default unit)
        "20m"  → 20 minutes
        "30s"  → 30 seconds
        "1h"   → 1 hour
        "1.5h" → 1.5 hours
        "0.5m" → 30 seconds
    """
    text = text.strip().lower()
    if not text:
        raise ValueError("empty duration")

    match = re.fullmatch(r"([\d.]+)\s*([smh]?)", text)
    if not match:
        raise ValueError(f"invalid duration format: {text!r}")

    value = float(match.group(1))
    unit = match.group(2) or "m"  # default to minutes

    if value < 0:
        raise ValueError("duration must be positive")
    if value == 0:
        raise ValueError("duration must be greater than 0")

    multipliers = {"s": 1, "m": 60, "h": 3600}
    return value * multipliers[unit]


def format_duration(seconds: float) -> str:
    """Format seconds into human-readable string like '1h 23m 45s'."""
    if seconds < 0:
        seconds = 0

    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60

    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if secs > 0 or not parts:
        if secs == int(secs):
            parts.append(f"{int(secs)}s")
        else:
            parts.append(f"{secs:.1f}s")

    return " ".join(parts)


def format_duration_short(seconds: float) -> str:
    """Format seconds into HH:MM:SS for ffmpeg."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def sanitize_filename(name: str) -> str:
    """Sanitize a string for use as a folder/file name."""
    # Replace problematic characters
    name = re.sub(r'[\\/*?:"<>|]', "_", name)
    # Collapse multiple underscores
    name = re.sub(r"_+", "_", name)
    # Trim
    name = name.strip("_. ")
    # Truncate to safe length
    if len(name) > 200:
        name = name[:200]
    return name or "unnamed"


def is_video_file(path: Path) -> bool:
    """Check if a path is a supported video file."""
    return path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS


def find_videos_in_dir(directory: Path) -> list[Path]:
    """Find all video files in a directory (non-recursive)."""
    return sorted(
        p
        for p in directory.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def is_subtitle_file(path: Path) -> bool:
    """Check if a path is a supported external subtitle file."""
    return path.is_file() and path.suffix.lower() in SUPPORTED_SUBTITLE_EXTENSIONS
