# Development

Contributor guide. The **shipped product** is `custom_components/mojelektro_stats/` (HACS). Everything below is developer tooling used to build, test, and debug that integration.

End-user install instructions: [`README.md`](../README.md). Agent rules: [`AGENTS.md`](../AGENTS.md).

## Setup

```bash
uv sync                 # dev deps only (lint, test, CLI) — not installed into HA
make test               # ruff + mypy + pyright + pytest
```

`pyproject.toml` configures this tooling. It is not a publishable package (`[tool.uv] package = false`).

## Make targets

```bash
make test                  # full check (lint + types + tests)
make test-lib              # vendored lib + CLI tests
make test-ha               # HA integration tests
make lint                  # ruff check + format check
make format                # apply ruff format
make type                  # mypy + pyright
make cli ARGS="types"      # repo-local CLI
make dev-up                # docker compose (HA + InfluxDB)
make dev-down              # stop dev stack
make regen-reading-types   # refresh lib/reading_types.py from cassette
make clean                 # remove caches
```

Fallbacks: `uv run pytest`, `uv run ruff check`, `uv run mypy`.

## Repository layout

### Shipped (HACS)

```
custom_components/mojelektro_stats/
├── manifest.json          # HACS metadata; requirements: [] (self-contained)
├── _bootstrap.py          # adds lib/ to sys.path at runtime
├── config_flow.py         # ConfigFlow + OptionsFlow
├── coordinator.py         # polling + backfill
├── dispatcher.py          # per-reading-type routing to sinks
├── sinks/                 # Statistics + InfluxDB writers
└── lib/mojelektro_api/        # vendored typed API client (no HA imports)
```

See [`ai-rules/home-assistant.md`](ai-rules/home-assistant.md) for integration patterns.

### Developer tooling (not shipped)

| Path | Purpose |
|------|---------|
| `cli/` | Typer CLI — `uv run python -m cli` ([`ai-rules/cli.md`](ai-rules/cli.md)) |
| `tests/lib/` | Vendored lib + CLI tests |
| `tests/ha/` | Integration tests (pytest-homeassistant-custom-component) |
| `scripts/` | `regen-reading-types.py`, `record-reading-types.py` |
| `docker/` | Local HA + InfluxDB for manual integration testing |
| `docs/` | Specs, ai-rules, this file |

## Local CLI

Debug the Moj Elektro API without running Home Assistant:

```bash
export MOJELEKTRO_APIKEY="<token>"
uv run python -m cli info <identifikator>
uv run python -m cli readings <identifikator> -t A_PLUS_15MIN --days 7
```

## Docker dev stack

```bash
make dev-up      # HA at :8123, InfluxDB at :8086
make dev-logs    # tail HA logs
make dev-restart # pick up custom_components edits
```

The integration is bind-mounted from `custom_components/mojelektro_stats/` (lib included).

## Test cassettes

CI replays committed VCR cassettes — no live API calls. Re-recording procedure: [`tests/lib/cassettes/README.md`](../tests/lib/cassettes/README.md).

## Reading-type catalog

`lib/mojelektro_api/reading_types.py` is generated. After re-recording the reading-types cassette: `make regen-reading-types`.

## Releases (HACS)

Version in `lib/mojelektro_api/__about__.py` and `manifest.json` — bump both by hand, in lockstep. See [`ai-rules/git-and-release.md`](ai-rules/git-and-release.md).
