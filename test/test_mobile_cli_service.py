from __future__ import annotations

import json
from pathlib import Path
import socket
from types import SimpleNamespace

import pytest

from cli.services.mobile import _public_gateway_url, prepare_server_mobile_gateway
from mobile_gateway import (
    MobileGatewayProject,
    MobileGatewayProjectRegistry,
    discover_running_mobile_gateway_projects,
    load_mobile_gateway_project_registry,
    publish_mobile_gateway_project,
)
from project.ids import compute_project_id


class _FakeCcbdClient:
    def __init__(self, *, project_id: str, project_root: str, display_name: str) -> None:
        self.project_id = project_id
        self.project_root = project_root
        self.display_name = display_name
        self.calls: list[tuple[str, object]] = []

    def ping(self, target: str) -> dict[str, object]:
        self.calls.append(('ping', target))
        return {
            'status': 'ok',
            'project_id': self.project_id,
            'project_root': self.project_root,
            'display_name': self.display_name,
            'health': 'healthy',
            'mount_state': 'mounted',
        }


def test_public_gateway_url_defaults_to_loopback_fallback() -> None:
    assert (
        _public_gateway_url(None, fallback='http://127.0.0.1:8787')
        == 'http://127.0.0.1:8787'
    )
    assert (
        _public_gateway_url('', fallback='http://127.0.0.1:8787')
        == 'http://127.0.0.1:8787'
    )


def test_public_gateway_url_accepts_origin_only() -> None:
    assert (
        _public_gateway_url('https://mobile.example.com', fallback='unused')
        == 'https://mobile.example.com'
    )
    assert (
        _public_gateway_url('https://mobile.example.com/', fallback='unused')
        == 'https://mobile.example.com'
    )
    assert (
        _public_gateway_url('https://mobile.example.com:8443', fallback='unused')
        == 'https://mobile.example.com:8443'
    )


