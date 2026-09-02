"""Portable path regression tests for standalone shell utilities."""

import stat
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_pre_session_cleanup_uses_home_scoped_profile(
    tmp_path: Path, monkeypatch
) -> None:
    hook = REPO_ROOT / ".claude/hooks/pre-session-cleanup.sh"
    if not hook.exists():
        pytest.skip("public snapshot excludes private Claude configuration")

    fake_bin = tmp_path / "bin"
    fake_home = tmp_path / "home"
    call_log = tmp_path / "calls.log"
    fake_bin.mkdir()
    fake_home.mkdir()

    _write_executable(fake_bin / "lsof", "#!/bin/sh\nexit 1\n")
    _write_executable(fake_bin / "pgrep", "#!/bin/sh\nexit 1\n")
    _write_executable(fake_bin / "find", "#!/bin/sh\nexit 0\n")
    _write_executable(
        fake_bin / "rm",
        '#!/bin/sh\nprintf "%s\\n" "$*" >> "$CALL_LOG"\n',
    )

    profile = fake_home / "Library/Caches/ms-playwright/mcp-chrome-profile"
    profile.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("CALL_LOG", str(call_log))
    monkeypatch.setenv("PATH", f"{fake_bin}:/usr/bin:/bin:/usr/sbin:/sbin")

    subprocess.run(
        ["bash", str(hook)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert call_log.read_text().splitlines() == [f"-rf {profile}"]


def test_venv_health_uses_repository_default(monkeypatch) -> None:
    monkeypatch.delenv("VENV_CACHE_DIR", raising=False)

    result = subprocess.run(
        ["bash", str(REPO_ROOT / "scripts/check-venv-health.sh")],
        check=True,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert f"{REPO_ROOT}/.venvs" in result.stdout


def test_venv_health_accepts_cache_override(tmp_path: Path, monkeypatch) -> None:
    cache_dir = tmp_path / "venvs"
    cache_dir.mkdir()
    monkeypatch.setenv("VENV_CACHE_DIR", str(cache_dir))

    result = subprocess.run(
        ["bash", str(REPO_ROOT / "scripts/check-venv-health.sh")],
        check=True,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert f"VENV_CACHE_DIR: {cache_dir}" in result.stdout
    assert f"Directory exists: {cache_dir}" in result.stdout


def test_critical_dependency_check_accepts_cache_override(
    tmp_path: Path, monkeypatch
) -> None:
    cache_dir = tmp_path / "venvs"
    pip = cache_dir / "api-server-dd0c3437492e8df90c3c3ea9b27923de/bin/pip"
    pip.parent.mkdir(parents=True)
    _write_executable(pip, "#!/bin/sh\nexit 0\n")
    monkeypatch.setenv("VENV_CACHE_DIR", str(cache_dir))

    result = subprocess.run(
        ["bash", str(REPO_ROOT / "scripts/check-critical-deps.sh")],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "All critical dependencies are installed" in result.stdout


def test_tracked_files_do_not_contain_personal_home_path() -> None:
    # Keep the forbidden path split so this test does not match its own source.
    personal_home = "/Users/" + "unicco/"
    git_check = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if git_check.returncode != 0:
        ignored_parts = {".git", ".venv", "node_modules", "__pycache__"}
        matches = []
        for path in REPO_ROOT.rglob("*"):
            relative_path = path.relative_to(REPO_ROOT)
            if not path.is_file() or ignored_parts.intersection(relative_path.parts):
                continue
            try:
                content = path.read_text()
            except (OSError, UnicodeDecodeError):
                continue
            if personal_home in content:
                matches.append(str(relative_path))
        assert not matches, "\n".join(matches)
        return

    grep_result = subprocess.run(
        ["git", "grep", "-n", personal_home, "--", "."],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert grep_result.returncode == 1, grep_result.stdout
