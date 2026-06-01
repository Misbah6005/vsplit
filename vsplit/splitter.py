"""Core split logic — calculate chunks and run ffmpeg."""

from __future__ import annotations

import math
import subprocess
from pathlib import Path

from vsplit.errors import DiskFullError, SplitError
from vsplit.utils import format_duration_short


def _safe_ffmpeg_path(path: Path) -> str:
    """Return a path string safe to pass to ffmpeg, even if the name starts with '-'."""
    text = str(path)
    if text.startswith("-"):
        # Prepend './' so ffmpeg cannot interpret a leading dash as an option flag
        return f"./{text}"
    return text


def calculate_chunks(
    total_seconds: float, chunk_seconds: float
) -> list[tuple[float, float]]:
    """Calculate (start, end) pairs for splitting.

    Args:
        total_seconds: Total video duration in seconds.
        chunk_seconds: Desired chunk duration in seconds.

    Returns:
        List of (start_time, end_time) tuples in seconds.
    """
    if chunk_seconds <= 0:
        raise ValueError("chunk duration must be positive")

    if not math.isfinite(total_seconds):
        raise ValueError("total duration must be a finite number")
    if total_seconds < 0:
        raise ValueError("total duration must be non-negative")

    if chunk_seconds >= total_seconds:
        return [(0.0, total_seconds)]

    chunks = []
    start = 0.0
    while start < total_seconds:
        end = min(start + chunk_seconds, total_seconds)
        chunks.append((start, end))
        start = end

    return chunks


def split_chunk(
    input_path: Path,
    output_path: Path,
    start: float,
    duration: float,
    input_args: list[str] | None = None,
    map_args: list[str] | None = None,
    codec_args: list[str] | None = None,
    metadata_args: list[str] | None = None,
    chunk_index: int = 0,
) -> subprocess.CompletedProcess:
    """Split a single chunk using ffmpeg.

    Args:
        input_path: Source video file.
        output_path: Output file path.
        start: Start time in seconds.
        duration: Chunk duration in seconds.
        map_args: Optional -map arguments (without "-map" prefix).

    Returns:
        CompletedProcess from ffmpeg.

    Raises:
        SplitError: If ffmpeg fails.
    """
    cmd = [
        "ffmpeg",
        "-y",  # overwrite output
        "-ss",
        format_duration_short(start),
        "-i",
        _safe_ffmpeg_path(input_path),
    ]

    if input_args:
        cmd.extend(input_args)

    cmd.extend(
        [
            "-t",
            format_duration_short(duration),
        ]
    )

    # Add map args if provided
    if map_args:
        for m in map_args:
            cmd.extend(["-map", m])

    if codec_args:
        cmd.extend(codec_args)
    else:
        cmd.extend(["-c", "copy"])

    if metadata_args:
        cmd.extend(metadata_args)

    cmd.extend(
        [
            "-avoid_negative_ts",
            "make_zero",
            "-movflags",
            "+faststart",
            _safe_ffmpeg_path(output_path),
        ]
    )

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600,  # 1 hour max per chunk
        )
    except subprocess.TimeoutExpired as exc:
        raise SplitError(
            chunk_index=chunk_index,
            message="ffmpeg timed out",
        ) from exc

    if result.returncode != 0:
        stderr = result.stderr.strip()
        # Check for disk full
        if "No space left on device" in stderr or "disk full" in stderr.lower():
            raise DiskFullError(chunk_index=chunk_index)
        raise SplitError(
            chunk_index=chunk_index,
            message=f"ffmpeg exited with code {result.returncode}",
            ffmpeg_output=stderr[-500:] if stderr else "",
        )

    return result
