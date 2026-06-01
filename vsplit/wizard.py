"""Interactive wizard — step-by-step guided flow."""

from __future__ import annotations

import glob
from pathlib import Path

from rich.prompt import Confirm, Prompt

from vsplit.batch import FileSettings, execute_split, prepare_file
from vsplit.display import (
    console,
    create_progress,
    print_box,
    print_dry_run,
    print_error,
    print_results,
    print_success,
    print_warning,
)
from vsplit.errors import ProbeError, VsplitError
from vsplit.picker import is_display_available, open_file_picker, open_subtitle_picker
from vsplit.probe import exceeds_compatibility_limits, get_duration, list_streams
from vsplit.streams import get_audio_streams, get_subtitle_streams
from vsplit.utils import (
    DEFAULT_CHUNK_SECONDS,
    SUPPORTED_EXTENSIONS,
    SUPPORTED_SUBTITLE_EXTENSIONS,
    find_videos_in_dir,
    format_duration,
    is_subtitle_file,
    is_video_file,
    parse_duration,
)

# ── Step 1: Pick Files ──────────────────────────────────────────────


def step_pick_files(all_mode: bool = False) -> list[Path]:
    """Pick video files.

    Fast mode opens the native picker immediately.
    All mode shows the full manual selection menu first.
    """
    current_dir = Path.cwd()
    videos_in_dir = find_videos_in_dir(current_dir)

    if not all_mode and is_display_available():
        files = _step_picker()
        if files:
            return files

    while True:
        lines = [
            "  1. Open file picker",
            f"  2. Browse current folder ({len(videos_in_dir)} video files found)",
            "  3. Enter a path or glob",
        ]

        if not is_display_available():
            lines[0] += " [dim](no display — will use path input)[/dim]"

        print_box(
            "Pick video",
            lines,
            "1, 2, 3, or press Enter for default",
        )

        choice = Prompt.ask("Choice", choices=["1", "2", "3"], default="1")

        if choice == "1":
            files = _step_picker()
            if files:
                return files
            continue

        elif choice == "2":
            files = _step_browse(videos_in_dir)
            if files:
                return files
            continue

        elif choice == "3":
            files = _step_path_input()
            if files:
                return files
            continue


def _step_picker() -> list[Path]:
    """Open OS file picker."""
    if not is_display_available():
        print_warning("No display available. Switching to path input.")
        return _step_path_input()

    try:
        selected = open_file_picker(multi=True, initial_dir=Path.cwd())
    except RuntimeError as e:
        print_warning(f"{e}\nFalling back to path input.")
        return _step_path_input()

    if not selected:
        return []

    # Filter to video files
    videos = [p for p in selected if is_video_file(p)]
    non_videos = [p for p in selected if not is_video_file(p)]

    if non_videos:
        print_warning(f"Skipped {len(non_videos)} non-video file(s).")

    if not videos:
        print_error("No video files found in selection.")
        return []

    return videos


def _step_browse(videos: list[Path]) -> list[Path]:
    """Browse video files in current directory."""
    if not videos:
        print_error(
            f"No video files found in {Path.cwd()}.\n"
            f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}\n"
            f"Use option 1 or 3 instead."
        )
        return []

    lines = []
    for i, v in enumerate(videos):
        try:
            dur = get_duration(v)
            lines.append(f"  {i + 1}. {v.name}  ({format_duration(dur)})")
        except ProbeError:
            lines.append(f"  {i + 1}. {v.name}  (duration unknown)")

    print_box(f"Videos in {Path.cwd()}", lines, "numbers, comma-separated")

    while True:
        raw = Prompt.ask("Pick")
        if not raw:
            print_error("Please select at least one file.")
            continue

        selected = _parse_number_list(raw, len(videos))
        if selected is not None:
            return [videos[i] for i in selected]


