from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "workflow_closure_smoke.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("workflow_closure_smoke", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_build_config_declares_full_workflow_and_loop_profiles() -> None:
    module = _load_module()

    text = module.build_config(provider="fake")

    assert "frontdesk:fake; planner:fake; clarification_broker:fake" in text
    assert "frontdesk:fake" in text
    assert "planner:fake" in text
    assert "clarification_broker:fake" in text
    assert "plan_reviewer:fake" in text
    assert "orchestrator:fake" in text
    assert "round_checker:fake" in text
    assert 'role = "agentroles.ccb_frontdesk"' in text
    assert 'role = "agentroles.ccb_planner"' in text
    assert 'role = "agentroles.ccb_clarification_broker"' in text
    assert 'role = "agentroles.ccb_plan_reviewer"' in text
    assert 'role = "agentroles.ccb_orchestrator"' in text
    assert 'role = "agentroles.ccb_round_checker"' in text
    assert '[loop.role_profiles.worker]' in text
    assert 'role = "agentroles.ccb_worker"' in text
    assert '[loop.role_profiles.code_reviewer]' in text
    assert 'role = "agentroles.ccb_checker"' in text


def test_prepare_project_writes_config_roles_plan_root_and_shims(tmp_path: Path) -> None:
    module = _load_module()
    test_root = tmp_path / "test_ccb2"
    ccb_test = tmp_path / "ccb_test"
    ccb_test.write_text("#!/usr/bin/env bash\n", encoding="utf-8")

    payload = module.prepare_project(
        test_root=test_root,
        project_name="workflow-closure-smoke",
        provider="fake",
        ccb_test=ccb_test,
        reset=False,
    )

    project_root = Path(payload["project_root"])
    role_store = Path(payload["role_store"])
    assert (project_root / ".ccb" / "ccb.config").is_file()
    assert (project_root / "docs" / "plantree" / "plans" / "workflow-smoke" / "README.md").is_file()
    assert (role_store / "installed" / "agentroles.ccb_planner" / "current" / "role.toml").is_file()
    assert (role_store / "installed" / "agentroles.ccb_orchestrator" / "current" / "role.toml").is_file()
    assert (role_store / "installed" / "agentroles.ccb_checker" / "current" / "role.toml").is_file()
    assert (project_root / "bin" / "ccb").is_file()
    assert (project_root / "bin" / "ask").is_file()
    assert str(ccb_test.resolve(strict=False)) in (project_root / "bin" / "ccb").read_text(encoding="utf-8")


def test_run_workflow_smoke_requires_review_and_auto_releases_capacity(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = _load_module()
    ccb_test = tmp_path / "ccb_test"
    ccb_test.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    runner_count = 0
    ready_count = 0

    def fake_run(command, **_kwargs):
        nonlocal runner_count, ready_count
        if command[-2:] == ["kill", "-f"]:
            return subprocess.CompletedProcess(command, 0, stdout="kill_status: ok\n", stderr="")
        if "--diagnose" in command:
            return subprocess.CompletedProcess(command, 0, stdout="allowed_source_test_project: yes\n", stderr="")
        if command[-2:] == ["config", "validate"]:
            return subprocess.CompletedProcess(command, 0, stdout="config_status: valid\n", stderr="")
        if "plan" in command and "task-create" in command:
            return subprocess.CompletedProcess(command, 0, stdout=_json({"status": "draft", "task_id": "task-closure"}), stderr="")
        if "question" in command:
            action = command[command.index("question") + 1]
            status = {
                "candidate-import": "draft",
                "user-batch-import": "needs_clarification",
                "answer-import": "needs_clarification",
                "normalized-import": "draft",
            }[action]
            return subprocess.CompletedProcess(command, 0, stdout=_json({"question_status": "ok", "task_status": status}), stderr="")
        if "plan" in command and "task-artifact" in command:
            return subprocess.CompletedProcess(command, 0, stdout=_json({"status": "draft"}), stderr="")
        if "plan" in command and "task-status" in command:
            ready_count += 1
            if ready_count == 1:
                return subprocess.CompletedProcess(command, 1, stdout="", stderr="plan task ready requires artifacts: review\n")
            return subprocess.CompletedProcess(command, 0, stdout=_json({"status": "ready"}), stderr="")
        if "plan" in command and "task-show" in command:
            return subprocess.CompletedProcess(command, 0, stdout=_json({"status": "blocked", "task": {"status": "blocked"}}), stderr="")
        if "loop" in command and "runner" in command:
            runner_count += 1
            if runner_count == 1:
                return subprocess.CompletedProcess(command, 0, stdout=_json({"loop_runner_status": "ok", "action": "activated_planner"}), stderr="")
            if runner_count == 2:
                return subprocess.CompletedProcess(command, 0, stdout=_json({"loop_runner_status": "paused", "action": "paused"}), stderr="")
            if runner_count == 3:
                return subprocess.CompletedProcess(command, 0, stdout=_json({"loop_runner_status": "ok", "action": "activated_planner"}), stderr="")
            if runner_count == 4:
                return subprocess.CompletedProcess(command, 0, stdout=_json({"loop_runner_status": "ok", "action": "activated_plan_reviewer"}), stderr="")
            project_arg = Path(command[command.index("--project") + 1])
            round_path = project_arg / ".ccb" / "runtime" / "loops" / "lpabc123" / "round.json"
            round_path.parent.mkdir(parents=True, exist_ok=True)
            round_path.write_text(
                _json(
                    {
                        "loop_id": "lpabc123",
                        "capacity": {
                            "release": {
                                "loop_capacity_status": "released",
                                "release_policy": "auto",
                                "retained_count": 0,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=_json(
                    {
                        "loop_runner_status": "ok",
                        "action": "ran_one_round",
                        "loop_id": "lpabc123",
                        "round_result": "blocked",
                        "round_result_source": "missing_round_checker_result",
                        "round": {"round_path": str(round_path)},
                    }
                ),
                stderr="",
            )
        if command[-1] == "ps":
            return subprocess.CompletedProcess(command, 0, stdout="agent: frontdesk\nagent: orchestrator\n", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    payload = module.run_workflow_smoke(
        test_root=tmp_path,
        project_name="workflow-closure-smoke",
        provider="fake",
        ccb_test=ccb_test,
        timeout_s=1,
        reset=True,
    )

    assert payload["workflow_smoke_status"] == "ok"
    assert payload["summary"]["checks"]["ready_before_review_rejected"] is True
    assert payload["summary"]["checks"]["release_policy_auto"] is True
    assert payload["summary"]["checks"]["release_retained_zero"] is True
    assert payload["summary"]["checks"]["dynamic_agents_absent_from_ps"] is True
    assert payload["summary"]["final_status"] == "blocked"
    assert runner_count == 5
    assert ready_count == 2


def test_tests_workflow_runs_workflow_closure_layout_cleanup_smoke() -> None:
    text = Path(".github/workflows/test.yml").read_text(encoding="utf-8")

    assert "Guard workflow closure layout cleanup smoke" in text
    assert "scripts/workflow_closure_smoke.py" in text
    assert "ci-workflow-closure" in text
    assert "matrix.os == 'ubuntu-latest' && matrix.python-version == '3.11'" in text
    assert 'run["workflow_smoke_status"] == "ok"' in text
    assert 'release["loop_capacity_status"] == "released"' in text
    assert 'release["retained_count"] == 0' in text
    assert 'not apply["namespace_reflow_errors"]' in text
    assert 'not apply["pane_identity_report"]["reflow_errors"]' in text


def _json(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False) + "\n"
