from __future__ import annotations

from io import StringIO
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from agents.config_loader import load_project_config
from ccbd.reload_plan import build_reload_dry_run_plan
from cli.models import ParsedAgentCommand
from cli.parser import CliParser
from cli.phase2 import maybe_handle_phase2


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def _write_installed_role(store_root: Path, role_id: str, *, default_agent_name: str) -> None:
    _write(
        store_root / 'installed' / role_id / 'current' / 'role.toml',
        f'''id = "{role_id}"
version = "0.1.0"

[identity]
default_agent_name = "{default_agent_name}"
''',
    )


def _project_with_agent_profiles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    project_root = tmp_path / 'repo-agent-lifecycle'
    role_store = tmp_path / 'roles'
    _write_installed_role(role_store, 'agentroles.general', default_agent_name='general')
    _write_installed_role(role_store, 'agentroles.code_reviewer', default_agent_name='code_reviewer')
    monkeypatch.setenv('AGENT_ROLES_STORE', str(role_store))
    _write(
        project_root / '.ccb' / 'ccb.config',
        """main:codex

[loop.capacity]
enabled = true
max_nodes = 2

[loop.role_profiles.code_reviewer]
role = "agentroles.code_reviewer"
provider = "codex"
thinking = "medium"
max_instances = 2
""",
    )
    return project_root


def _run_phase2(argv: list[str], *, cwd: Path) -> tuple[int, dict[str, object], str]:
    stdout = StringIO()
    stderr = StringIO()
    result = maybe_handle_phase2(argv, cwd=cwd, stdout=stdout, stderr=stderr)
    payload = json.loads(stdout.getvalue()) if stdout.getvalue().strip() else {}
    return result, payload, stderr.getvalue()


def _namespace(project_id: str):
    return SimpleNamespace(
        project_id=project_id,
        namespace_epoch=1,
        tmux_socket_path='/tmp/ccb-test-tmux.sock',
        tmux_session_name='ccb-test-session',
        workspace_window_name='main',
        workspace_window_id='@main',
        workspace_epoch=1,
        ui_attachable=True,
    )


def test_agent_parser_supports_add_and_remove_commands() -> None:
    parser = CliParser()

    assert parser.parse(
        [
            'agent',
            'add',
            'helper:codex',
            '--role',
            'agentroles.general',
            '--hidden',
            '--json',
        ]
    ) == ParsedAgentCommand(
        project=None,
        action='add',
        agent_name='helper',
        provider='codex',
        role='agentroles.general',
        visibility='hidden',
        json_output=True,
    )
    assert parser.parse(
        [
            'agent',
            'remove',
            'helper',
            '--policy',
            'kill',
            '--force',
            '--reason',
            'operator reset',
            '--json',
        ]
    ) == ParsedAgentCommand(
        project=None,
        action='remove',
        agent_name='helper',
        policy='kill',
        force=True,
        reason='operator reset',
        json_output=True,
    )
    assert parser.parse(
        [
            'agent',
            'release',
            'reviewer',
            '--idle-only',
            '--json',
        ]
    ) == ParsedAgentCommand(
        project=None,
        action='release',
        agent_name='reviewer',
        policy='auto',
        idle_only=True,
        json_output=True,
    )
    assert parser.parse(['agent', 'park', 'planner2', '--json']) == ParsedAgentCommand(
        project=None,
        action='park',
        agent_name='planner2',
        json_output=True,
    )
    assert parser.parse(['agent', 'resume', 'planner2', '--hidden', '--json']) == ParsedAgentCommand(
        project=None,
        action='resume',
        agent_name='planner2',
        visibility='hidden',
        json_output=True,
    )


def test_agent_parser_supports_hot_load_placement_options() -> None:
    parser = CliParser()

    assert parser.parse(
        [
            'agent',
            'add',
            'worker1:codex',
            '--profile',
            'code_reviewer',
            '--window',
            'node-loop1-node1',
            '--window-class',
            'execution-node',
            '--loop-id',
            'loop1',
            '--node-id',
            'node1',
            '--hidden',
            '--json',
        ]
    ) == ParsedAgentCommand(
        project=None,
        action='add',
        agent_name='worker1',
        provider='codex',
        profile='code_reviewer',
        window_name='node-loop1-node1',
        window_class='execution-node',
        loop_id='loop1',
        node_id='node1',
        visibility='hidden',
        json_output=True,
    )


