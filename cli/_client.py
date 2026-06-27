from __future__ import annotations

import os
import sys

import questionary
import typer

from mojelektro import MojElektroClient, Server

_MISSING_TOKEN_MSG = "API token not provided. Use --token or set MOJELEKTRO_APIKEY."


async def build_client(ctx: typer.Context) -> MojElektroClient:
    """Resolve the API token (--token / env / interactive prompt) and build
    a client. Async because the prompt runs inside the caller's event loop."""
    token = ctx.obj["token"] or os.environ.get("MOJELEKTRO_APIKEY")
    if not token:
        if not sys.stdin.isatty():
            raise typer.BadParameter(_MISSING_TOKEN_MSG)
        answer = await questionary.password("Moj Elektro API token:").ask_async()
        token = answer if isinstance(answer, str) and answer else None
    if not token:
        raise typer.BadParameter(_MISSING_TOKEN_MSG)
    server = Server.PRODUCTION if ctx.obj["server"] == "prod" else Server.TEST
    return MojElektroClient(token, server=server)
