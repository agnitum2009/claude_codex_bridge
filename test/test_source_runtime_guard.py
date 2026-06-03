from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CCB = REPO_ROOT / "ccb"


def _run_source_ccb(args: list[str], *, cwd: Path, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.pop("PYTEST_CURRENT_TEST", None)
    env.pop("CCB_SOURCE_RUNTIME_OK", None)
    env.pop("CCB_SOURCE_ALLOWED_ROOTS", None)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(CCB), *args],
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def test_source_ccb_allows_introspection_outside_test_roots() -> None:
    proc = _run_source_ccb(["--print-version"], cwd=REPO_ROOT)

    assert proc.returncode == 0
    assert proc.stdout.strip()


def test_source_ccb_rejects_stateful_commands_outside_test_roots() -> None:
    proc = _run_source_ccb(["doctor"], cwd=REPO_ROOT)

    assert proc.returncode == 1
    assert "Refusing to run the CCB source checkout outside an allowed test project" in proc.stderr
    assert "Use the installed release `ccb` for normal projects" in proc.stderr


def test_source_ccb_allows_stateful_commands_under_configured_test_root(tmp_path: Path) -> None:
    allowed = tmp_path / "test-project"
    project = allowed / "repo"
    project.mkdir(parents=True)
    (project / ".ccb").mkdir()
    (project / ".ccb" / "ccb.config").write_text("cmd; agent1:codex\n", encoding="utf-8")

    proc = _run_source_ccb(
        ["config", "validate"],
        cwd=project,
        extra_env={"CCB_SOURCE_ALLOWED_ROOTS": str(allowed)},
    )

    assert proc.returncode == 0
    assert "config_status: valid" in proc.stdout


def test_source_ccb_explicit_override_allows_one_off_run(tmp_path: Path) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    (project / ".ccb").mkdir()
    (project / ".ccb" / "ccb.config").write_text("cmd; agent1:codex\n", encoding="utf-8")

    proc = _run_source_ccb(["config", "validate"], cwd=project, extra_env={"CCB_SOURCE_RUNTIME_OK": "1"})

    assert proc.returncode == 0
    assert "config_status: valid" in proc.stdout
