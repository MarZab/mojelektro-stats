#!/usr/bin/env python3
"""Release helper for the HACS integration (wrapped by `mise run release`).

Versions live in two files that must stay in lockstep:
`custom_components/mojelektro_stats/lib/mojelektro_api/__about__.py` and the
integration's `manifest.json`. Versions are `X.Y.Z` (stable) or PEP 440
pre-releases `X.Y.ZaN` / `X.Y.ZbN` / `X.Y.ZrcN` (beta channel), matching what
`.github/workflows/release.yaml` accepts.

    mise run release                    show the current version and channel
    mise run release -- beta            bump, commit, tag vX, then ask to push
    mise run release -- 1.1.0 --dry-run print what it would do

KIND: patch | minor | major | alpha | beta | rc | final.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, replace
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ABOUT = Path("custom_components/mojelektro_stats/lib/mojelektro_api/__about__.py")
MANIFEST = Path("custom_components/mojelektro_stats/manifest.json")

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:(a|b|rc)(\d+))?$")
_ABOUT_RE = re.compile(r'^__version__ = "([^"]*)"$', re.MULTILINE)
_MANIFEST_RE = re.compile(r'("version"\s*:\s*")([^"]*)(")')
_PHASES = ("a", "b", "rc")
_PHASE_FOR_KIND = {"alpha": "a", "beta": "b", "rc": "rc"}
KINDS = ("patch", "minor", "major", "alpha", "beta", "rc", "final")


class ReleaseError(Exception):
    """A user-facing problem; printed without a traceback."""


@dataclass(frozen=True, slots=True)
class Version:
    major: int
    minor: int
    patch: int
    phase: str | None = None  # "a" | "b" | "rc"
    number: int | None = None

    @classmethod
    def parse(cls, text: str) -> Version:
        match = _VERSION_RE.match(text.strip())
        if match is None:
            raise ReleaseError(
                f"invalid version {text!r}: use X.Y.Z or X.Y.Z(a|b|rc)N, e.g. 1.1.0b1"
            )
        major, minor, patch, phase, number = match.groups()
        return cls(
            int(major), int(minor), int(patch), phase, None if number is None else int(number)
        )

    @property
    def is_prerelease(self) -> bool:
        return self.phase is not None

    @property
    def channel(self) -> str:
        return "beta (pre-release)" if self.is_prerelease else "stable"

    def base(self) -> Version:
        return Version(self.major, self.minor, self.patch)

    def __str__(self) -> str:
        core = f"{self.major}.{self.minor}.{self.patch}"
        return core if self.phase is None else f"{core}{self.phase}{self.number}"


def _bump_part(version: Version, part: str) -> Version:
    if part == "major":
        return Version(version.major + 1, 0, 0)
    if part == "minor":
        return Version(version.major, version.minor + 1, 0)
    if part == "patch":
        return Version(version.major, version.minor, version.patch + 1)
    raise ReleaseError(f"unknown version part {part!r}")


def next_version(current: Version, kind: str, base: str = "minor") -> Version:
    """Compute the version a bump of ``kind`` produces from ``current``."""
    if kind in ("major", "minor", "patch"):
        return _bump_part(current.base(), kind)
    if kind == "final":
        if not current.is_prerelease:
            raise ReleaseError(f"{current} is already a stable version")
        return current.base()
    if kind in _PHASE_FOR_KIND:
        phase = _PHASE_FOR_KIND[kind]
        if current.phase is None:
            # Start a pre-release of the next version.
            return replace(_bump_part(current, base), phase=phase, number=1)
        if current.phase == phase:
            assert current.number is not None
            return replace(current, number=current.number + 1)
        if _PHASES.index(phase) > _PHASES.index(current.phase):
            return replace(current, phase=phase, number=1)
        raise ReleaseError(f"can't go from {current} back to an {kind} of the same version")
    raise ReleaseError(f"unknown bump {kind!r}; use a version or one of {', '.join(KINDS)}")


def resolve_target(current: Version, spec: str, base: str = "minor") -> Version:
    """``spec`` is an explicit version or a bump kind."""
    target = next_version(current, spec, base) if spec in KINDS else Version.parse(spec)
    if _sort_key(target) <= _sort_key(current):
        raise ReleaseError(f"{target} is not newer than the current {current}")
    return target


def _sort_key(v: Version) -> tuple[int, int, int, int, int]:
    # Pre-releases sort before the final release of the same X.Y.Z.
    phase_rank = len(_PHASES) if v.phase is None else _PHASES.index(v.phase)
    return (v.major, v.minor, v.patch, phase_rank, v.number or 0)


# --- version files ---------------------------------------------------------


def read_versions(root: Path) -> tuple[str, str]:
    about = _ABOUT_RE.search((root / ABOUT).read_text(encoding="utf-8"))
    if about is None:
        raise ReleaseError(f"no __version__ line in {ABOUT}")
    manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    return about.group(1), str(manifest.get("version", ""))


def current_version(root: Path) -> Version:
    about, manifest = read_versions(root)
    if about != manifest:
        raise ReleaseError(
            f"versions out of lockstep: {ABOUT} has {about!r}, {MANIFEST} has {manifest!r}"
        )
    return Version.parse(about)


def write_version(root: Path, version: Version) -> None:
    """Rewrite both files in place, keeping the rest of their formatting."""
    about_path, manifest_path = root / ABOUT, root / MANIFEST
    about_text = _ABOUT_RE.sub(f'__version__ = "{version}"', about_path.read_text("utf-8"), 1)
    manifest_text, count = _MANIFEST_RE.subn(
        rf"\g<1>{version}\g<3>", manifest_path.read_text("utf-8"), 1
    )
    if count != 1:
        raise ReleaseError(f"no version field in {MANIFEST}")
    json.loads(manifest_text)  # still valid JSON
    about_path.write_text(about_text, encoding="utf-8")
    manifest_path.write_text(manifest_text, encoding="utf-8")
    if read_versions(root) != (str(version), str(version)):
        raise ReleaseError("version rewrite did not take; check both files")


# --- git -------------------------------------------------------------------


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise ReleaseError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _require_clean(root: Path) -> None:
    if _git(root, "status", "--porcelain", "--untracked-files=no"):
        raise ReleaseError("working tree has uncommitted changes; commit or stash them first")


def _tag_exists(root: Path, tag: str) -> bool:
    return bool(_git(root, "tag", "--list", tag))


# --- command ---------------------------------------------------------------


def _confirm(prompt: str) -> bool:
    """Ask on a terminal; anything but y/yes (or no terminal) means no."""
    return sys.stdin.isatty() and input(prompt).strip().lower() in ("y", "yes")


def release(root: Path, spec: str, base: str, *, dry_run: bool, yes: bool) -> None:
    """Bump both version files, commit, tag, then push (after confirming)."""
    current = current_version(root)
    target = resolve_target(current, spec, base)
    tag = f"v{target}"
    print(f"{current} -> {target}  ({target.channel})")
    if dry_run:
        return
    _require_clean(root)
    if _tag_exists(root, tag):
        raise ReleaseError(f"tag {tag} already exists")

    write_version(root, target)
    _git(root, "add", str(ABOUT), str(MANIFEST))
    _git(root, "commit", "-m", f"chore: release {tag}")
    _git(root, "tag", "-a", tag, "-m", f"Moj Elektro Stats {tag}")
    print(f"committed and tagged {tag}")

    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    if not (yes or _confirm(f"Push {branch} and {tag}? [y/N] ")):
        print(f"not pushed. When ready: git push origin {branch} {tag}")
        return
    _git(root, "push", "origin", branch, tag)
    print(f"pushed {branch} and {tag}; the release workflow publishes the GitHub release")


def main(argv: list[str] | None = None, root: Path = REPO_ROOT) -> int:
    parser = argparse.ArgumentParser(
        prog="mise run release --",
        description="Show the version, or bump, commit, tag and push a release.",
    )
    parser.add_argument(
        "spec",
        nargs="?",
        metavar="VERSION|KIND",
        help=f"a version (1.1.0b1) or one of {', '.join(KINDS)}; omit to show the current one",
    )
    parser.add_argument(
        "--base",
        choices=("patch", "minor", "major"),
        default="minor",
        help="part a pre-release from a stable version bumps (default: minor)",
    )
    parser.add_argument("--dry-run", action="store_true", help="only print the new version")
    parser.add_argument("--yes", "-y", action="store_true", help="push without asking")
    args = parser.parse_args(argv)
    try:
        if args.spec is None:
            version = current_version(root)
            print(f"{version}  ({version.channel}, tag v{version})")
        else:
            release(root, args.spec, args.base, dry_run=args.dry_run, yes=args.yes)
    except ReleaseError as exc:
        print(f"release: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