def _step_path_input() -> list[Path]:
    """Let user type a path or glob."""
    print_box(
        "Enter path or glob",
        ["Examples: /movies/vid.mkv, *.mp4, /series/season1/"],
        "path or glob",
    )

    while True:
        raw = Prompt.ask("Video path")
        if not raw:
            print_error("Please enter a path or glob.")
            continue

        raw = raw.strip()

        # Expand glob
        if any(c in raw for c in "*?"):
            matches = glob.glob(raw, recursive=True)
            if not matches:
                print_error(f'No files matched "{raw}".')
                continue
            paths = [Path(m) for m in matches]
            videos = [p for p in paths if is_video_file(p)]
            if not videos:
                print_error(f'No video files matched "{raw}".')
                continue
            return videos

        # Direct path
        p = Path(raw).expanduser().resolve()
        if not p.exists():
            print_error(f'Path "{raw}" does not exist.')
            continue

        if p.is_dir():
            videos = find_videos_in_dir(p)
            if not videos:
                print_error(
                    f"No video files found in {p}.\n"
                    f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
                )
                continue
            return videos

        if not is_video_file(p):
            print_error(
                f'Unsupported format "{p.suffix}". '
                f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            )
            continue

        return [p]


def _parse_number_list(raw: str, max_num: int) -> list[int] | None:
    """Parse comma-separated numbers. Returns 0-indexed list or None on error."""
    try:
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        indices = []
        for p in parts:
            n = int(p)
            if n < 1 or n > max_num:
                print_error(f"Invalid number {n}. Choose between 1 and {max_num}.")
                return None
            indices.append(n - 1)
        if not indices:
            print_error("Please select at least one.")
            return None
        return list(dict.fromkeys(indices))  # deduplicate, preserve order
    except ValueError:
        print_error("Invalid input. Enter numbers separated by commas (e.g. 1,2,3).")
        return None


# ── Step 2: Inspect & Confirm ───────────────────────────────────────


def step_inspect(
    files: list[Path],
    all_mode: bool = False,
) -> tuple[list[Path], dict[Path, list[dict]]]:
    """Probe files and show a compact summary.

    Returns:
        (valid_files, streams_by_file)
    """
    valid_files = []
    streams_by_file = {}
    probe_errors = {}

    for f in files:
        try:
            streams = list_streams(f)
            streams_by_file[f] = streams
            valid_files.append(f)
        except ProbeError as e:
            probe_errors[f] = e

    # Show valid files as compact summaries
    lines = []
    for f in valid_files:
        streams = streams_by_file[f]
        audio = _summarize_languages(get_audio_streams(streams), fallback="no audio")
        subtitles = _summarize_languages(get_subtitle_streams(streams), fallback="none")
        try:
            duration = format_duration(get_duration(f))
        except ProbeError:
            duration = "unknown"
        lines.append(f"  {f.name}")
        lines.append(f"    Length: {duration}")
        lines.append(f"    Audio: {audio}")
        lines.append(f"    Subtitles: {subtitles}")

    if lines:
        print_box("Quick summary", lines)

    # Handle errors
    for f, err in probe_errors.items():
        console.print(f"[bold red]Error:[/bold red] {f.name}: {err}")
        if len(files) > 1:
            skip = Confirm.ask(f"Skip {f.name} and continue?", default=True)
            if not skip:
                return [], {}
        else:
            return [], {}

    if not valid_files:
        print_error("No valid video files.")
        return [], {}

    if all_mode and not Confirm.ask(f"Use {len(valid_files)} file(s)?", default=True):
        return [], {}

    return valid_files, streams_by_file


# ── Step 3: Chunk Duration ──────────────────────────────────────────


def step_duration() -> float:
    """Step 3: Ask for chunk duration. Returns seconds."""
    print_box(
        "Chunk size",
        [],
        "number + unit: s = seconds, m = minutes, h = hours. No unit = minutes.\n"
        "Examples: 20, 20m, 5m, 30s, 1h, 1.5h",
    )

    while True:
        raw = Prompt.ask("Chunk size", default="20m")
        if not raw:
            raw = "20m"

        try:
            seconds = parse_duration(raw)
            return seconds
        except ValueError as e:
            print_error(str(e))
            continue


def step_compatibility_mode() -> bool:
    """Ask whether to re-encode for maximum TV/device compatibility."""
    print_box(
        "Compatibility mode",
        [
            "Default is fast stream-copy: keeps the original container/codecs.",
            "Use compatibility mode only for problem files. It re-encodes to MP4 and is slower.",
        ],
        "y or n",
    )
    return Confirm.ask("Re-encode for maximum compatibility?", default=False)


