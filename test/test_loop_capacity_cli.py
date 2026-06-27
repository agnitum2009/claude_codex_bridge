from __future__ import annotations

from io import StringIO
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from agents.config_loader import load_project_config
from ccbd.reload_plan import build_reload_dry_run_plan
from cli.context import CliContextBuilder
from cli.models import ParsedLoopCapacityCommand, ParsedLoopRunOnceCommand, ParsedLoopRunnerCommand
from cli.parser import CliParser
from cli.phase2 import maybe_handle_phase2
from cli.phase2_runtime.handlers_ops import handle_loop_run_once
from cli.services.ask_runtime import AskSummary
from cli.services.loop_run_once import loop_run_once
from cli.services.loop_runner import loop_runner_once
from cli.services.plan_tasks import plan_task
from cli.services.watch import WatchEventBatch
import cli.services.loop_capacity as loop_capacity_module


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


def _project_with_loop_capacity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    project_root = tmp_path / 'repo-loop-capacity'
    role_store = tmp_path / 'roles'
    _write_installed_role(role_store, 'agentroles.coder', default_agent_name='coder')
    _write_installed_role(role_store, 'agentroles.code_reviewer', default_agent_name='code_reviewer')
    monkeypatch.setenv('AGENT_ROLES_STORE', str(role_store))
    _write(
        project_root / '.ccb' / 'ccb.config',
        """cmd; orchestrator:codex

[loop.capacity]
enabled = true
max_nodes = 3
default_lifetime = "current_round"
name_template = "loop-{loop_id}-{profile}-{index}"
reuse = "prefer_idle"

[loop.role_profiles.worker]
role = "agentroles.coder"
provider = "codex"
thinking = "high"
workspace_mode = "git-worktree"
workspace_group = "worker_pool"
max_instances = 2
reuse = "prefer_idle"

[loop.role_profiles.code_reviewer]
role = "agentroles.code_reviewer"
provider = "codex"
thinking = "medium"
workspace_mode = "git-worktree"
workspace_group = "review_pool"
max_instances = 1
""",
    )
    return project_root


def _add_ready_plan_task(project_root: Path, *, task_id: str = 'task-001') -> None:
    plan_root = project_root / 'docs' / 'plantree' / 'plans' / 'demo-plan'
    task_root = plan_root / 'tasks' / task_id
    _write(plan_root / 'README.md', '# Demo Plan\n')
    artifacts: dict[str, dict[str, object]] = {}
    for kind, filename, text in (
        ('requirements', 'requirements.md', 'requirements text\n'),
        ('acceptance', 'acceptance-criteria.md', 'acceptance text\n'),
        ('verification', 'verification-contract.md', 'verification text\n'),
        ('handoff', 'handoff.md', 'handoff text\n'),
        ('review', 'review.md', 'review text\n'),
    ):
        path = task_root / filename
        _write(path, text)
        artifacts[kind] = {
            'kind': kind,
            'path': str(path.relative_to(project_root)),
            'source_path': str(path.relative_to(project_root)),
            'sha256': 'test',
            'bytes': len(text.encode('utf-8')),
            'imported_at': '2026-06-27T00:00:00Z',
        }
    record = {
        'task_id': task_id,
        'title': 'Task id bridge',
        'plan_slug': 'demo-plan',
        'plan_root': 'docs/plantree/plans/demo-plan',
        'status': 'ready',
        'current_loop': None,
        'owner': 'loop_runner',
        'created_at': '2026-06-27T00:00:00Z',
        'updated_at': '2026-06-27T00:00:00Z',
        'task_root': str(task_root.relative_to(project_root)),
        'artifacts': artifacts,
    }
    _write(
        plan_root / 'tasks' / 'index.json',
        json.dumps(
            {
                'schema_version': 1,
                'record_type': 'ccb_plan_task_index',
                'plan_slug': 'demo-plan',
                'plan_root': str(plan_root),
                'updated_at': '2026-06-27T00:00:00Z',
                'tasks': [record],
            },
            ensure_ascii=False,
            indent=2,
        )
        + '\n',
    )


