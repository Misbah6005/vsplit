"""Shared test fixtures for vsplit."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


@pytest.fixture(scope="session")
def ffmpeg_available() -> bool:
    """True if ffmpeg and ffprobe are on PATH."""
    return FFMPEG_AVAILABLE


requires_ffmpeg = pytest.mark.skipif(
    not FFMPEG_AVAILABLE,
    reason="ffmpeg/ffprobe not installed",
)


@pytest.fixture
def tmp_videos(tmp_path: Path) -> Path:
    """Return a temp directory ready to receive generated test videos."""
    d = tmp_path / "videos"
    d.mkdir()
    return d


@pytest.fixture
def make_video(tmp_path: Path):
    """Factory: generate a short test video with given parameters.

    Usage:
        path = make_video("clip.mp4", duration=2, width=320, height=240, audio=True)
    """

    def _make(
        name: str,
        duration: float = 2.0,
        width: int = 320,
        height: int = 240,
        audio: bool = False,
        audio_lang: str | None = None,
        subtitle: Path | None = None,
    ) -> Path:
        out = tmp_path / name
        cmd = [
            "ffmpeg",
            "-y",
            "-f", "lavfi",
            "-i", f"testsrc=duration={duration}:size={width}x{height}:rate=30",
        ]
        if audio:
            cmd.extend(["-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}"])
        if subtitle is not None:
            cmd.extend(["-i", str(subtitle)])
        cmd.extend(["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"])
        if audio:
            cmd.extend(["-c:a", "aac"])
            if audio_lang:
                cmd.extend(["-metadata:s:a:0", f"language={audio_lang}"])
        if subtitle is not None:
            cmd.extend(["-c:s", "mov_text"])
        cmd.extend(["-shortest", str(out)])
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"ffmpeg failed: {result.returncode}\n{result.stderr[-500:]}"
            )
        return out

    return _make