# ── Step 4: Stream & Subtitle Settings ──────────────────────────────


def step_batch_strategy(file_count: int) -> str:
    """Ask how batch settings should be applied."""
    if file_count <= 1:
        return "same"

    lines = [
        "  1. Use the same settings for all files",
        "  2. Use the same settings, then override some files",
    ]
    print_box("Batch mode", lines, "1 or 2")
    choice = Prompt.ask("Choice", choices=["1", "2"], default="1")
    return "override" if choice == "2" else "same"


def apply_settings_to_indices(
    files: list[Path],
    streams_by_file: dict[Path, list[dict]],
    file_settings: list[FileSettings],
    indices: list[int],
    ask_duration: bool = True,
):
    """Apply interactive settings to selected file indices."""
    targets = [files[index] for index in indices]
    target_settings = [file_settings[index] for index in indices]

    if ask_duration:
        duration = step_duration()
        for file_settings_item in target_settings:
            file_settings_item.chunk_seconds = duration

    step_audio(targets, streams_by_file, target_settings)
    step_subtitles(targets, streams_by_file, target_settings)
    step_external_subtitles(targets, target_settings)

    for offset, index in enumerate(indices):
        file_settings[index] = target_settings[offset]


def step_audio(
    files: list[Path],
    streams_by_file: dict[Path, list[dict]],
    file_settings: list[FileSettings],
) -> list[FileSettings]:
    """Ask whether to keep one audio track or all audio tracks."""
    audio_groups = [
        get_audio_streams(streams_by_file[file_path]) for file_path in files
    ]
    if len(files) > 1 and _tracks_match(audio_groups):
        _apply_audio_selection(audio_groups[0], file_settings, "all selected files")
        return file_settings

    for i, file_path in enumerate(files):
        _apply_audio_selection(audio_groups[i], [file_settings[i]], file_path.name)

    return file_settings


def step_subtitles(
    files: list[Path],
    streams_by_file: dict[Path, list[dict]],
    file_settings: list[FileSettings],
) -> list[FileSettings]:
    """Ask how subtitles should be handled for each file."""
    subtitle_groups = [
        get_subtitle_streams(streams_by_file[file_path]) for file_path in files
    ]
    if len(files) > 1 and _tracks_match(subtitle_groups):
        _apply_subtitle_selection(
            subtitle_groups[0], file_settings, "all selected files"
        )
        return file_settings

    for i, file_path in enumerate(files):
        _apply_subtitle_selection(
            subtitle_groups[i], [file_settings[i]], file_path.name
        )

    return file_settings


def step_external_subtitles(
    files: list[Path],
    file_settings: list[FileSettings],
) -> list[FileSettings]:
    """Pick external subtitles only for files that requested import."""
    import_indices = [
        index
        for index, item in enumerate(file_settings)
        if getattr(item, "subtitle_mode", None) == "import"
    ]
    if not import_indices:
        return file_settings

    if len(import_indices) == len(file_settings) and len(file_settings) > 1:
        subtitles = _pick_external_subtitles(files[0])
        if not subtitles:
            for item in file_settings:
                item.external_subtitles = []
            return file_settings

        external_subtitles = _prompt_external_subtitle_languages(subtitles)
        for item in file_settings:
            item.external_subtitles = list(external_subtitles)
            item.include_subtitles = False
            item.subtitle_languages = None
            item.subtitle_indices = None
        return file_settings

    for i, file_path in enumerate(files):
        if getattr(file_settings[i], "subtitle_mode", None) != "import":
            continue

        subtitles = _pick_external_subtitles(file_path)
        if not subtitles:
            file_settings[i].external_subtitles = []
            continue

        file_settings[i].external_subtitles = _prompt_external_subtitle_languages(
            subtitles
        )
        file_settings[i].include_subtitles = False
        file_settings[i].subtitle_languages = None
        file_settings[i].subtitle_indices = None

    return file_settings


