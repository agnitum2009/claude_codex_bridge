from __future__ import annotations

from io import StringIO
import json
from pathlib import Path

from cli.models import ParsedLayoutCommand
from cli.parser import CliParser
from cli.phase2 import maybe_handle_phase2
from storage.paths import PathLayout


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding='utf-8')


def _run_phase2(argv: list[str], *, cwd: Path) -> tuple[int, dict[str, object], str]:
    stdout = StringIO()
    stderr = StringIO()
    result = maybe_handle_phase2(argv, cwd=cwd, stdout=stdout, stderr=stderr)
    payload = json.loads(stdout.getvalue()) if stdout.getvalue().strip() else {}
    return result, payload, stderr.getvalue()


def test_layout_parser_supports_status_without_pane_count() -> None:
    assert CliParser().parse(['layout', 'status', '--json']) == ParsedLayoutCommand(
        project=None,
        action='status',
        json_output=True,
    )


def test_layout_status_reports_effective_windows_and_dynamic_agent_overlay(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-layout-status'
    _write(
        project_root / '.ccb' / 'ccb.config',
        """version = 2
entry_window = "main"

[windows]
main = "frontdesk:codex"
plan-orchestrate = "planner:codex"
""",
    )
    layout = PathLayout(project_root)
    _write_json(
        layout.runtime_state_root / 'runtime' / 'agents' / 'helper' / 'lifecycle.json',
        {
            'schema_version': 1,
            'record_type': 'ccb_dynamic_agent_lifecycle',
            'agent_lifecycle_status': 'active',
            'agent': 'helper',
            'role': 'agentroles.worker',
            'provider': 'codex',
            'workspace_mode': 'inplace',
            'target': '.',
            'lifecycle_state': 'hidden',
            'visibility_state': 'hidden',
            'dispatch_disabled': False,
            'window_name': 'plan-orchestrate',
            'placement': {
                'mode': 'window',
                'window_name': 'plan-orchestrate',
                'layout_policy': 'append-or-create-window',
                'pane_id': '%9',
            },
            'pane_id': '%9',
        },
    )

    result, payload, stderr = _run_phase2(['layout', 'status', '--json'], cwd=project_root)

    assert result == 0, stderr
    assert payload['layout_status'] == 'ok'
    assert payload['action'] == 'status'
    assert payload['windows_explicit'] is True
    assert payload['window_count'] == 2
    assert payload['pane_count'] == 3
    windows = {window['name']: window for window in payload['windows']}
    assert windows['main']['agent_names'] == ['frontdesk']
    assert windows['plan-orchestrate']['agent_names'] == ['planner', 'helper']
    helper = [agent for agent in windows['plan-orchestrate']['agents'] if agent['agent'] == 'helper'][0]
    assert helper['source'] == 'dynamic'
    assert helper['lifecycle_state'] == 'hidden'
    assert helper['pane_id'] == '%9'
    assert helper['runtime_state'] == 'missing'
    assert payload['namespace']['status'] == 'unmounted'


def test_layout_status_marks_loop_capacity_agents_as_loop_source(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-layout-status-loop'
    _write(
        project_root / '.ccb' / 'ccb.config',
        """version = 2
entry_window = "main"

[windows]
main = "orchestrator:fake"
""",
    )
    layout = PathLayout(project_root)
    _write_json(
        layout.runtime_state_root / 'runtime' / 'loops' / 'round1' / 'capacity.json',
        {
            'schema_version': 1,
            'record_type': 'ccb_loop_capacity_state',
            'loop_capacity_status': 'ensured',
            'loop_id': 'round1',
            'agents': [
                {
                    'name': 'loop-round1-worker-1',
                    'profile': 'worker',
                    'role': 'agentroles.coder',
                    'provider': 'fake',
                    'workspace_mode': 'inplace',
                    'loop_id': 'round1',
                    'node_id': 'node1',
                    'window_name': 'node-round1-node1',
                    'placement': {
                        'mode': 'execution_node',
                        'loop_id': 'round1',
                        'node_id': 'node1',
                        'window_name': 'node-round1-node1',
                    },
                    'state': 'planned',
                },
                {
                    'name': 'loop-round1-code_reviewer-1',
                    'profile': 'code_reviewer',
                    'role': 'agentroles.code_reviewer',
                    'provider': 'fake',
                    'workspace_mode': 'inplace',
                    'loop_id': 'round1',
                    'node_id': 'node1',
                    'window_name': 'node-round1-node1',
                    'placement': {
                        'mode': 'execution_node',
                        'loop_id': 'round1',
                        'node_id': 'node1',
                        'window_name': 'node-round1-node1',
                    },
                    'state': 'planned',
                },
            ],
        },
    )

    result, payload, stderr = _run_phase2(['layout', 'status', '--json'], cwd=project_root)

    assert result == 0, stderr
    assert payload['loop_agent_count'] == 2
    windows = {window['name']: window for window in payload['windows']}
    node_agents = windows['node-round1-node1']['agents']
    assert [(agent['agent'], agent['source'], agent['loop_id'], agent['node_id']) for agent in node_agents] == [
        ('loop-round1-worker-1', 'loop', 'round1', 'node1'),
        ('loop-round1-code_reviewer-1', 'loop', 'round1', 'node1'),
    ]
    assert node_agents[0]['profile'] == 'worker'
    assert node_agents[1]['profile'] == 'code_reviewer'


def test_layout_status_skips_tmux_observation_for_unmounted_namespace_state(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo-layout-status-unmounted'
    _write(
        project_root / '.ccb' / 'ccb.config',
        """version = 2
entry_window = "main"

[windows]
main = "main:fake"
""",
    )
    layout = PathLayout(project_root)
    _write_json(
        layout.ccbd_state_path,
        {
            'schema_version': 2,
            'record_type': 'ccbd_project_namespace_state',
            'project_id': layout.project_id,
            'namespace_epoch': 1,
            'tmux_socket_path': str(layout.ccbd_tmux_socket_path),
            'tmux_session_name': layout.ccbd_tmux_session_name,
            'layout_version': 3,
            'layout_signature': 'stale-signature',
            'workspace_window_name': 'main',
            'workspace_window_id': '@0',
            'workspace_epoch': 1,
            'ui_attachable': False,
        },
    )

    result, payload, stderr = _run_phase2(['layout', 'status', '--json'], cwd=project_root)

    assert result == 0, stderr
    assert payload['namespace']['state_load_status'] == 'ok'
    assert payload['namespace']['status'] == 'unmounted'
    assert payload['observed'] == {
        'observe_status': 'skipped',
        'reason': 'namespace_unmounted',
    }
