"""Batch orchestration — process multiple files with parallel execution."""

from __future__ import annotations

from pathlib import Path

from vsplit.compat import (
    BASIC_OUTPUT_SUFFIX,
    basic_encoder_name,
    build_basic_codec_args,
    filter_basic_subtitles,
)
from vsplit.errors import SubtitleFileError
from vsplit.probe import exceeds_compatibility_limits, get_duration, list_streams
from vsplit.splitter import calculate_chunks
from vsplit.streams import build_ffmpeg_maps, select_audio, select_subtitles
from vsplit.utils import DEFAULT_CHUNK_SECONDS, is_subtitle_file, sanitize_filename


class FileSettings:
    """Settings for a single file in a batch."""

    def __init__(
        self,
        path: Path,
        chunk_seconds: float = DEFAULT_CHUNK_SECONDS,
        languages: list[str] | None = None,
        audio_indices: list[int] | None = None,
        subtitle_languages: list[str] | None = None,
        subtitle_indices: list[int] | None = None,
        include_subtitles: bool = True,
        external_subtitles: list[dict] | None = None,
        subtitle_mode: str = "existing",
        compatibility_mode: bool = False,
    ):
        self.path = path
        self.chunk_seconds = chunk_seconds
        self.languages = languages
        self.audio_indices = audio_indices
        self.subtitle_languages = subtitle_languages
        self.subtitle_indices = subtitle_indices
        self.include_subtitles = include_subtitles
        self.external_subtitles = external_subtitles or []
        self.subtitle_mode = subtitle_mode
        self.compatibility_mode = compatibility_mode

    def __repr__(self):
        return (
            f"FileSettings({self.path.name}, "
            f"chunk={self.chunk_seconds}s, "
            f"lang={self.languages}, "
            f"audio_idx={self.audio_indices}, "
            f"sub_lang={self.subtitle_languages}, "
            f"sub_idx={self.subtitle_indices}, "
            f"include_subs={self.include_subtitles}, "
            f"mode={self.subtitle_mode}, "
            f"compat={self.compatibility_mode}, "
            f"ext_subs={len(self.external_subtitles)})"
        )


def _normalize_external_subtitles(external_subtitles: list[dict]) -> list[dict]:
    """Normalize and validate external subtitle config."""
    normalized = []
    for item in external_subtitles:
        path = Path(item["path"]).expanduser().resolve()
        if not path.exists():
            raise SubtitleFileError(f"Subtitle file does not exist: {path}")
        if not is_subtitle_file(path):
            raise SubtitleFileError(f"Unsupported subtitle format: {path.suffix}")
        normalized.append(
            {
                "path": path,
                "language": item.get("language"),
            }
        )
    return normalized


def _build_metadata_args(
    subtitle_selection: list[dict],
    external_subtitles: list[dict],
) -> list[str]:
    """Build metadata args for output subtitle streams."""
    args = []
    start_index = len(subtitle_selection)
    for offset, external_subtitle in enumerate(external_subtitles):
        language = external_subtitle.get("language")
        if language:
            args.extend(
                [f"-metadata:s:s:{start_index + offset}", f"language={language}"]
            )
    return args


def _build_input_args(external_subtitles: list[dict]) -> list[str]:
    """Build extra ffmpeg input args for external subtitle files."""
    args = []
    for external_subtitle in external_subtitles:
        args.extend(["-i", str(external_subtitle["path"])])
    return args


def _subtitle_codec_for_external(path: Path, output_suffix: str) -> str:
    """Choose a soft-subtitle codec for an external subtitle file."""
    output_suffix = output_suffix.lower()
    input_suffix = path.suffix.lower()

    if output_suffix in {".mp4", ".m4v", ".mov"}:
        return "mov_text"
    if input_suffix in {".ass", ".ssa"}:
        return "ass"
    return "subrip"


def _build_stream_copy_codec_args(
    output_suffix: str,
    subtitle_selection: list[dict],
    external_subtitles: list[dict],
) -> list[str]:
    """Build codec args for fast stream-copy mode."""
    args = ["-c:v", "copy", "-c:a", "copy", "-c:t", "copy"]

    subtitle_count = len(subtitle_selection) + len(external_subtitles)
    if subtitle_count == 0:
        return args

    if output_suffix.lower() in {".mp4", ".m4v", ".mov"}:
        args.extend(["-c:s", "mov_text"])
        return args

    for index in range(len(subtitle_selection)):
        args.extend([f"-c:s:{index}", "copy"])

    for ext_offset, external_subtitle in enumerate(external_subtitles):
        codec = _subtitle_codec_for_external(external_subtitle["path"], output_suffix)
        output_index = len(subtitle_selection) + ext_offset
        args.extend([f"-c:s:{output_index}", codec])

    return args