def step_override_files(
    files: list[Path],
    streams_by_file: dict[Path, list[dict]],
    file_settings: list[FileSettings],
) -> list[FileSettings]:
    """Override settings for selected files only."""
    while True:
        summaries = []
        for i, fs in enumerate(file_settings):
            audio = _describe_audio_setting(fs, streams_by_file[fs.path])
            subtitles = _describe_subtitle_setting(fs, streams_by_file[fs.path])
            if fs.external_subtitles:
                subtitles += f" +{len(fs.external_subtitles)} external"
            summaries.append(
                f"  {i + 1}. {fs.path.name}  ->  {format_duration(fs.chunk_seconds)}, audio: {audio}, subtitles: {subtitles}"
            )

        print_box("Overrides", summaries, 'file numbers to change, or "done"')
        raw = Prompt.ask("Override which")
        if not raw or raw.lower() == "done":
            return file_settings

        indices = _parse_number_list(raw, len(files))
        if indices is None:
            continue

        for index in indices:
            apply_settings_to_indices(
                files,
                streams_by_file,
                file_settings,
                [index],
                ask_duration=True,
            )


def _format_track_label(track: dict) -> str:
    """Format an audio/subtitle track label for prompts."""
    language = track.get("lang") or "unknown"
    title = track.get("title") or ""
    label = language
    if title:
        label += f" - {title}"
    return label


def _summarize_languages(tracks: list[dict], fallback: str) -> str:
    """Summarize track languages for quick scan output."""
    if not tracks:
        return fallback
    labels = []
    for track in tracks:
        label = track.get("lang") or track.get("title") or f"#{track['index']}"
        if label not in labels:
            labels.append(label)
    return ", ".join(labels)


def _describe_audio_setting(settings: FileSettings, streams: list[dict]) -> str:
    """Describe the current audio selection for summaries."""
    if settings.audio_indices:
        selected = [
            _format_track_label(track)
            for track in get_audio_streams(streams)
            if track["index"] in settings.audio_indices
        ]
        return ", ".join(selected) or "custom"
    if settings.languages:
        return ", ".join(settings.languages)
    return "all"


def _describe_subtitle_setting(settings: FileSettings, streams: list[dict]) -> str:
    """Describe the current subtitle selection for summaries."""
    if settings.subtitle_mode == "import":
        return "import"
    if not settings.include_subtitles:
        return "none"
    if settings.subtitle_indices:
        selected = [
            _format_track_label(track)
            for track in get_subtitle_streams(streams)
            if track["index"] in settings.subtitle_indices
        ]
        return ", ".join(selected) or "custom"
    if settings.subtitle_languages:
        return ", ".join(settings.subtitle_languages)
    subtitle_tracks = get_subtitle_streams(streams)
    if len(subtitle_tracks) == 1:
        return _format_track_label(subtitle_tracks[0])
    return "all"


def _pick_external_subtitles(file_path: Path) -> list[Path]:
    """Pick external subtitle files using the native picker when available."""
    if is_display_available():
        try:
            selected = open_subtitle_picker(multi=False, initial_dir=file_path.parent)
        except RuntimeError as error:
            print_warning(f"{error}\nFalling back to path input.")
        else:
            return selected

    print_box(
        f"Import subtitle for {file_path.name}",
        [
            "Leave blank to skip.",
            f"Supported: {', '.join(sorted(SUPPORTED_SUBTITLE_EXTENSIONS))}",
        ],
        "subtitle path, glob, or Enter to skip",
    )
    while True:
        raw = Prompt.ask("Subtitle file", default="").strip()
        if not raw or raw.lower() == "none":
            return []
        subtitles = _resolve_external_subtitles(raw)
        if subtitles is not None:
            return subtitles


def _prompt_external_subtitle_languages(subtitles: list[Path]) -> list[dict]:
    """Prompt for languages for picked external subtitle files."""
    external_subtitles = []
    for subtitle_path in subtitles:
        language = Prompt.ask(
            f"Language for {subtitle_path.name}",
            default="",
            show_default=False,
        ).strip()
        external_subtitles.append(
            {
                "path": subtitle_path,
                "language": language or None,
            }
        )
    return external_subtitles


