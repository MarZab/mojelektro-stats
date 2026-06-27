# Documentation

This repository ships a **HACS Home Assistant integration** (`custom_components/mojelektro/`). The docs below are for contributors and AI agents; end users install via HACS and configure through Home Assistant's UI.

## Start here

| Audience | Entry point |
|----------|-------------|
| End users | [`README.md`](../README.md) — install via HACS, what the integration does |
| Contributors | [`development.md`](development.md) — dev setup, make targets, repo layout |
| AI agents | [`AGENTS.md`](../AGENTS.md) — project framing, hard rules, rule index |

## Integration (primary)

| Doc | Read when editing |
|------|-------------------|
| [`ai-rules/home-assistant.md`](ai-rules/home-assistant.md) | ConfigFlow, coordinator, sinks, manifest |
| [`ai-rules/library.md`](ai-rules/library.md) | Vendored `lib/mojelektro/` API client |
| [`ai-rules/errors-and-logging.md`](ai-rules/errors-and-logging.md) | Exceptions, log redaction |

## Developer tooling (secondary)

| Doc / path | Purpose |
|------------|---------|
| [`development.md`](development.md) | `uv sync`, `make test`, Docker dev stack |
| [`ai-rules/cli.md`](ai-rules/cli.md) | Repo-local CLI (`cli/`) |
| [`ai-rules/testing.md`](ai-rules/testing.md) | `tests/`, VCR cassettes |
| [`tests/lib/cassettes/README.md`](../tests/lib/cassettes/README.md) | Recording API cassettes |
| [`ai-rules/python.md`](ai-rules/python.md) | Typing, ruff, async conventions |
| [`ai-rules/git-and-release.md`](ai-rules/git-and-release.md) | HACS release flow |

Task-specific rule picker: [`ai-rules/README.md`](ai-rules/README.md).

## Design and planning

| Path | Purpose |
|------|---------|
| [`superpowers/specs/`](superpowers/specs/) | Design specs — source of truth for non-trivial changes |
| [`superpowers/plans/`](superpowers/plans/) | Implementation plans |

## Version

Single source: [`custom_components/mojelektro/lib/mojelektro/__about__.py`](../custom_components/mojelektro/lib/mojelektro/__about__.py). Keep `manifest.json` `"version"` in sync.
