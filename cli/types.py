from __future__ import annotations

import typer

from cli._format import OutputFormat, dump
from mojelektro.reading_types import KNOWN_READING_TYPES, ReadingTypeInfo


def _row(rt: ReadingTypeInfo) -> dict[str, str]:
    return {
        "name": rt.name,
        "code": rt.code.value.removeprefix("ReadingType="),
        "oznaka": rt.oznaka,
        "perioda": rt.perioda,
        "tip": rt.tip,
        "vrsta": rt.vrsta,
        "opis": rt.opis,
    }


def types_cmd(
    ctx: typer.Context,
    filter: str | None = typer.Option(None, "--filter", help="Substring filter."),
) -> None:
    """List reading types."""
    rows = [_row(rt) for rt in KNOWN_READING_TYPES]
    if filter:
        needle = filter.lower()
        rows = [row for row in rows if any(needle in v.lower() for v in row.values())]
    typer.echo(dump(rows, OutputFormat(ctx.obj["format"])))
