# vsplit

[![CI](https://github.com/Misbah6005/vsplit/actions/workflows/ci.yml/badge.svg)](https://github.com/Misbah6005/vsplit/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

Fast video splitter CLI — split videos quickly with stream-copy by default, with an optional universal MP4 re-encode for problem files.

## Features

- Split video files into equal-duration chunks
- Fast default stream-copy preserves the original container, codecs, and quality
- Optional `--compat` / `--re-encode` outputs universal `.mp4` chunks for maximum device compatibility
- Compatibility mode encodes video as H.264 Baseline at max 1080p/60fps, audio as AAC stereo, and keeps text-based subtitles
- Hardware acceleration: uses Intel/AMD VAAPI H.264 encoding automatically when available, with a software `libx264` fallback
- Preserve audio tracks and subtitles
- Pick audio / subtitle tracks by language code (`--lang`, `--sub-lang`) or by stream index (`--audio-index`, `--sub-index`)
- Mux external soft subtitle files (`--add-sub` / `--add-sub-lang`)
- Parallel processing for faster splitting
- Interactive wizard or CLI mode
- Native file picker integration (zenity, kdialog, yad, tkinter)
- Dry-run mode to preview the ffmpeg command list before running

## Requirements

- Python 3.10 or newer
- `ffmpeg` and `ffprobe` on `PATH` (must be installed separately)

Install ffmpeg via your system package manager:

```bash
# Debian / Ubuntu / Linux Mint
sudo apt install ffmpeg

# Fedora
sudo dnf install ffmpeg

# Arch
sudo pacman -S ffmpeg

# macOS
brew install ffmpeg
```

## Installation

```bash
pip install vsplit
```

Or run from a clone without installing:

```bash
git clone https://github.com/Misbah6005/vsplit.git
cd vsplit
pip install -e .
```

## Usage

```bash
# Interactive wizard (no arguments)
vsplit

# Split a video file into 20-minute chunks (default)
vsplit video.mkv -d 20m

# Split with a custom output directory
vsplit video.mkv -d 10m -o ./output/

# Re-encode to universal MP4 for files that won't play on your TV/device
vsplit video.mkv -d 10m --compat

# Keep only English audio and English subtitles
vsplit movie.mkv -d 20m --lang eng --sub-lang eng

# List all streams in a video (codec, language, channels, etc.)
vsplit video.mkv --list-streams

# Preview what vsplit would do without writing any files
vsplit video.mkv -d 10m --dry-run
```

Run `vsplit --help` for the full list of options.

## How it works

- **Stream-copy mode (default):** calls `ffmpeg -c copy` for each chunk, which only remuxes the existing streams at the requested keyframes. No re-encoding, near-instant, no quality loss.
- **Compatibility mode (`--compat`):** runs `ffmpeg` with a fixed H.264 Baseline / AAC / MP4 text-subtitle profile, capped at 1080p and 60fps so the output plays on old TVs and streaming sticks. On machines with an Intel or AMD GPU, vsplit detects VAAPI support and uses `h264_vaapi` for hardware-accelerated encoding; otherwise it falls back to `libx264`.
- **Auto-cap:** if the source exceeds 1080p or 60fps and you didn't pass `--compat`, vsplit warns and switches to compatibility mode for that file.

## License

MIT — see [LICENSE](LICENSE).
