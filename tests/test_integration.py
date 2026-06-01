"""Tests that require ffmpeg/ffprobe."""


from tests.conftest import requires_ffmpeg

pytestmark = requires_ffmpeg


def test_probe_get_duration(make_video):
    path = make_video("clip.mp4", duration=2)
    from vsplit.probe import get_duration

    duration = get_duration(path)
    assert 1.5 < duration < 2.5


def test_probe_list_streams(make_video):
    path = make_video("clip.mp4", duration=1, audio=True, audio_lang="eng")
    from vsplit.probe import list_streams

    streams = list_streams(path)
    types = {s["type"] for s in streams}
    assert "video" in types
    assert "audio" in types


def test_split_round_trip(make_video, tmp_path):
    """Split a 6s video into 2s chunks, verify chunk count and playability."""
    from vsplit.batch import FileSettings, execute_split, prepare_file

    src = make_video("src.mp4", duration=6)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    settings = FileSettings(path=src, chunk_seconds=2.0)
    prep = prepare_file(settings, output_root=out_dir)
    assert len(prep["chunks"]) == 3

    results = execute_split(prep, parallel=2)
    assert len(results) == 3
    for chunk in results:
        assert chunk.exists()
        assert chunk.stat().st_size > 0


def test_split_compat_mode(make_video, tmp_path):
    """Compatibility mode should produce MP4 chunks with text-based output."""
    from vsplit.batch import FileSettings, execute_split, prepare_file

    src = make_video("src.mp4", duration=4)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    settings = FileSettings(path=src, chunk_seconds=2.0, compatibility_mode=True)
    prep = prepare_file(settings, output_root=out_dir)

    results = execute_split(prep, parallel=1)
    for chunk in results:
        assert chunk.suffix == ".mp4"
        assert chunk.exists()
