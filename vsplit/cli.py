"""CLI entry point — typer app definition."""

from __future__ import annotations

import glob
from pathlib import Path

import typer

from vsplit import __version__
from vsplit.batch import FileSettings, execute_split, prepare_file
from vsplit.display import (
    console,
    create_progress,
    print_dry_run,
    print_error,
    print_results,
    print_streams_table,
    print_warning,
)
from vsplit.errors import ProbeError, VsplitError, check_ffmpeg
from vsplit.probe import list_streams
from vsplit.streams import get_audio_streams, get_subtitle_streams
from vsplit.utils import (
    DEFAULT_CHUNK_SECONDS,
    SUPPORTED_EXTENSIONS,
    find_videos_in_dir,
    is_video_file,
    parse_duration,
)
from vsplit.wizard import run_wizard

app = typer.Typer(
    name="vsplit",
    help="Fast video splitter — stream-copy by default, optional universal MP4 re-encode.",
    rich_markup_mode="rich",
)


def version_callback(value: bool):
    if value:
        print(f"vsplit {__version__}")
        raise typer.Exit()


@app.command()
def main(
    input_path: str | None = typer.Argument(
        None,
        help="Video file, folder, or glob to split. Omit for interactive mode.",
    ),
    inputs: list[str] = typer.Option(
        None,
        "-i",
        "--input",
        help="Extra video file(s), folder(s), or glob(s). Repeatable.",
    ),
    duration: str | None = typer.Option(
        None,
        "-d",
        "--duration",
        help="Chunk duration (e.g. 20, 20m, 30s, 1h). Default: 20m",
    ),
    output: Path | None = typer.Option(
        None,
        "-o",
        "--output",
        help="Output root folder. Default: next to input file.",
    ),
    parallel: int = typer.Option(
        0,
        "-p",
        "--parallel",
        help="Max parallel ffmpeg processes. 0 = auto (4 stream-copy, 1 compatibility re-encode).",
    ),
    lang: list[str] = typer.Option(
        None,
        "-l",
        "--lang",
        help="Audio language(s) to include (ISO 639 codes). Repeatable.",
    ),
    audio_index: list[int] = typer.Option(
        None,
        "-a",
        "--audio-index",
        help="Audio-relative stream index to include (0 = first audio). Repeatable.",
    ),
    sub_lang: list[str] = typer.Option(
        None,
        "--sub-lang",
        help="Subtitle language(s) to include. Repeatable.",
    ),
    sub_index: list[int] = typer.Option(
        None,
        "--sub-index",
        help="Subtitle-relative stream index to include (0 = first subtitle).",
    ),
    no_subs: bool = typer.Option(
        False,
        "--no-subs",
        help="Drop all existing subtitle streams.",
    ),
    add_sub: list[Path] = typer.Option(
        None,
        "--add-sub",
        help="Add an external soft subtitle file. Repeatable.",
    ),
    add_sub_lang: list[str] = typer.Option(
        None,
        "--add-sub-lang",
        help="Language for each --add-sub entry, in the same order. Repeatable.",
    ),
    all_mode: bool = typer.Option(
        False,
        "--all",
        help="Use the full manual workflow instead of the default fast picker flow.",
    ),
    list_streams_flag: bool = typer.Option(
        False,
        "--list-streams",
        help="Show all streams and exit.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would happen without splitting.",
    ),
    compatibility_mode: bool = typer.Option(
        False,
        "--compat",
        "--re-encode",
        help="Re-encode to universal MP4 for problem files. Slower than default stream copy.",
    ),
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=version_callback,
        is_eager=True,
        help="Show version.",
    ),
):
    """Split video files into chunks.

    Run with no arguments for interactive wizard.
    """
    # Check ffmpeg
    try:
        check_ffmpeg()
    except VsplitError as e:
        print_error(str(e))
        raise typer.Exit(1)

    # Validate parallel
    if parallel < 0:
        print_error("Parallel count must be 0 or greater.")
        raise typer.Exit(1)

    # Resolve input file(s)
    raw_inputs = []
    if input_path:
        raw_inputs.append(input_path)
    raw_inputs.extend(inputs or [])

    files = _resolve_inputs(raw_inputs)

    # If user did not pass any input, run interactive wizard
    if not raw_inputs:
        result = run_wizard(
            output_root=output,
            parallel=parallel,
            dry_run=dry_run,
            all_mode=all_mode,
            compatibility_mode=compatibility_mode,
        )
        if result is None:
            raise typer.Exit(1)
        raise typer.Exit(0)

    # User passed explicit input(s), but none resolved successfully.
    if not files:
        raise typer.Exit(1)

    # List streams mode
    if list_streams_flag:
        for f in files:
            try:
                streams = list_streams(f)
                print_streams_table(streams, f.name)
                console.print()
            except ProbeError as e:
                print_error(f"{f.name}: {e}")
        raise typer.Exit(0)

    # Parse duration
    chunk_seconds = None
    if duration:
        try:
            chunk_seconds = parse_duration(duration)
        except ValueError as e:
            print_error(f"Invalid duration: {e}")
            raise typer.Exit(1)

    # Build settings
    external_subtitles = _pair_external_subtitles(add_sub or [], add_sub_lang or [])

    if audio_index and lang:
        print_warning(
            "--audio-index and --lang both specified; --audio-index takes precedence."
        )
    if sub_index and sub_lang:
        print_warning(
            "--sub-index and --sub-lang both specified; --sub-index takes precedence."
        )

    file_settings = []
    file_streams = {}
    for f in files:
        try:
            streams = list_streams(f)
            file_streams[f] = streams
        except ProbeError as e:
            print_error(f"{f.name}: {e}")
            continue

        audio_rel_indices = None
        if audio_index:
            audio_rel_indices = _rel_to_abs_audio_indices(streams, audio_index)
            if audio_rel_indices is None:
                print_error(f"{f.name}: audio stream index {audio_index} out of range.")
                continue

        sub_rel_indices = None
        if sub_index:
            sub_rel_indices = _rel_to_abs_sub_indices(streams, sub_index)
            if sub_rel_indices is None:
                print_error(
                    f"{f.name}: subtitle stream index {sub_index} out of range."
                )
                continue

        fs = FileSettings(
            path=f,
            chunk_seconds=chunk_seconds or DEFAULT_CHUNK_SECONDS,
            languages=None if audio_index else (lang if lang else None),
            audio_indices=audio_rel_indices,
            subtitle_languages=None if sub_index else (sub_lang if sub_lang else None),
            subtitle_indices=sub_rel_indices,
            include_subtitles=not no_subs,
            external_subtitles=external_subtitles,
            compatibility_mode=compatibility_mode,
        )
        file_settings.append(fs)

    if not file_settings:
        raise typer.Exit(1)

    # Non-interactive execution
    try:
        prep_list = []
        for fs in file_settings:
            prep = prepare_file(fs, output)
            prep_list.append(prep)

        if dry_run:
            for prep in prep_list:
                print_dry_run(prep)
            raise typer.Exit(0)

        all_results = {}
        with create_progress() as progress:
            for prep in prep_list:
                task = progress.add_task(
                    f"Splitting {prep['path'].name}",
                    total=len(prep["chunks"]),
                )

                def on_progress(current, total, path, elapsed):
                    progress.update(task, completed=current)

                output_paths = execute_split(
                    prep,
                    parallel=parallel,
                    on_progress=on_progress,
                )
                all_results[prep["path"]] = output_paths
                progress.remove_task(task)

        print_results(all_results)

    except KeyboardInterrupt:
        console.print("\n[bold yellow]Interrupted.[/bold yellow]")
        raise typer.Exit(130)
    except VsplitError as e:
        print_error(str(e))
        raise typer.Exit(1)


