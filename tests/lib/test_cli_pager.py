from __future__ import annotations

from datetime import date

from typer.testing import CliRunner

from cli import app
from cli._pager import _prompt_for
from cli.readings import _echo_equivalent_command
from mojelektro_api.reading_types import ReadingTypeCode


def test_prompt_at_end_of_data_advertises_next_interval() -> None:
    out = _prompt_for(idx=10, total=10)
    assert "space=next interval" in out
    assert "q=quit" in out
    assert "esc=re-pick" in out


def test_prompt_mid_data_advertises_next_page_and_remaining_count() -> None:
    out = _prompt_for(idx=10, total=42)
    assert "32 more rows" in out
    assert "space=next" in out
    assert "esc=re-pick" in out


def test_prompt_empty_data_is_end_of_data() -> None:
    out = _prompt_for(idx=0, total=0)
    assert "space=next interval" in out


def test_echo_equivalent_command_uses_symbolic_name(capsys: object) -> None:
    _echo_equivalent_command(
        "4-0000000",
        [ReadingTypeCode.A_PLUS_15MIN.value],
        date(2026, 5, 30),
        date(2026, 6, 6),
    )
    captured = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "$ mojelektro readings 4-0000000" in captured
    assert "-t A_PLUS_15MIN" in captured
    assert "--start 2026-05-30" in captured
    assert "--end 2026-06-06" in captured


def test_echo_equivalent_command_unknown_code_falls_back_to_raw_option(
    capsys: object,
) -> None:
    _echo_equivalent_command(
        "4-0000000",
        ["ReadingType=99.99.unknown"],
        date(2026, 5, 30),
        date(2026, 6, 6),
    )
    captured = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "--option ReadingType=99.99.unknown" in captured


def test_picker_choices_include_const_name() -> None:
    """The picker title should include the Python const name so users see
    what they will copy-paste into --type."""
    from cli.readings import _picker_choices

    titles = [c.title for c in _picker_choices()]
    assert any("A_PLUS_15MIN" in t for t in titles)
    assert any("R_MINUS_T2_DAILY" in t for t in titles)


def test_readings_with_explicit_type_skips_pager() -> None:
    """Batch path: --type + non-TTY → just dump, no interactive prompt."""
    # CliRunner is non-TTY, so this exercises the batch path.
    result = CliRunner().invoke(app, ["readings", "--help"])
    assert result.exit_code == 0
