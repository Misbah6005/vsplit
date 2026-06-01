# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2025-05-02

### Added
- Initial public release
- Fast video splitting via ffmpeg stream-copy by default
- Optional `--compat` / `--re-encode` mode for universal MP4 output
  - H.264 Baseline, max 1080p/30fps, AAC stereo audio, MP4 text subtitles
  - Intel VAAPI H.264 hardware encoding when available
- Audio selection by language (`--lang`) or index (`--audio-index`)
- Subtitle selection by language (`--sub-lang`) or index (`--sub-index`)
- Drop all existing subtitles with `--no-subs`
- Add external soft subtitle files with `--add-sub` and `--add-sub-lang`
- Parallel processing with `--parallel` (auto: 4 stream-copy, 1 re-encode)
- Interactive wizard and CLI modes
- Native file picker integration (zenity, kdialog, yad, tkinter)
- Dry-run mode (`--dry-run`) to preview commands without running them
- Stream inspection (`--list-streams`)
- Rich terminal output (tables, progress bars, panels)
