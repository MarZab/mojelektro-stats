from __future__ import annotations

import asyncio

import typer

from cli._client import build_client
from cli._format import OutputFormat, dump
from cli._resolve import resolve_gsrn_mt


def info_cmd(ctx: typer.Context, identifikator: str) -> None:
    """Show merilno mesto (technical details)."""

    async def _run() -> dict[str, object]:
        client = await build_client(ctx)
        async with client:
            return dict(await client.get_merilno_mesto(identifikator))

    typer.echo(dump(asyncio.run(_run()), OutputFormat(ctx.obj["format"])))


def contract_cmd(ctx: typer.Context, identifier: str) -> None:
    """Show merilna tocka (contractual details)."""

    async def _run() -> dict[str, object]:
        client = await build_client(ctx)
        async with client:
            gsrn = await resolve_gsrn_mt(client, identifier)
            return await client.get_merilna_tocka(gsrn)

    typer.echo(dump(asyncio.run(_run()), OutputFormat(ctx.obj["format"])))
