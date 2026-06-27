from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "dynamic_layout_smoke.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("dynamic_layout_smoke", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_build_multi_node_config_declares_explicit_windows_and_loop_profiles() -> None:
    module = _load_module()

    text = module.build_multi_node_config()

    assert 'entry_window = "main"' in text
    assert '[windows]' in text
    assert 'main = "orchestrator:fake"' in text
    assert '[loop.capacity]' in text
    assert 'max_nodes = 4' in text
    assert '[loop.role_profiles.worker]' in text
    assert 'role = "agentroles.coder"' in text
    assert '[loop.role_profiles.code_reviewer]' in text
    assert 'role = "agentroles.code_reviewer"' in text


def test_build_configs_accept_provider() -> None:
    module = _load_module()

    assert 'main = "orchestrator:codex"' in module.build_multi_node_config(provider="codex")
    assert 'provider = "codex"' in module.build_multi_node_config(provider="codex")
    assert 'main = "main:claude"' in module.build_same_window_config(provider="claude")
    assert 'main = "main:claude"' in module.build_single_agent_window_config(provider="claude")
    assert 'plan-orchestrate = "planner:gemini"' in module.build_window_class_config(provider="gemini")
    assert 'main = "frontdesk:qwen"' in module.build_resolve_preflight_config(provider="qwen")
    assert 'provider = "qwen"' in module.build_resolve_preflight_config(provider="qwen")


def test_build_resolve_preflight_config_can_use_static_filler_provider() -> None:
    module = _load_module()

    text = module.build_resolve_preflight_config(provider="codex", static_provider="fake")

    assert 'main = "frontdesk:fake"' in text
    assert 'plan-orchestrate = "p1:fake, p2:fake, p3:fake, p4:fake, p5:fake, p6:fake"' in text
    assert '[loop.role_profiles.worker]' in text
    assert 'provider = "codex"' in text


def test_build_window_class_config_declares_plan_orchestrate_window() -> None:
    module = _load_module()

    text = module.build_window_class_config()

    assert 'entry_window = "main"' in text
    assert '[windows]' in text
    assert 'main = "frontdesk:fake"' in text
    assert 'plan-orchestrate = "planner:fake"' in text


def test_build_resolve_preflight_config_declares_full_class_and_loop_profiles() -> None:
    module = _load_module()

    text = module.build_resolve_preflight_config()

    assert 'main = "frontdesk:fake"' in text
    assert 'plan-orchestrate = "p1:fake, p2:fake, p3:fake, p4:fake, p5:fake, p6:fake"' in text
    assert '[loop.capacity]' in text
    assert 'name_template = "loop-{loop_id}-{profile}-{index}"' in text
    assert '[loop.role_profiles.worker]' in text
    assert '[loop.role_profiles.code_reviewer]' in text


def test_prepare_projects_write_configs_and_roles(tmp_path: Path) -> None:
    module = _load_module()

    multi = module.prepare_multi_node_project(test_root=tmp_path, project_name="multi", reset=False)
    same = module.prepare_same_window_project(test_root=tmp_path, project_name="same", reset=False)
    single = module.prepare_single_agent_window_project(test_root=tmp_path, project_name="single", reset=False)
    window_class = module.prepare_window_class_project(test_root=tmp_path, project_name="window-class", reset=False)
    resolve = module.prepare_resolve_preflight_project(test_root=tmp_path, project_name="resolve", reset=False)

    multi_root = Path(multi["project_root"])
    same_root = Path(same["project_root"])
    single_root = Path(single["project_root"])
    window_class_root = Path(window_class["project_root"])
    resolve_root = Path(resolve["project_root"])
    assert (multi_root / ".ccb" / "ccb.config").read_text(encoding="utf-8").startswith("version = 2")
    assert (same_root / ".ccb" / "ccb.config").read_text(encoding="utf-8").startswith("version = 2")
    assert (single_root / ".ccb" / "ccb.config").read_text(encoding="utf-8").startswith("version = 2")
    assert 'plan-orchestrate = "planner:fake"' in (window_class_root / ".ccb" / "ccb.config").read_text(encoding="utf-8")
    assert 'plan-orchestrate = "p1:fake, p2:fake, p3:fake, p4:fake, p5:fake, p6:fake"' in (resolve_root / ".ccb" / "ccb.config").read_text(encoding="utf-8")
    assert (Path(multi["role_store"]) / "installed" / "agentroles.coder" / "current" / "role.toml").is_file()
    assert (Path(multi["role_store"]) / "installed" / "agentroles.code_reviewer" / "current" / "role.toml").is_file()
    assert (Path(same["role_store"]) / "installed" / "agentroles.general" / "current" / "role.toml").is_file()
    assert (Path(single["role_store"]) / "installed" / "agentroles.general" / "current" / "role.toml").is_file()
    assert (Path(window_class["role_store"]) / "installed" / "agentroles.general" / "current" / "role.toml").is_file()
    assert (Path(resolve["role_store"]) / "installed" / "agentroles.general" / "current" / "role.toml").is_file()
    assert (Path(resolve["role_store"]) / "installed" / "agentroles.coder" / "current" / "role.toml").is_file()
    assert (Path(resolve["role_store"]) / "installed" / "agentroles.code_reviewer" / "current" / "role.toml").is_file()