@pytest.mark.parametrize(
    ('value', 'message'),
    [
        ('mobile.example.com', 'absolute http\\(s\\) origin URL'),
        ('ftp://mobile.example.com', 'absolute http\\(s\\) origin URL'),
        ('https://mobile.example.com/pair', 'must not include a path'),
        ('https://mobile.example.com?debug=1', 'params, query, or fragment'),
        ('https://mobile.example.com#pair', 'params, query, or fragment'),
        ('https://user:pass@mobile.example.com', 'must not include credentials'),
        ('https://mobile.example.com:bad', 'port must be valid'),
    ],
)
def test_public_gateway_url_rejects_non_origin_url(value: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _public_gateway_url(value, fallback='unused')


def test_host_project_registry_publish_and_loads_redacted_projects(tmp_path: Path) -> None:
    registry_path = tmp_path / 'mobile' / 'projects.json'
    socket_path = tmp_path / 'one' / '.ccb' / 'ccbd' / 'ccbd.sock'

    publish_mobile_gateway_project(
        project_id='proj-one',
        project_root=tmp_path / 'one',
        ccbd_socket_path=socket_path,
        display_name='one',
        registry_path=registry_path,
        updated_at='2026-06-24T00:00:00Z',
    )

    payload = json.loads(registry_path.read_text(encoding='utf-8'))
    assert payload['record_type'] == 'ccb_mobile_host_project_registry'
    assert payload['projects'][0]['project_id'] == 'proj-one'
    assert payload['projects'][0]['ccbd_socket_path'] == str(socket_path)

    registry = load_mobile_gateway_project_registry(registry_path=registry_path)
    projects = registry.projects()
    assert len(projects) == 1
    assert projects[0].project_id == 'proj-one'
    assert projects[0].project_root == tmp_path / 'one'
    assert projects[0].public_display_name == 'one'


def test_running_project_discovery_reads_ccbd_main_project_cmdline(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / 'running-project'
    project_root.mkdir()
    socket_path = tmp_path / 'ccbd.sock'
    unix_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    unix_socket.bind(str(socket_path))
    monkeypatch.setattr(
        'mobile_gateway.project_registry._ccbd_socket_path_for_project',
        lambda root: socket_path,
    )
    try:
        projects = discover_running_mobile_gateway_projects(
            cmdlines=[
                ['python', '/opt/ccb/lib/ccbd/main.py', '--project', str(project_root)],
                ['python', '/opt/ccb/lib/ccbd/keeper_main.py', '--project', str(tmp_path / 'ignored')],
            ]
        )
    finally:
        unix_socket.close()

    assert len(projects) == 1
    assert projects[0].project_id == compute_project_id(project_root)
    assert projects[0].project_root == project_root.resolve()
    assert projects[0].public_display_name == 'running-project'


def test_host_project_registry_can_merge_running_projects(tmp_path: Path, monkeypatch) -> None:
    registry_path = tmp_path / 'mobile' / 'projects.json'
    publish_mobile_gateway_project(
        project_id='proj-persisted',
        project_root=tmp_path / 'persisted',
        ccbd_socket_path=tmp_path / 'persisted.sock',
        display_name='persisted',
        registry_path=registry_path,
    )
    running = MobileGatewayProject(
        project_id='proj-running',
        project_root=tmp_path / 'running',
        display_name='running',
        ccbd_client_factory=lambda: None,
    )
    monkeypatch.setattr(
        'mobile_gateway.project_registry.discover_running_mobile_gateway_projects',
        lambda: (running,),
    )

    registry = load_mobile_gateway_project_registry(
        registry_path=registry_path,
        include_running=True,
    )

    assert [project.project_id for project in registry.projects()] == [
        'proj-persisted',
        'proj-running',
    ]


def test_prepare_server_mobile_gateway_includes_running_projects(tmp_path: Path, monkeypatch) -> None:
    fake = _FakeCcbdClient(
        project_id='proj-running',
        project_root='/srv/running',
        display_name='running',
    )
    registry = MobileGatewayProjectRegistry(
        [
            MobileGatewayProject(
                project_id='proj-running',
                project_root=Path('/srv/running'),
                ccbd_client_factory=lambda: fake,
                display_name='running',
            )
        ]
    )
    seen: dict[str, object] = {}

    def fake_load_mobile_gateway_project_registry(**kwargs):
        seen.update(kwargs)
        return registry

    monkeypatch.setattr(
        'cli.services.mobile.load_mobile_gateway_project_registry',
        fake_load_mobile_gateway_project_registry,
    )
    monkeypatch.setattr('cli.services.mobile.mobile_host_state_dir', lambda: tmp_path / 'mobile-state')

    handle = prepare_server_mobile_gateway(
        SimpleNamespace(listen='127.0.0.1:0', public_url=None, route_provider='lan'),
        host_id='host-test',
    )
    try:
        assert seen['include_running'] is True
        assert handle.summary['project_count'] == 1
        assert handle.summary['projects'][0]['display_name'] == 'running'
    finally:
        handle.close()


def test_prepare_server_mobile_gateway_uses_host_registry_without_socket_leak(tmp_path: Path, monkeypatch) -> None:
    first = _FakeCcbdClient(project_id='proj-one', project_root='/srv/one', display_name='one')
    second = _FakeCcbdClient(project_id='proj-two', project_root='/srv/two', display_name='two')
    registry = MobileGatewayProjectRegistry(
        [
            MobileGatewayProject(
                project_id='proj-one',
                project_root=Path('/srv/one'),
                ccbd_client_factory=lambda: first,
                display_name='one',
            ),
            MobileGatewayProject(
                project_id='proj-two',
                project_root=Path('/srv/two'),
                ccbd_client_factory=lambda: second,
                display_name='two',
            ),
        ]
    )
    monkeypatch.setattr('cli.services.mobile.mobile_host_state_dir', lambda: tmp_path / 'mobile-state')

    handle = prepare_server_mobile_gateway(
        SimpleNamespace(listen='127.0.0.1:0', public_url=None, route_provider='lan'),
        project_registry=registry,
        host_id='host-test',
    )
    try:
        summary = handle.summary
    finally:
        handle.close()

    assert summary['mode'] == 'loopback_server_registry'
    assert summary['host_id'] == 'host-test'
    assert summary['project_id'] == 'host-test'
    assert summary['project_count'] == 2
    assert [item['id'] for item in summary['projects']] == ['proj-one', 'proj-two']
    assert summary['pairing']['project_id'] == 'host-test'
    assert summary['pairing']['gateway_url'].startswith('http://127.0.0.1:')
    assert 'ccbd.sock' not in json.dumps(summary)
    assert first.calls == [('ping', 'ccbd')]
    assert second.calls == [('ping', 'ccbd')]
