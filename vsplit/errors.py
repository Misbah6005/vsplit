"""Error handling for vsplit."""

from pathlib import Path


class VsplitError(Exception):
    """Base exception for vsplit."""

    pass


class FFmpegNotFoundError(VsplitError):
    """ffmpeg or ffprobe not found on system."""

    pass


class ProbeError(VsplitError):
    """Error probing a video file."""

    def __init__(self, path: Path, message: str):
        self.path = path
        self.message = message
        super().__init__(f"{path}: {message}")


class NoVideoStreamError(ProbeError):
    """File has no video stream."""

    def __init__(self, path: Path):
        super().__init__(path, "No video stream found (may be audio-only)")


class CorruptFileError(ProbeError):
    """File is corrupted or unreadable."""

    def __init__(self, path: Path):
        super().__init__(path, "Could not read file (corrupted or unsupported format)")


class EmptyFileError(ProbeError):
    """File is empty."""

    def __init__(self, path: Path):
        super().__init__(path, "File is empty (0 bytes)")


class NoAudioMatchError(VsplitError):
    """No audio streams match the requested language."""

    def __init__(self, path: Path, requested: list[str], available: list[str]):
        self.path = path
        self.requested = requested
        self.available = available
        super().__init__(
            f"{path}: No audio streams matching {requested}. Available: {available}"
        )


class NoSubtitleMatchError(VsplitError):
    """No subtitle streams match the requested selection."""

    def __init__(self, path: Path, requested: list[str], available: list[str]):
        self.path = path
        self.requested = requested
        self.available = available
        super().__init__(
            f"{path}: No subtitle streams matching {requested}. Available: {available}"
        )


class SplitError(VsplitError):
    """Error during splitting."""

    def __init__(self, chunk_index: int, message: str, ffmpeg_output: str = ""):
        self.chunk_index = chunk_index
        self.ffmpeg_output = ffmpeg_output
        super().__init__(f"Chunk {chunk_index}: {message}")


class DiskFullError(SplitError):
    """Disk ran out of space during split."""

    def __init__(self, chunk_index: int):
        super().__init__(chunk_index, "Disk full")


class SubtitleFileError(VsplitError):
    """External subtitle file error."""

    pass


class OutputDirError(VsplitError):
    """Cannot create or write to output directory."""

    def __init__(self, path: Path, reason: str):
        self.path = path
        self.reason = reason
        super().__init__(f"Cannot create output directory {path}: {reason}")


def check_ffmpeg():
    """Verify ffmpeg and ffprobe are installed."""
    import shutil

    if not shutil.which("ffmpeg"):
        raise FFmpegNotFoundError(
            "ffmpeg not found. Install it:\n"
            "  apt install ffmpeg  (Debian/Ubuntu)\n"
            "  brew install ffmpeg  (macOS)\n"
            "  https://ffmpeg.org/download.html"
        )
    if not shutil.which("ffprobe"):
        raise FFmpegNotFoundError(
            "ffprobe not found (usually comes with ffmpeg). "
            "Install the full ffmpeg package."
        )