def _tracks_match(track_groups: list[list[dict]]) -> bool:
    """Check whether all selected files share the same track layout."""
    if not track_groups:
        return True
    first = _track_signature(track_groups[0])
    return all(_track_signature(group) == first for group in track_groups[1:])


def _track_signature(tracks: list[dict]) -> list[tuple[str | None, str | None]]:
    """Build a comparable signature for audio/subtitle prompts."""
    return [(track.get("lang"), track.get("title")) for track in tracks]


def _apply_audio_selection(
    audio_tracks: list[dict],
    file_settings: list[FileSettings],
    file_label: str,
):
    """Apply a simple audio choice to one or more files."""
    if len(audio_tracks) == 0:
        print_warning(f"{file_label} has no audio streams. Will split video only.")
        for item in file_settings:
            item.languages = None
            item.audio_indices = None
        return

    if len(audio_tracks) == 1:
        language = audio_tracks[0].get("lang") or "track 1"
        print_success(f"Audio: keeping {language} for {file_label}.")
        for item in file_settings:
            item.languages = None
            item.audio_indices = None
        return

    lines = [
        "  1. Keep one audio track",
        "  2. Keep all audio tracks",
    ]
    print_box(
        f"Audio for {file_label}",
        lines,
        "1 or 2",
    )

    while True:
        raw = Prompt.ask("Audio", choices=["1", "2"], default="1")
        if raw == "2":
            for item in file_settings:
                item.languages = None
                item.audio_indices = None
            return

        selected = _choose_one_track(audio_tracks, label=f"Audio for {file_label}")
        if selected is None:
            return

        for item in file_settings:
            item.languages = None
            item.audio_indices = [selected["index"]]
        return


def _apply_subtitle_selection(
    subtitle_tracks: list[dict],
    file_settings: list[FileSettings],
    file_label: str,
):
    """Apply a simple subtitle choice to one or more files."""
    if len(subtitle_tracks) == 0:
        lines = [
            "  1. No subtitles",
            "  2. Import external subtitle",
        ]
        print_box(f"Subtitles for {file_label}", lines, "1 or 2")
        choice = Prompt.ask("Choice", choices=["1", "2"], default="1")
        for item in file_settings:
            item.include_subtitles = False
            item.subtitle_languages = None
            item.subtitle_indices = None
            item.subtitle_mode = "import" if choice == "2" else "none"
        return

    if len(subtitle_tracks) == 1:
        lines = [
            "  1. Keep existing subtitle",
            "  2. No subtitles",
            "  3. Import external subtitle",
        ]
    else:
        lines = [
            "  1. No subtitles",
            "  2. Keep one existing subtitle",
            "  3. Import external subtitle",
        ]
    print_box(
        f"Subtitles for {file_label}",
        lines,
        "1, 2, or 3",
    )

    while True:
        if len(subtitle_tracks) == 1:
            choice = Prompt.ask("Subtitles", choices=["1", "2", "3"], default="1")
            if choice == "1":
                for item in file_settings:
                    item.include_subtitles = True
                    item.subtitle_languages = None
                    item.subtitle_indices = None
                    item.subtitle_mode = "existing"
                return
            if choice == "2":
                for item in file_settings:
                    item.include_subtitles = False
                    item.subtitle_languages = None
                    item.subtitle_indices = None
                    item.subtitle_mode = "none"
                return
            for item in file_settings:
                item.include_subtitles = False
                item.subtitle_languages = None
                item.subtitle_indices = None
                item.subtitle_mode = "import"
            return

        choice = Prompt.ask("Subtitles", choices=["1", "2", "3"], default="2")
        if choice == "1":
            for item in file_settings:
                item.include_subtitles = False
                item.subtitle_languages = None
                item.subtitle_indices = None
                item.subtitle_mode = "none"
            return

        if choice == "3":
            for item in file_settings:
                item.include_subtitles = False
                item.subtitle_languages = None
                item.subtitle_indices = None
                item.subtitle_mode = "import"
            return

        selected = _choose_one_track(
            subtitle_tracks,
            label=f"Existing subtitle for {file_label}",
        )
        if selected is None:
            return

        for item in file_settings:
            item.include_subtitles = True
            item.subtitle_languages = None
            item.subtitle_indices = [selected["index"]]
            item.subtitle_mode = "existing"
        return


