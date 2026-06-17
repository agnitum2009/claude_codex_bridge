from __future__ import annotations

import json
from pathlib import Path
import sys
import time

import pytest

from ccbd.api_models import DeliveryScope, JobRecord, JobStatus, MessageEnvelope
from completion.models import CompletionItemKind, CompletionSourceKind, CompletionStatus
from provider_backends.zai.execution import observe_zai_output
from provider_core.pathing import session_filename_for_agent
from provider_core.registry import build_default_backend_registry
from provider_execution.base import ProviderRuntimeContext, ProviderSubmission


PROVIDERS = ("qwen", "cursor", "copilot", "crush", "kiro", "pi", "zai")
STRUCTURED_PROVIDERS = ("qwen", "cursor", "copilot", "pi")


def _job(provider: str, work_dir: Path) -> JobRecord:
    agent_name = f"{provider}1"
    return JobRecord(
        job_id=f"job_{provider}_run123",
        submission_id=f"sub_{provider}",
        agent_name=agent_name,
        provider=provider,
        request=MessageEnvelope(
            project_id="proj",
            to_agent=agent_name,
            from_actor="main",
            body=f"Reply exactly from {provider}",
            task_id=None,
            reply_to=None,
            message_type="ask",
            delivery_scope=DeliveryScope.SINGLE,
        ),
        status=JobStatus.RUNNING,
        terminal_decision=None,
        cancel_requested_at=None,
        created_at="2026-06-13T00:00:00Z",
        updated_at="2026-06-13T00:00:00Z",
        workspace_path=str(work_dir),
    )


def _runtime_context(provider: str, work_dir: Path) -> ProviderRuntimeContext:
    agent_name = f"{provider}1"
    return ProviderRuntimeContext(
        agent_name=agent_name,
        workspace_path=str(work_dir),
        backend_type="pane-backed",
        runtime_ref="%1",
        session_ref=str(work_dir / ".ccb" / session_filename_for_agent(provider, agent_name)),
    )


def _write_session(provider: str, work_dir: Path) -> None:
    agent_name = f"{provider}1"
    runtime_dir = work_dir / ".ccb" / "agents" / agent_name / "provider-runtime" / provider
    state_dir = work_dir / ".ccb" / "agents" / agent_name / "provider-state" / provider
    session = {
        "active": True,
        "agent_name": agent_name,
        "runtime_dir": str(runtime_dir),
        "completion_artifact_dir": str(runtime_dir / "completion"),
        "work_dir": str(work_dir),
        "pane_id": "%1",
        f"{provider}_state_dir": str(state_dir),
        f"{provider}_home": str(state_dir / "home"),
        f"{provider}_data_dir": str(state_dir / "data"),
    }
    session_path = work_dir / ".ccb" / session_filename_for_agent(provider, agent_name)
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_text(json.dumps(session, ensure_ascii=True), encoding="utf-8")


def _adapter(provider: str):
    backend = build_default_backend_registry(include_optional=True, include_test_doubles=False).get(provider)
    assert backend is not None
    assert backend.execution_adapter is not None
    return backend.execution_adapter


def _install_stub(monkeypatch, provider: str, *, mode: str = "") -> None:
    stub = Path("test/stubs/provider_stub.py").resolve()
    monkeypatch.setenv(f"{provider.upper()}_START_CMD", f"{sys.executable} {stub} --provider {provider}")
    if mode:
        monkeypatch.setenv(f"{provider.upper()}_STUB_MODE", mode)
    else:
        monkeypatch.delenv(f"{provider.upper()}_STUB_MODE", raising=False)


def _run_to_terminal(adapter, submission: ProviderSubmission):
    current = submission
    emitted: list[CompletionItemKind] = []
    for index in range(150):
        result = adapter.poll(current, now=f"2026-06-13T00:00:{index % 60:02d}Z")
        if result is not None:
            current = result.submission
            emitted.extend(item.kind for item in result.items)
            if result.decision is not None:
                return result, emitted
        time.sleep(0.02)
    raise AssertionError("provider adapter did not terminalize")


@pytest.mark.parametrize("provider", PROVIDERS)
def test_native_cli_provider_adapter_completes_from_native_process(monkeypatch, tmp_path: Path, provider: str) -> None:
    work_dir = tmp_path / f"repo-{provider}"
    work_dir.mkdir()
    _write_session(provider, work_dir)
    _install_stub(monkeypatch, provider)

    adapter = _adapter(provider)
    submission = adapter.start(_job(provider, work_dir), context=_runtime_context(provider, work_dir), now="2026-06-13T00:00:00Z")

    assert submission.source_kind is CompletionSourceKind.STRUCTURED_RESULT_STREAM
    assert submission.runtime_state["mode"] == f"{provider}_run"

    terminal, emitted = _run_to_terminal(adapter, submission)

    assert terminal.decision is not None
    assert terminal.decision.status is CompletionStatus.COMPLETED
    assert terminal.decision.reply == f"stub reply for job_{provider}_run123"
    assert CompletionItemKind.ANCHOR_SEEN in emitted
    assert CompletionItemKind.ASSISTANT_FINAL in emitted
    assert CompletionItemKind.TURN_BOUNDARY in emitted