def _resolve_inputs(raw_inputs: list[str]) -> list[Path]:
    """Resolve CLI inputs (file, folder, or glob) to unique video paths."""
    files: list[Path] = []

    for raw in raw_inputs:
        # Expand glob patterns
        if any(c in raw for c in "*?"):
            matches = [Path(m) for m in glob.glob(raw, recursive=True)]
            videos = [match.resolve() for match in matches if is_video_file(match)]
            if not matches:
                print_error(f'No files matched "{raw}".')
            elif not videos:
                print_error(
                    f'No video files matched "{raw}". Supported: {", ".join(sorted(SUPPORTED_EXTENSIONS))}'
                )
            else:
                files.extend(videos)
            continue

        p = Path(raw).expanduser().resolve()
        if not p.exists():
            print_error(f'Path "{raw}" does not exist.')
            continue

        if p.is_dir():
            videos = find_videos_in_dir(p)
            if not videos:
                print_error(f"No video files found in {p}.")
                continue
            files.extend(videos)
            continue

        if is_video_file(p):
            files.append(p)
            continue

        print_error(
            f'Unsupported format "{p.suffix}". Supported: {", ".join(sorted(SUPPORTED_EXTENSIONS))}'
        )

    seen: set[Path] = set()
    unique_files: list[Path] = []
    for file_path in files:
        if file_path not in seen:
            seen.add(file_path)
            unique_files.append(file_path)

    return unique_files


def _pair_external_subtitles(paths: list[Path], languages: list[str]) -> list[dict]:
    """Pair external subtitle files with optional language tags."""
    if len(languages) > len(paths):
        print_error("More --add-sub-lang values were provided than --add-sub files.")
        raise typer.Exit(1)

    paired = []
    for index, path in enumerate(paths):
        language = languages[index] if index < len(languages) else None
        paired.append({"path": path, "language": language})
    return paired


def _rel_to_abs_audio_indices(
    streams: list[dict], rel_indices: list[int]
) -> list[int] | None:
    """Convert audio-relative indices (0 = first audio) to absolute stream indices."""
    audio = get_audio_streams(streams)
    if not audio:
        return []
    abs_indices = []
    for rel_idx in rel_indices:
        if rel_idx < 0 or rel_idx >= len(audio):
            return None
        abs_indices.append(audio[rel_idx]["index"])
    return abs_indices


def _rel_to_abs_sub_indices(
    streams: list[dict], rel_indices: list[int]
) -> list[int] | None:
    """Convert subtitle-relative indices (0 = first subtitle) to absolute stream indices."""
    subs = get_subtitle_streams(streams)
    if not subs:
        return []
    abs_indices = []
    for rel_idx in rel_indices:
        if rel_idx < 0 or rel_idx >= len(subs):
            return None
        abs_indices.append(subs[rel_idx]["index"])
    return abs_indices


if __name__ == "__main__":
    app()