def test_agent_add_profile_writes_runtime_overlay_and_config_includes_agent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = _project_with_agent_profiles(tmp_path, monkeypatch)

    result, payload, stderr = _run_phase2(
        ['agent', 'add', 'reviewer', '--profile', 'code_reviewer', '--hidden', '--json'],
        cwd=project_root,
    )

    assert result == 0, stderr
    assert payload['agent_lifecycle_status'] == 'active'
    assert payload['agent'] == 'reviewer'
    assert payload['profile'] == 'code_reviewer'
    assert payload['role'] == 'agentroles.code_reviewer'
    assert payload['provider'] == 'codex'
    assert payload['lifecycle_state'] == 'hidden'
    assert payload['apply']['apply_status'] == 'deferred_until_start'
    state_path = Path(str(payload['state_path']))
    assert state_path.exists()

    loaded = load_project_config(project_root)
    assert 'reviewer' in loaded.config.agents
    assert 'reviewer' in loaded.config.default_agents
    assert loaded.config.agents['reviewer'].role == 'agentroles.code_reviewer'


def test_agent_add_to_existing_window_projects_add_agent_reload_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = _project_with_agent_profiles(tmp_path, monkeypatch)
    current = load_project_config(project_root, include_loop_overlays=False).config

    result, payload, stderr = _run_phase2(
        ['agent', 'add', 'helper:codex', '--role', 'agentroles.general', '--window', 'main', '--hidden', '--json'],
        cwd=project_root,
    )

    assert result == 0, stderr
    assert payload['window_name'] == 'main'
    loaded = load_project_config(project_root).config
    assert loaded.windows_explicit is True
    assert [(window.name, window.agent_names, window.layout_spec) for window in loaded.windows] == [
        ('main', ('main', 'helper'), 'main:codex; helper:codex'),
    ]
    plan = build_reload_dry_run_plan(current, loaded, project_id='proj-1', current_namespace=_namespace('proj-1'))
    assert plan['plan_class'] == 'add_agent'
    assert plan['namespace_patch_plan']['status'] == 'planned'
    assert plan['namespace_patch_plan']['steps'] == [
        {
            'action': 'create_agent_pane',
            'window': 'main',
            'agent': 'helper',
            'role': 'agent',
            'slot_key': 'helper',
            'managed_by': 'ccbd',
            'anchor_agent': 'main',
            'reason': 'new agent appended to existing managed window',
        }
    ]


def test_agent_add_to_new_window_projects_add_window_reload_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = _project_with_agent_profiles(tmp_path, monkeypatch)
    current = load_project_config(project_root, include_loop_overlays=False).config

    result, payload, stderr = _run_phase2(
        ['agent', 'add', 'helper:codex', '--role', 'agentroles.general', '--window', 'review', '--hidden', '--json'],
        cwd=project_root,
    )

    assert result == 0, stderr
    assert payload['window_name'] == 'review'
    loaded = load_project_config(project_root).config
    assert loaded.windows_explicit is True
    assert [(window.name, window.agent_names, window.layout_spec) for window in loaded.windows] == [
        ('main', ('main',), 'main:codex'),
        ('review', ('helper',), 'helper:codex'),
    ]
    plan = build_reload_dry_run_plan(current, loaded, project_id='proj-1', current_namespace=_namespace('proj-1'))
    assert plan['plan_class'] == 'add_window'
    assert {'add_agent', 'add_window'} == {item['op'] for item in plan['operations']}
    assert plan['namespace_patch_plan']['status'] == 'planned'
    assert [step['action'] for step in plan['namespace_patch_plan']['steps']] == [
        'create_window',
        'create_sidebar_pane',
        'create_agent_pane',
    ]
    assert plan['namespace_patch_plan']['steps'][-1]['window'] == 'review'
    assert plan['namespace_patch_plan']['steps'][-1]['agent'] == 'helper'


