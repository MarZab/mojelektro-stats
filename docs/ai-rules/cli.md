# CLI rules

**Developer tooling only.** The CLI under `tools/cli/` is for local API debugging and scripting. It is not installed via HACS and does not ship to Home Assistant users.

## Stack

Typer for command structure + Rich (via Typer) for help output. `questionary` provides the interactive picker + token prompt. CLI deps are dev-only (`uv sync`); they are not part of the HACS integration.

## Entry point

Run from the repo root after `uv sync`:

```bash
mise run cli -- <subcommand> ...              # or: PYTHONPATH=tools uv run python -m cli
mise run cli -- info 4-XXXXXXX
```

The Typer app lives in `tools/cli/__init__.py` as `app`. `tools/cli/_path.py` adds the vendored lib to `sys.path` so the CLI works outside pytest.

## Conventions

- `python -m cli` loads the repo-root `.env` first (`cli/_env.py`, never overriding variables already set). Tests invoke `app` directly, so they never see it.
- Usage point: the positional argument of `info`, `contract`, `readings` and `daily` falls back to `MOJELEKTRO_USAGE_POINT` (also for `hourly`).
- Token from `--token` or `MOJELEKTRO_APIKEY` env var. **If neither is set and stdin is a TTY, the CLI prompts.** In non-TTY contexts (CI, pipes) a missing token raises `BadParameter`.
- Server selection from `--server prod|test` or `MOJELEKTRO_SERVER` env var. Default `prod`. Hidden from `--help` unless `-v` is passed.
- Output format `--format table|json|yaml` (root option, before the subcommand). Default `table`.
- `-v` / `--verbose` surfaces niche options + helper commands in `--help`.
- Every command is an `asyncio.run(_impl(...))` thin shell over the same async client. No sync API duplication.
- Non-zero exit on any `MojElektroError`. Print the exception class name and message to stderr.

## Command shape

```
mise run cli -- info IDENTIFIKATOR                     # merilno mesto
mise run cli -- contract IDENTIFIER                    # merilna tocka (resolves short id)
mise run cli -- readings [USAGE_POINT] [...]           # interactive when args missing on TTY
mise run cli -- types [--filter SUBSTRING]             # hardcoded reading-type catalog
mise run cli -- daily [USAGE_POINT] [-t TYPE] [--check] # per-day usage from daily register readings
mise run cli -- hourly [USAGE_POINT] [-t TYPE] [--start D] # per-hour usage, checked against the daily register
```

The `info` / `contract` / `readings` commands accept either the short `identifikator` (e.g. `4-XXXXXXX`) or the 18-digit GSRN — short form is resolved via `/merilno-mesto`.

The top-level `--help` table shows each command's positional arguments inline (e.g. `info IDENTIFIKATOR`) — the listing is driven by a `TyperGroup` subclass in `tools/cli/__init__.py` that mutates `cmd.name` on listing and restores the bare key on lookup.

Don't add command aliases. Don't make commands depend on a config file — env vars and flags are the configuration surface.

## Output

- `table` — aligned text columns, no box drawing, no truncation. Dict payloads (e.g. `info` / `contract` responses) are flattened to dot-path `key value` rows so nested objects don't render as `{'k': 'v'}` blobs.
- `json` — `json.dumps(payload, indent=2, sort_keys=True, default=str)`.
- `yaml` — `yaml.safe_dump(payload, sort_keys=True, allow_unicode=True)`.
- `readings` table output is a **pivot**: rows are timestamps, columns are reading-type oznake. `json`/`yaml` emit the same pivoted rows so machine consumers also get the condensed shape.

Time values are passed through as the API delivered them (ISO 8601 with timezone offset).

## Interactive readings

`mise run cli -- readings <id>` with no `--type` / `--option` and a TTY:

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

## `daily`

Per-day usage = difference between consecutive daily register (STANJE) readings. Logic lives in `cli/_daily.py` (pure, unit-tested); the command in `cli/daily.py`.

- **Day attribution:** a reading belongs to the local (Europe/Ljubljana) date of `timestamp - 1 s`. Daily registers are stamped at the midnight after the day they close, 15-minute intervals at the end of their slot. This matches the mojelektro.si portal and the integration's StatisticsSink, and handles 23/25-hour DST days.
- **Days:** `--start`/`--end` are inclusive. The default is the last `--days` (7) complete days, ending yesterday.
- **Types:** `-t` (repeatable) > `MOJELEKTRO_DAILY_TYPES` (comma- or space-separated names) > `A_PLUS_T0/T1/T2_DAILY` + `A_MINUS_T0_DAILY`. Non-STANJE types are rejected.
- **Fetching:** one extra day either side, split into ≤35-day requests (the API cap); duplicate timestamps from overlapping chunks are dropped.
- **Missing readings** give a blank cell (JSON `null`), never 0. Negative usage is marked `!` in table output.
- **`--check`** (opt-in) also fetches `A_PLUS_15MIN` and adds `15min` (the day's summed intervals) and `diff` (`A+_T0 - 15min`) columns.

## `hourly`

Per-hour usage from 15-minute energy (KOLICINA) readings, with a per-day check against the daily register. Command in `cli/hourly.py`; shares `cli/_daily.py`.

- **Hours:** an interval belongs to the hour of `timestamp - 1 s`. Hours are keyed by UTC start internally, because aware datetimes sharing a ZoneInfo ignore `fold` when compared, which would merge the repeated 02:00 on the autumn DST day. They're shown in local time with the offset (`02:00+0200`, `02:00+0100`). Days have 23, 24 or 25 rows.
- **Days:** same as `daily`, but `--days` defaults to 1 (yesterday).
- **Types:** `-t` > `MOJELEKTRO_HOURLY_TYPES` > `A_PLUS_15MIN` + `A_MINUS_15MIN`. Only energy types are accepted (`A±`, `R±`); power (`P±`, `Q±`) is an average and can't be summed.
- **Check:** each day gets `hours` (sum of the hour rows), `register` (the matching `*_T0_DAILY` difference) and `diff` (`register - hours`) rows. Differences above 0.01 are listed at the bottom.
