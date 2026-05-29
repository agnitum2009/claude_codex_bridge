from __future__ import annotations

from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pytest

from agents.config_loader import load_project_config
from ccbd.app import CcbdApp
from ccbd.models import LeaseHealth, LeaseInspection
import ccbd.handlers.project_reload as project_reload_handler
from ccbd.reload_plan import build_reload_dry_run_plan
from ccbd.socket_client import CcbdClient
from cli.context import CliContext
from cli.models import ParsedReloadCommand
from cli.parser import CliParser, CliUsageError
from cli.phase2 import maybe_handle_phase2
from cli.render import render_reload
from cli.services.reload import reload_config_dry_run
from project.resolver import bootstrap_project
from storage.paths import PathLayout


BASE_CONFIG = """version = 2
entry_window = "main"

[windows]
main = "agent1:codex, agent2:claude"

[ui.sidebar]
mode = "every_window"
width = "15%"
bottom_height = 20
"""


def test_reload_dry_run_no_change_updates_metrics_without_mutation(tmp_path: Path, monkeypatch) -> None:
    project_root = _project(tmp_path / 'repo-no-change', BASE_CONFIG)
    app = CcbdApp(project_root, clock=lambda: '2026-05-29T00:00:00Z', pid=4242)
    before_snapshot = _runtime_file_snapshot(project_root)
    load_calls: list[Path] = []
    original_load = project_reload_handler.load_project_config

    def _load_once(root):
        load_calls.append(Path(root))
        return original_load(root)

    _block_mutation_paths(app, monkeypatch)
    monkeypatch.setattr(project_reload_handler, 'load_project_config', _load_once)

    assert app.control_plane_metrics.last_reload_duration_s is None

    payload = app.socket_server._handlers['project_reload_config']({'dry_run': True})

    assert payload['status'] == 'ok'
    assert payload['plan_class'] == 'no_change'
    assert payload['operations'] == []
    assert payload['drain_intents'] == []
    assert payload['safe_to_apply'] is False
    assert payload['future_safe_to_apply'] is True
    assert payload['mutation_enabled'] is False
    assert load_calls == [project_root]
    assert _runtime_file_snapshot(project_root) == before_snapshot
    assert app.service_graph.version == 1
    assert app.config_identity['config_signature'] == payload['old_config_signature']
    assert app.config_identity['config_signature'] == payload['new_config_signature']
    assert app.control_plane_metrics.last_reload_duration_s is not None
    assert app.control_plane_metrics.last_reload_plan_class == 'no_change'
    assert app.control_plane_metrics.last_reload_error is None


@pytest.mark.parametrize(
    ('new_text', 'expected_class', 'expected_ops'),
    [
        (
            BASE_CONFIG.replace('agent1:codex, agent2:claude', 'agent1:codex, agent2:claude, agent3:codex'),
            'add_agent',
            {'add_agent'},
        ),
        (
            """version = 2
entry_window = "main"

[windows]
main = "agent1:codex, agent2:claude"
review = "agent3:codex"

[ui.sidebar]
mode = "every_window"
width = "15%"
bottom_height = 20
""",
            'add_window',
            {'add_window', 'add_agent'},
        ),
        (
            BASE_CONFIG.replace('agent1:codex, agent2:claude', 'agent1:codex'),
            'remove_agent',
            {'remove_agent'},
        ),
        (
            BASE_CONFIG.replace('agent2:claude', 'agent2:codex'),
            'replace_agent',
            {'replace_agent'},
        ),
        (
            BASE_CONFIG.replace('agent1:codex, agent2:claude', 'agent2:claude, agent1:codex'),
            'layout_change',
            {'layout_change'},
        ),
        (
            """version = 2
entry_window = "main"

[windows]
main = "agent1:codex, agent2:claude"
review = "agent3:codex"

[ui.sidebar]
mode = "every_window"
""".replace(
                'main = "agent1:codex, agent2:claude"\nreview = "agent3:codex"',
                'main = "agent1:codex, agent3:codex"\nreview = "agent2:claude"',
            ),
            'move_agent',
            {'move_agent'},
        ),
    ],
)
def test_reload_plan_classifies_runtime_and_layout_changes(
    tmp_path: Path,
    new_text: str,
    expected_class: str,
    expected_ops: set[str],
) -> None:
    current = _load_config(tmp_path / 'current', BASE_CONFIG)
    new = _load_config(tmp_path / 'new', new_text)

    plan = build_reload_dry_run_plan(current, new)

    assert plan['status'] == 'ok'
    assert plan['plan_class'] == expected_class
    assert expected_ops <= {item['op'] for item in plan['operations']}
    if expected_ops & {'remove_agent', 'replace_agent'}:
        assert plan['drain_intents']
    else:
        assert plan['drain_intents'] == []
    assert plan['safe_to_apply'] is False
    assert plan['mutation_enabled'] is False