@pytest.mark.parametrize("provider", PROVIDERS)
def test_native_cli_provider_adapter_reports_empty_reply(monkeypatch, tmp_path: Path, provider: str) -> None:
    work_dir = tmp_path / f"repo-empty-{provider}"
    work_dir.mkdir()
    _write_session(provider, work_dir)
    _install_stub(monkeypatch, provider, mode="empty")

    adapter = _adapter(provider)
    submission = adapter.start(_job(provider, work_dir), context=_runtime_context(provider, work_dir), now="2026-06-13T00:00:00Z")
    terminal, _emitted = _run_to_terminal(adapter, submission)

    assert terminal.decision is not None
    assert terminal.decision.status is CompletionStatus.INCOMPLETE
    assert terminal.decision.reason == f"{provider}_empty_reply"


@pytest.mark.parametrize("provider", PROVIDERS)
def test_native_cli_provider_adapter_reports_nonzero_exit(monkeypatch, tmp_path: Path, provider: str) -> None:
    work_dir = tmp_path / f"repo-failed-{provider}"
    work_dir.mkdir()
    _write_session(provider, work_dir)
    _install_stub(monkeypatch, provider, mode="permission")

    adapter = _adapter(provider)
    submission = adapter.start(_job(provider, work_dir), context=_runtime_context(provider, work_dir), now="2026-06-13T00:00:00Z")
    terminal, _emitted = _run_to_terminal(adapter, submission)

    assert terminal.decision is not None
    assert terminal.decision.status is CompletionStatus.FAILED
    assert terminal.decision.reason == f"{provider}_run_failed"
    assert "permission denied" in str(terminal.decision.diagnostics.get("stderr_tail") or "")


@pytest.mark.parametrize("provider", PROVIDERS)
def test_native_cli_provider_adapter_reports_run_timeout(monkeypatch, tmp_path: Path, provider: str) -> None:
    work_dir = tmp_path / f"repo-timeout-{provider}"
    work_dir.mkdir()
    _write_session(provider, work_dir)
    _install_stub(monkeypatch, provider, mode="timeout")
    monkeypatch.setenv("STUB_TIMEOUT_SLEEP", "5")
    monkeypatch.setenv(f"CCB_{provider.upper()}_RUN_TIMEOUT_S", "0.1")

    adapter = _adapter(provider)
    submission = adapter.start(_job(provider, work_dir), context=_runtime_context(provider, work_dir), now="2026-06-13T00:00:00Z")
    terminal, emitted = _run_to_terminal(adapter, submission)

    assert terminal.decision is not None
    assert terminal.decision.status is CompletionStatus.INCOMPLETE
    assert terminal.decision.reason == f"{provider}_run_timeout"
    assert terminal.decision.diagnostics["run_timeout_s"] == 0.1
    assert CompletionItemKind.ANCHOR_SEEN in emitted


def test_zai_observer_extracts_assistant_and_drops_progress(tmp_path: Path) -> None:
    stdout = tmp_path / "zai.out"
    stdout.write_text(
        "\n".join(
            [
                json.dumps({"role": "user", "content": "CCB_REQ_ID: job_zai\nread file"}, ensure_ascii=True),
                json.dumps({"role": "assistant", "content": "Using tools to help you..."}, ensure_ascii=True),
                json.dumps({"role": "assistant", "content": "alpha beta gamma"}, ensure_ascii=True),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    observation = observe_zai_output(stdout)

    assert observation.error == ""
    assert observation.text == "alpha beta gamma"


@pytest.mark.parametrize("provider", STRUCTURED_PROVIDERS)
def test_native_cli_structured_tool_event_does_not_terminalize_before_final(tmp_path: Path, provider: str) -> None:
    stdout = tmp_path / f"{provider}.jsonl"
    stdout.write_text(
        json.dumps(
            {
                "type": "tool_call",
                "role": "assistant",
                "status": "tool_calls",
                "name": "demo",
            },
            ensure_ascii=True,
        )
        + "\n",
        encoding="utf-8",
    )
    submission = ProviderSubmission(
        job_id=f"job_tool_{provider}",
        agent_name=f"{provider}1",
        provider=provider,
        accepted_at="2026-06-13T00:00:00Z",
        ready_at="2026-06-13T00:00:00Z",
        source_kind=CompletionSourceKind.STRUCTURED_RESULT_STREAM,
        reply="",
        runtime_state={
            "mode": f"{provider}_run",
            "provider": provider,
            "job_id": f"job_tool_{provider}",
            "request_anchor": f"job_tool_{provider}",
            "stdout_path": str(stdout),
            "stderr_path": str(tmp_path / "stderr.log"),
            "next_seq": 1,
            "anchor_emitted": False,
            "returncode": None,
        },
    )

    active = _adapter(provider).poll(submission, now="2026-06-13T00:00:01Z")

    assert active is not None
    assert active.decision is None

    active.submission.runtime_state["returncode"] = 0
    terminal = _adapter(provider).poll(active.submission, now="2026-06-13T00:00:02Z")

    assert terminal is not None
    assert terminal.decision is not None
    assert terminal.decision.status is CompletionStatus.INCOMPLETE
    assert terminal.decision.reason == f"{provider}_run_finished:tool_calls"
