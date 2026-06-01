"""Smoke tests for the vsplit CLI."""

from typer.testing import CliRunner

from vsplit.cli import app

runner = CliRunner()


def test_help_runs():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Usage:" in result.output
    assert "INPUT_PATH" in result.output


def test_version_flag():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "vsplit" in result.output
    assert "0.1.0" in result.output


def test_missing_input_reports_error(tmp_path):
    result = runner.invoke(app, [str(tmp_path / "nope.mp4")])
    assert result.exit_code == 1


def test_list_streams_missing_file(tmp_path):
    fake = tmp_path / "ghost.mp4"
    result = runner.invoke(app, [str(fake), "--list-streams"])
    assert result.exit_code == 1
