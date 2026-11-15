from __future__ import annotations

import sys
from collections.abc import Callable
from functools import wraps
from typing import Any

import typer
from typer.core import TyperGroup

import cli._path  # noqa: F401
from cli._format import OutputFormat
from mojelektro_api.errors import (
    AuthError,
    InvalidRequestError,
    MojElektroError,
    NotFoundError,
    TransportError,
)

# Detect -v/--verbose ahead of Typer dispatch so we can conditionally
# *show* niche options/commands in --help output. This only affects
# the help surface; behavior is identical either way and any of these
# can still be invoked without -v.
_VERBOSE = any(arg in {"-v", "--verbose"} for arg in sys.argv[1:])


def _display_name(key: str, cmd: Any) -> str:
    """`info` → `info IDENTIFIKATOR`; optional args wrapped in [BRACKETS]."""
    args: list[str] = []
    for p in cmd.params:
        if getattr(p, "param_type_name", "") != "argument":
            continue
        name = (p.name or "").upper()
        args.append(name if p.required else f"[{name}]")
    return f"{key} {' '.join(args)}" if args else key


class _ArgsInCommandsTable(TyperGroup):
    """Show each subcommand's positional arguments next to its name in
    the top-level --help table. Rich's panel renderer reads ``cmd.name``
    for the command-column text, so we rewrite it on listing and restore
    the registered key on lookup so the resolved name (used for
    ``ctx.command_path``) stays the bare command."""

    def list_commands(self, ctx: Any) -> list[str]:
        for key, cmd in self.commands.items():
            cmd.name = _display_name(key, cmd)
        return super().list_commands(ctx)

    def resolve_command(self, ctx: Any, args: list[str]) -> tuple[Any, Any, list[str]]:
        cmd_name, cmd, rest = super().resolve_command(ctx, args)
        if cmd is not None:
            for key, registered in self.commands.items():
                if registered is cmd:
                    return key, cmd, rest
        return cmd_name, cmd, rest


app = typer.Typer(
    name="mojelektro",
    help="Typed CLI for the Moj Elektro API.",
    no_args_is_help=True,
    add_completion=False,
    cls=_ArgsInCommandsTable,
)


_EXIT_CODES: dict[type[MojElektroError], int] = {
    InvalidRequestError: 2,
    AuthError: 3,
    NotFoundError: 4,
    TransportError: 5,
}


def handle_errors(func: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except MojElektroError as exc:
            code = next(
                (v for k, v in _EXIT_CODES.items() if isinstance(exc, k)),
                1,
            )
            print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
            if exc.request_url:
                print(f"  request:  {exc.request_url}", file=sys.stderr)
            if exc.status_code is not None:
                print(f"  status:   {exc.status_code}", file=sys.stderr)
            if exc.response_body:
                print("  response body:", file=sys.stderr)
                for line in exc.response_body.splitlines() or [exc.response_body]:
                    print(f"    {line}", file=sys.stderr)
            raise typer.Exit(code) from exc

    return wrapper


@app.callback()
def _root(
    ctx: typer.Context,
    token: str | None = typer.Option(None, "--token", envvar="MOJELEKTRO_APIKEY"),
    server: str = typer.Option(
        "prod",
        "--server",
        envvar="MOJELEKTRO_SERVER",
        hidden=not _VERBOSE,
    ),
    fmt: OutputFormat = typer.Option(
        OutputFormat.TABLE,
        "--format",
        "-f",
        case_sensitive=False,
        help="Output format.",
    ),
    verbose: bool = typer.Option(False, "-v", "--verbose"),
) -> None:
    """Moj Elektro CLI."""
    ctx.obj = {"token": token, "server": server, "format": fmt, "verbose": verbose}


from cli.meter import contract_cmd, info_cmd  # noqa: E402
from cli.readings import readings_cmd  # noqa: E402
from cli.types import types_cmd  # noqa: E402

# `types` dumps the hardcoded reading-type catalog — useful for
# inspection but not part of the main readings workflow, so it stays
# hidden from the default --help and surfaces with -v.
app.command("types")(handle_errors(types_cmd))
app.command("info")(handle_errors(info_cmd))
app.command("contract")(handle_errors(contract_cmd))
app.command("readings")(readings_cmd)
