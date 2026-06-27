# CLI rules

**Developer tooling only.** The CLI under `cli/` is for local API debugging and scripting. It is not installed via HACS and does not ship to Home Assistant users.

## Stack

Typer for command structure + Rich (via Typer) for help output. `questionary` provides the interactive picker + token prompt. CLI deps are dev-only (`uv sync`); they are not part of the HACS integration.

## Entry point

Run from the repo root after `uv sync`:

```bash
uv run python -m cli <subcommand> ...
make cli ARGS="info 4-XXXXXXX"
```

The Typer app lives in `cli/__init__.py` as `app`. `cli/_path.py` adds the vendored lib to `sys.path` so the CLI works outside pytest.

## Conventions

- Token from `--token` or `MOJELEKTRO_APIKEY` env var. **If neither is set and stdin is a TTY, the CLI prompts.** In non-TTY contexts (CI, pipes) a missing token raises `BadParameter`.
- Server selection from `--server prod|test` or `MOJELEKTRO_SERVER` env var. Default `prod`. Hidden from `--help` unless `-v` is passed.
- Output format `--format table|json|yaml` (root option, before the subcommand). Default `table`.
- `-v` / `--verbose` surfaces niche options + helper commands in `--help`.
- Every command is an `asyncio.run(_impl(...))` thin shell over the same async client. No sync API duplication.
- Non-zero exit on any `MojElektroError`. Print the exception class name and message to stderr.

## Command shape

```
python -m cli info IDENTIFIKATOR                     # merilno mesto
python -m cli contract IDENTIFIER                    # merilna tocka (resolves short id)
python -m cli readings [USAGE_POINT] [...]           # interactive when args missing on TTY
python -m cli types [--filter SUBSTRING]             # hardcoded reading-type catalog
```

The `info` / `contract` / `readings` commands accept either the short `identifikator` (e.g. `4-XXXXXXX`) or the 18-digit GSRN — short form is resolved via `/merilno-mesto`.

The top-level `--help` table shows each command's positional arguments inline (e.g. `info IDENTIFIKATOR`) — the listing is driven by a `TyperGroup` subclass in `cli/__init__.py` that mutates `cmd.name` on listing and restores the bare key on lookup.

Don't add command aliases. Don't make commands depend on a config file — env vars and flags are the configuration surface.

## Output

- `table` — aligned text columns, no box drawing, no truncation. Dict payloads (e.g. `info` / `contract` responses) are flattened to dot-path `key value` rows so nested objects don't render as `{'k': 'v'}` blobs.
- `json` — `json.dumps(payload, indent=2, sort_keys=True, default=str)`.
- `yaml` — `yaml.safe_dump(payload, sort_keys=True, allow_unicode=True)`.
- `readings` table output is a **pivot**: rows are timestamps, columns are reading-type oznake. `json`/`yaml` emit the same pivoted rows so machine consumers also get the condensed shape.

Time values are passed through as the API delivered them (ISO 8601 with timezone offset).

## Interactive readings

`python -m cli readings <id>` with no `--type` / `--option` and a TTY:

1. Multi-select picker over `KNOWN_READING_TYPES`.
2. After confirm, prints the equivalent non-interactive command, then fetches + pages.
3. Pager keys: `SPACE` = next page (or next older window at end-of-data), `ESC` = back to picker, `q` / `Ctrl-C` = quit.

The pager is POSIX-only (`termios`) — the CLI as a whole is intended for Linux/macOS dev environments and the HA Docker runtime.

## Errors in the CLI

- Print the exception class name and message to stderr, plus `request:`, `status:`, `response body:` lines when populated.
- Exit codes (part of the CLI's scripting contract):
  - `0` success
  - `1` other `MojElektroError`
  - `2` `InvalidRequestError`
  - `3` `AuthError`
  - `4` `NotFoundError`
  - `5` `TransportError`
