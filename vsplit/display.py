"""Display utilities — progress bars, tables, formatted output."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table
from rich.text import Text

from vsplit.utils import format_duration

console = Console()


def print_box(title: str, lines: list[str], allowed: str | None = None):
    """Print a styled box with title, content, and optional allowed-input line."""
    content = ""
    if allowed:
        content += f"[dim]Allowed: {allowed}[/dim]\n"
    if lines:
        content += "\n".join(lines)
    console.print(Panel(content, title=title, border_style="blue"))


def print_error(message: str):
    """Print an error message."""
    console.print(f"[bold red]Error:[/bold red] {message}")


def print_warning(message: str):
    """Print a warning message."""
    console.print(f"[bold yellow]Warning:[/bold yellow] {message}")


def print_success(message: str):
    """Print a success message."""
    console.print(f"[bold green]✓[/bold green] {message}")


def print_streams_table(streams: list[dict], file_name: str = ""):
    """Print a table of media streams."""
    title = "Streams"
    if file_name:
        title += f" — {file_name}"

    table = Table(title=title, show_lines=False)
    table.add_column("#", style="dim", width=4)
    table.add_column("Type", style="cyan", width=10)
    table.add_column("Codec", width=10)
    table.add_column("Details")
    table.add_column("Language", width=8)
    table.add_column("Title", width=20)

    for stream in streams:
        details = ""
        if stream["type"] == "video" and stream.get("width"):
            details = f"{stream['width']}x{stream['height']}"
        elif stream["type"] == "audio":
            parts = []
            if stream.get("channels"):
                parts.append(f"{stream['channels']}ch")
            if stream.get("sample_rate"):
                parts.append(f"{stream['sample_rate']}Hz")
            details = " ".join(parts)
        elif stream["type"] == "subtitle":
            details = "text"

        table.add_row(
            str(stream["index"]),
            stream["type"],
            stream.get("codec", "unknown"),
            details,
            stream.get("lang") or "",
            stream.get("title") or "",
        )

    console.print(table)


def print_settings_summary(file_settings: list[dict]):
    """Print current settings for each file."""
    for i, item in enumerate(file_settings):
        dur = format_duration(item["chunk_seconds"])
        lang = ", ".join(item.get("languages") or []) or "all"
        console.print(
            f"  {i + 1}. {item['path'].name}  ->  {dur} chunks, audio: {lang}"
        )


def create_progress():
    """Create a rich progress bar for splitting."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=30),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
    )


def _render_command_lines(
    path: Path,
    output_dir: Path,
    ext: str,
    index: int,
    start: float,
    end: float,
    prep: dict,
) -> list[str]:
    """Render a single ffmpeg command preview."""
    input_args = prep.get("input_args", [])
    map_args = prep.get("map_args", [])
    codec_args = prep.get("codec_args", [])
    metadata_args = prep.get("metadata_args", [])

    command_parts = [f"ffmpeg -ss {start:.1f} -i {path.name}"]
    for input_index in range(0, len(input_args), 2):
        command_parts.append(f"-i {Path(input_args[input_index + 1]).name}")
    command_parts.append(f"-t {end - start:.1f}")

    lines = [escape("  " + " ".join(command_parts))]
    if map_args:
        lines.append(escape("    " + " ".join(f"-map {arg}" for arg in map_args)))
    if codec_args:
        lines.append(escape("    " + " ".join(codec_args)))
    if metadata_args:
        lines.append(escape("    " + " ".join(metadata_args)))
    lines.append(escape(f"    {output_dir.name}/{index}{ext}"))
    return lines


def print_dry_run(prep: dict):
    """Print dry run output showing what would happen."""
    path = prep["path"]
    duration = prep["duration"]
    chunks = prep["chunks"]
    output_dir = prep["output_dir"]
    subtitle_sel = prep.get("subtitle_selection", [])
    external_subtitles = prep.get("external_subtitles", [])
    skipped_subtitles = prep.get("skipped_subtitles", [])
    compatibility_mode = prep.get("compatibility_mode", False)

    if compatibility_mode:
        encoder = prep.get("compat_encoder") or "H.264"
        compat_reason = prep.get("compatibility_reason", "")
        if compat_reason:
            format_line = (
                f"MP4, {encoder} Baseline video (max 1080p, 60fps), AAC stereo audio "
                f"[auto cap: {compat_reason}]"
            )
        else:
            format_line = (
                f"MP4, {encoder} Baseline video (max 1080p, 60fps), "
                "AAC stereo audio"
            )
    else:
        format_line = "Fast stream-copy, original container/codecs"

    lines = [
        f"[bold]Input:[/bold]   {escape(str(path))} ({format_duration(duration)})",
        f"[bold]Output:[/bold]  {escape(str(output_dir))}/",
        f"[bold]Format:[/bold]  {format_line}",
        f"[bold]Chunks:[/bold]  {len(chunks)} files ({format_duration(prep['chunk_seconds'])} each)",
    ]

    audio_sel = prep.get("audio_selection", [])
    if audio_sel:
        audio_str = ", ".join(
            stream.get("lang") or f"#{stream['index']}" for stream in audio_sel
        )
        lines.append(f"[bold]Audio:[/bold]   {audio_str}")
    else:
        lines.append("[bold]Audio:[/bold]   all streams")

    if subtitle_sel or external_subtitles:
        subtitle_parts = [
            stream.get("lang") or f"#{stream['index']}" for stream in subtitle_sel
        ]
        subtitle_parts.extend(
            f"external:{item['path'].name}"
            + (f" ({item['language']})" if item.get("language") else "")
            for item in external_subtitles
        )
        lines.append(f"[bold]Subtitles:[/bold] {', '.join(subtitle_parts)}")
    else:
        lines.append("[bold]Subtitles:[/bold] none")

    if skipped_subtitles:
        skipped = ", ".join(
            stream.get("lang") or stream.get("codec") or f"#{stream['index']}"
            for stream in skipped_subtitles
        )
        lines.append(f"[bold]Skipped subtitles:[/bold] {skipped} (not basic text)")

    lines.append("")
    lines.append("[bold]Commands:[/bold]")

    ext = prep.get("output_suffix", path.suffix)
    shown = min(3, len(chunks))
    for i in range(shown):
        start, end = chunks[i]
        lines.extend(_render_command_lines(path, output_dir, ext, i, start, end, prep))
        lines.append("")

    if len(chunks) > shown:
        lines.append(f"  ... ({len(chunks) - shown} more commands)")
        lines.append("")
        i = len(chunks) - 1
        start, end = chunks[i]
        lines.extend(_render_command_lines(path, output_dir, ext, i, start, end, prep))

    console.print(
        Panel(
            Text.from_markup("\n".join(lines), emoji=False),
            title="Dry Run — No files will be modified",
            border_style="yellow",
        )
    )


def print_results(all_results: dict[Path, list[Path]]):
    """Print final results summary."""
    lines = []
    total_chunks = 0
    for input_path, output_paths in all_results.items():
        lines.append(escape(f"  {input_path.parent.name}/{input_path.name}"))
        if output_paths:
            lines.append(
                escape(f"    -> {output_paths[0].parent}/  ({len(output_paths)} files)")
            )
        else:
            lines.append("    -> no output files")
        total_chunks += len(output_paths)

    lines.append("")
    lines.append(
        f"[bold green]Done.[/bold green] {len(all_results)} file(s), {total_chunks} chunks total."
    )

    console.print(
        Panel(
            Text.from_markup("\n".join(lines), emoji=False),
            title="Results",
            border_style="green",
        )
    )