def test_prepare_only_can_generate_real_provider_window_class_project(tmp_path: Path) -> None:
    module = _load_module()

    payload = module.run_dynamic_layout_smoke(
        test_root=tmp_path,
        project_prefix="real-provider-prepare",
        ccb_test=Path(__file__),
        provider="codex",
        flows=("window-class",),
        prepare_only=True,
        reset=True,
    )

    assert payload["dynamic_layout_smoke_status"] == "prepared"
    assert payload["flows"] == ["window-class"]
    assert len(payload["prepared"]) == 1
    config = Path(payload["prepared"][0]["project_root"]) / ".ccb" / "ccb.config"
    assert 'main = "frontdesk:codex"' in config.read_text(encoding="utf-8")
    assert payload["preflight"]["checks"]["provider"] == "codex"


def test_prepare_only_can_generate_resolve_preflight_project(tmp_path: Path) -> None:
    module = _load_module()

    payload = module.run_dynamic_layout_smoke(
        test_root=tmp_path,
        project_prefix="resolve-prepare",
        ccb_test=Path(__file__),
        provider="claude",
        flows=("resolve-preflight",),
        prepare_only=True,
        reset=True,
    )

    assert payload["dynamic_layout_smoke_status"] == "prepared"
    assert payload["flows"] == ["resolve-preflight"]
    assert len(payload["prepared"]) == 1
    config = Path(payload["prepared"][0]["project_root"]) / ".ccb" / "ccb.config"
    assert 'plan-orchestrate = "p1:claude, p2:claude, p3:claude, p4:claude, p5:claude, p6:claude"' in config.read_text(encoding="utf-8")


def test_prepare_only_can_generate_single_agent_window_project(tmp_path: Path) -> None:
    module = _load_module()

    payload = module.run_dynamic_layout_smoke(
        test_root=tmp_path,
        project_prefix="single-window-prepare",
        ccb_test=Path(__file__),
        provider="fake",
        flows=("single-agent-window",),
        prepare_only=True,
        reset=True,
    )

    assert payload["dynamic_layout_smoke_status"] == "prepared"
    assert payload["flows"] == ["single-agent-window"]
    assert len(payload["prepared"]) == 1
    config = Path(payload["prepared"][0]["project_root"]) / ".ccb" / "ccb.config"
    assert 'main = "main:fake"' in config.read_text(encoding="utf-8")


def test_prepare_only_can_generate_same_window_continuous_project(tmp_path: Path) -> None:
    module = _load_module()

    payload = module.run_dynamic_layout_smoke(
        test_root=tmp_path,
        project_prefix="continuous-prepare",
        ccb_test=Path(__file__),
        provider="fake",
        flows=("same-window-continuous",),
        prepare_only=True,
        reset=True,
    )

    assert payload["dynamic_layout_smoke_status"] == "prepared"
    assert payload["flows"] == ["same-window-continuous"]
    assert len(payload["prepared"]) == 1
    config = Path(payload["prepared"][0]["project_root"]) / ".ccb" / "ccb.config"
    assert 'main = "main:fake"' in config.read_text(encoding="utf-8")


