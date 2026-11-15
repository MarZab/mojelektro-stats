from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import date, datetime, timedelta
from decimal import Decimal

import typer
import yaml

from cli._client import build_client
from cli._daily import (
    LOCAL_TZ,
    STATE_VRSTA,
    Column,
    build_rows,
    chunk_window,
    column_totals,
    days_between,
    fetch_range,
    register_by_day,
    sum_by_day,
    usage_by_day,
)
from cli._env import USAGE_POINT_ENVVAR
from cli._format import OutputFormat, render_aligned_lines
from cli._resolve import resolve_gsrn_mm
from mojelektro_api.models import MeterReadings
from mojelektro_api.reading_types import BY_NAME, ReadingTypeCode, ReadingTypeInfo

DAILY_TYPES_ENVVAR = "MOJELEKTRO_DAILY_TYPES"
DEFAULT_DAILY_TYPES: tuple[str, ...] = (
    "A_PLUS_T0_DAILY",
    "A_PLUS_T1_DAILY",
    "A_PLUS_T2_DAILY",
    "A_MINUS_T0_DAILY",
)
_CHECK_INTERVAL = BY_NAME["A_PLUS_15MIN"]
_CHECK_REGISTER = BY_NAME["A_PLUS_T0_DAILY"]
_CHECK_SUM_LABEL = "15min"
_CHECK_DIFF_LABEL = "diff"
_NEGATIVE_MARK = " !"


def resolve_daily_types(names: list[str] | None, env_value: str | None) -> list[ReadingTypeInfo]:
    """Pick reading types: explicit -t > MOJELEKTRO_DAILY_TYPES > defaults.

    The env var takes names separated by commas and/or whitespace. Only
    daily register (STANJE) types make sense to diff.
    """
    if names:
        chosen = list(names)
    elif env_value and env_value.strip():
        chosen = [n for n in re.split(r"[,\s]+", env_value.strip()) if n]
    else:
        chosen = list(DEFAULT_DAILY_TYPES)

    infos: list[ReadingTypeInfo] = []
    for name in chosen:
        info = BY_NAME.get(name)
        if info is None or info.vrsta != STATE_VRSTA:
            valid = ", ".join(rt.name for rt in BY_NAME.values() if rt.vrsta == STATE_VRSTA)
            raise typer.BadParameter(
                f"{name!r} is not a daily register type. Valid: {valid}",
                param_hint=f"--type / {DAILY_TYPES_ENVVAR}",
            )
        if info not in infos:
            infos.append(info)
    return infos


def resolve_days(start: date | None, end: date | None, days: int, today: date) -> tuple[date, date]:
    """Inclusive day range. Default ends yesterday (today isn't closed yet)."""
    if days < 1:
        raise typer.BadParameter("must be at least 1", param_hint="--days")
    if start is not None and end is not None:
        first, last = start, end
    elif start is not None:
        first, last = start, start + timedelta(days=days - 1)
    else:
        last = end if end is not None else today - timedelta(days=1)
        first = last - timedelta(days=days - 1)
    if first > last:
        raise typer.BadParameter("--start must not be after --end", param_hint="--start")
    return first, last


def compute_daily(
    payloads: list[MeterReadings],
    types: list[ReadingTypeInfo],
    days: list[date],
    *,
    check: bool,
) -> tuple[list[str], list[dict[str, Decimal | None]]]:
    """Return (column labels, one row per day)."""
    columns = [
        Column(info.oznaka, usage_by_day(register_by_day(payloads, info), days)) for info in types
    ]
    if check:
        sums = sum_by_day(payloads, _CHECK_INTERVAL)
        columns.append(Column(_CHECK_SUM_LABEL, {day: sums.get(day) for day in days}))
        register_col = next((c for c in columns if c.label == _CHECK_REGISTER.oznaka), None)
        if register_col is not None:
            diffs: dict[date, Decimal | None] = {}
            for day in days:
                usage, total = register_col.values.get(day), sums.get(day)
                diffs[day] = None if usage is None or total is None else usage - total
            columns.append(Column(_CHECK_DIFF_LABEL, diffs))
    return [c.label for c in columns], build_rows(days, columns)


