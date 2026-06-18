from __future__ import annotations

import json
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from mobile_gateway import MobileGatewayError, MobileGatewayService, build_mobile_gateway_server, parse_listen_address


class _FakeCcbdClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def ping(self, target: str = 'ccbd') -> dict[str, object]:
        self.calls.append(('ping', target))
        return {
            'project_id': 'proj-demo',
            'mount_state': 'mounted',
            'health': 'healthy',
            'namespace_epoch': 4,
            'namespace_tmux_socket_path': '/tmp/ccb-demo/tmux.sock',
            'namespace_tmux_session_name': 'ccb-demo',
            'namespace_ui_attachable': True,
        }

    def project_view(self, *, schema_version: int = 1) -> dict[str, object]:
        self.calls.append(('project_view', schema_version))
        return {
            'view': {
                'project': {
                    'id': 'proj-demo',
                    'root': '/srv/demo',
                    'display_name': 'demo',
                },
                'namespace': {
                    'epoch': 4,
                    'socket_path': '/tmp/ccb-demo/tmux.sock',
                    'session_name': 'ccb-demo',
                    'active_window': 'main',
                    'active_pane_id': '%2',
                },
                'windows': [],
                'agents': [],
                'comms': [],
            },
            'cache': {'sequence': 1},
        }


def _service(fake: _FakeCcbdClient, *, mobile_dir: Path | None = None) -> MobileGatewayService:
    return MobileGatewayService(
        project_id='proj-demo',
        project_root=Path('/srv/demo'),
        ccbd_client_factory=lambda: fake,
        mobile_dir=mobile_dir,
        clock=lambda: '2026-06-18T00:00:00Z',
    )


def test_parse_listen_accepts_loopback_only() -> None:
    assert parse_listen_address(None).text == '127.0.0.1:8787'
    assert parse_listen_address('127.0.0.1:0').text == '127.0.0.1:0'
    assert parse_listen_address('localhost:8787').text == 'localhost:8787'
    with pytest.raises(ValueError, match='loopback'):
        parse_listen_address('0.0.0.0:8787')


def test_health_and_projects_use_ccbd_without_exposing_tmux_socket() -> None:
    fake = _FakeCcbdClient()
    service = _service(fake)

    health = service.health_payload()
    projects = service.projects_payload()

    assert health['status'] == 'ok'
    assert health['ccbd']['namespace_epoch'] == 4
    assert projects['projects'][0]['id'] == 'proj-demo'
    assert 'tmux.sock' not in json.dumps(projects)
    assert fake.calls == [('ping', 'ccbd'), ('ping', 'ccbd')]


def test_project_view_redacts_server_tmux_evidence() -> None:
    fake = _FakeCcbdClient()
    payload = _service(fake).project_view_payload('proj-demo')
    namespace = payload['view']['namespace']

    assert namespace['epoch'] == 4
    assert namespace['active_pane_id'] == '%2'
    assert 'socket_path' not in namespace
    assert 'session_name' not in namespace
    assert 'tmux.sock' not in json.dumps(payload)
    assert 'ccb-demo' not in json.dumps(payload)
    assert fake.calls == [('project_view', 1)]


def test_project_view_rejects_unknown_project() -> None:
    with pytest.raises(MobileGatewayError, match='unknown project') as excinfo:
        _service(_FakeCcbdClient()).project_view_payload('other')
    assert excinfo.value.status_code == 404


def test_pairing_claim_creates_hashed_device_records_and_audit(tmp_path: Path) -> None:
    service = _service(_FakeCcbdClient(), mobile_dir=tmp_path / 'mobile')
    pairing = service.create_pairing_payload(gateway_url='http://127.0.0.1:8787')
    pairing_code = str(pairing['pairing_code'])

    status, claim = service.dispatch_post(
        '/v1/pairing/claim',
        {
            'pairing_code': pairing_code,
            'device_name': 'Pixel Fold',
        },
    )
    device_token = str(claim['device_token'])
    device_id = str(claim['device']['device_id'])

    assert status == 201
    assert claim['host_profile']['device_id'] == device_id
    assert claim['host_profile']['scopes'] == ['view']
    assert claim['host_profile']['route_provider'] == 'lan'

    status, me = service.dispatch_get('/v1/devices/me', {'Authorization': f'Bearer {device_token}'})
    assert status == 200
    assert me['device']['name'] == 'Pixel Fold'
    assert me['device']['revoked'] is False

    stored_pairings = (tmp_path / 'mobile' / 'pairing-tokens.jsonl').read_text(encoding='utf-8')
    stored_devices = (tmp_path / 'mobile' / 'devices.json').read_text(encoding='utf-8')
    stored_audit = (tmp_path / 'mobile' / 'audit.jsonl').read_text(encoding='utf-8')
    assert pairing_code not in stored_pairings
    assert pairing_code not in stored_audit
    assert device_token not in stored_devices
    assert device_token not in stored_audit
    assert 'sha256:' in stored_pairings
    assert 'sha256:' in stored_devices

    with pytest.raises(MobileGatewayError) as duplicate:
        service.dispatch_post('/v1/pairing/claim', {'pairing_code': pairing_code})
    assert duplicate.value.status_code == 409

    status, revoked = service.dispatch_post(
        f'/v1/devices/{device_id}/revoke',
        {},
        {'Authorization': f'Bearer {device_token}'},
    )
    assert status == 200
    assert revoked['device']['revoked'] is True
    with pytest.raises(MobileGatewayError) as denied:
        service.dispatch_get('/v1/devices/me', {'Authorization': f'Bearer {device_token}'})
    assert denied.value.status_code == 401


def test_http_server_exposes_g1_get_endpoints() -> None:
    fake = _FakeCcbdClient()
    service = _service(fake)
    server = build_mobile_gateway_server(parse_listen_address('127.0.0.1:0'), service)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    try:
        thread.start()
        host, port = server.server_address[:2]
        base = f'http://{host}:{port}'

        with urlopen(f'{base}/v1/health') as response:
            health = json.loads(response.read().decode('utf-8'))
        with urlopen(f'{base}/v1/projects') as response:
            projects = json.loads(response.read().decode('utf-8'))
        with urlopen(f'{base}/v1/projects/proj-demo/view') as response:
            view = json.loads(response.read().decode('utf-8'))

        assert health['status'] == 'ok'
        assert projects['projects'][0]['id'] == 'proj-demo'
        assert 'socket_path' not in view['view']['namespace']
        with pytest.raises(HTTPError) as excinfo:
            urlopen(f'{base}/v1/projects/other/view')
        assert excinfo.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
