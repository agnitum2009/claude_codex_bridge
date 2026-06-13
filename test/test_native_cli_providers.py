from __future__ import annotations

from pathlib import Path

from agents.models import (
    AgentSpec,
    PermissionMode,
    QueuePolicy,
    RestoreMode,
    RuntimeMode,
    WorkspaceMode,
)
from cli.models import ParsedStartCommand
from provider_backends.deepseek.launcher import build_start_cmd as build_deepseek_start_cmd
from provider_backends.kimi.launcher import build_start_cmd as build_kimi_start_cmd


def _spec(
    name: str,
    provider: str,
    *,
    startup_args: tuple[str, ...] = (),
    provider_command_template: str | None = None,
) -> AgentSpec:
    return AgentSpec(
        name=name,
        provider=provider,
        target=".",
        workspace_mode=WorkspaceMode.GIT_WORKTREE,
        workspace_root=None,
        runtime_mode=RuntimeMode.PANE_BACKED,
        restore_default=RestoreMode.AUTO,
        permission_default=PermissionMode.MANUAL,
        queue_policy=QueuePolicy.SERIAL_PER_AGENT,
        startup_args=startup_args,
        provider_command_template=provider_command_template,
    )


def test_kimi_start_cmd_uses_env_override_and_auto_without_implicit_restore(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("KIMI_START_CMD", "/tmp/stub-kimi --profile test")
    command = ParsedStartCommand(project=None, agent_names=("kimi_agent",), restore=True, auto_permission=True)
    spec = _spec("kimi_agent", "kimi", startup_args=("--model", "kimi-k2"))

    cmd = build_kimi_start_cmd(command, spec, tmp_path / "runtime", "launch-1")

    assert cmd.endswith("/tmp/stub-kimi --profile test --auto-approve --model kimi-k2")
    assert "--continue" not in cmd


def test_kimi_start_cmd_preserves_explicit_user_restore_and_does_not_duplicate_auto_flags(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("KIMI_START_CMD", raising=False)
    command = ParsedStartCommand(project=None, agent_names=("kimi_agent",), restore=True, auto_permission=True)
    spec = _spec("kimi_agent", "kimi", startup_args=("--yolo", "--session", "abc"))

    cmd = build_kimi_start_cmd(command, spec, tmp_path / "runtime", "launch-1")

    assert cmd.endswith("kimi --yolo --session abc")
    assert "--auto-approve" not in cmd
    assert "--continue" not in cmd


def test_kimi_start_cmd_treats_legacy_auto_flag_as_explicit(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("KIMI_START_CMD", raising=False)
    command = ParsedStartCommand(project=None, agent_names=("kimi_agent",), restore=True, auto_permission=True)
    spec = _spec("kimi_agent", "kimi", startup_args=("--auto", "--session", "abc"))

    cmd = build_kimi_start_cmd(command, spec, tmp_path / "runtime", "launch-1")

    assert cmd.endswith("kimi --auto --session abc")
    assert "--auto-approve" not in cmd
    assert "--continue" not in cmd


def test_deepseek_start_cmd_defaults_to_deepcode_and_keeps_startup_args(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("DEEPSEEK_START_CMD", raising=False)
    command = ParsedStartCommand(project=None, agent_names=("deep_agent",), restore=True, auto_permission=True)
    spec = _spec("deep_agent", "deepseek", startup_args=("--raw",))

    cmd = build_deepseek_start_cmd(command, spec, tmp_path / "runtime", "launch-1")

    assert cmd.endswith("deepcode --raw")


def test_deepseek_start_cmd_supports_env_override_and_template(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DEEPSEEK_START_CMD", "/tmp/deepcode --config demo")
    command = ParsedStartCommand(project=None, agent_names=("deep_agent",), restore=False, auto_permission=False)
    spec = _spec("deep_agent", "deepseek", provider_command_template="sandbox=1 {command}")

    cmd = build_deepseek_start_cmd(command, spec, tmp_path / "runtime", "launch-1")

    assert cmd.endswith("sandbox=1 /tmp/deepcode --config demo")
