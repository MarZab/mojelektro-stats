from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from scripts.release import (
    ABOUT,
    MANIFEST,
    ReleaseError,
    Version,
    current_version,
    main,
    next_version,
    resolve_target,
    write_version,
)

_REPO = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("current", "kind", "base", "expected"),
    [
        ("1.0.1", "patch", "minor", "1.0.2"),
        ("1.0.1", "minor", "minor", "1.1.0"),
        ("1.0.1", "major", "minor", "2.0.0"),
        ("1.0.1", "beta", "minor", "1.1.0b1"),
        ("1.0.1", "beta", "patch", "1.0.2b1"),
        ("1.0.1", "rc", "major", "2.0.0rc1"),
        ("1.1.0b1", "beta", "minor", "1.1.0b2"),
        ("1.1.0b2", "rc", "minor", "1.1.0rc1"),
        ("1.1.0a3", "beta", "minor", "1.1.0b1"),
        ("1.1.0rc1", "final", "minor", "1.1.0"),
        ("1.1.0rc1", "patch", "minor", "1.1.1"),
    ],
)
def test_next_version(current: str, kind: str, base: str, expected: str) -> None:
    assert str(next_version(Version.parse(current), kind, base)) == expected


def test_cannot_go_back_a_phase() -> None:
    with pytest.raises(ReleaseError, match="back"):
        next_version(Version.parse("1.1.0rc1"), "beta")


def test_final_needs_a_prerelease() -> None:
    with pytest.raises(ReleaseError, match="already a stable"):
        next_version(Version.parse("1.0.1"), "final")


@pytest.mark.parametrize("text", ["1.1", "v1.1.0", "1.1.0-beta.1", "1.1.0b", "1.1.0beta1"])
def test_rejects_non_pep440_shapes(text: str) -> None:
    with pytest.raises(ReleaseError, match="invalid version"):
        Version.parse(text)


@pytest.mark.parametrize("target", ["1.0.1", "1.0.0", "1.0.1rc1"])
def test_explicit_target_must_be_newer(target: str) -> None:
    with pytest.raises(ReleaseError, match="not newer"):
        resolve_target(Version.parse("1.0.1"), target)


def test_prerelease_sorts_before_final() -> None:
    assert str(resolve_target(Version.parse("1.1.0b2"), "1.1.0")) == "1.1.0"


