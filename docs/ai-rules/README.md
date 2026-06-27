# AI rules

Coding standards for the **Moj Elektro HACS integration**. Project overview and hard rules: [`AGENTS.md`](../../AGENTS.md).

Read **one** rule file matching your task. Default to integration rules unless you are explicitly working on dev tooling.

## Integration (most tasks)

| File | Paths |
|------|-------|
| [`home-assistant.md`](home-assistant.md) | `custom_components/mojelektro/` — ConfigFlow, coordinator, sinks, manifest |
| [`library.md`](library.md) | `custom_components/mojelektro/lib/mojelektro/` — vendored API client |
| [`errors-and-logging.md`](errors-and-logging.md) | Exception hierarchy, log redaction |
| [`python.md`](python.md) | Typing, ruff, async (all Python) |
| [`testing.md`](testing.md) | `tests/` — pytest, VCR cassettes |
| [`git-and-release.md`](git-and-release.md) | HACS versioning and releases |

## Developer tooling (only when touching these paths)

| File | Paths |
|------|-------|
| [`cli.md`](cli.md) | `cli/` — local debug CLI, not shipped to HA |

## Common combinations

- **Integration feature** → `home-assistant.md` + `python.md` + `testing.md`
- **API client change** → `library.md` + `python.md` + `testing.md`
- **CLI command** → `cli.md` + `library.md` + `testing.md`
- **Error handling** → `errors-and-logging.md` (+ `library.md` or `home-assistant.md`)
