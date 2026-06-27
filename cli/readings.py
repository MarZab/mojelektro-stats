from __future__ import annotations

import asyncio
import sys
from datetime import UTC, date, datetime, timedelta

import questionary
import typer

from cli._client import build_client
from cli._format import (
    OutputFormat,
    compute_widths,
    dump_readings,
    format_row,
    pivot_readings,
)
from cli._pager import paginate
from cli._resolve import resolve_gsrn_mm
from mojelektro import MojElektroClient
from mojelektro.reading_types import BY_NAME, BY_RAW_CODE, KNOWN_READING_TYPES

# Highlight only the marker (pointer arrow + checkbox dot), not the
# focused row's text — questionary's default `highlighted` style colors
# the entire row, which makes the value hard to read.
_CHECKBOX_STYLE = questionary.Style(
    [
        ("highlighted", ""),
        ("pointer", "fg:cyan bold"),
        ("selected", "fg:cyan bold"),
    ]
)


def _resolve_types(
    type_names: list[str] | None,
    raw_options: list[str] | None,
) -> list[str]:
    resolved: list[str] = []
    for name in type_names or []:
        info = BY_NAME.get(name)
        if info is None:
            available = ", ".join(sorted(BY_NAME))
            raise typer.BadParameter(
                f"unknown reading type {name!r}. Available: {available}",
                param_hint="--type",
            )
        resolved.append(info.code.value)
    resolved.extend(raw_options or [])
    return resolved


def _picker_choices() -> list[questionary.Choice]:
    # Layout: <const name>  <oznaka>  <perioda>  <opis>
    name_w = max(len(rt.name) for rt in KNOWN_READING_TYPES)
    oznaka_w = max(len(rt.oznaka) for rt in KNOWN_READING_TYPES)
    perioda_w = max(len(rt.perioda) for rt in KNOWN_READING_TYPES)
    return [
        questionary.Choice(
            title=(
                f"{rt.name.ljust(name_w)}  "
                f"{rt.oznaka.ljust(oznaka_w)}  "
                f"{rt.perioda.ljust(perioda_w)}  "
                f"{rt.opis}"
            ),
            value=rt.code.value,
        )
        for rt in KNOWN_READING_TYPES
    ]


def _echo_equivalent_command(
    usage_point: str, options: list[str], start_d: date, end_d: date
) -> None:
    """Print the non-interactive command that produces the same output."""
    parts = ["mojelektro", "readings", usage_point]
    for code in options:
        raw = code.removeprefix("ReadingType=")
        info = BY_RAW_CODE.get(raw)
        if info is not None:
            parts.extend(["-t", info.name])
        else:
            parts.extend(["--option", code])
    parts.extend(["--start", start_d.isoformat(), "--end", end_d.isoformat()])
    typer.echo("$ " + " ".join(parts))


async def _prompt_types_async() -> list[str]:
    """Multi-select picker over the catalog (async). Returns selected codes
    (with the `ReadingType=` prefix) or [] when the user cancels."""
    if not sys.stdin.isatty():
        return []
    answer = await questionary.checkbox(
        "Select reading types (space to toggle, enter to confirm)",
        choices=_picker_choices(),
        style=_CHECKBOX_STYLE,
    ).ask_async()
    return answer or []


