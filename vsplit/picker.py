"""Native OS file picker helpers."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from vsplit.utils import SUPPORTED_EXTENSIONS, SUPPORTED_SUBTITLE_EXTENSIONS


def is_display_available() -> bool:
    """Check if a display/GUI is available."""
    if sys.platform == "win32":
        return True
    if sys.platform == "darwin":
        return True

    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def get_picker_backend() -> str | None:
    """Return the best available picker backend for the current environment."""
    if not is_display_available():
        return None

    if sys.platform.startswith("linux"):
        for command in ("zenity", "kdialog", "yad"):
            if shutil.which(command):
                return command

    try:
        import tkinter  # noqa: F401
    except ImportError:
        return None

    return "tkinter"


def open_file_picker(
    multi: bool = True,
    initial_dir: Path | None = None,
    title: str = "Select Video Files",
    extensions: set[str] | None = None,
) -> list[Path]:
    """Open the best available native file picker dialog.

    Returns a list of selected paths. Returns an empty list if the user cancels.
    Raises RuntimeError if no supported GUI picker backend is available.
    """
    backend = get_picker_backend()
    if not backend:
        raise RuntimeError(
            "No supported GUI picker backend is available.\n"
            "Install one of: zenity, kdialog, yad, or python3-tk."
        )

    if backend == "zenity":
        return _open_with_zenity(
            multi=multi,
            initial_dir=initial_dir,
            title=title,
            extensions=extensions or SUPPORTED_EXTENSIONS,
        )
    if backend == "kdialog":
        return _open_with_kdialog(
            multi=multi,
            initial_dir=initial_dir,
            title=title,
            extensions=extensions or SUPPORTED_EXTENSIONS,
        )
    if backend == "yad":
        return _open_with_yad(
            multi=multi,
            initial_dir=initial_dir,
            title=title,
            extensions=extensions or SUPPORTED_EXTENSIONS,
        )
    if backend == "tkinter":
        return _open_with_tkinter(
            multi=multi,
            initial_dir=initial_dir,
            title=title,
            extensions=extensions or SUPPORTED_EXTENSIONS,
        )

    raise RuntimeError(f"Unsupported picker backend: {backend}")


def open_subtitle_picker(
    multi: bool = False,
    initial_dir: Path | None = None,
) -> list[Path]:
    """Open a native subtitle picker dialog."""
    return open_file_picker(
        multi=multi,
        initial_dir=initial_dir,
        title="Select Subtitle Files",
        extensions=SUPPORTED_SUBTITLE_EXTENSIONS,
    )


def _globs_for(extensions: set[str]) -> list[str]:
    return [f"*{ext}" for ext in sorted(extensions)]


def _open_with_zenity(
    multi: bool,
    initial_dir: Path | None,
    title: str,
    extensions: set[str],
) -> list[Path]:
    cmd = [
        "zenity",
        "--file-selection",
        f"--title={title}",
        f"--file-filter=Files | {' '.join(_globs_for(extensions))}",
        "--file-filter=All files | *",
    ]

    if multi:
        cmd.extend(["--multiple", "--separator=\n"])
    if initial_dir:
        seed = initial_dir if initial_dir.is_dir() else initial_dir.parent
        cmd.append(f"--filename={seed}/")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 1:
        return []
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "zenity file picker failed")

    selected = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return [Path(path) for path in selected]


def _open_with_kdialog(
    multi: bool,
    initial_dir: Path | None,
    title: str,
    extensions: set[str],
) -> list[Path]:
    start = initial_dir if initial_dir else Path.home()
    if start.is_file():
        start = start.parent

    filters = "Files (" + " ".join(_globs_for(extensions)) + ")"
    cmd = ["kdialog", "--title", title, "--getopenfilename", str(start), filters]
    if multi:
        cmd.extend(["--multiple", "--separate-output"])

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 1:
        return []
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "kdialog file picker failed")

    selected = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return [Path(path) for path in selected]


def _open_with_yad(
    multi: bool,
    initial_dir: Path | None,
    title: str,
    extensions: set[str],
) -> list[Path]:
    cmd = [
        "yad",
        "--file-selection",
        f"--title={title}",
        f"--file-filter={' '.join(_globs_for(extensions))}",
    ]
    if multi:
        cmd.extend(["--multiple", "--separator=\n"])
    if initial_dir:
        seed = initial_dir if initial_dir.is_dir() else initial_dir.parent
        cmd.append(f"--filename={seed}/")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 1:
        return []
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "yad file picker failed")

    selected = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return [Path(path) for path in selected]


def _open_with_tkinter(
    multi: bool,
    initial_dir: Path | None,
    title: str,
    extensions: set[str],
) -> list[Path]:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    filetypes = [
        ("Files", " ".join(_globs_for(extensions))),
        ("All files", "*.*"),
    ]
    kwargs = {
        "title": title,
        "filetypes": filetypes,
    }
    if initial_dir:
        kwargs["initialdir"] = str(
            initial_dir if initial_dir.is_dir() else initial_dir.parent
        )

    try:
        if multi:
            selected = filedialog.askopenfilenames(**kwargs)
        else:
            single = filedialog.askopenfilename(**kwargs)
            selected = (single,) if single else ()
    finally:
        root.destroy()

    return [Path(path) for path in selected]
