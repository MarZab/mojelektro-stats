# Agent instructions

Guidance for AI coding agents working in this repository.

## What this project is

**HACS Home Assistant integration first.** The shipped product is `custom_components/mojelektro/` — a self-contained custom component with a vendored API client under `lib/mojelektro/`. Users install via HACS; no PyPI package, no extra `manifest.json` requirements.

Everything else in the repo is **developer tooling**:

| Path | Role |
|------|------|
| `custom_components/mojelektro/` | Integration + vendored lib — **primary** |
| `cli/` | Local CLI for API debugging |
| `tests/` | pytest (lib, CLI, integration) |
| `scripts/` | Catalog regeneration, version bumps |
| `docker/` | Local HA + InfluxDB dev stack |
| `docs/` | Specs, ai-rules, contributor docs |
| `pyproject.toml` | Dev-tool config only (`uv sync`, ruff, mypy, pytest) — not published |

Architecture: **thin library, smart integration**. The vendored lib is pure typed API access. ConfigFlow, coordinator, statistics import, and InfluxDB writes live in the integration. The lib never imports HA.

## Documentation map

| Doc | When to read |
|-----|--------------|
| [`docs/README.md`](docs/README.md) | Documentation index |
| [`docs/ai-rules/home-assistant.md`](docs/ai-rules/home-assistant.md) | Integration changes (start here for most tasks) |
| [`docs/ai-rules/library.md`](docs/ai-rules/library.md) | Vendored `lib/mojelektro/` API client |
| [`docs/development.md`](docs/development.md) | Dev setup, make targets, repo layout |
| [`docs/ai-rules/`](docs/ai-rules/) | Task-specific coding rules |
| [`docs/superpowers/specs/2026-06-07-mojelektro-design.md`](docs/superpowers/specs/2026-06-07-mojelektro-design.md) | Design spec — read before non-trivial changes |

If a change deviates from the design spec, update the spec in the same commit.

## Rules to follow

Read the one relevant file in [`docs/ai-rules/`](docs/ai-rules/) before editing:

| Rule file | Scope |
|-----------|-------|
| [`home-assistant.md`](docs/ai-rules/home-assistant.md) | `custom_components/mojelektro/` (integration) |
| [`library.md`](docs/ai-rules/library.md) | `custom_components/mojelektro/lib/mojelektro/` |
| [`python.md`](docs/ai-rules/python.md) | Typing, style, async, dependencies |
| [`testing.md`](docs/ai-rules/testing.md) | `tests/` |
| [`errors-and-logging.md`](docs/ai-rules/errors-and-logging.md) | Exceptions, logging |
| [`git-and-release.md`](docs/ai-rules/git-and-release.md) | Version bumps, HACS releases |
| [`cli.md`](docs/ai-rules/cli.md) | `cli/` (dev only) |

## Quick commands (development)

```bash
make test                  # ruff + mypy + pyright + pytest
make lint                  # ruff check + format
make dev-up                # docker compose (HA + InfluxDB)
make regen-reading-types   # refresh vendored reading-type catalog
make cli ARGS="types"      # run repo-local CLI
```

## Hard rules

1. **The vendored lib never imports `homeassistant`** or any HA-specific module.
2. **Never log the API token.** Tests verify redaction in diagnostics dumps.
3. **No retries inside the lib.** The HA coordinator and dev CLI handle retry policy.
4. **All new code is typed.** `mypy --strict` and `pyright` must pass.
5. **All new code has tests.** Lib → `tests/lib/`; integration → `tests/ha/`.
6. **No live API calls in CI.** VCR cassettes or mocks only.
7. **Version truth:** `custom_components/mojelektro/lib/mojelektro/__about__.py` + matching `manifest.json` `"version"`. Bump via `scripts/bump-version.sh`.
8. **Reading-type catalog** is hardcoded in `lib/mojelektro/reading_types.py`. Regenerate with `make regen-reading-types`.

## What not to do without checking with the human

- Add runtime dependencies to the integration (`manifest.json` `requirements` or vendored `lib/` deps).
- Change the lib's public surface (`lib/mojelektro/__init__.py` exports).
- Re-introduce sync entry points to the lib.
- Add HA concepts to the lib (sinks, entities, statistics).
- Change the per-measurement routing schema without `async_migrate_entry`.
- Treat this repo as a PyPI/library product — it ships through HACS only.