def _readings(
    ctx: typer.Context,
    usage_point: str | None = typer.Argument(None, help="identifikator or gsrnMm."),
    type_: list[str] = typer.Option(None, "--type", "-t", help="Reading type name (repeatable)."),
    option: list[str] = typer.Option(None, "--option", help="Raw reading type code (repeatable)."),
    start: datetime | None = typer.Option(
        None, "--start", formats=["%Y-%m-%d"], help="Window start (YYYY-MM-DD)."
    ),
    end: datetime | None = typer.Option(
        None, "--end", formats=["%Y-%m-%d"], help="Window end (YYYY-MM-DD)."
    ),
    days: int = typer.Option(7, "--days", help="Window size in days."),
) -> None:
    """Fetch meter readings."""
    if usage_point is None:
        typer.echo(ctx.get_help())
        raise typer.Exit(0)

    end_d = end.date() if end else datetime.now(UTC).date()
    start_d = start.date() if start else end_d - timedelta(days=days)
    fmt = OutputFormat(ctx.obj["format"])

    explicit = bool(type_) or bool(option)
    interactive = (
        not explicit and fmt is OutputFormat.TABLE and sys.stdin.isatty() and sys.stdout.isatty()
    )

    if not interactive:
        options = _resolve_types(type_, option)
        if not options:
            raise typer.BadParameter(
                "at least one --type or --option is required when not on a TTY",
                param_hint="--type/--option",
            )
        asyncio.run(_run_batch(ctx, usage_point, start_d, end_d, options, fmt))
        return

    asyncio.run(_run_interactive(ctx, usage_point, start_d, end_d))


async def _run_batch(
    ctx: typer.Context,
    usage_point: str,
    start_d: date,
    end_d: date,
    options: list[str],
    fmt: OutputFormat,
) -> None:
    client = await build_client(ctx)
    async with client:
        gsrn = await resolve_gsrn_mm(client, usage_point)
        out = await client.get_meter_readings(gsrn, start_d, end_d, options=options)
    typer.echo(dump_readings(dict(out), fmt))


async def _run_interactive(
    ctx: typer.Context,
    usage_point: str,
    start_d: date,
    end_d: date,
) -> None:
    """Pick types → fetch window → paginate → next window or back to picker.

    Pager actions:
      - SPACE mid-data       → next page
      - SPACE at end-of-data → fetch the next (older) interval and continue
      - ESC                  → re-prompt for types
      - q / Ctrl-C           → quit

    Column header is printed once at the top; each window's footer is the
    `=== window: <start> .. <end> ===` banner shown after the last row of
    that window.
    """
    client = await build_client(ctx)
    duration = end_d - start_d if end_d > start_d else timedelta(days=1)
    async with client:
        gsrn = await resolve_gsrn_mm(client, usage_point)
        while True:
            options = await _prompt_types_async()
            if not options:
                return
            _echo_equivalent_command(usage_point, options, start_d, end_d)
            action = await _walk_windows(client, gsrn, options, start_d, end_d, duration)
            if action == "quit":
                return
            # action == "back" → loop and reprompt for types


async def _walk_windows(
    client: MojElektroClient,
    gsrn: str,
    options: list[str],
    start_d: date,
    end_d: date,
    duration: timedelta,
) -> str:
    """Stream paginated windows. Returns 'quit' or 'back'."""
    window_start, window_end = start_d, end_d
    columns: list[str] | None = None
    widths: list[int] = []
    while True:
        payload = dict(
            await client.get_meter_readings(gsrn, window_start, window_end, options=options)
        )
        pivot_cols, pivot_rows = pivot_readings(payload)

        if columns is None:
            # First window establishes the column ordering and widths so
            # subsequent windows stay aligned without reprinting the header.
            columns = pivot_cols if pivot_rows else ["timestamp"]
            string_rows = [[row.get(col, "") for col in columns] for row in pivot_rows]
            widths = compute_widths(columns, string_rows)
            header_lines = [
                format_row(columns, widths),
                format_row(["-" * w for w in widths], widths),
            ]
        else:
            string_rows = [[row.get(col, "") for col in columns] for row in pivot_rows]
            header_lines = []

        data_lines = (
            [format_row(row, widths) for row in string_rows] if string_rows else ["(no data)"]
        )
        banner = f"=== window: {window_start.isoformat()} .. {window_end.isoformat()} ==="

        action = paginate(header_lines, data_lines, footer_lines=[banner])
        if action == "quit":
            return "quit"
        if action == "back":
            return "back"
        # next_window: shift one duration further into the past
        window_end = window_start
        window_start = window_end - duration


from cli import handle_errors  # noqa: E402

readings_cmd = handle_errors(_readings)