def test_same_window_continuous_flow_grows_to_six_and_shrinks_to_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    project_root = tmp_path / "project"
    role_store = tmp_path / "roles"
    calls: list[tuple[str, str]] = []
    helper_panes = {f"helper{index}": f"%{index + 1}" for index in range(1, 6)}

    monkeypatch.setattr(
        module,
        "prepare_same_window_project",
        lambda **_kwargs: {"project_root": str(project_root), "role_store": str(role_store)},
    )

    def fake_run(name, command, **_kwargs):
        calls.append((name, " ".join(str(item) for item in command)))
        if name.startswith("ask_helper3"):
            return {
                "name": name,
                "returncode": 0,
                "stdout": "accepted job=job_helper3 target=helper3\n[CCB_ASYNC_SUBMITTED job=job_helper3 target=helper3]\n",
                "stderr": "",
            }
        if name.startswith("watch_job_"):
            return {
                "name": name,
                "returncode": 0,
                "stdout": "watch_status: terminal\nstatus: completed\n",
                "stderr": "",
            }
        if name.startswith("ask_main"):
            return {
                "name": name,
                "returncode": 0,
                "stdout": "accepted job=job_main target=main\n[CCB_ASYNC_SUBMITTED job=job_main target=main]\n",
                "stderr": "",
            }
        return {"name": name, "returncode": 0, "stdout": "ok\n", "stderr": ""}

    def fake_run_json(name, command, **_kwargs):
        calls.append((name, " ".join(str(item) for item in command)))
        if name.startswith("add_helper"):
            return {
                "name": name,
                "returncode": 0,
                "stdout": "{}\n",
                "stderr": "",
                "payload": {"apply": {"plan_class": "add_agent"}},
            }
        if name == "layout_after_grow_to_six":
            return {
                "name": name,
                "returncode": 0,
                "stdout": "{}\n",
                "stderr": "",
                "payload": {
                    "dynamic_agent_count": 5,
                    "windows": [
                        {
                            "name": "main",
                            "agent_names": ["main", *helper_panes],
                            "agents": [
                                {"agent": "main", "pane_id": "%1"},
                                *[
                                    {"agent": helper, "pane_id": pane}
                                    for helper, pane in helper_panes.items()
                                ],
                            ],
                        }
                    ],
                },
            }
        if name.startswith("remove_helper"):
            helper = name.removeprefix("remove_")
            return {
                "name": name,
                "returncode": 0,
                "stdout": "{}\n",
                "stderr": "",
                "payload": {
                    "apply": {
                        "plan_class": "remove_agent",
                        "namespace_reflowed_windows": ["main"],
                        "namespace_removed_agents": {helper: helper_panes[helper]},
                    }
                },
            }
        if name == "layout_after_shrink_to_one":
            return {
                "name": name,
                "returncode": 0,
                "stdout": "{}\n",
                "stderr": "",
                "payload": {
                    "dynamic_agent_count": 0,
                    "windows": [
                        {
                            "name": "main",
                            "agent_names": ["main"],
                            "agents": [{"agent": "main", "pane_id": "%1"}],
                        }
                    ],
                },
            }
        raise AssertionError(f"unexpected json command {name}")

    monkeypatch.setattr(module, "_run", fake_run)
    monkeypatch.setattr(module, "_run_json", fake_run_json)

    payload = module._run_same_window_continuous_flow(
        test_root=tmp_path,
        project_name="continuous",
        provider="fake",
        ccb_test=Path("ccb_test"),
        provider_home=tmp_path / "home",
        command_timeout_s=1,
        reset=True,
        keep_running=False,
    )

    assert payload["flow_status"] == "ok"
    assert payload["checks"]["grew_to_six_order"] is True
    assert payload["checks"]["shrunk_to_one_order"] is True
    add_names = [name for name, _command in calls if name.startswith("add_helper")]
    remove_names = [name for name, _command in calls if name.startswith("remove_helper")]
    assert add_names == ["add_helper1", "add_helper2", "add_helper3", "add_helper4", "add_helper5"]
    assert remove_names == ["remove_helper5", "remove_helper4", "remove_helper3", "remove_helper2", "remove_helper1"]