def test_reload_plan_classifies_sidebar_view_only_change(tmp_path: Path) -> None:
    current = _load_config(
        tmp_path / 'current-view',
        BASE_CONFIG
        + """
[ui.sidebar.view]
comms_limit = 4
tips = ["C-b d detach"]
""",
    )
    new = _load_config(
        tmp_path / 'new-view',
        BASE_CONFIG
        + """
[ui.sidebar.view]
comms_limit = 5
tips = ["C-b c new win"]
""",
    )

    plan = build_reload_dry_run_plan(current, new)

    assert plan['plan_class'] == 'view_only_change'
    assert plan['operations'][0]['op'] == 'view_only_change'
    assert plan['drain_intents'] == []
    assert plan['old_config_signature'] == plan['new_config_signature']
    assert plan['future_safe_to_apply'] is True


def test_reload_dry_run_invalid_config_is_structured_and_non_mutating(tmp_path: Path, monkeypatch) -> None:
    project_root = _project(tmp_path / 'repo-invalid', BASE_CONFIG)
    app = CcbdApp(project_root, clock=lambda: '2026-05-29T00:00:00Z', pid=4242)
    before_identity = dict(app.config_identity)
    before_snapshot = _runtime_file_snapshot(project_root)
    _block_mutation_paths(app, monkeypatch)
    _write_config(project_root, 'version = 2\n\n[windows]\nmain = "agent1"\n')

    payload = app.socket_server._handlers['project_reload_config']({'dry_run': True})

    assert payload['status'] == 'invalid_config'
    assert payload['plan_class'] == 'invalid_config'
    assert payload['errors']
    assert payload['safe_to_apply'] is False
    assert app.config_identity == before_identity
    assert _runtime_file_snapshot(project_root) == before_snapshot
    assert app.control_plane_metrics.last_reload_plan_class == 'invalid_config'
    assert app.control_plane_metrics.last_reload_error


