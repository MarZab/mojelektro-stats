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
- Bump both files together with `mise run release` (below), which keeps `__about__.py` (`__version__`) and `manifest.json` (`"version"`) in lockstep.

Bump rules pre-1.0:
- `0.x.0` for breaking changes (lib public surface, integration config schema).
- `0.x.y` for additive / fix.

Post-1.0: standard SemVer.

## Release flow

```bash
mise run release                     # current version + channel
mise run release -- minor --dry-run  # what it would do
mise run release -- minor            # bump both files, commit, tag vX.Y.Z, ask to push
```

1. Add a `## X.Y.Z` section for the new version at the top of `CHANGELOG.md`, with a re-import note when stored statistics change. Commit it.
2. `mise run release -- VERSION|KIND` first prints its plan: the version change in both files, the commit `chore: release vX.Y.Z`, the annotated tag, the branch and remote it pushes to, and whether `release.yaml` will publish a full release or a pre-release. It also warns when `CHANGELOG.md` has no section for that version. It changes nothing until you confirm with `y`; `--yes` skips the question, and without a terminal it refuses unless `--yes` is given. It needs a clean tree and a new tag; `--dry-run` shows the plan, listing anything that would block it, and stops.
   KIND is `patch`, `minor`, `major`, `alpha`, `beta`, `rc` or `final`; an explicit version like `1.2.0` also works. It must be newer than the current one.
3. CI does the rest:
   - `validate.yaml` runs `hacs/action` and `hassfest` on every push/PR and nightly.
   - `release.yaml` checks the tag matches `manifest.json` and creates a full GitHub Release with auto-generated notes. (HACS default inclusion requires a real Release, not just a tag.)
4. Users see the update in Home Assistant's Marketplace (2026.11+) or HACS (older).

### Beta channel

Pre-releases use Home Assistant's own PEP 440 style: `X.Y.ZbN` for betas, `X.Y.ZrcN` for release candidates (`aN` for alphas). Not SemVer `-beta.1`; `release.yaml` rejects that.

```bash
mise run release -- beta     # 1.0.1 -> 1.1.0b1 (from a stable version: next minor; --base patch|major)
mise run release -- beta     # 1.1.0b1 -> 1.1.0b2
mise run release -- rc       # 1.1.0b2 -> 1.1.0rc1
mise run release -- final    # 1.1.0rc1 -> 1.1.0
```

`release.yaml` publishes `a`/`b`/`rc` tags as GitHub **pre-releases**. Stable `vX.Y.Z` tags are marked latest.

HACS offers pre-releases only to users who opt in to beta versions for this repository (in HACS's repository options; the exact location varies between HACS versions). Everyone else stays on the latest stable release. Ordering is `1.0.1 < 1.1.0b1 < 1.1.0rc1 < 1.1.0`, so beta users move to the final release when it ships. To fix a bad beta, tag the next one (`b2`).

## HACS default catalog (Marketplace)

The Marketplace in HA 2026.11+ still uses the [hacs/default](https://github.com/hacs/default) catalog. Inclusion checks: `hacs/action` + hassfest pass with no ignores (`validate.yaml` skips only the `license` check, and only on pull requests, because HACS reads the license from the default branch), a full GitHub Release exists, an OSI `LICENSE`, `custom_components/mojelektro_stats/brand/icon.png`, repo description + topics + issues enabled, and `hacs.json` `country: "SI"` (Slovenia-only service). Don't break these.

If a release is bad: tag a fix release (`X.Y.Z+1`). Do not delete or move tags.

## What never gets committed

- The API token (`.env` is gitignored).
- Real cassettes with unscrubbed tokens.
- Editor cruft (`.idea/`, `.vscode/` — gitignored).
- Real PII in source or in cassettes. Use the conftest scrubbing pipeline + the placeholders documented in [`tests/lib/cassettes/README.md`](../../tests/lib/cassettes/README.md).
