# Python rules

Apply to all Python in this repo. The **product** is the HACS integration; `cli/`, `tests/`, and `scripts/` are developer tooling that follow the same standards.

## Version

Python 3.12 minimum. Use 3.12+ syntax (`type X = ...`, `X | None`, `Self`).

## Tooling

- **Package + lock**: `uv`. `uv sync` to install dev deps, `uv add --dev <pkg>` to add dev deps. This repo is not published to PyPI (`[tool.uv] package = false`).
- **Lint + format**: `ruff` (single tool, no `black`/`isort`/`flake8`).
- **Types**: `mypy --strict` + `pyright` (second opinion in CI).

Do not introduce `pip`, `pip-tools`, `poetry`, `pdm`, `setuptools`, `tox`. We have one chain.

## Typing

- Type every signature: parameters, return, generics. No untyped `def`s.
- Use `from __future__ import annotations` at the top of every module that has forward references; consistent across the lib.
- Prefer `X | None` over `Optional[X]`. Prefer built-in generics (`list[T]`, `dict[K, V]`) over `typing.List` etc.
- `Final` for module-level constants. `Literal` for closed string enums where an `enum.Enum` would be overkill.
- API response payloads are typed via `TypedDict` (runtime-equivalent to `dict`). The client returns parsed JSON directly — no Pydantic round-trip. Use a `dataclass` (frozen) only when the lib produces the value itself and consumers benefit from attribute access.
- `# type: ignore[code]` must include the error code AND a one-line comment explaining why. Plain `# type: ignore` is rejected by review.

## Style

- `ruff format` is canonical. Don't fight it.
- 100-char soft line limit (ruff default).
- Docstrings only where they add information a name doesn't. No "Returns the X" docstrings on `get_x()`.
- Comments only when the *why* is non-obvious — workarounds, surprising constraints, references to issue numbers. No "what" comments.
- Imports sorted by `ruff` (`I` rules enabled). No relative imports across packages; relative is OK within a single package.

## Async

- The library is async-only. Public methods are `async def`.
- Use `httpx.AsyncClient` for HTTP. Reuse one client per `MojElektroClient` instance.
- Use `asyncio.timeout(seconds)` for time bounds — not `asyncio.wait_for`.
- Avoid `asyncio.create_task` without keeping a reference. Tasks must be awaited or stored.

## Dependencies

Runtime deps in the vendored lib are a cost — each one ships inside the HACS integration. Keep them minimal:

- **Integration / lib runtime:** `httpx` (only hard runtime dep today; vendored under `lib/`).
- **Dev-only (CLI, tests):** `typer`, `rich`, `pyyaml`, `questionary`, pytest stack, etc. — in `[dependency-groups] dev` in `pyproject.toml`. Never add these to `manifest.json` `requirements`.

Before adding any integration runtime dep, confirm it's small, well-maintained, and worth vendoring or listing in `manifest.json`.

## Module organization

- Files should hold one clear concept. When a file passes ~400 lines, it's usually doing too much.
- One public class per module is a good default.
- `__init__.py` exports the public surface explicitly via `__all__`. No `from .x import *`.