def _choose_one_track(tracks: list[dict], label: str) -> dict | None:
    """Let the user choose a single track from a numbered list."""
    lines = [
        f"  {index + 1}. {_format_track_label(track)}"
        for index, track in enumerate(tracks)
    ]
    print_box(label, lines, f"1 to {len(tracks)}")
    while True:
        raw = Prompt.ask("Track")
        index = _parse_single_number(raw, len(tracks))
        if index is not None:
            return tracks[index]


def _parse_track_selection(
    raw: str, tracks: list[dict], kind: str
) -> list[dict] | None:
    """Parse number/code-based audio or subtitle selection."""
    parts = [part.strip() for part in raw.split(",") if part.strip()]
    selected = []
    errors = []

    for part in parts:
        try:
            index = int(part) - 1
            if 0 <= index < len(tracks):
                if tracks[index] not in selected:
                    selected.append(tracks[index])
            else:
                errors.append(f"{part} (out of range 1-{len(tracks)})")
            continue
        except ValueError:
            pass

        part_lower = part.lower()
        matched = [
            track for track in tracks if (track.get("lang") or "").lower() == part_lower
        ]
        if matched:
            for track in matched:
                if track not in selected:
                    selected.append(track)
        else:
            available = list({track.get("lang") or "unknown" for track in tracks})
            errors.append(f'"{part}" (not found, available: {", ".join(available)})')

    if errors and selected:
        print_warning(
            f"Kept {len(selected)} {kind} track(s). Ignored: {', '.join(errors)}"
        )

    if not selected:
        if errors:
            print_error(", ".join(errors))
        print_error(f"No {kind} tracks selected.")
        return None

    return selected


def _resolve_external_subtitles(raw: str) -> list[Path] | None:
    """Resolve an external subtitle path or glob."""
    if any(char in raw for char in "*?"):
        matches = [
            Path(match).expanduser().resolve()
            for match in glob.glob(raw, recursive=True)
        ]
    else:
        matches = [Path(raw).expanduser().resolve()]

    subtitle_files = [
        match for match in matches if match.exists() and is_subtitle_file(match)
    ]
    if subtitle_files:
        return subtitle_files

    if matches and all(match.exists() for match in matches):
        print_error(
            f"No supported subtitle files found. Supported: {', '.join(sorted(SUPPORTED_SUBTITLE_EXTENSIONS))}"
        )
    else:
        print_error(f'No subtitle files matched "{raw}".')
    return None


def _parse_single_number(raw: str, max_num: int) -> int | None:
    """Parse a single number (1-indexed). Returns 0-indexed or None."""
    try:
        n = int(raw.strip())
        if 1 <= n <= max_num:
            return n - 1
        print_error(f"Invalid number. Choose between 1 and {max_num}.")
        return None
    except ValueError:
        print_error("Enter a number.")
        return None


# ── Step 6: Preview ────────────────────────────────────────────────


def step_preview(prep_list: list[dict]) -> bool:
    """Show dry-run preview. Returns True if user wants to proceed."""
    for prep in prep_list:
        print_dry_run(prep)

    return Confirm.ask("Proceed with splitting?", default=True)


# ── Step 7: Confirm Overwrite ──────────────────────────────────────


def step_confirm_overwrite(prep_list: list[dict]) -> bool:
    """Check for existing output files and confirm overwrite."""
    existing = []
    for prep in prep_list:
        for p in prep["output_paths"]:
            if p.exists():
                existing.append(p)

    if not existing:
        return True

    print_warning(f"{len(existing)} output file(s) already exist.")
    for p in existing[:5]:
        print_warning(f"  {p}")
    if len(existing) > 5:
        print_warning(f"  ... and {len(existing) - 5} more")

    return Confirm.ask("Overwrite existing files?", default=True)


# ── Full Wizard ─────────────────────────────────────────────────────


