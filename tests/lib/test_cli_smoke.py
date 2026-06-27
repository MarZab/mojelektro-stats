from __future__ import annotations

from typer.testing import CliRunner

from cli import app


def test_help_exits_zero() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "mojelektro" in result.stdout.lower()


def test_default_help_shows_primary_commands() -> None:
    """Primary surface: info / contract / readings / types."""
    result = CliRunner().invoke(app, ["--help"])
    for expected in ("info", "contract", "readings", "types"):
        assert expected in result.stdout, f"missing {expected}"


def test_format_choices_in_help() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert "[table|json|yaml]" in result.stdout


def test_info_help() -> None:
    result = CliRunner().invoke(app, ["info", "--help"])
    assert result.exit_code == 0
    assert "merilno mesto" in result.stdout


def test_contract_help() -> None:
    result = CliRunner().invoke(app, ["contract", "--help"])
    assert result.exit_code == 0
    assert "merilna tocka" in result.stdout


def test_readings_help() -> None:
    result = CliRunner().invoke(app, ["readings", "--help"])
    assert result.exit_code == 0
    assert "--type" in result.stdout
    assert "--option" in result.stdout
    assert "--start" in result.stdout
    assert "--end" in result.stdout
    assert "--days" in result.stdout


def test_readings_no_args_shows_help() -> None:
    """`mojelektro readings` (no USAGE_POINT) prints help and exits 0."""
    result = CliRunner().invoke(app, ["readings"])
    assert result.exit_code == 0
    assert "USAGE_POINT" in result.stdout


def test_types_lists_hardcoded_catalog() -> None:
    """`types` dumps the hardcoded catalog — no token, no API call."""
    result = CliRunner().invoke(app, ["-f", "json", "types"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "A_PLUS_15MIN" in result.stdout
    assert "R_MINUS_T2_DAILY" in result.stdout
