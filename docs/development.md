# Development

Contributor guide. The **shipped product** is `custom_components/mojelektro_stats/` (HACS). Everything below is developer tooling used to build, test, and debug that integration.

End-user install instructions: [`README.md`](../README.md). Agent rules: [`AGENTS.md`](../AGENTS.md).

## Setup

Tooling is managed by [mise](https://mise.jdx.dev): `mise.toml` pins Python and uv, and tasks live as scripts in `tools/tasks/`.

```bash
mise install            # Python + uv at the pinned versions
mise run setup          # uv sync — dev deps only (lint, test, CLI), not installed into HA
mise run check          # ruff + mypy + pyright + pytest
```

`pyproject.toml` configures this tooling. It is not a publishable package (`[tool.uv] package = false`).

## Tasks

`mise tasks` lists everything. Arguments after `--` are passed through. `mise.toml` defines a shell alias `mr` for `mise run` (active when your shell runs `mise activate`), so `mr check`, `mr dev:up`, and so on work.

```bash
mise run check                 # full check (lint + types + tests)
mise run test                  # pytest (e.g. mise run test -- -k stanje)
mise run test:lib              # vendored lib + CLI tests
mise run test:ha               # HA integration tests
mise run lint                  # ruff check + format check
mise run format                # apply ruff fixes + format
mise run type                  # mypy + pyright
mise run cli -- types          # repo-local CLI
mise run dev:up                # docker compose (HA + InfluxDB)
mise run dev:down              # stop dev stack
mise run regen-reading-types   # refresh lib/reading_types.py from cassette
mise run clean                 # remove caches
mise run sandbox -- plan       # sbx dev sandbox: plan | create | run | rm (tools/sandbox/run.sh)
```

To add a task, drop an executable script in `tools/tasks/` with a `#MISE description="…"` header. Subdirectories become namespaces (`tools/tasks/dev/up` → `dev:up`, `test/_default` → `test`).

Without mise: `uv run pytest`, `uv run ruff check .`, `uv run mypy`.

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
| `tools/cli/` | Typer CLI — `mise run cli --` ([`ai-rules/cli.md`](ai-rules/cli.md)) |
| `tests/lib/` | Vendored lib + CLI tests |
| `tests/ha/` | Integration tests (pytest-homeassistant-custom-component) |
| `tools/scripts/` | `regen-reading-types.py`, `record-reading-types.py` |
| `tools/tasks/` | mise task scripts (`mise tasks`) |
| `mise.toml` | Pinned Python + uv, task config |
| `docker/` | Local HA + InfluxDB for manual integration testing |
| `docs/` | Specs, ai-rules, this file |

## Local CLI

Debug the Moj Elektro API without running Home Assistant:

```bash
export MOJELEKTRO_APIKEY="<token>"
mise run cli -- info <identifikator>
mise run cli -- readings <identifikator> -t A_PLUS_15MIN --days 7
```

## Docker dev stack

```bash
mise run dev:up      # HA at :8123, InfluxDB at :8086
mise run dev:logs    # tail HA logs
mise run dev:restart # pick up custom_components edits
```

The integration is bind-mounted from `custom_components/mojelektro_stats/` (lib included).

## Test cassettes

CI replays committed VCR cassettes — no live API calls. Re-recording procedure: [`tests/lib/cassettes/README.md`](../tests/lib/cassettes/README.md).

## Reading-type catalog

`lib/mojelektro_api/reading_types.py` is generated. After re-recording the reading-types cassette: `mise run regen-reading-types`.

## Releases (HACS)

Version in `lib/mojelektro_api/__about__.py` and `manifest.json` — bump both by hand, in lockstep. See [`ai-rules/git-and-release.md`](ai-rules/git-and-release.md).