def run_wizard(
    initial_files: list[Path] | None = None,
    initial_duration: float | None = None,
    initial_languages: list[str] | None = None,
    output_root: Path | None = None,
    parallel: int = 0,
    dry_run: bool = False,
    all_mode: bool = False,
    compatibility_mode: bool = False,
) -> dict | None:
    """Run the full interactive wizard.

    Returns:
        dict with results, or None if cancelled.
    """
    try:
        # Step 1: Pick files
        if initial_files:
            files = initial_files
        else:
            files = step_pick_files(all_mode=all_mode)
            if not files:
                return None

        # Step 2: Inspect
        valid_files, streams_by_file = step_inspect(files, all_mode=all_mode)
        if not valid_files:
            return None

        # Init settings
        file_settings = [
            FileSettings(
                path=f,
                chunk_seconds=initial_duration or DEFAULT_CHUNK_SECONDS,
                languages=initial_languages,
                compatibility_mode=compatibility_mode,
            )
            for f in valid_files
        ]

        # Step 3: Batch strategy first
        strategy = step_batch_strategy(len(valid_files))

        # Step 4: Apply shared settings
        apply_settings_to_indices(
            valid_files,
            streams_by_file,
            file_settings,
            list(range(len(valid_files))),
            ask_duration=initial_duration is None,
        )

        # Step 5: Override only chosen files if requested
        if strategy == "override":
            file_settings = step_override_files(
                valid_files, streams_by_file, file_settings
            )

        # Final option: keep fast stream-copy, or re-encode only for problem devices.
        # Skip if any file already triggers auto-cap
        needs_compat = False
        for f in valid_files:
            auto_triggered, _ = exceeds_compatibility_limits(f)
            if auto_triggered:
                needs_compat = True
                break

        if not compatibility_mode and not needs_compat:
            compatibility_mode = step_compatibility_mode()

        for settings in file_settings:
            settings.compatibility_mode = compatibility_mode

        # Prepare all files
        prep_list = []
        prep_errors = {}
        for fs in file_settings:
            try:
                prep = prepare_file(fs, output_root)
                prep_list.append(prep)
            except VsplitError as e:
                console.print(f"[bold red]Error:[/bold red] {fs.path.name}: {e}")
                prep_errors[fs.path] = e

        if prep_errors:
            skip = Confirm.ask(
                f"Skip {len(prep_errors)} file(s) with errors and continue?",
                default=True,
            )
            if not skip:
                return None
            console.print(f"[dim]Skipping {len(prep_errors)} file(s).[/dim]")

        if not prep_list:
            print_error("No files to process.")
            return None

        # Step 6: Preview (if dry_run)
        if dry_run:
            for prep in prep_list:
                print_dry_run(prep)
            return {}

        # Only offer preview in the full manual workflow.
        if all_mode and Confirm.ask("Preview before splitting?", default=False):
            if not step_preview(prep_list):
                return None

        # Step 7: Confirm overwrite
        if not step_confirm_overwrite(prep_list):
            print_error("Aborted.")
            return None

        # Step 8: Execute
        all_results = {}
        failed_files = []

        with create_progress() as progress:
            for file_idx, prep in enumerate(prep_list):
                task = progress.add_task(
                    f"Splitting {prep['path'].name}",
                    total=len(prep["chunks"]),
                )

                def on_progress(current, total, path, elapsed):
                    progress.update(task, completed=current)

                try:
                    output_paths = execute_split(
                        prep,
                        parallel=parallel,
                        on_progress=on_progress,
                    )
                    all_results[prep["path"]] = output_paths
                except VsplitError as e:
                    console.print(
                        f"[bold red]Error:[/bold red] {prep['path'].name}: {e}"
                    )
                    all_results[prep["path"]] = []
                    failed_files.append(prep["path"])
                finally:
                    progress.remove_task(task)

        if failed_files:
            console.print(
                f"[bold yellow]Warning:[/bold yellow] {len(failed_files)} file(s) failed."
            )

        print_results(all_results)
        return all_results

    except KeyboardInterrupt:
        console.print(
            "\n[bold yellow]Interrupted.[/bold yellow] Partial output may be saved."
        )
        return None