def test_prepare_only_can_generate_light_real_provider_resolve_preflight_project(tmp_path: Path) -> None:
    module = _load_module()

    payload = module.run_dynamic_layout_smoke(
        test_root=tmp_path,
        project_prefix="resolve-light",
        ccb_test=Path(__file__),
        provider="codex",
        flows=("resolve-preflight",),
        resolve_preflight_static_provider="fake",
        prepare_only=True,
        reset=True,
    )

    assert payload["dynamic_layout_smoke_status"] == "prepared"
    assert payload["resolve_preflight_static_provider"] == "fake"
    config = Path(payload["prepared"][0]["project_root"]) / ".ccb" / "ccb.config"
    text = config.read_text(encoding="utf-8")
    assert 'main = "frontdesk:fake"' in text
    assert 'plan-orchestrate = "p1:fake, p2:fake, p3:fake, p4:fake, p5:fake, p6:fake"' in text
    assert 'provider = "codex"' in text


def test_real_provider_run_requires_explicit_opt_in(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()
    monkeypatch.delenv(module.REAL_RUN_ENV, raising=False)

    with pytest.raises(RuntimeError, match=module.REAL_RUN_ENV):
        module.run_dynamic_layout_smoke(
            test_root=tmp_path,
            project_prefix="real-provider-run",
            ccb_test=Path(__file__),
            provider="codex",
            flows=("window-class",),
        )


def test_real_home_mode_ignores_isolated_home_when_override_is_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    isolated_home = tmp_path / "source_home"
    real_home = tmp_path / "real_home"
    monkeypatch.setenv("HOME", str(isolated_home))
    monkeypatch.setenv("CCB_REAL_HOME", str(real_home))

    assert module._provider_home(test_root=tmp_path, mode="real-home") == real_home


def test_main_passes_command_timeout_to_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()
    captured = {}

    def fake_runner(**kwargs):
        captured.update(kwargs)
        return {"dynamic_layout_smoke_status": "prepared"}

    monkeypatch.setattr(module, "run_dynamic_layout_smoke", fake_runner)

    assert module.main(["--command-timeout", "123", "--prepare-only", "--resolve-preflight-static-provider", "fake"]) == 0
    assert captured["command_timeout_s"] == 123
    assert captured["resolve_preflight_static_provider"] == "fake"


def test_main_runs_repeated_providers_as_matrix(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()
    calls = []

    def fake_runner(**kwargs):
        calls.append(kwargs)
        return {
            "dynamic_layout_smoke_status": "ok",
            "provider": kwargs["provider"],
            "flows": list(kwargs["flows"]),
            "checks": {"window_class_middle_release": True},
            "results": [],
        }

    monkeypatch.setattr(module, "run_dynamic_layout_smoke", fake_runner)

    assert module.main(["--provider", "codex", "--provider", "claude", "--flow", "window-class"]) == 0
    assert [(call["provider"], call["project_prefix"]) for call in calls] == [
        ("codex", "dynamic-layout-smoke-codex"),
        ("claude", "dynamic-layout-smoke-claude"),
    ]
    assert calls[0]["flows"] == ("window-class",)


def test_provider_matrix_payload_compacts_provider_results(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()

    def fake_runner(**kwargs):
        return {
            "dynamic_layout_smoke_status": "ok",
            "provider": kwargs["provider"],
            "provider_home_mode": kwargs["provider_home_mode"],
            "flows": ["window-class"],
            "checks": {"window_class_middle_release": True},
            "results": [],
        }

    monkeypatch.setattr(module, "run_dynamic_layout_smoke", fake_runner)

    payload = module.run_dynamic_layout_provider_matrix(
        test_root=tmp_path,
        project_prefix="matrix",
        ccb_test=Path(__file__),
        providers=("codex", "claude", "codex"),
        flows=("window-class",),
    )
    compact = module.compact_smoke_payload(payload)

    assert payload["dynamic_layout_smoke_status"] == "ok"
    assert payload["providers"] == ["codex", "claude"]
    assert compact["provider_results"][0]["provider"] == "codex"
    assert compact["provider_results"][1]["provider"] == "claude"


def test_run_records_timeout_without_raising(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()

    def fake_run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd=["ccb"], timeout=1, output="partial out", stderr="partial err")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    result = module._run("slow", ["ccb"], cwd=tmp_path, env={}, timeout=1)

    assert result["returncode"] is None
    assert result["timeout"] is True
    assert result["stdout"] == "partial out"
    assert result["stderr"] == "partial err"
    compact = module._compact_command(result)
    assert compact["timeout"] is True


def test_payload_helpers_extract_window_agents_and_panes() -> None:
    module = _load_module()
    result = {
        "payload": {
            "windows": [
                {
                    "name": "main",
                    "agent_names": ["main", "helper1"],
                    "agents": [
                        {"agent": "main", "pane_id": "%1"},
                        {"agent": "helper1", "pane_id": "%2"},
                    ],
                }
            ]
        }
    }

    assert module._window_agents(result) == {"main": ["main", "helper1"]}
    assert module._agent_panes(result) == {"main": "%1", "helper1": "%2"}


def test_compact_payload_keeps_checks_and_window_summary_without_full_stdout() -> None:
    module = _load_module()
    payload = {
        "dynamic_layout_smoke_status": "ok",
        "checks": {"flow": True},
        "results": [
            {
                "flow": "flow",
                "flow_status": "ok",
                "checks": {"ok": True},
                "commands": [
                    {
                        "name": "layout",
                        "returncode": 0,
                        "stdout": "line1\nline2\nline3\nline4\n",
                        "payload": {
                            "action": "remove",
                            "layout_status": "ok",
                            "loop_agent_count": 2,
                            "resolved_window_name": "node-round1-node1",
                            "will_create_window": True,
                            "apply": {
                                "plan_class": "remove_agent",
                                "apply_status": "applied",
                                "namespace_removed_agents": {"helper": "%2"},
                                "namespace_removed_windows": ["review"],
                            },
                            "windows": [
                                {
                                    "name": "node-round1-node1",
                                    "agent_names": ["worker", "checker"],
                                    "pane_count": 2,
                                    "large": "ignored",
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }

    compact = module.compact_smoke_payload(payload)

    assert compact["dynamic_layout_smoke_status"] == "ok"
    command = compact["results"][0]["commands"][0]
    assert command["stdout_excerpt"] == ["line1", "line2", "line3"]
    assert command["payload"] == {
        "action": "remove",
        "layout_status": "ok",
        "loop_agent_count": 2,
        "resolved_window_name": "node-round1-node1",
        "will_create_window": True,
        "apply": {
            "plan_class": "remove_agent",
            "apply_status": "applied",
            "namespace_removed_agents": {"helper": "%2"},
            "namespace_removed_windows": ["review"],
        },
        "windows": [
            {
                "name": "node-round1-node1",
                "agents": ["worker", "checker"],
                "pane_count": 2,
            }
        ],
    }


def test_tests_workflow_runs_same_window_continuous_fake_smoke() -> None:
    text = Path(".github/workflows/test.yml").read_text(encoding="utf-8")

    assert "Guard same-window continuous dynamic layout smoke" in text
    assert "scripts/dynamic_layout_smoke.py" in text
    assert "ci-same-window-continuous" in text
    assert "matrix.os == 'ubuntu-latest' && matrix.python-version == '3.11'" in text
    assert "--provider fake" in text
    assert "--flow same-window-continuous" in text
    assert 'payload["dynamic_layout_smoke_status"] == "ok"' in text
    assert 'payload["checks"]["same_window_continuous_1_to_6_to_1"] is True' in text
    assert 'checks["grew_to_six_order"] is True' in text
    assert 'checks["shrunk_to_one_order"] is True' in text
    step = text.split("Guard same-window continuous dynamic layout smoke", 1)[1].split("Guard workflow closure layout cleanup smoke", 1)[0]
    assert "--run" not in step
    assert "codex" not in step
    assert "claude" not in step
