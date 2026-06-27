# Git and release rules

This repo releases through **HACS**, not PyPI. Tags and GitHub Releases notify HACS users; `custom_components/mojelektro_stats/` is the deliverable.

## Branching

- `master` is the integration branch. Always green in CI.
- Feature branches: `feat/<short-topic>`, `fix/<short-topic>`, `docs/<short-topic>`, `refactor/<short-topic>`, `chore/<short-topic>`.
- Rebase before merging. No merge commits on `master`.

## Commits

- Conventional Commits style. Imperative subject under 72 chars.
- Body explains the *why*, not the *what*. The diff shows the what.
- One logical change per commit. Mixed-purpose commits get split.

Allowed types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `build`, `ci`, `perf`.

Scope is optional but useful: `feat(coordinator): ...`, `fix(cli): ...`, `chore(deps): ...`.

## Pull requests

- One topic per PR. Big topics get split into reviewable chunks.
- PR description has:
  - What changed and why (link to the spec section if relevant).
  - Test plan: a checklist of how to verify.
  - Risks / migration notes if any.
- CI must be green before merge. No `--no-verify`. No skipped checks.

## Versioning

- SemVer.
- Single source: `custom_components/mojelektro_stats/lib/mojelektro_api/__about__.py` (`__version__ = "X.Y.Z"`).
- The integration's `manifest.json` `"version"` must always match the lib's `__about__.py`.
- Bump both files together by hand: `__about__.py` (`__version__`) and `manifest.json` (`"version"`). Keep them in lockstep.

Bump rules pre-1.0:
- `0.x.0` for breaking changes (lib public surface, integration config schema).
- `0.x.y` for additive / fix.

Post-1.0: standard SemVer.

## Release flow

1. Bump `__about__.py` + `manifest.json` to `X.Y.Z` and commit.
2. Tag: `git tag vX.Y.Z && git push --tags`.
3. CI does the rest:
   - Runs `hacs/action` to validate HACS structure.
   - Creates a GitHub Release with auto-generated notes + the CHANGELOG entry.
4. HACS users see the new version under their custom repository.

If a release is bad: tag a fix release (`X.Y.Z+1`). Do not delete or move tags.

## What never gets committed

- The API token (`.env` is gitignored).
- Real cassettes with unscrubbed tokens.
- Editor cruft (`.idea/`, `.vscode/` — gitignored).
- Real PII in source or in cassettes. Use the conftest scrubbing pipeline + the placeholders documented in [`tests/lib/cassettes/README.md`](../../tests/lib/cassettes/README.md).
