# vsplit

Fast video splitter CLI — split videos quickly with stream-copy by default, with optional universal MP4 re-encode for problem files.

## Features

- Split video files into equal-duration chunks
- Fast default stream-copy keeps the original container/codecs
- Optional `--compat` / `--re-encode` outputs basic `.mp4` chunks for maximum device compatibility
- Compatibility mode encodes video as H.264 Baseline at max 1080p/30fps, audio as AAC stereo, and subtitles as MP4 text
- On this Intel i3 system, compatibility mode uses Intel VAAPI H.264 hardware encoding when available
- Preserve audio tracks and subtitles
- Parallel processing for faster splitting
- Interactive wizard or CLI mode
- Native file picker integration (zenity, kdialog, yad, tkinter)

## Installation

```bash
pip install vsplit
```

## Usage

```bash
# Interactive mode
vsplit

# Split a video file
vsplit video.mkv -d 20m

# Split with custom output directory
vsplit video.mkv -d 10m -o ./output/

# Re-encode only for problem files that do not play on your TV/device
vsplit video.mkv -d 10m --compat

# List streams in a video
vsplit video.mkv --list-streams
```