def _add_plan_task_record(
    project_root: Path,
    *,
    task_id: str,
    status: str,
    artifacts: dict[str, dict[str, object]] | None = None,
    current_loop: str | None = None,
) -> None:
    plan_root = project_root / 'docs' / 'plantree' / 'plans' / 'demo-plan'
    task_root = plan_root / 'tasks' / task_id
    _write(plan_root / 'README.md', '# Demo Plan\n')
    record = {
        'task_id': task_id,
        'title': f'{status} task',
        'plan_slug': 'demo-plan',
        'plan_root': 'docs/plantree/plans/demo-plan',
        'status': status,
        'current_loop': current_loop,
        'owner': 'planner' if status in {'draft', 'partial', 'replan_required'} else 'frontdesk',
        'created_at': '2026-06-27T00:00:00Z',
        'updated_at': '2026-06-27T00:00:00Z',
        'task_root': str(task_root.relative_to(project_root)),
        'artifacts': artifacts or {},
    }
    index_path = plan_root / 'tasks' / 'index.json'
    try:
        index = json.loads(index_path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        index = {
            'schema_version': 1,
            'record_type': 'ccb_plan_task_index',
            'plan_slug': 'demo-plan',
            'plan_root': str(plan_root),
            'updated_at': '2026-06-27T00:00:00Z',
            'tasks': [],
        }
    index['tasks'].append(record)
    _write(index_path, json.dumps(index, ensure_ascii=False, indent=2) + '\n')


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


def test_loop_capacity_parser_supports_scriptable_json_commands() -> None:
    parser = CliParser()

    assert parser.parse(
        [
            'loop',
            'capacity',
            'ensure',
            '--loop-id',
            'round1',
            '--profile',
            'worker=2',
            '--profile',
            'code_reviewer',
            '--json',
        ]
    ) == ParsedLoopCapacityCommand(
        project=None,
        action='ensure',
        loop_id='round1',
        profile_counts=(('worker', 2), ('code_reviewer', 1)),
        json_output=True,
    )
    assert parser.parse(
        ['loop', 'capacity', 'status', '--loop-id', 'round1', '--json']
    ) == ParsedLoopCapacityCommand(project=None, action='status', loop_id='round1', json_output=True)
    assert parser.parse(
        ['loop', 'capacity', 'release', '--loop-id', 'round1', '--idle-only', '--json']
    ) == ParsedLoopCapacityCommand(project=None, action='release', loop_id='round1', idle_only=True, json_output=True)
    assert parser.parse(
        ['loop', 'capacity', 'release', '--loop-id', 'round1', '--policy', 'auto', '--json']
    ) == ParsedLoopCapacityCommand(project=None, action='release', loop_id='round1', policy='auto', json_output=True)
    assert parser.parse(
        [
            'loop',
            'run-once',
            '--loop-id',
            'round1',
            '--task',
            'ship the slice',
            '--worker-profile',
            'worker',
            '--reviewer-profile',
            'code_reviewer',
            '--orchestrator',
            'orchestrator',
            '--round-checker',
            'round_checker',
            '--timeout',
            '5',
            '--json',
        ]
    ) == ParsedLoopRunOnceCommand(
        project=None,
        loop_id='round1',
        task='ship the slice',
        worker_profile='worker',
        reviewer_profile='code_reviewer',
        orchestrator='orchestrator',
        round_checker='round_checker',
        timeout_s=5.0,
        json_output=True,
    )
    assert parser.parse(
        ['loop', 'run-once', '--task-id', 'task-001', '--json']
    ) == ParsedLoopRunOnceCommand(project=None, task_id='task-001', json_output=True)
    assert parser.parse(
        ['loop', 'runner', '--once', '--timeout', '5', '--json']
    ) == ParsedLoopRunnerCommand(project=None, once=True, timeout_s=5.0, json_output=True)


def test_loop_capacity_ensure_places_worker_and_reviewer_in_execution_node_window(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = _project_with_loop_capacity(tmp_path, monkeypatch)
    _write(
        project_root / '.ccb' / 'ccb.config',
        """version = 2
entry_window = "main"

[windows]
main = "orchestrator:codex"

[loop.capacity]
enabled = true
max_nodes = 3
default_lifetime = "current_round"
name_template = "loop-{loop_id}-{profile}-{index}"
reuse = "prefer_idle"

[loop.role_profiles.worker]
role = "agentroles.coder"
provider = "codex"
thinking = "high"
workspace_mode = "git-worktree"
workspace_group = "worker_pool"
max_instances = 2
reuse = "prefer_idle"

[loop.role_profiles.code_reviewer]
role = "agentroles.code_reviewer"
provider = "codex"
thinking = "medium"
workspace_mode = "git-worktree"
workspace_group = "review_pool"
max_instances = 1
""",
    )
    current = load_project_config(project_root, include_loop_overlays=False).config

    result, payload, stderr = _run_phase2(
        [
            'loop',
            'capacity',
            'ensure',
            '--loop-id',
            'round1',
            '--profile',
            'worker=1',
            '--profile',
            'code_reviewer=1',
            '--json',
        ],
        cwd=project_root,
    )

    assert result == 0, stderr
    assert [(agent['name'], agent['node_id'], agent['placement']['window_name']) for agent in payload['agents']] == [
        ('loop-round1-worker-1', 'node1', 'node-round1-node1'),
        ('loop-round1-code_reviewer-1', 'node1', 'node-round1-node1'),
    ]
    loaded = load_project_config(project_root).config
    assert [(window.name, window.agent_names, window.layout_spec) for window in loaded.windows] == [
        ('main', ('orchestrator',), 'orchestrator:codex'),
        (
            'node-round1-node1',
            ('loop-round1-worker-1', 'loop-round1-code_reviewer-1'),
            'loop-round1-worker-1:codex(worktree); loop-round1-code_reviewer-1:codex(worktree)',
        ),
    ]
    plan = build_reload_dry_run_plan(current, loaded, project_id='proj-1', current_namespace=_namespace('proj-1'))
    assert plan['plan_class'] == 'add_window'
    assert [step['action'] for step in plan['namespace_patch_plan']['steps']] == [
        'create_window',
        'create_sidebar_pane',
        'create_agent_pane',
        'create_agent_pane',
    ]


def test_loop_capacity_ensure_places_multiple_nodes_in_separate_windows_and_release_cleans_layout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / 'repo-loop-capacity-explicit-multi-node'
    role_store = tmp_path / 'roles'
    _write_installed_role(role_store, 'agentroles.coder', default_agent_name='coder')
    _write_installed_role(role_store, 'agentroles.code_reviewer', default_agent_name='code_reviewer')
    monkeypatch.setenv('AGENT_ROLES_STORE', str(role_store))
    _write(
        project_root / '.ccb' / 'ccb.config',
        """version = 2
entry_window = "main"

[windows]
main = "orchestrator:codex"

[loop.capacity]
enabled = true
max_nodes = 4
default_lifetime = "current_round"
name_template = "loop-{loop_id}-{profile}-{index}"
reuse = "prefer_idle"

[loop.role_profiles.worker]
role = "agentroles.coder"
provider = "codex"
thinking = "high"
workspace_mode = "git-worktree"
workspace_group = "worker_pool"
max_instances = 2
reuse = "prefer_idle"

[loop.role_profiles.code_reviewer]
role = "agentroles.code_reviewer"
provider = "codex"
thinking = "medium"
workspace_mode = "git-worktree"
workspace_group = "review_pool"
max_instances = 2
""",
    )
    current = load_project_config(project_root, include_loop_overlays=False).config

    result, payload, stderr = _run_phase2(
        [
            'loop',
            'capacity',
            'ensure',
            '--loop-id',
            'round2',
            '--profile',
            'worker=2',
            '--profile',
            'code_reviewer=2',
            '--json',
        ],
        cwd=project_root,
    )

    assert result == 0, stderr
    assert [(agent['name'], agent['node_id'], agent['created_sequence']) for agent in payload['agents']] == [
        ('loop-round2-worker-1', 'node1', 1),
        ('loop-round2-worker-2', 'node2', 2),
        ('loop-round2-code_reviewer-1', 'node1', 3),
        ('loop-round2-code_reviewer-2', 'node2', 4),
    ]
    loaded = load_project_config(project_root).config
    assert [(window.name, window.agent_names) for window in loaded.windows] == [
        ('main', ('orchestrator',)),
        ('node-round2-node1', ('loop-round2-worker-1', 'loop-round2-code_reviewer-1')),
        ('node-round2-node2', ('loop-round2-worker-2', 'loop-round2-code_reviewer-2')),
    ]
    plan = build_reload_dry_run_plan(current, loaded, project_id='proj-1', current_namespace=_namespace('proj-1'))
    assert plan['plan_class'] == 'add_window'
    assert [step['action'] for step in plan['namespace_patch_plan']['steps']] == [
        'create_window',
        'create_sidebar_pane',
        'create_agent_pane',
        'create_agent_pane',
        'create_window',
        'create_sidebar_pane',
        'create_agent_pane',
        'create_agent_pane',
    ]

    result, status_payload, stderr = _run_phase2(['layout', 'status', '--json'], cwd=project_root)

    assert result == 0, stderr
    assert status_payload['loop_agent_count'] == 4
    windows = {window['name']: window for window in status_payload['windows']}
    assert windows['node-round2-node1']['agent_names'] == [
        'loop-round2-worker-1',
        'loop-round2-code_reviewer-1',
    ]
    assert windows['node-round2-node2']['agent_names'] == [
        'loop-round2-worker-2',
        'loop-round2-code_reviewer-2',
    ]
    assert {agent['source'] for agent in windows['node-round2-node1']['agents']} == {'loop'}
    assert {agent['source'] for agent in windows['node-round2-node2']['agents']} == {'loop'}

    result, release_payload, stderr = _run_phase2(
        ['loop', 'capacity', 'release', '--loop-id', 'round2', '--idle-only', '--json'],
        cwd=project_root,
    )

    assert result == 0, stderr
    assert release_payload['released_count'] == 4
    released = load_project_config(project_root).config
    assert [(window.name, window.agent_names) for window in released.windows] == [
        ('main', ('orchestrator',)),
    ]
    result, released_status, stderr = _run_phase2(['layout', 'status', '--json'], cwd=project_root)
    assert result == 0, stderr
    assert released_status['loop_agent_count'] == 0
    assert [(window['name'], window['agent_names']) for window in released_status['windows']] == [
        ('main', ['orchestrator']),
    ]


def test_loop_run_once_writes_round_artifacts_and_releases_capacity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = _project_with_loop_capacity(tmp_path, monkeypatch)
    command = ParsedLoopRunOnceCommand(project=None, loop_id='round1', task='ship the slice', timeout_s=7.0)
    context = CliContextBuilder().build(command, cwd=project_root, bootstrap_if_missing=False)
    calls: list[tuple[str, object]] = []

    def fake_loop_capacity(_context, capacity_command):
        calls.append(('capacity', capacity_command.action))
        if capacity_command.action == 'ensure':
            assert capacity_command.profile_counts == (('worker', 1), ('code_reviewer', 1))
            return {
                'loop_capacity_status': 'ensured',
                'loop_id': capacity_command.loop_id,
                'project_id': context.project.project_id,
                'agent_count': 2,
                'agents': [
                    {'name': 'loop-round1-worker-1', 'profile': 'worker', 'state': 'planned'},
                    {'name': 'loop-round1-code_reviewer-1', 'profile': 'code_reviewer', 'state': 'planned'},
                ],
                'apply': {'apply_status': 'applied', 'action': 'add_agent'},
            }
        if capacity_command.action == 'release':
            assert capacity_command.policy == 'auto'
            assert capacity_command.idle_only is False
            return {
                'loop_capacity_status': 'released',
                'loop_id': capacity_command.loop_id,
                'project_id': context.project.project_id,
                'agent_count': 2,
                'released_count': 2,
                'retained_count': 0,
                'release_policy': 'auto',
                'idle_only': True,
                'agents': [
                    {'name': 'loop-round1-worker-1', 'profile': 'worker', 'state': 'released'},
                    {'name': 'loop-round1-code_reviewer-1', 'profile': 'code_reviewer', 'state': 'released'},
                ],
                'apply': {'apply_status': 'applied', 'action': 'remove_agent'},
            }
        raise AssertionError(f'unexpected capacity action {capacity_command.action}')

    def fake_submit_ask(_context, ask_command):
        calls.append(('ask', ask_command.target))
        if ask_command.target == 'round_checker':
            assert ask_command.sender == 'system'
        return AskSummary(
            project_id=context.project.project_id,
            submission_id=f'sub_{ask_command.target}',
            jobs=(
                {
                    'job_id': f'job_{ask_command.target}',
                    'agent_name': ask_command.target,
                    'status': 'accepted',
                },
            ),
        )

    def fake_watch_ask_job(_context, job_id, _out, *, timeout, emit_output):
        calls.append(('watch', job_id))
        assert timeout == 7.0
        assert emit_output is False
        target = str(job_id).removeprefix('job_')
        return WatchEventBatch(
            target=job_id,
            job_id=job_id,
            agent_name=target,
            target_kind='job',
            target_name=job_id,
            provider='codex',
            provider_instance=None,
            cursor=1,
            generation=1,
            terminal=True,
            status='completed',
            reply=f'reply from {target}',
            events=(),
        )

    payload = loop_run_once(
        context,
        command,
        services=SimpleNamespace(
            loop_capacity=fake_loop_capacity,
            submit_ask=fake_submit_ask,
            watch_ask_job=fake_watch_ask_job,
        ),
    )

    assert payload['loop_run_status'] == 'ok'
    assert payload['agents'] == {
        'worker': 'loop-round1-worker-1',
        'reviewer': 'loop-round1-code_reviewer-1',
        'orchestrator': 'orchestrator',
        'round_checker': 'round_checker',
    }
    assert calls == [
        ('capacity', 'ensure'),
        ('ask', 'loop-round1-worker-1'),
        ('watch', 'job_loop-round1-worker-1'),
        ('ask', 'loop-round1-code_reviewer-1'),
        ('watch', 'job_loop-round1-code_reviewer-1'),
        ('ask', 'orchestrator'),
        ('watch', 'job_orchestrator'),
        ('ask', 'round_checker'),
        ('watch', 'job_round_checker'),
        ('capacity', 'release'),
    ]

    loop_dir = project_root / '.ccb' / 'runtime' / 'loops' / 'round1'
    round_payload = json.loads((loop_dir / 'round.json').read_text(encoding='utf-8'))
    asks = [json.loads(line) for line in (loop_dir / 'asks.jsonl').read_text(encoding='utf-8').splitlines()]
    events = [json.loads(line) for line in (loop_dir / 'events.jsonl').read_text(encoding='utf-8').splitlines()]
    assert round_payload['loop_run_status'] == 'ok'
    assert round_payload['capacity']['release']['release_policy'] == 'auto'
    assert round_payload['capacity']['release']['idle_only'] is True
    assert [ask['purpose'] for ask in asks] == ['worker', 'reviewer', 'aggregate', 'round_checker']
    assert [event['kind'] for event in events] == [
        'loop_run_started',
        'ask_terminal',
        'ask_terminal',
        'ask_terminal',
        'ask_terminal',
        'loop_run_finished',
    ]
    assert (loop_dir / 'breadcrumb.md').read_text(encoding='utf-8').startswith('Loop: round1\n')
    assert (loop_dir / 'artifacts' / 'worker-reply.md').read_text(encoding='utf-8') == 'reply from loop-round1-worker-1'
    assert (loop_dir / 'artifacts' / 'reviewer-reply.md').read_text(encoding='utf-8') == 'reply from loop-round1-code_reviewer-1'
    assert (loop_dir / 'artifacts' / 'aggregate-reply.md').read_text(encoding='utf-8') == 'reply from orchestrator'
    assert (loop_dir / 'artifacts' / 'round_checker-reply.md').read_text(encoding='utf-8') == 'reply from round_checker'


def test_loop_run_once_task_id_binds_ready_task_and_reads_handoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = _project_with_loop_capacity(tmp_path, monkeypatch)
    _add_ready_plan_task(project_root, task_id='task-bridge')
    command = ParsedLoopRunOnceCommand(project=None, loop_id='loop-a', task_id='task-bridge', timeout_s=7.0)
    context = CliContextBuilder().build(command, cwd=project_root, bootstrap_if_missing=False)
    worker_messages: list[str] = []

    def fake_loop_capacity(_context, capacity_command):
        if capacity_command.action == 'ensure':
            return {
                'loop_capacity_status': 'ensured',
                'loop_id': capacity_command.loop_id,
                'project_id': context.project.project_id,
                'agent_count': 2,
                'agents': [
                    {'name': 'loop-loop-a-worker-1', 'profile': 'worker', 'state': 'planned'},
                    {'name': 'loop-loop-a-code_reviewer-1', 'profile': 'code_reviewer', 'state': 'planned'},
                ],
                'apply': {'apply_status': 'applied', 'action': 'add_agent'},
            }
        if capacity_command.action == 'release':
            return {
                'loop_capacity_status': 'released',
                'loop_id': capacity_command.loop_id,
                'project_id': context.project.project_id,
                'agent_count': 2,
                'released_count': 2,
                'retained_count': 0,
                'release_policy': 'auto',
                'idle_only': True,
                'agents': [],
                'apply': {'apply_status': 'applied', 'action': 'remove_agent'},
            }
        raise AssertionError(f'unexpected capacity action {capacity_command.action}')

    def fake_submit_ask(_context, ask_command):
        if ask_command.target == 'loop-loop-a-worker-1':
            worker_messages.append(ask_command.message)
        return AskSummary(
            project_id=context.project.project_id,
            submission_id=f'sub_{ask_command.target}',
            jobs=(
                {
                    'job_id': f'job_{ask_command.target}',
                    'agent_name': ask_command.target,
                    'status': 'accepted',
                },
            ),
        )

    def fake_watch_ask_job(_context, job_id, _out, *, timeout, emit_output):
        target = str(job_id).removeprefix('job_')
        return WatchEventBatch(
            target=job_id,
            job_id=job_id,
            agent_name=target,
            target_kind='job',
            target_name=job_id,
            provider='codex',
            provider_instance=None,
            cursor=1,
            generation=1,
            terminal=True,
            status='completed',
            reply='round result: pass' if target == 'round_checker' else f'reply from {target}',
            events=(),
        )

    payload = loop_run_once(
        context,
        command,
        services=SimpleNamespace(
            loop_capacity=fake_loop_capacity,
            submit_ask=fake_submit_ask,
            watch_ask_job=fake_watch_ask_job,
        ),
    )

    assert payload['loop_run_status'] == 'ok'
    assert payload['task_id'] == 'task-bridge'
    assert worker_messages
    assert 'Handoff:\nhandoff text' in worker_messages[0]
    shown = plan_task(context, SimpleNamespace(action='task-show', task_id='task-bridge'))
    assert shown['task']['status'] == 'running'
    assert shown['task']['current_loop'] == 'loop-a'
    breadcrumb = (project_root / '.ccb' / 'runtime' / 'loops' / 'loop-a' / 'breadcrumb.md').read_text(encoding='utf-8')
    assert 'Task: task-bridge\n' in breadcrumb


def test_loop_runner_once_binds_runs_imports_and_stops_after_one_task(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = _project_with_loop_capacity(tmp_path, monkeypatch)
    _add_ready_plan_task(project_root, task_id='task-runner')
    command = ParsedLoopRunnerCommand(project=None, once=True, timeout_s=11.0, json_output=True)
    context = CliContextBuilder().build(command, cwd=project_root, bootstrap_if_missing=False)
    seen: dict[str, object] = {}

    def fake_loop_run_once(_context, run_command, _services):
        seen['task_id'] = run_command.task_id
        seen['timeout_s'] = run_command.timeout_s
        loop_dir = project_root / '.ccb' / 'runtime' / 'loops' / run_command.loop_id
        loop_dir.mkdir(parents=True, exist_ok=True)
        round_path = loop_dir / 'round.json'
        payload = {
            'schema_version': 1,
            'record_type': 'ccb_loop_run_once_round',
            'loop_run_status': 'ok',
            'loop_id': run_command.loop_id,
            'task_id': run_command.task_id,
            'round_checker': {'job_id': 'job_round_checker', 'reply': 'round result: pass\nverified\n'},
            'paths': {'round': str(round_path)},
        }
        _write(round_path, json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
        return payload

    payload = loop_runner_once(
        context,
        command,
        services=SimpleNamespace(loop_run_once=fake_loop_run_once, plan_task=plan_task),
    )

    assert payload['loop_runner_status'] == 'ok'
    assert payload['action'] == 'ran_one_round'
    assert payload['task_id'] == 'task-runner'
    assert payload['round_result'] == 'pass'
    assert payload['round_result_source'] == 'round_checker_reply'
    assert payload['task_status'] == 'done'
    assert payload['next_activation'] == 'stop'
    assert seen == {'task_id': 'task-runner', 'timeout_s': 11.0}
    shown = plan_task(context, SimpleNamespace(action='task-show', task_id='task-runner'))
    assert shown['task']['status'] == 'done'
    assert shown['task']['current_loop'] is None
    assert shown['task']['artifacts']['round_pass']['round_result'] == 'pass'
    assert shown['task']['artifacts']['round_pass']['actor'] == {
        'source': 'loop_runner',
        'actor': 'loop_runner',
        'job_id': 'job_round_checker',
    }


def test_loop_runner_once_does_not_infer_pass_without_round_checker_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = _project_with_loop_capacity(tmp_path, monkeypatch)
    _add_ready_plan_task(project_root, task_id='task-runner')
    command = ParsedLoopRunnerCommand(project=None, once=True, timeout_s=11.0, json_output=True)
    context = CliContextBuilder().build(command, cwd=project_root, bootstrap_if_missing=False)

    def fake_loop_run_once(_context, run_command, _services):
        loop_dir = project_root / '.ccb' / 'runtime' / 'loops' / run_command.loop_id
        loop_dir.mkdir(parents=True, exist_ok=True)
        round_path = loop_dir / 'round.json'
        payload = {
            'schema_version': 1,
            'record_type': 'ccb_loop_run_once_round',
            'loop_run_status': 'ok',
            'loop_id': run_command.loop_id,
            'task_id': run_command.task_id,
            'round_checker': {'reply': 'round checker completed without a machine result line\n'},
            'paths': {'round': str(round_path)},
        }
        _write(round_path, json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
        return payload

    payload = loop_runner_once(
        context,
        command,
        services=SimpleNamespace(loop_run_once=fake_loop_run_once, plan_task=plan_task),
    )

    assert payload['loop_runner_status'] == 'ok'
    assert payload['round_result'] == 'blocked'
    assert payload['round_result_source'] == 'missing_round_checker_result'
    assert payload['task_status'] == 'blocked'
    shown = plan_task(context, SimpleNamespace(action='task-show', task_id='task-runner'))
    assert shown['task']['status'] == 'blocked'
    assert shown['task']['artifacts']['round_blocker']['round_result'] == 'blocked'


def test_loop_runner_once_returns_idle_when_no_ready_task(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = _project_with_loop_capacity(tmp_path, monkeypatch)
    command = ParsedLoopRunnerCommand(project=None, once=True, json_output=True)
    context = CliContextBuilder().build(command, cwd=project_root, bootstrap_if_missing=False)

    payload = loop_runner_once(context, command, services=SimpleNamespace())

    assert payload['loop_runner_status'] == 'idle'
    assert payload['reason'] == 'no_actionable_task'


def test_loop_runner_once_activates_planner_for_draft_task(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = _project_with_loop_capacity(tmp_path, monkeypatch)
    _add_plan_task_record(project_root, task_id='task-draft', status='draft')
    command = ParsedLoopRunnerCommand(project=None, once=True, timeout_s=11.0, json_output=True)
    context = CliContextBuilder().build(command, cwd=project_root, bootstrap_if_missing=False)
    seen: dict[str, object] = {}

    def fake_submit_ask(_context, ask_command):
        seen['target'] = ask_command.target
        seen['sender'] = ask_command.sender
        seen['task_id'] = ask_command.task_id
        seen['artifact_request'] = ask_command.artifact_request
        seen['message'] = ask_command.message
        return AskSummary(
            project_id=context.project.project_id,
            submission_id=None,
            jobs=({'job_id': 'job_planner', 'agent_name': 'planner', 'status': 'submitted'},),
        )

    def forbidden_loop_run_once(*_args, **_kwargs):
        raise AssertionError('draft task must not start execution')

    payload = loop_runner_once(
        context,
        command,
        services=SimpleNamespace(submit_ask=fake_submit_ask, loop_run_once=forbidden_loop_run_once),
    )

    assert payload['loop_runner_status'] == 'ok'
    assert payload['action'] == 'activated_planner'
    assert payload['reason'] == 'draft_task'
    assert payload['task_id'] == 'task-draft'
    assert payload['next_owner'] == 'planner'
    assert payload['ask']['job_id'] == 'job_planner'
    assert seen['target'] == 'planner'
    assert seen['sender'] == 'system'
    assert seen['artifact_request'] is True
    assert 'Status: draft' in str(seen['message'])
    activation = json.loads(Path(str(payload['activation_path'])).read_text(encoding='utf-8'))
    assert activation['task_id'] == 'task-draft'
    assert activation['ask']['job_id'] == 'job_planner'
    assert activation['script_write_rules']


def test_loop_runner_once_activates_planner_with_round_evidence_for_partial_task(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = _project_with_loop_capacity(tmp_path, monkeypatch)
    round_path = project_root / 'docs' / 'plantree' / 'plans' / 'demo-plan' / 'tasks' / 'task-partial' / 'round-partial.md'
    _write(round_path, 'round result: partial\n')
    _add_plan_task_record(
        project_root,
        task_id='task-partial',
        status='partial',
        artifacts={
            'round_partial': {
                'kind': 'round_partial',
                'path': str(round_path.relative_to(project_root)),
                'source_path': str(round_path.relative_to(project_root)),
                'sha256': 'test',
                'bytes': 22,
                'imported_at': '2026-06-27T00:00:00Z',
                'loop_id': 'loop-prev',
                'round_result': 'partial',
            }
        },
    )
    command = ParsedLoopRunnerCommand(project=None, once=True, json_output=True)
    context = CliContextBuilder().build(command, cwd=project_root, bootstrap_if_missing=False)

    def fake_submit_ask(_context, _ask_command):
        return AskSummary(
            project_id=context.project.project_id,
            submission_id=None,
            jobs=({'job_id': 'job_planner_partial', 'agent_name': 'planner', 'status': 'submitted'},),
        )

    payload = loop_runner_once(
        context,
        command,
        services=SimpleNamespace(submit_ask=fake_submit_ask),
    )

    assert payload['action'] == 'activated_planner'
    assert payload['reason'] == 'partial_task'
    activation = json.loads(Path(str(payload['activation_path'])).read_text(encoding='utf-8'))
    assert activation['round_evidence_refs'] == [
        {
            'kind': 'round_partial',
            'path': str(round_path.relative_to(project_root)),
            'round_result': 'partial',
            'loop_id': 'loop-prev',
        }
    ]


@pytest.mark.parametrize(
    ('status', 'expected_action', 'expected_runner_status', 'expected_owner'),
    (
        ('needs_clarification', 'paused', 'paused', 'frontdesk'),
        ('blocked', 'blocked', 'blocked', 'frontdesk_or_recovery'),
        ('done', 'terminal', 'terminal', 'none'),
    ),
)
def test_loop_runner_once_stops_without_provider_activation_for_paused_or_terminal_tasks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    expected_action: str,
    expected_runner_status: str,
    expected_owner: str,
) -> None:
    project_root = _project_with_loop_capacity(tmp_path, monkeypatch)
    _add_plan_task_record(project_root, task_id=f'task-{status}', status=status)
    command = ParsedLoopRunnerCommand(project=None, once=True, json_output=True)
    context = CliContextBuilder().build(command, cwd=project_root, bootstrap_if_missing=False)

    def forbidden_submit(*_args, **_kwargs):
        raise AssertionError('paused or terminal tasks must not submit asks')

    payload = loop_runner_once(
        context,
        command,
        services=SimpleNamespace(submit_ask=forbidden_submit),
    )

    assert payload['loop_runner_status'] == expected_runner_status
    assert payload['action'] == expected_action
    assert payload['task_id'] == f'task-{status}'
    assert payload['next_owner'] == expected_owner


def test_loop_run_once_records_failure_and_releases_after_watch_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = _project_with_loop_capacity(tmp_path, monkeypatch)
    command = ParsedLoopRunOnceCommand(project=None, loop_id='round1', task='ship the slice', timeout_s=7.0)
    context = CliContextBuilder().build(command, cwd=project_root, bootstrap_if_missing=False)
    calls: list[tuple[str, object]] = []

    def fake_loop_capacity(_context, capacity_command):
        calls.append(('capacity', capacity_command.action))
        if capacity_command.action == 'ensure':
            return {
                'loop_capacity_status': 'ensured',
                'loop_id': capacity_command.loop_id,
                'project_id': context.project.project_id,
                'agent_count': 2,
                'agents': [
                    {'name': 'loop-round1-worker-1', 'profile': 'worker', 'state': 'planned'},
                    {'name': 'loop-round1-code_reviewer-1', 'profile': 'code_reviewer', 'state': 'planned'},
                ],
                'apply': {'apply_status': 'applied', 'action': 'add_agent'},
            }
        if capacity_command.action == 'release':
            return {
                'loop_capacity_status': 'released',
                'loop_id': capacity_command.loop_id,
                'project_id': context.project.project_id,
                'agent_count': 2,
                'released_count': 2,
                'retained_count': 0,
                'release_policy': 'auto',
                'idle_only': True,
                'agents': [
                    {'name': 'loop-round1-worker-1', 'profile': 'worker', 'state': 'released'},
                    {'name': 'loop-round1-code_reviewer-1', 'profile': 'code_reviewer', 'state': 'released'},
                ],
                'apply': {'apply_status': 'applied', 'action': 'remove_agent'},
            }
        raise AssertionError(f'unexpected capacity action {capacity_command.action}')

    def fake_submit_ask(_context, ask_command):
        calls.append(('ask', ask_command.target))
        return AskSummary(
            project_id=context.project.project_id,
            submission_id=f'sub_{ask_command.target}',
            jobs=(
                {
                    'job_id': f'job_{ask_command.target}',
                    'agent_name': ask_command.target,
                    'status': 'accepted',
                },
            ),
        )

    def fake_watch_ask_job(_context, job_id, _out, *, timeout, emit_output):
        calls.append(('watch', job_id))
        raise RuntimeError('watch transport failed')

    payload = loop_run_once(
        context,
        command,
        services=SimpleNamespace(
            loop_capacity=fake_loop_capacity,
            submit_ask=fake_submit_ask,
            watch_ask_job=fake_watch_ask_job,
        ),
    )

    assert payload['loop_run_status'] == 'failed'
    assert payload['failure'] == {
        'stage': 'execution',
        'error_type': 'RuntimeError',
        'error': 'watch transport failed',
    }
    assert payload['capacity']['release']['loop_capacity_status'] == 'released'
    assert payload['capacity']['release']['release_policy'] == 'auto'
    assert payload['capacity']['release']['idle_only'] is True
    assert calls == [
        ('capacity', 'ensure'),
        ('ask', 'loop-round1-worker-1'),
        ('watch', 'job_loop-round1-worker-1'),
        ('capacity', 'release'),
    ]

    loop_dir = project_root / '.ccb' / 'runtime' / 'loops' / 'round1'
    round_payload = json.loads((loop_dir / 'round.json').read_text(encoding='utf-8'))
    events = [json.loads(line) for line in (loop_dir / 'events.jsonl').read_text(encoding='utf-8').splitlines()]
    breadcrumb = (loop_dir / 'breadcrumb.md').read_text(encoding='utf-8')
    assert round_payload['loop_run_status'] == 'failed'
    assert round_payload['failure']['error'] == 'watch transport failed'
    assert [event['kind'] for event in events] == [
        'loop_run_started',
        'loop_run_failed',
        'loop_run_finished',
    ]
    assert 'Phase: blocked\n' in breadcrumb
    assert 'Blocked: failed\n' in breadcrumb


def test_loop_run_once_json_handler_returns_nonzero_for_incomplete_round() -> None:
    out = StringIO()
    command = ParsedLoopRunOnceCommand(project=None, loop_id='round1', task='ship', json_output=True)

    exit_code = handle_loop_run_once(
        SimpleNamespace(),
        command,
        out,
        SimpleNamespace(
            loop_run_once=lambda _context, _command, _services: {'loop_run_status': 'incomplete'},
            render_loop_run_once=lambda _payload: (),
            write_lines=lambda _out, _lines: None,
        ),
    )

    assert exit_code == 1
    assert json.loads(out.getvalue()) == {'loop_run_status': 'incomplete'}


def test_loop_run_once_does_not_bootstrap_missing_project(tmp_path: Path) -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = maybe_handle_phase2(
        ['loop', 'run-once', '--loop-id', 'round1', '--task', 'ship', '--json'],
        cwd=tmp_path,
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 1
    assert stdout.getvalue() == ''
    assert not (tmp_path / '.ccb').exists()
    assert 'command_status: failed' in stderr.getvalue()


def test_loop_capacity_ensure_status_release_json_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = _project_with_loop_capacity(tmp_path, monkeypatch)

    result, ensured, err = _run_phase2(
        [
            'loop',
            'capacity',
            'ensure',
            '--loop-id',
            'round1',
            '--profile',
            'worker=1',
            '--profile',
            'code_reviewer=1',
            '--json',
        ],
        cwd=project_root,
    )

    assert result == 0
    assert err == ''
    assert ensured['loop_capacity_status'] == 'ensured'
    assert ensured['loop_id'] == 'round1'
    assert ensured['agent_count'] == 2
    assert [agent['name'] for agent in ensured['agents']] == [
        'loop-round1-worker-1',
        'loop-round1-code_reviewer-1',
    ]
    assert ensured['agents'][0]['role'] == 'agentroles.coder'
    assert ensured['agents'][0]['workspace_group'] == 'worker_pool'
    assert ensured['apply']['apply_status'] == 'deferred_until_start'
    assert Path(str(ensured['state_path'])).is_file()

    validate_out = StringIO()
    validate_err = StringIO()
    validate_result = maybe_handle_phase2(
        ['config', 'validate'],
        cwd=project_root,
        stdout=validate_out,
        stderr=validate_err,
    )
    assert validate_result == 0
    assert validate_err.getvalue() == ''
    assert 'agents: loop-round1-code_reviewer-1, loop-round1-worker-1, orchestrator' in validate_out.getvalue()

    result, status, err = _run_phase2(
        ['loop', 'capacity', 'status', '--loop-id', 'round1', '--json'],
        cwd=project_root,
    )

    assert result == 0
    assert err == ''
    assert status['loop_capacity_status'] == 'ensured'
    assert status['agent_count'] == 2
    assert [agent['state'] for agent in status['agents']] == ['planned', 'planned']

    result, released, err = _run_phase2(
        ['loop', 'capacity', 'release', '--loop-id', 'round1', '--idle-only', '--json'],
        cwd=project_root,
    )

    assert result == 0
    assert err == ''
    assert released['loop_capacity_status'] == 'released'
    assert released['release_policy'] == 'idle-only'
    assert released['idle_only'] is True
    assert released['released_count'] == 2
    assert released['apply']['apply_status'] == 'deferred_until_start'
    assert [agent['state'] for agent in released['agents']] == ['released', 'released']

    result, rerelease, err = _run_phase2(
        ['loop', 'capacity', 'release', '--loop-id', 'round1', '--policy', 'auto', '--json'],
        cwd=project_root,
    )

    assert result == 0
    assert err == ''
    assert rerelease['loop_capacity_status'] == 'released'
    assert rerelease['release_policy'] == 'auto'
    assert rerelease['idle_only'] is True
    assert rerelease['released_count'] == 2

    state = json.loads(Path(str(released['state_path'])).read_text(encoding='utf-8'))
    events = [
        json.loads(line)
        for line in Path(str(released['events_path'])).read_text(encoding='utf-8').splitlines()
    ]
    assert state['loop_capacity_status'] == 'released'
    assert [event['event'] for event in events] == ['ensure', 'release', 'release']

    validate_out = StringIO()
    validate_err = StringIO()
    validate_result = maybe_handle_phase2(
        ['config', 'validate'],
        cwd=project_root,
        stdout=validate_out,
        stderr=validate_err,
    )
    assert validate_result == 0
    assert validate_err.getvalue() == ''
    assert 'agents: orchestrator' in validate_out.getvalue()
    assert 'loop-round1-worker-1' not in validate_out.getvalue()


def test_loop_capacity_ensure_while_mounted_reports_pane_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = _project_with_loop_capacity(tmp_path, monkeypatch)
    worker = 'loop-round1-worker-1'
    reviewer = 'loop-round1-code_reviewer-1'
    monkeypatch.setattr(
        loop_capacity_module,
        'ping_local_state',
        lambda _context: SimpleNamespace(mount_state='mounted', socket_connectable=True, reason=None),
    )
    monkeypatch.setattr(
        loop_capacity_module,
        'reload_config',
        lambda _context, _command: {
            'status': 'published',
            'stage': 'publish_transaction',
            'plan_class': 'add_window',
            'published_graph_version': 7,
            'namespace_patch': {
                'status': 'applied',
                'agent_panes': {worker: '%2', reviewer: '%3'},
                'preserved_before': {'orchestrator': '%1'},
                'preserved_after': {'orchestrator': '%1'},
            },
            'runtime_mount': {
                'status': 'mounted',
                'mounted_agents': [worker, reviewer],
                'runtime_authority_written_agents': [worker, reviewer],
            },
        },
    )

    result, ensured, err = _run_phase2(
        [
            'loop',
            'capacity',
            'ensure',
            '--loop-id',
            'round1',
            '--profile',
            'worker=1',
            '--profile',
            'code_reviewer=1',
            '--json',
        ],
        cwd=project_root,
    )

    assert result == 0
    assert err == ''
    assert ensured['apply']['apply_status'] == 'applied'
    assert ensured['apply']['plan_class'] == 'add_window'
    assert ensured['apply']['namespace_agent_panes'] == {worker: '%2', reviewer: '%3'}
    assert ensured['apply']['namespace_preserved_before'] == {'orchestrator': '%1'}
    assert ensured['apply']['namespace_preserved_after'] == {'orchestrator': '%1'}
    assert ensured['apply']['runtime_mount_status'] == 'mounted'
    assert ensured['apply']['pane_identity_report']['added_agents'] == [
        {'agent': reviewer, 'pane_id': '%3', 'pane_identity_source': 'namespace_agent_panes'},
        {'agent': worker, 'pane_id': '%2', 'pane_identity_source': 'namespace_agent_panes'},
    ]
    assert ensured['apply']['pane_identity_report']['preserved_agents'] == [
        {
            'agent': 'orchestrator',
            'before_pane_id': '%1',
            'after_pane_id': '%1',
            'pane_identity_source': 'namespace_preserved_before_after',
            'changed': False,
        }
    ]
    assert ensured['apply']['pane_identity_report']['mounted_agents'] == [worker, reviewer]


def test_loop_capacity_ensure_rejects_unknown_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = _project_with_loop_capacity(tmp_path, monkeypatch)

    stdout = StringIO()
    stderr = StringIO()
    result = maybe_handle_phase2(
        [
            'loop',
            'capacity',
            'ensure',
            '--loop-id',
            'round1',
            '--profile',
            'unknown=1',
            '--json',
        ],
        cwd=project_root,
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 1
    assert stdout.getvalue() == ''
    assert 'command_status: failed' in stderr.getvalue()
    assert "unknown loop role profile 'unknown'" in stderr.getvalue()


def test_loop_capacity_release_retains_busy_agents(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = _project_with_loop_capacity(tmp_path, monkeypatch)
    result, ensured, err = _run_phase2(
        [
            'loop',
            'capacity',
            'ensure',
            '--loop-id',
            'round1',
            '--profile',
            'worker=1',
            '--profile',
            'code_reviewer=1',
            '--json',
        ],
        cwd=project_root,
    )
    assert result == 0
    assert err == ''
    assert ensured['agent_count'] == 2

    class FakeRuntimeStore:
        def __init__(self, _paths):
            pass

        def load_best_effort(self, agent_name):
            if agent_name == 'loop-round1-worker-1':
                return SimpleNamespace(state=SimpleNamespace(value='busy'), queue_depth=0)
            return SimpleNamespace(state=SimpleNamespace(value='idle'), queue_depth=0)

    monkeypatch.setattr(loop_capacity_module, 'AgentRuntimeStore', FakeRuntimeStore)
    monkeypatch.setattr(
        loop_capacity_module,
        'ping_local_state',
        lambda _context: SimpleNamespace(mount_state='mounted', socket_connectable=True, reason=None),
    )
    monkeypatch.setattr(
        loop_capacity_module,
        '_apply_reload_if_mounted',
        lambda _context, *, action: {'apply_status': 'applied', 'action': action, 'reload_status': 'noop'},
    )

    result, released, err = _run_phase2(
        ['loop', 'capacity', 'release', '--loop-id', 'round1', '--policy', 'auto', '--json'],
        cwd=project_root,
    )

    assert result == 0
    assert err == ''
    assert released['loop_capacity_status'] == 'ensured'
    assert released['release_policy'] == 'auto'
    assert released['idle_only'] is True
    assert released['released_count'] == 1
    assert released['retained_count'] == 1
    assert released['retained'] == [
        {
            'name': 'loop-round1-worker-1',
            'queue_depth': 0,
            'reason': 'runtime_state=busy',
            'runtime_state': 'busy',
        }
    ]
    states = {agent['name']: agent['state'] for agent in released['agents']}
    assert states == {
        'loop-round1-worker-1': 'retained',
        'loop-round1-code_reviewer-1': 'released',
    }

    validate_out = StringIO()
    validate_err = StringIO()
    validate_result = maybe_handle_phase2(
        ['config', 'validate'],
        cwd=project_root,
        stdout=validate_out,
        stderr=validate_err,
    )
    assert validate_result == 0
    assert validate_err.getvalue() == ''
    assert 'loop-round1-worker-1' in validate_out.getvalue()
    assert 'loop-round1-code_reviewer-1' not in validate_out.getvalue()

    class IdleRuntimeStore:
        def __init__(self, _paths):
            pass

        def load_best_effort(self, _agent_name):
            return SimpleNamespace(state=SimpleNamespace(value='idle'), queue_depth=0)

    monkeypatch.setattr(loop_capacity_module, 'AgentRuntimeStore', IdleRuntimeStore)
    result, final_release, err = _run_phase2(
        ['loop', 'capacity', 'release', '--loop-id', 'round1', '--policy', 'auto', '--json'],
        cwd=project_root,
    )

    assert result == 0
    assert err == ''
    assert final_release['loop_capacity_status'] == 'released'
    assert final_release['release_policy'] == 'auto'
    assert final_release['retained_count'] == 0
    final_worker = next(agent for agent in final_release['agents'] if agent['name'] == 'loop-round1-worker-1')
    assert final_worker['state'] == 'released'
    assert 'retain_reason' not in final_worker
    assert 'runtime_state' not in final_worker
    assert 'queue_depth' not in final_worker