def test_reload_dry_run_missing_project_config_is_invalid_not_default_fallback(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root = _project(tmp_path / 'repo-missing-config', BASE_CONFIG)
    app = CcbdApp(project_root, clock=lambda: '2026-05-29T00:00:00Z', pid=4242)
    before_identity = dict(app.config_identity)
    before_snapshot = _runtime_file_snapshot(project_root)
    _block_mutation_paths(app, monkeypatch)
    (project_root / '.ccb' / 'ccb.config').unlink()

    payload = app.socket_server._handlers['project_reload_config']({'dry_run': True})

    assert payload['status'] == 'invalid_config'
    assert payload['plan_class'] == 'invalid_config'
    assert payload['errors'] == [f'project config not found: {project_root / ".ccb" / "ccb.config"}']
    assert app.config_identity == before_identity
    assert _runtime_file_snapshot(project_root) == before_snapshot
    assert app.control_plane_metrics.last_reload_plan_class == 'invalid_config'
    assert app.control_plane_metrics.last_reload_error


def test_reload_non_dry_run_is_rejected_without_reload_metrics(tmp_path: Path) -> None:
    project_root = _project(tmp_path / 'repo-reject-non-dry-run', BASE_CONFIG)
    app = CcbdApp(project_root, clock=lambda: '2026-05-29T00:00:00Z', pid=4242)

    with pytest.raises(ValueError, match='dry_run=true'):
        app.socket_server._handlers['project_reload_config']({'dry_run': False})

    assert app.control_plane_metrics.last_reload_duration_s is None
    assert app.control_plane_metrics.last_reload_plan_class is None
    assert app.control_plane_metrics.last_reload_error is None


def test_reload_cli_parser_endpoint_render_and_phase2_return_code(monkeypatch, tmp_path: Path) -> None:
    parser = CliParser()
    assert parser.parse(['reload', '--dry-run']) == ParsedReloadCommand(project=None, dry_run=True)
    with pytest.raises(CliUsageError, match='requires --dry-run'):
        parser.parse(['reload'])

    rendered = render_reload(
        {
            'status': 'ok',
            'dry_run': True,
            'mutation_enabled': False,
            'plan_class': 'add_agent',
            'safe_to_apply': False,
            'future_safe_to_apply': True,
            'old_config_signature': 'old',
            'new_config_signature': 'new',
            'operations': [{'op': 'add_agent', 'agent': 'agent3', 'window': 'main', 'reason': 'new'}],
            'drain_intents': [],
            'warnings': ['Phase 3 dry-run only; mutation capability is disabled.'],
            'reasons': ['add_agent agent3: new'],
            'errors': [],
        }
    )
    assert rendered == (
        'reload_status: ok',
        'dry_run: true',
        'mutation_enabled: false',
        'plan_class: add_agent',
        'safe_to_apply: false',
        'future_safe_to_apply: true',
        'old_config_signature: old',
        'new_config_signature: new',
        'reload_operation: op=add_agent agent=agent3 window=main reason=new',
        'reload_reason: add_agent agent3: new',
        'reload_warning: Phase 3 dry-run only; mutation capability is disabled.',
    )

    import cli.phase2 as phase2_module

    fake_context = SimpleNamespace(project=SimpleNamespace(project_root=tmp_path, project_id='proj-reload'))
    bootstrap_called = False

    def _unexpected_bootstrap(_project_root):
        nonlocal bootstrap_called
        bootstrap_called = True
        raise AssertionError('reload dry-run must not bootstrap or write config')

    monkeypatch.setattr(phase2_module, '_build_context', lambda command, cwd, out: fake_context)
    monkeypatch.setattr(phase2_module, 'ensure_bootstrap_project_config', _unexpected_bootstrap)
    monkeypatch.setattr(
        phase2_module,
        'reload_config_dry_run',
        lambda context, command: {
            'status': 'ok',
            'dry_run': True,
            'mutation_enabled': False,
            'plan_class': 'no_change',
            'safe_to_apply': False,
            'future_safe_to_apply': True,
            'old_config_signature': 'same',
            'new_config_signature': 'same',
            'operations': [],
            'drain_intents': [],
            'reasons': ['config identity and presentation fields are unchanged'],
            'warnings': [],
            'errors': [],
        },
    )

    stdout = StringIO()
    stderr = StringIO()
    code = maybe_handle_phase2(['reload', '--dry-run'], cwd=tmp_path, stdout=stdout, stderr=stderr)

    assert code == 0
    assert bootstrap_called is False
    assert 'reload_status: ok\n' in stdout.getvalue()
    assert 'plan_class: no_change\n' in stdout.getvalue()
    assert stderr.getvalue() == ''


def test_ccbd_client_reload_endpoint_builds_dry_run_payload(monkeypatch, tmp_path: Path) -> None:
    client = CcbdClient(tmp_path / 'ccbd.sock')
    calls: list[tuple[str, dict]] = []
    monkeypatch.setattr(client, 'request', lambda op, payload=None: calls.append((op, payload)) or {'status': 'ok'})

    assert client.project_reload_config(dry_run=True) == {'status': 'ok'}
    assert calls == [('project_reload_config', {'dry_run': True})]


def test_reload_service_connects_drifted_current_daemon_without_compatibility_restart(
    monkeypatch,
    tmp_path: Path,
) -> None:
    project_root = _project(tmp_path / 'repo-drifted-reload-service', BASE_CONFIG)
    project = bootstrap_project(project_root)
    command = ParsedReloadCommand(project=None, dry_run=True)
    context = CliContext(command=command, cwd=project_root, project=project, paths=PathLayout(project_root))
    inspection = LeaseInspection(
        lease=None,
        health=LeaseHealth.HEALTHY,
        pid_alive=True,
        socket_connectable=True,
        heartbeat_fresh=True,
        takeover_allowed=False,
        reason='healthy',
    )
    object.__setattr__(inspection, 'phase', 'mounted')

    import cli.services.daemon as daemon_service

    monkeypatch.setattr(daemon_service, 'inspect_daemon', lambda _context: (None, None, inspection))
    monkeypatch.setattr(
        daemon_service,
        'connect_mounted_daemon',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError('reload dry-run must not require config-compatible daemon')),
    )

    class _Client:
        def __init__(self, socket_path):
            self.socket_path = socket_path

        def project_reload_config(self, *, dry_run: bool) -> dict:
            return {'status': 'ok', 'dry_run': dry_run, 'socket_path': str(self.socket_path)}

    monkeypatch.setattr(daemon_service, 'CcbdClient', _Client)

    payload = reload_config_dry_run(context, command)

    assert payload == {
        'status': 'ok',
        'dry_run': True,
        'socket_path': str(context.paths.ccbd_socket_path),
    }


def _project(project_root: Path, config_text: str) -> Path:
    project_root.mkdir(parents=True, exist_ok=True)
    _write_config(project_root, config_text)
    return project_root


def _write_config(project_root: Path, text: str) -> None:
    config_path = project_root / '.ccb' / 'ccb.config'
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(text, encoding='utf-8')


def _load_config(project_root: Path, text: str):
    _project(project_root, text)
    return load_project_config(project_root).config


def _runtime_file_snapshot(project_root: Path) -> dict[str, bytes]:
    root = project_root / '.ccb' / 'ccbd'
    if not root.exists():
        return {}
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob('*'))
        if path.is_file()
    }


def _block_mutation_paths(app: CcbdApp, monkeypatch) -> None:
    def _fail(*_args, **_kwargs):
        raise AssertionError('reload dry-run must not mutate runtime, tmux, or service graph')

    monkeypatch.setattr(app, 'publish_service_graph', _fail, raising=False)
    for method_name in ('ensure_started', 'destroy', 'recreate', 'patch_topology', 'refresh'):
        monkeypatch.setattr(app.project_namespace, method_name, _fail, raising=False)
    for store_name in (
        'lifecycle_store',
        'namespace_state_store',
        'namespace_event_store',
        'start_policy_store',
        'restore_store',
        'startup_report_store',
        'shutdown_report_store',
        'restore_report_store',
    ):
        store = getattr(app, store_name, None)
        if store is not None:
            monkeypatch.setattr(store, 'save', _fail, raising=False)
            monkeypatch.setattr(store, 'append', _fail, raising=False)