# --- files and git ---------------------------------------------------------


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A throwaway git repo holding copies of the two version files, with a
    bare `origin` remote so push can run without touching the network."""
    root = tmp_path / "repo"
    for rel in (ABOUT, MANIFEST):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(_REPO / rel, root / rel)
    write_version(root, Version.parse("1.0.1"))
    remote = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    _git(root.parent, "init", "-q", "-b", "main", str(root))
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "test")
    _git(root, "remote", "add", "origin", str(remote))
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    return root


def test_write_version_keeps_files_in_lockstep(repo: Path) -> None:
    manifest_before = (repo / MANIFEST).read_text()
    write_version(repo, Version.parse("1.1.0b1"))
    assert str(current_version(repo)) == "1.1.0b1"
    manifest_after = (repo / MANIFEST).read_text()
    # Only the version value changed; key order and formatting are kept.
    assert manifest_after == manifest_before.replace('"1.0.1"', '"1.1.0b1"')
    assert json.loads(manifest_after)["version"] == "1.1.0b1"


def test_mismatched_files_are_reported(repo: Path) -> None:
    about = repo / ABOUT
    about.write_text(about.read_text().replace("1.0.1", "9.9.9"))
    with pytest.raises(ReleaseError, match="lockstep"):
        current_version(repo)


def test_release_bumps_commits_tags_and_pushes(repo: Path) -> None:
    assert main(["beta", "--yes"], root=repo) == 0
    assert str(current_version(repo)) == "1.1.0b1"
    assert _git(repo, "log", "-1", "--format=%s") == "chore: release v1.1.0b1"
    assert _git(repo, "tag", "--list") == "v1.1.0b1"
    remote = _git(repo, "ls-remote", "origin")
    assert "refs/tags/v1.1.0b1" in remote
    assert "refs/heads/main" in remote


def _unchanged(repo: Path) -> None:
    assert str(current_version(repo)) == "1.0.1"
    assert _git(repo, "log", "-1", "--format=%s") == "init"
    assert _git(repo, "tag", "--list") == ""
    assert _git(repo, "ls-remote", "origin") == ""


def _fake_terminal(monkeypatch: pytest.MonkeyPatch, answer: str) -> list[str]:
    prompts: list[str] = []
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    def fake_input(prompt: str) -> str:
        prompts.append(prompt)
        return answer

    monkeypatch.setattr("builtins.input", fake_input)
    return prompts


def test_plan_lists_every_step(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["minor", "--dry-run"], root=repo) == 0
    out = capsys.readouterr().out
    assert "Release v1.1.0  (stable)" in out
    assert "set the version 1.0.1 -> 1.1.0" in out
    assert 'commit on main: "chore: release v1.1.0"' in out
    assert "create the annotated tag v1.1.0" in out
    assert "push main and v1.1.0 to origin" in out
    assert "full GitHub Release, marked latest" in out
    assert "dry run: nothing changed" in out


def test_plan_names_a_prerelease(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["beta", "--dry-run"], root=repo) == 0
    assert "GitHub pre-release (HACS beta channel)" in capsys.readouterr().out


def test_plan_warns_about_a_missing_changelog_section(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["patch", "--dry-run"], root=repo) == 0
    assert "CHANGELOG.md has no '## 1.0.2' section" in capsys.readouterr().out

    (repo / "CHANGELOG.md").write_text("# Changelog\n\n## 1.0.2\n\n- fix\n")
    _git(repo, "add", "CHANGELOG.md")
    _git(repo, "commit", "-q", "-m", "changelog")
    assert main(["patch", "--dry-run"], root=repo) == 0
    assert "warning" not in capsys.readouterr().out


def test_declining_changes_nothing(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    prompts = _fake_terminal(monkeypatch, "n")
    assert main(["patch"], root=repo) == 0
    assert prompts == ["Proceed? [y/N] "]
    assert "aborted: nothing changed" in capsys.readouterr().out
    _unchanged(repo)


def test_confirming_releases(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    prompts = _fake_terminal(monkeypatch, "y")
    assert main(["patch"], root=repo) == 0
    assert len(prompts) == 1  # one confirmation covers every step
    assert str(current_version(repo)) == "1.0.2"
    assert "refs/tags/v1.0.2" in _git(repo, "ls-remote", "origin")


def test_without_a_terminal_it_needs_yes(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["1.0.2"], root=repo) == 1  # pytest's stdin is not a terminal
    assert "--yes" in capsys.readouterr().err
    _unchanged(repo)


def test_dry_run_changes_nothing(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["rc", "--dry-run"], root=repo) == 0
    assert "1.0.1 -> 1.1.0rc1" in capsys.readouterr().out
    _unchanged(repo)


def test_no_argument_shows_current(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([], root=repo) == 0
    assert capsys.readouterr().out.strip() == "1.0.1  (stable, tag v1.0.1)"


def test_release_refuses_a_dirty_tree(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (repo / MANIFEST).write_text((repo / MANIFEST).read_text() + "\n")
    assert main(["patch"], root=repo) == 1
    assert "uncommitted changes" in capsys.readouterr().err
    assert _git(repo, "tag", "--list") == ""


def test_release_refuses_an_existing_tag(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _git(repo, "tag", "v1.0.2")
    assert main(["patch"], root=repo) == 1
    assert "already exists" in capsys.readouterr().err
    assert str(current_version(repo)) == "1.0.1"


def test_dry_run_reports_blockers(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (repo / MANIFEST).write_text((repo / MANIFEST).read_text() + "\n")
    _git(repo, "tag", "v1.0.2")
    assert main(["patch", "--dry-run"], root=repo) == 0
    out = capsys.readouterr().out
    assert "Release v1.0.2" in out
    assert "blocked: working tree has uncommitted changes" in out
    assert "blocked: tag v1.0.2 already exists" in out