def _cell(value: Decimal | None, *, mark_negative: bool) -> str:
    if value is None:
        return ""
    text = str(value)
    return text + _NEGATIVE_MARK if mark_negative and value < 0 else text


def render_daily(
    labels: list[str],
    days: list[date],
    rows: list[dict[str, Decimal | None]],
    fmt: OutputFormat,
) -> str:
    if fmt in (OutputFormat.JSON, OutputFormat.YAML):
        records = [
            {
                "date": day.isoformat(),
                **{k: (None if v is None else float(v)) for k, v in row.items()},
            }
            for day, row in zip(days, rows, strict=True)
        ]
        if fmt is OutputFormat.JSON:
            return json.dumps(records, indent=2) + "\n"
        return yaml.safe_dump(records, sort_keys=False, allow_unicode=True)

    usage_labels = [label for label in labels if label != _CHECK_DIFF_LABEL]
    string_rows = [
        [
            day.isoformat(),
            *(_cell(row.get(label), mark_negative=label != _CHECK_DIFF_LABEL) for label in labels),
        ]
        for day, row in zip(days, rows, strict=True)
    ]
    totals = column_totals(rows, usage_labels)
    string_rows.append(
        ["total", *(_cell(totals.get(label), mark_negative=False) for label in labels)]
    )
    header, data = render_aligned_lines(["date", *labels], string_rows)
    lines = [*header, *data[:-1], header[1], data[-1]]
    if any(
        (v := row.get(label)) is not None and v < 0
        for row in rows
        for label in labels
        if label != _CHECK_DIFF_LABEL
    ):
        lines.append(f"{_NEGATIVE_MARK.strip()} register went backwards (meter change?)")
    return "\n".join(lines) + "\n"


async def fetch_payloads(
    ctx: typer.Context, usage_point: str, options: list[str], first: date, last: date
) -> list[MeterReadings]:
    fetch_start, fetch_end = fetch_range(first, last)
    client = await build_client(ctx)
    async with client:
        gsrn = await resolve_gsrn_mm(client, usage_point)
        return [
            await client.get_meter_readings(gsrn, chunk_start, chunk_end, options=options)
            for chunk_start, chunk_end in chunk_window(fetch_start, fetch_end)
        ]


def _daily(
    ctx: typer.Context,
    usage_point: str = typer.Argument(
        ..., envvar=USAGE_POINT_ENVVAR, help="identifikator or gsrnMm."
    ),
    type_: list[str] = typer.Option(
        None,
        "--type",
        "-t",
        help=(
            "Daily register type (repeatable). Default: "
            f"${DAILY_TYPES_ENVVAR} (comma-separated) or {', '.join(DEFAULT_DAILY_TYPES)}."
        ),
    ),
    start: datetime | None = typer.Option(
        None, "--start", formats=["%Y-%m-%d"], help="First day (YYYY-MM-DD, inclusive)."
    ),
    end: datetime | None = typer.Option(
        None, "--end", formats=["%Y-%m-%d"], help="Last day (YYYY-MM-DD, inclusive)."
    ),
    days: int = typer.Option(7, "--days", help="Number of days, ending yesterday by default."),
    check: bool = typer.Option(
        False, "--check", help="Cross-check A+ against the summed 15-minute readings."
    ),
) -> None:
    """Daily usage: the difference between consecutive daily register readings."""
    types = resolve_daily_types(type_, os.environ.get(DAILY_TYPES_ENVVAR))
    today = datetime.now(LOCAL_TZ).date()
    first, last = resolve_days(
        start.date() if start else None, end.date() if end else None, days, today
    )
    options: list[str] = [info.code.value for info in types]
    if check:
        options.append(ReadingTypeCode.A_PLUS_15MIN.value)

    payloads = asyncio.run(fetch_payloads(ctx, usage_point, options, first, last))
    day_list = days_between(first, last)
    labels, rows = compute_daily(payloads, types, day_list, check=check)
    typer.echo(render_daily(labels, day_list, rows, OutputFormat(ctx.obj["format"])), nl=False)


from cli import handle_errors  # noqa: E402

daily_cmd = handle_errors(_daily)