def test_agent_add_with_loop_node_places_agent_in_node_window(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = _project_with_agent_profiles(tmp_path, monkeypatch)

    result, payload, stderr = _run_phase2(
        [
            'agent',
            'add',
            'worker1:codex',
            '--role',
            'agentroles.general',
            '--loop-id',
            'round1',
            '--node-id',
            'node1',
            '--hidden',
            '--json',
        ],
        cwd=project_root,
    )

    assert result == 0, stderr
    assert payload['placement']['mode'] == 'execution_node'
    assert payload['resolved_window_name'] == 'node-round1-node1'
    assert payload['placement']['window_name'] == 'node-round1-node1'
    loaded = load_project_config(project_root).config
    assert [(window.name, window.agent_names, window.layout_spec) for window in loaded.windows] == [
        ('main', ('main',), 'main:codex'),
        ('node-round1-node1', ('worker1',), 'worker1:codex'),
    ]


def test_agent_add_second_loop_node_agent_appends_without_reordering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = _project_with_agent_profiles(tmp_path, monkeypatch)
    result, worker, stderr = _run_phase2(
        [
            'agent',
            'add',
            'worker1:codex',
            '--role',
            'agentroles.general',
            '--loop-id',
            'round1',
            '--node-id',
            'node1',
            '--hidden',
            '--json',
        ],
        cwd=project_root,
    )
    assert result == 0, stderr
    assert worker['created_sequence'] == 1
    after_worker = load_project_config(project_root).config

    result, checker, stderr = _run_phase2(
        [
            'agent',
            'add',
            'checker1:codex',
            '--role',
            'agentroles.general',
            '--loop-id',
            'round1',
            '--node-id',
            'node1',
            '--hidden',
            '--json',
        ],
        cwd=project_root,
    )

    assert result == 0, stderr
    assert checker['created_sequence'] == 2
    assert checker['resolved_window_name'] == 'node-round1-node1'
    loaded = load_project_config(project_root).config
    assert [(window.name, window.agent_names, window.layout_spec) for window in loaded.windows] == [
        ('main', ('main',), 'main:codex'),
        ('node-round1-node1', ('worker1', 'checker1'), 'worker1:codex; checker1:codex'),
    ]
    plan = build_reload_dry_run_plan(after_worker, loaded, project_id='proj-1', current_namespace=_namespace('proj-1'))
    assert plan['plan_class'] == 'add_agent'
    assert plan['namespace_patch_plan']['steps'] == [
        {
            'action': 'create_agent_pane',
            'window': 'node-round1-node1',
            'agent': 'checker1',
            'role': 'agent',
            'slot_key': 'checker1',
            'managed_by': 'ccbd',
            'anchor_agent': 'worker1',
            'reason': 'new agent appended to existing managed window',
        }
    ]


def test_agent_add_with_window_class_creates_class_window(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = _project_with_agent_profiles(tmp_path, monkeypatch)

    result, payload, stderr = _run_phase2(
        [
            'agent',
            'add',
            'planner2:codex',
            '--role',
            'agentroles.general',
            '--window-class',
            'plan-orchestrate',
            '--hidden',
            '--json',
        ],
        cwd=project_root,
    )

    assert result == 0, stderr
    assert payload['placement']['mode'] == 'window_class'
    assert payload['resolved_window_name'] == 'plan-orchestrate'
    assert payload['placement']['window_name'] == 'plan-orchestrate'
    loaded = load_project_config(project_root).config
    assert [(window.name, window.agent_names, window.layout_spec) for window in loaded.windows] == [
        ('main', ('main',), 'main:codex'),
        ('plan-orchestrate', ('planner2',), 'planner2:codex'),
    ]


def test_agent_add_with_window_class_overflows_to_next_class_window(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / 'repo-agent-lifecycle-overflow'
    role_store = tmp_path / 'roles'
    _write_installed_role(role_store, 'agentroles.general', default_agent_name='general')
    monkeypatch.setenv('AGENT_ROLES_STORE', str(role_store))
    _write(
        project_root / '.ccb' / 'ccb.config',
        """version = 2
entry_window = "main"

[windows]
main = "main:codex"
plan-orchestrate = "p1:codex, p2:codex, p3:codex, p4:codex, p5:codex, p6:codex"
""",
    )

    result, payload, stderr = _run_phase2(
        [
            'agent',
            'add',
            'planner2:codex',
            '--role',
            'agentroles.general',
            '--window-class',
            'plan-orchestrate',
            '--hidden',
            '--json',
        ],
        cwd=project_root,
    )

    assert result == 0, stderr
    assert payload['placement']['mode'] == 'window_class'
    assert payload['window_class'] == 'plan-orchestrate'
    assert payload['resolved_window_name'] == 'plan-orchestrate-2'
    assert payload['placement']['window_name'] == 'plan-orchestrate-2'
    loaded = load_project_config(project_root).config
    assert [(window.name, window.agent_names) for window in loaded.windows] == [
        ('main', ('main',)),
        ('plan-orchestrate', ('p1', 'p2', 'p3', 'p4', 'p5', 'p6')),
        ('plan-orchestrate-2', ('planner2',)),
    ]


def test_agent_add_while_mounted_applies_reload_and_reports_runtime_details(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = _project_with_agent_profiles(tmp_path, monkeypatch)
    monkeypatch.setattr(
        'cli.services.agent_lifecycle.ping_local_state',
        lambda _context: SimpleNamespace(mount_state='mounted', socket_connectable=True, reason=None),
    )
    monkeypatch.setattr(
        'cli.services.agent_lifecycle.reload_config',
        lambda _context, _command: {
            'status': 'published',
            'stage': 'publish_transaction',
            'plan_class': 'add_agent',
            'published_graph_version': 2,
            'namespace_patch': {
                'status': 'applied',
                'agent_panes': {'helper': '%3'},
            },
            'runtime_mount': {
                'status': 'mounted',
                'mounted_agents': ['helper'],
                'runtime_authority_written_agents': ['helper'],
            },
        },
    )

    result, payload, stderr = _run_phase2(
        ['agent', 'add', 'helper:codex', '--role', 'agentroles.general', '--hidden', '--json'],
        cwd=project_root,
    )

    assert result == 0, stderr
    assert payload['apply']['apply_status'] == 'applied'
    assert payload['apply']['reload_status'] == 'published'
    assert payload['apply']['plan_class'] == 'add_agent'
    assert payload['apply']['namespace_agent_panes'] == {'helper': '%3'}
    assert payload['apply']['runtime_mount_status'] == 'mounted'
    assert payload['apply']['runtime_authority_written_agents'] == ['helper']
    assert payload['pane_id'] == '%3'
    assert payload['applied']['status'] == 'applied'
    assert payload['applied']['window_name'] == 'main'
    assert payload['applied']['pane_id'] == '%3'
    assert payload['placement']['window_name'] == 'main'
    assert payload['placement']['pane_id'] == '%3'
    assert 'helper' in load_project_config(project_root).config.agents


def test_agent_add_while_mounted_reports_reload_failure_details_and_rolls_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = _project_with_agent_profiles(tmp_path, monkeypatch)
    monkeypatch.setattr(
        'cli.services.agent_lifecycle.ping_local_state',
        lambda _context: SimpleNamespace(mount_state='mounted', socket_connectable=True, reason=None),
    )
    monkeypatch.setattr(
        'cli.services.agent_lifecycle.reload_config',
        lambda _context, _command: {
            'status': 'failed',
            'stage': 'namespace_patch',
            'plan_class': 'add_agent',
            'diagnostics': {'reason': 'namespace_patch_failed'},
            'namespace_patch': {
                'status': 'failed',
                'diagnostics': {
                    'reason': 'namespace_patch_failed',
                    'error': "anchor pane missing for preserved agent 'main'",
                },
            },
        },
    )

    result, _payload, stderr = _run_phase2(
        ['agent', 'add', 'helper:codex', '--role', 'agentroles.general', '--hidden', '--json'],
        cwd=project_root,
    )

    assert result == 1
    assert 'stage=namespace_patch' in stderr
    assert 'plan_class=add_agent' in stderr
    assert 'reason=namespace_patch_failed' in stderr
    assert "anchor pane missing for preserved agent 'main'" in stderr
    assert 'helper' not in load_project_config(project_root).config.agents


def test_agent_remove_auto_parks_unknown_or_long_lived_dynamic_agent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = _project_with_agent_profiles(tmp_path, monkeypatch)
    result, payload, stderr = _run_phase2(
        ['agent', 'add', 'helper:codex', '--role', 'agentroles.general', '--hidden', '--json'],
        cwd=project_root,
    )
    assert result == 0, stderr
    assert payload['role_class'] == 'unknown'

    result, removed, stderr = _run_phase2(
        ['agent', 'remove', 'helper', '--policy', 'auto', '--json'],
        cwd=project_root,
    )

    assert result == 0, stderr
    assert removed['requested_policy'] == 'auto'
    assert removed['resolved_policy'] == 'park'
    assert removed['lifecycle_state'] == 'parked'
    loaded = load_project_config(project_root).config
    assert 'helper' in loaded.agents
    assert loaded.agents['helper'].dispatch_disabled is True


def test_agent_park_resume_projects_dispatch_disabled_overlay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = _project_with_agent_profiles(tmp_path, monkeypatch)
    result, _payload, stderr = _run_phase2(
        ['agent', 'add', 'helper:codex', '--role', 'agentroles.general', '--window', 'main', '--hidden', '--json'],
        cwd=project_root,
    )
    assert result == 0, stderr
    before_park = load_project_config(project_root).config
    assert before_park.agents['helper'].dispatch_disabled is False

    result, parked, stderr = _run_phase2(['agent', 'park', 'helper', '--json'], cwd=project_root)

    assert result == 0, stderr
    assert parked['lifecycle_state'] == 'parked'
    assert parked['dispatch_disabled'] is True
    after_park = load_project_config(project_root).config
    assert after_park.agents['helper'].dispatch_disabled is True
    park_plan = build_reload_dry_run_plan(before_park, after_park, project_id='proj-1', current_namespace=_namespace('proj-1'))
    assert park_plan['plan_class'] == 'view_only_change'
    assert park_plan['operations'] == [
        {
            'op': 'view_only_change',
            'agent': 'helper',
            'fields': ['dispatch_disabled'],
            'reason': 'existing agent dispatch availability changed without runtime replacement',
        }
    ]

    result, resumed, stderr = _run_phase2(['agent', 'resume', 'helper', '--hidden', '--json'], cwd=project_root)

    assert result == 0, stderr
    assert resumed['lifecycle_state'] == 'hidden'
    assert resumed['dispatch_disabled'] is False
    assert load_project_config(project_root).config.agents['helper'].dispatch_disabled is False


def test_agent_remove_unload_removes_dynamic_overlay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = _project_with_agent_profiles(tmp_path, monkeypatch)
    result, _payload, stderr = _run_phase2(
        ['agent', 'add', 'reviewer', '--profile', 'code_reviewer', '--hidden', '--json'],
        cwd=project_root,
    )
    assert result == 0, stderr

    result, removed, stderr = _run_phase2(
        ['agent', 'remove', 'reviewer', '--policy', 'unload', '--idle-only', '--json'],
        cwd=project_root,
    )

    assert result == 0, stderr
    assert removed['resolved_policy'] == 'unload'
    assert removed['lifecycle_state'] == 'unloaded'
    assert removed['apply']['apply_status'] == 'deferred_until_start'
    assert 'reviewer' not in load_project_config(project_root).config.agents


def test_agent_release_auto_unloads_short_lived_dynamic_agent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = _project_with_agent_profiles(tmp_path, monkeypatch)
    result, payload, stderr = _run_phase2(
        ['agent', 'add', 'reviewer', '--profile', 'code_reviewer', '--hidden', '--json'],
        cwd=project_root,
    )
    assert result == 0, stderr
    assert payload['role_class'] == 'short_lived_execution'

    result, released, stderr = _run_phase2(
        ['agent', 'release', 'reviewer', '--idle-only', '--json'],
        cwd=project_root,
    )

    assert result == 0, stderr
    assert released['action'] == 'release'
    assert released['requested_action'] == 'release'
    assert released['requested_policy'] == 'auto'
    assert released['resolved_policy'] == 'unload'
    assert released['lifecycle_state'] == 'unloaded'
    assert released['apply']['apply_status'] == 'deferred_until_start'
    assert 'reviewer' not in load_project_config(project_root).config.agents


def test_agent_remove_while_mounted_unloads_and_reports_runtime_details(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = _project_with_agent_profiles(tmp_path, monkeypatch)
    reload_results = [
        {
            'status': 'published',
            'stage': 'publish_transaction',
            'plan_class': 'add_agent',
            'published_graph_version': 2,
            'namespace_patch': {
                'status': 'applied',
                'agent_panes': {'helper': '%3'},
            },
            'runtime_mount': {
                'status': 'mounted',
                'mounted_agents': ['helper'],
                'runtime_authority_written_agents': ['helper'],
            },
        },
        {
            'status': 'published',
            'stage': 'publish_transaction',
            'plan_class': 'remove_agent',
            'published_graph_version': 3,
            'namespace_patch': {
                'status': 'applied',
                'removed_agents': {'helper': '%3'},
                'removed_panes': ['%3'],
            },
            'runtime_mount': {
                'status': 'unloaded',
                'unloaded_agents': ['helper'],
                'runtime_authority_stopped_agents': ['helper'],
            },
        },
    ]
    monkeypatch.setattr(
        'cli.services.agent_lifecycle.ping_local_state',
        lambda _context: SimpleNamespace(mount_state='mounted', socket_connectable=True, reason=None),
    )
    monkeypatch.setattr(
        'cli.services.agent_lifecycle.reload_config',
        lambda _context, _command: reload_results.pop(0),
    )

    result, added, stderr = _run_phase2(
        ['agent', 'add', 'helper:codex', '--role', 'agentroles.general', '--window', 'main', '--hidden', '--json'],
        cwd=project_root,
    )
    assert result == 0, stderr
    assert added['pane_id'] == '%3'
    assert 'helper' in load_project_config(project_root).config.agents

    result, removed, stderr = _run_phase2(
        ['agent', 'remove', 'helper', '--policy', 'unload', '--idle-only', '--json'],
        cwd=project_root,
    )

    assert result == 0, stderr
    assert removed['resolved_policy'] == 'unload'
    assert removed['lifecycle_state'] == 'unloaded'
    assert removed['apply']['apply_status'] == 'applied'
    assert removed['apply']['plan_class'] == 'remove_agent'
    assert removed['apply']['namespace_removed_agents'] == {'helper': '%3'}
    assert removed['apply']['namespace_removed_panes'] == ['%3']
    assert removed['apply']['runtime_mount_status'] == 'unloaded'
    assert removed['apply']['unloaded_agents'] == ['helper']
    assert removed['apply']['runtime_authority_stopped_agents'] == ['helper']
    assert removed['last_pane_id'] == '%3'
    assert removed['pane_id'] is None
    assert removed['placement']['last_pane_id'] == '%3'
    assert removed['placement']['pane_id'] is None
    assert removed['applied']['status'] == 'unloaded'
    assert removed['applied']['removed_pane_id'] == '%3'
    assert removed['applied']['window_name'] == 'main'
    assert removed['applied']['unloaded_agents'] == ['helper']
    assert 'helper' not in load_project_config(project_root).config.agents
    assert reload_results == []


def test_agent_park_while_mounted_publishes_config_only_change_without_losing_pane(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = _project_with_agent_profiles(tmp_path, monkeypatch)
    reload_results = [
        {
            'status': 'published',
            'stage': 'publish_transaction',
            'plan_class': 'add_agent',
            'published_graph_version': 2,
            'namespace_patch': {
                'status': 'applied',
                'agent_panes': {'helper': '%3'},
            },
            'runtime_mount': {
                'status': 'mounted',
                'mounted_agents': ['helper'],
                'runtime_authority_written_agents': ['helper'],
            },
        },
        {
            'status': 'published',
            'stage': 'publish_transaction',
            'plan_class': 'view_only_change',
            'published_graph_version': 3,
            'namespace_patch': {'status': 'applied'},
            'runtime_mount': {'status': 'noop'},
        },
    ]
    monkeypatch.setattr(
        'cli.services.agent_lifecycle.ping_local_state',
        lambda _context: SimpleNamespace(mount_state='mounted', socket_connectable=True, reason=None),
    )
    monkeypatch.setattr(
        'cli.services.agent_lifecycle.reload_config',
        lambda _context, _command: reload_results.pop(0),
    )

    result, added, stderr = _run_phase2(
        ['agent', 'add', 'helper:codex', '--role', 'agentroles.general', '--window', 'main', '--hidden', '--json'],
        cwd=project_root,
    )
    assert result == 0, stderr
    assert added['pane_id'] == '%3'

    result, parked, stderr = _run_phase2(['agent', 'park', 'helper', '--json'], cwd=project_root)

    assert result == 0, stderr
    assert parked['lifecycle_state'] == 'parked'
    assert parked['dispatch_disabled'] is True
    assert parked['apply']['apply_status'] == 'applied'
    assert parked['apply']['plan_class'] == 'view_only_change'
    assert parked['pane_id'] == '%3'
    assert parked['placement']['pane_id'] == '%3'
    assert parked['applied']['status'] == 'transitioned'
    assert parked['applied']['pane_id'] == '%3'
    assert parked['applied']['dispatch_disabled'] is True
    assert reload_results == []


def test_agent_remove_kill_requires_force_and_reason(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = _project_with_agent_profiles(tmp_path, monkeypatch)
    result, _payload, stderr = _run_phase2(
        ['agent', 'add', 'helper:codex', '--role', 'agentroles.general', '--hidden', '--json'],
        cwd=project_root,
    )
    assert result == 0, stderr

    result, _payload, stderr = _run_phase2(
        ['agent', 'remove', 'helper', '--policy', 'kill', '--json'],
        cwd=project_root,
    )

    assert result == 1
    assert 'requires --force and --reason' in stderr


def test_agent_add_requires_role_or_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = _project_with_agent_profiles(tmp_path, monkeypatch)

    result, _payload, stderr = _run_phase2(
        ['agent', 'add', 'helper:codex', '--hidden', '--json'],
        cwd=project_root,
    )

    assert result == 1
    assert 'requires --role or --profile' in stderr