def prepare_file(
    settings: FileSettings,
    output_root: Path | None = None,
) -> dict:
    """Prepare a single file for splitting.

    Probes the file, determines audio selection, builds map args,
    calculates chunks, and sets up output directory.

    Returns:
        dict with keys: path, duration, streams, audio_selection,
                        map_args, chunks, output_dir, output_paths
    """
    path = settings.path
    duration = get_duration(path)
    streams = list_streams(path)

    external_subtitles = _normalize_external_subtitles(settings.external_subtitles)

    # Select audio
    audio_selection = select_audio(
        streams,
        languages=settings.languages,
        indices=settings.audio_indices,
        path=path,
    )

    subtitle_selection = select_subtitles(
        streams,
        languages=settings.subtitle_languages,
        indices=settings.subtitle_indices,
        include_subtitles=settings.include_subtitles,
        path=path,
    )

    skipped_subtitles = []
    auto_compat = settings.compatibility_mode
    auto_compat_reason = ""

    if not auto_compat:
        auto_compat, auto_compat_reason = exceeds_compatibility_limits(path)

    if auto_compat:
        subtitle_selection, skipped_subtitles = filter_basic_subtitles(subtitle_selection)

    # Build ffmpeg maps
    map_args = build_ffmpeg_maps(
        streams,
        audio_selection=audio_selection,
        subtitle_selection=subtitle_selection,
        external_subtitles=external_subtitles,
        include_attachments=not settings.compatibility_mode,
    )

    # Calculate chunks
    chunks = calculate_chunks(duration, settings.chunk_seconds)

    # Output directory
    if output_root:
        output_dir = output_root / f"{sanitize_filename(path.stem)}_parts"
    else:
        output_dir = path.parent / f"{sanitize_filename(path.stem)}_parts"

    # Output paths
    ext = BASIC_OUTPUT_SUFFIX if auto_compat else path.suffix
    output_paths = [output_dir / f"{i}{ext}" for i in range(len(chunks))]

    input_args = _build_input_args(external_subtitles)
    if auto_compat:
        codec_args = build_basic_codec_args(subtitle_selection, external_subtitles)
    else:
        codec_args = _build_stream_copy_codec_args(
            ext, subtitle_selection, external_subtitles
        )
    metadata_args = _build_metadata_args(subtitle_selection, external_subtitles)

    return {
        "path": path,
        "duration": duration,
        "streams": streams,
        "audio_selection": audio_selection,
        "subtitle_selection": subtitle_selection,
        "skipped_subtitles": skipped_subtitles,
        "external_subtitles": external_subtitles,
        "input_args": input_args,
        "map_args": map_args,
        "codec_args": codec_args,
        "metadata_args": metadata_args,
        "chunks": chunks,
        "output_dir": output_dir,
        "output_paths": output_paths,
        "chunk_seconds": settings.chunk_seconds,
        "output_suffix": ext,
        "compatibility_mode": auto_compat,
        "compatibility_reason": auto_compat_reason,
        "compat_encoder": basic_encoder_name() if auto_compat else None,
    }


def execute_split(
    prep: dict,
    parallel: int = 0,
    on_progress=None,
) -> list[Path]:
    """Execute the split for a single prepared file.

    Args:
        prep: Output from prepare_file().
        parallel: Max parallel ffmpeg processes.
        on_progress: Callback(current, total, output_path, elapsed) for each chunk.

    Returns:
        List of output file paths.
    """
    path = prep["path"]
    output_dir = prep["output_dir"]
    chunks = prep["chunks"]
    input_args = prep["input_args"]
    map_args = prep["map_args"]
    codec_args = prep["codec_args"]
    metadata_args = prep["metadata_args"]
    ext = prep.get("output_suffix", BASIC_OUTPUT_SUFFIX)

    if parallel < 1:
        parallel = 1 if prep.get("compatibility_mode") else 4

    output_dir.mkdir(parents=True, exist_ok=True)

    import concurrent.futures
    import time

    results = []
    total = len(chunks)

    def split_one(idx_and_chunk):
        i, (start, end) = idx_and_chunk
        output_path = output_dir / f"{i}{ext}"
        chunk_duration = end - start

        from vsplit.splitter import split_chunk

        t0 = time.monotonic()
        split_chunk(
            path,
            output_path,
            start,
            chunk_duration,
            input_args,
            map_args,
            codec_args,
            metadata_args,
            chunk_index=i,
        )
        elapsed = time.monotonic() - t0
        return i, output_path, elapsed

    with concurrent.futures.ThreadPoolExecutor(max_workers=parallel) as executor:
        futures = {
            executor.submit(split_one, (i, chunk)): i for i, chunk in enumerate(chunks)
        }

        done_count = 0
        for future in concurrent.futures.as_completed(futures):
            i, output_path, elapsed = future.result()
            done_count += 1
            results.append((i, output_path, elapsed))
            if on_progress:
                on_progress(done_count, total, output_path, elapsed)

    # Sort by chunk index
    results.sort(key=lambda x: x[0])
    return [r[1] for r in results]
