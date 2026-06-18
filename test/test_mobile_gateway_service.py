from __future__ import annotations

import base64
import json
import os
import socket
import struct
import threading
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from mobile_gateway import MobileGatewayError, MobileGatewayService, build_mobile_gateway_server, parse_listen_address


class _FakeCcbdClient:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

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
                'windows': [
                    {
                        'name': 'main',
                        'label': 'main',
                        'kind': 'agents',
                        'order': 0,
                        'active': True,
                        'agents': ['mobile'],
                    }
                ],
                'agents': [
                    {
                        'name': 'mobile',
                        'provider': 'codex',
                        'window': 'main',
                        'order': 0,
                        'pane_id': '%2',
                        'active': True,
                    }
                ],
                'comms': [],
            },
            'cache': {'sequence': 1},
        }

    def project_focus_agent(self, *, agent: str, namespace_epoch: int | None = None) -> dict[str, object]:
        self.calls.append(('project_focus_agent', agent, namespace_epoch))
        return {
            'focused': True,
            'kind': 'agent',
            'window': 'main',
            'agent': agent,
            'namespace_epoch': namespace_epoch,
        }

    def project_focus_window(self, *, window: str, namespace_epoch: int | None = None) -> dict[str, object]:
        self.calls.append(('project_focus_window', window, namespace_epoch))
        return {
            'focused': True,
            'kind': 'window',
            'window': window,
            'agent': None,
            'namespace_epoch': namespace_epoch,
        }


class _FakeTerminalSession:
    def __init__(self, target) -> None:
        self.target = target
        self.outputs = [b'hello']
        self.writes: list[bytes] = []
        self.pastes: list[str] = []
        self.resizes: list[object] = []
        self.closed = False

    def read(self, timeout_seconds: float = 0.1) -> bytes | None:
        if self.outputs:
            return self.outputs.pop(0)
        time.sleep(min(0.01, max(0.0, timeout_seconds)))
        return b''

    def write(self, data: bytes) -> None:
        self.writes.append(data)

    def paste(self, text: str) -> None:
        self.pastes.append(text)

    def resize(self, geometry) -> None:
        self.resizes.append(geometry)

    def close(self) -> None:
        self.closed = True


def _service(
    fake: _FakeCcbdClient,
    *,
    mobile_dir: Path | None = None,
    terminal_session_factory=None,
) -> MobileGatewayService:
    return MobileGatewayService(
        project_id='proj-demo',
        project_root=Path('/srv/demo'),
        ccbd_client_factory=lambda: fake,
        mobile_dir=mobile_dir,
        clock=lambda: '2026-06-18T00:00:00Z',
        terminal_session_factory=terminal_session_factory,
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
    pairing = service.create_pairing_payload(
        gateway_url='https://mobile.example.com',
        route_provider='cloudflare_tunnel',
    )
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
    assert claim['host_profile']['scopes'] == ['focus', 'terminal_input', 'view']
    assert claim['host_profile']['route_provider'] == 'cloudflare_tunnel'
    assert claim['host_profile']['gateway_url'] == 'https://mobile.example.com'

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


def test_terminal_open_requires_terminal_scope_and_mints_hashed_token(tmp_path: Path) -> None:
    service = _service(_FakeCcbdClient(), mobile_dir=tmp_path / 'mobile')
    pairing = service.create_pairing_payload(gateway_url='http://127.0.0.1:8787')
    _, claim = service.dispatch_post(
        '/v1/pairing/claim',
        {
            'pairing_code': str(pairing['pairing_code']),
            'device_name': 'Pixel Fold',
        },
    )
    token = str(claim['device_token'])

    status, handle = service.dispatch_post(
        '/v1/projects/proj-demo/terminals',
        {
            'schema_version': 1,
            'project_id': 'proj-demo',
            'namespace_epoch': 4,
            'target': {
                'kind': 'agent',
                'agent': 'mobile',
                'window': 'main',
                'pane_id': '%2',
            },
            'geometry': {
                'columns': 100,
                'rows': 30,
                'pixel_width': 960,
                'pixel_height': 640,
            },
        },
        {
            'Authorization': f'Bearer {token}',
            'Host': '127.0.0.1:8787',
        },
    )

    assert status == 201
    assert str(handle['terminal_id']).startswith('term_')
    assert handle['terminal_token']
    assert handle['expires_at']
    assert handle['websocket_url'] == f'ws://127.0.0.1:8787/v1/terminals/{handle["terminal_id"]}'
    assert handle['target_epoch'] == 4
    assert handle['target_summary'] == {
        'project_id': 'proj-demo',
        'agent': 'mobile',
        'window': 'main',
    }
    assert 'tmux.sock' not in json.dumps(handle)
    assert 'ccb-demo' not in json.dumps(handle)

    stored_tokens = (tmp_path / 'mobile' / 'terminal-tokens.jsonl').read_text(encoding='utf-8')
    stored_audit = (tmp_path / 'mobile' / 'audit.jsonl').read_text(encoding='utf-8')
    assert str(handle['terminal_token']) not in stored_tokens
    assert str(handle['terminal_token']) not in stored_audit
    assert 'sha256:' in stored_tokens
    assert '"last_input_seq": 0' in stored_tokens


def test_terminal_open_rejects_missing_scope_and_stale_epoch(tmp_path: Path) -> None:
    service = _service(_FakeCcbdClient(), mobile_dir=tmp_path / 'mobile')
    pairing = service.create_pairing_payload(
        gateway_url='http://127.0.0.1:8787',
        scopes=('view', 'focus'),
    )
    _, claim = service.dispatch_post(
        '/v1/pairing/claim',
        {
            'pairing_code': str(pairing['pairing_code']),
            'device_name': 'Pixel Fold',
        },
    )
    view_only_token = str(claim['device_token'])
    request = {
        'schema_version': 1,
        'project_id': 'proj-demo',
        'namespace_epoch': 4,
        'target': {
            'kind': 'agent',
            'agent': 'mobile',
            'window': 'main',
            'pane_id': '%2',
        },
        'geometry': {
            'columns': 100,
            'rows': 30,
        },
    }

    with pytest.raises(MobileGatewayError) as missing:
        service.dispatch_post('/v1/projects/proj-demo/terminals', request)
    assert missing.value.status_code == 401

    with pytest.raises(MobileGatewayError) as denied:
        service.dispatch_post(
            '/v1/projects/proj-demo/terminals',
            request,
            {'Authorization': f'Bearer {view_only_token}'},
        )
    assert denied.value.status_code == 403

    terminal_pairing = service.create_pairing_payload(gateway_url='http://127.0.0.1:8787')
    _, terminal_claim = service.dispatch_post(
        '/v1/pairing/claim',
        {
            'pairing_code': str(terminal_pairing['pairing_code']),
            'device_name': 'iPad',
        },
    )
    terminal_token = str(terminal_claim['device_token'])
    stale_request = dict(request)
    stale_request['namespace_epoch'] = 3
    with pytest.raises(MobileGatewayError) as stale:
        service.dispatch_post(
            '/v1/projects/proj-demo/terminals',
            stale_request,
            {'Authorization': f'Bearer {terminal_token}'},
        )
    assert stale.value.status_code == 409


def test_terminal_websocket_streams_frames_and_rejects_replayed_input(tmp_path: Path) -> None:
    sessions: list[_FakeTerminalSession] = []

    def session_factory(target):
        session = _FakeTerminalSession(target)
        sessions.append(session)
        return session

    service = _service(
        _FakeCcbdClient(),
        mobile_dir=tmp_path / 'mobile',
        terminal_session_factory=session_factory,
    )
    pairing = service.create_pairing_payload(gateway_url='http://127.0.0.1:8787')
    _, claim = service.dispatch_post(
        '/v1/pairing/claim',
        {
            'pairing_code': str(pairing['pairing_code']),
            'device_name': 'Pixel Fold',
        },
    )
    _, handle = service.dispatch_post(
        '/v1/projects/proj-demo/terminals',
        {
            'project_id': 'proj-demo',
            'namespace_epoch': 4,
            'target': {
                'kind': 'agent',
                'agent': 'mobile',
                'window': 'main',
            },
            'geometry': {
                'columns': 100,
                'rows': 30,
            },
        },
        {'Authorization': f'Bearer {claim["device_token"]}'},
    )
    server = build_mobile_gateway_server(parse_listen_address('127.0.0.1:0'), service)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    sock = None
    try:
        thread.start()
        host, port = server.server_address[:2]
        sock = _websocket_connect(host, port, f'/v1/terminals/{handle["terminal_id"]}')
        _websocket_send_json(
            sock,
            {
                'type': 'open',
                'terminal_id': handle['terminal_id'],
                'token': handle['terminal_token'],
            },
        )

        output = _websocket_read_until(sock, 'output')
        assert output['seq'] == 1
        assert base64.b64decode(str(output['bytes_b64'])) == b'hello'
        assert sessions
        assert sessions[0].target.socket_path == '/tmp/ccb-demo/tmux.sock'
        assert sessions[0].target.session_name == 'ccb-demo'
        assert sessions[0].target.geometry.columns == 100
        assert sessions[0].target.geometry.rows == 30

        _websocket_send_json(sock, {'type': 'input', 'seq': 1, 'bytes_b64': base64.b64encode(b'a').decode('ascii')})
        _wait_for(lambda: sessions[0].writes == [b'a'])
        _websocket_send_json(sock, {'type': 'paste', 'seq': 2, 'text': 'hello paste'})
        _wait_for(lambda: sessions[0].pastes == ['hello paste'])
        _websocket_send_json(sock, {'type': 'resize', 'columns': 120, 'rows': 36})
        _wait_for(lambda: len(sessions[0].resizes) == 1)
        assert sessions[0].resizes[0].columns == 120
        assert sessions[0].resizes[0].rows == 36

        _websocket_send_json(sock, {'type': 'input', 'seq': 2, 'bytes_b64': base64.b64encode(b'b').decode('ascii')})
        error = _websocket_read_until(sock, 'error')
        assert error['code'] == 'replayed_sequence'
        closed = _websocket_read_until(sock, 'closed')
        assert closed['reason'] == 'replayed_sequence'
        _wait_for(lambda: sessions[0].closed)

        stored_tokens = (tmp_path / 'mobile' / 'terminal-tokens.jsonl').read_text(encoding='utf-8')
        assert str(handle['terminal_token']) not in stored_tokens
        assert '"last_input_seq": 2' in stored_tokens
        assert '"closed_reason": "replayed_sequence"' in stored_tokens
    finally:
        if sock is not None:
            sock.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_terminal_websocket_resumes_after_transport_disconnect_with_matching_cursor(tmp_path: Path) -> None:
    sessions: list[_FakeTerminalSession] = []

    def session_factory(target):
        session = _FakeTerminalSession(target)
        sessions.append(session)
        return session

    service = _service(
        _FakeCcbdClient(),
        mobile_dir=tmp_path / 'mobile',
        terminal_session_factory=session_factory,
    )
    pairing = service.create_pairing_payload(gateway_url='http://127.0.0.1:8787')
    _, claim = service.dispatch_post('/v1/pairing/claim', {'pairing_code': str(pairing['pairing_code'])})
    _, handle = service.dispatch_post(
        '/v1/projects/proj-demo/terminals',
        {
            'project_id': 'proj-demo',
            'namespace_epoch': 4,
            'target': {'kind': 'agent', 'agent': 'mobile', 'window': 'main'},
        },
        {'Authorization': f'Bearer {claim["device_token"]}'},
    )
    server = build_mobile_gateway_server(parse_listen_address('127.0.0.1:0'), service)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    sock = None
    resumed_sock = None
    try:
        thread.start()
        host, port = server.server_address[:2]
        sock = _websocket_connect(host, port, f'/v1/terminals/{handle["terminal_id"]}')
        _websocket_send_json(
            sock,
            {
                'type': 'open',
                'terminal_id': handle['terminal_id'],
                'token': handle['terminal_token'],
            },
        )
        first_output = _websocket_read_until(sock, 'output')
        assert first_output['seq'] == 1
        sock.close()
        sock = None
        _wait_for(lambda: sessions[0].closed)
        stored_after_disconnect = (tmp_path / 'mobile' / 'terminal-tokens.jsonl').read_text(encoding='utf-8')
        assert '"last_output_seq": 1' in stored_after_disconnect
        assert '"disconnected_reason": "transport_disconnected"' in stored_after_disconnect
        assert '"closed_reason"' not in stored_after_disconnect

        resumed_sock = _websocket_connect(host, port, f'/v1/terminals/{handle["terminal_id"]}')
        _websocket_send_json(
            resumed_sock,
            {
                'type': 'open',
                'terminal_id': handle['terminal_id'],
                'token': handle['terminal_token'],
                'resume_cursor': 1,
            },
        )
        open_ack = _websocket_read_until(resumed_sock, 'open')
        assert open_ack['resume_cursor'] == 1
        assert open_ack['last_input_seq'] == 0
        second_output = _websocket_read_until(resumed_sock, 'output')
        assert second_output['seq'] == 2
        assert len(sessions) == 2

        _websocket_send_json(resumed_sock, {'type': 'closed', 'reason': 'client_closed'})
        closed = _websocket_read_until(resumed_sock, 'closed')
        assert closed['reason'] == 'client_closed'
        _wait_for(lambda: sessions[1].closed)
        stored_after_close = (tmp_path / 'mobile' / 'terminal-tokens.jsonl').read_text(encoding='utf-8')
        assert '"last_output_seq": 2' in stored_after_close
        assert '"closed_reason": "client_closed"' in stored_after_close
    finally:
        if sock is not None:
            sock.close()
        if resumed_sock is not None:
            resumed_sock.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_terminal_websocket_rejects_stale_resume_cursor(tmp_path: Path) -> None:
    sessions: list[_FakeTerminalSession] = []
    service = _service(
        _FakeCcbdClient(),
        mobile_dir=tmp_path / 'mobile',
        terminal_session_factory=lambda target: sessions.append(_FakeTerminalSession(target)) or sessions[-1],
    )
    pairing = service.create_pairing_payload(gateway_url='http://127.0.0.1:8787')
    _, claim = service.dispatch_post('/v1/pairing/claim', {'pairing_code': str(pairing['pairing_code'])})
    _, handle = service.dispatch_post(
        '/v1/projects/proj-demo/terminals',
        {
            'project_id': 'proj-demo',
            'namespace_epoch': 4,
            'target': {'kind': 'agent', 'agent': 'mobile', 'window': 'main'},
        },
        {'Authorization': f'Bearer {claim["device_token"]}'},
    )
    server = build_mobile_gateway_server(parse_listen_address('127.0.0.1:0'), service)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    sock = None
    stale_sock = None
    try:
        thread.start()
        host, port = server.server_address[:2]
        sock = _websocket_connect(host, port, f'/v1/terminals/{handle["terminal_id"]}')
        _websocket_send_json(
            sock,
            {
                'type': 'open',
                'terminal_id': handle['terminal_id'],
                'token': handle['terminal_token'],
            },
        )
        assert _websocket_read_until(sock, 'output')['seq'] == 1
        sock.close()
        sock = None
        _wait_for(lambda: sessions[0].closed)

        stale_sock = _websocket_connect(host, port, f'/v1/terminals/{handle["terminal_id"]}')
        _websocket_send_json(
            stale_sock,
            {
                'type': 'open',
                'terminal_id': handle['terminal_id'],
                'token': handle['terminal_token'],
                'resume_cursor': 0,
            },
        )
        error = _websocket_read_until(stale_sock, 'error')
        assert error['code'] == 'stale_resume_cursor'
        closed = _websocket_read_until(stale_sock, 'closed')
        assert closed['reason'] == 'stale_resume_cursor'
        assert len(sessions) == 1
    finally:
        if sock is not None:
            sock.close()
        if stale_sock is not None:
            stale_sock.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_terminal_websocket_rejects_invalid_open_token(tmp_path: Path) -> None:
    sessions: list[_FakeTerminalSession] = []
    service = _service(
        _FakeCcbdClient(),
        mobile_dir=tmp_path / 'mobile',
        terminal_session_factory=lambda target: sessions.append(_FakeTerminalSession(target)) or sessions[-1],
    )
    pairing = service.create_pairing_payload(gateway_url='http://127.0.0.1:8787')
    _, claim = service.dispatch_post('/v1/pairing/claim', {'pairing_code': str(pairing['pairing_code'])})
    _, handle = service.dispatch_post(
        '/v1/projects/proj-demo/terminals',
        {
            'project_id': 'proj-demo',
            'namespace_epoch': 4,
            'target': {'kind': 'agent', 'agent': 'mobile', 'window': 'main'},
        },
        {'Authorization': f'Bearer {claim["device_token"]}'},
    )
    server = build_mobile_gateway_server(parse_listen_address('127.0.0.1:0'), service)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    sock = None
    try:
        thread.start()
        host, port = server.server_address[:2]
        sock = _websocket_connect(host, port, f'/v1/terminals/{handle["terminal_id"]}')
        _websocket_send_json(
            sock,
            {
                'type': 'open',
                'terminal_id': handle['terminal_id'],
                'token': 'wrong-token',
            },
        )
        error = _websocket_read_until(sock, 'error')
        assert error['code'] == 'invalid_token'
        assert sessions == []
    finally:
        if sock is not None:
            sock.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_focus_routes_require_focus_scope_and_return_redacted_project_view(tmp_path: Path) -> None:
    fake = _FakeCcbdClient()
    service = _service(fake, mobile_dir=tmp_path / 'mobile')
    pairing = service.create_pairing_payload(gateway_url='http://127.0.0.1:8787')
    _, claim = service.dispatch_post(
        '/v1/pairing/claim',
        {
            'pairing_code': str(pairing['pairing_code']),
            'device_name': 'Pixel Fold',
        },
    )
    token = str(claim['device_token'])

    status, focused = service.dispatch_post(
        '/v1/projects/proj-demo/focus-agent',
        {
            'agent': 'mobile',
            'namespace_epoch': 4,
        },
        {'Authorization': f'Bearer {token}'},
    )
    assert status == 200
    assert focused['focus']['focused'] is True
    assert focused['focus']['agent'] == 'mobile'
    assert focused['view']['namespace']['epoch'] == 4
    assert 'socket_path' not in focused['view']['namespace']
    assert 'session_name' not in focused['view']['namespace']

    status, focused = service.dispatch_post(
        '/v1/projects/proj-demo/focus-window',
        {
            'window': 'main',
            'namespace_epoch': 4,
        },
        {'Authorization': f'Bearer {token}'},
    )
    assert status == 200
    assert focused['focus']['kind'] == 'window'
    assert ('project_focus_agent', 'mobile', 4) in fake.calls
    assert ('project_focus_window', 'main', 4) in fake.calls


def test_focus_routes_reject_missing_or_view_only_device_scope(tmp_path: Path) -> None:
    service = _service(_FakeCcbdClient(), mobile_dir=tmp_path / 'mobile')
    pairing = service.create_pairing_payload(
        gateway_url='http://127.0.0.1:8787',
        scopes=('view',),
    )
    _, claim = service.dispatch_post(
        '/v1/pairing/claim',
        {
            'pairing_code': str(pairing['pairing_code']),
            'device_name': 'Pixel Fold',
        },
    )
    token = str(claim['device_token'])

    with pytest.raises(MobileGatewayError) as missing:
        service.dispatch_post(
            '/v1/projects/proj-demo/focus-agent',
            {'agent': 'mobile', 'namespace_epoch': 4},
        )
    assert missing.value.status_code == 401

    with pytest.raises(MobileGatewayError) as denied:
        service.dispatch_post(
            '/v1/projects/proj-demo/focus-agent',
            {'agent': 'mobile', 'namespace_epoch': 4},
            {'Authorization': f'Bearer {token}'},
        )
    assert denied.value.status_code == 403


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


def _websocket_connect(host: str, port: int, path: str) -> socket.socket:
    sock = socket.create_connection((host, port), timeout=2)
    key = base64.b64encode(os.urandom(16)).decode('ascii')
    request = (
        f'GET {path} HTTP/1.1\r\n'
        f'Host: {host}:{port}\r\n'
        'Upgrade: websocket\r\n'
        'Connection: Upgrade\r\n'
        f'Sec-WebSocket-Key: {key}\r\n'
        'Sec-WebSocket-Version: 13\r\n'
        '\r\n'
    )
    sock.sendall(request.encode('ascii'))
    response = b''
    while b'\r\n\r\n' not in response:
        response += sock.recv(4096)
    assert b' 101 ' in response.split(b'\r\n', 1)[0]
    return sock


def _websocket_send_json(sock: socket.socket, payload: dict[str, object]) -> None:
    body = json.dumps(payload).encode('utf-8')
    header = bytearray([0x81])
    length = len(body)
    if length < 126:
        header.append(0x80 | length)
    elif length <= 0xFFFF:
        header.append(0x80 | 126)
        header.extend(struct.pack('!H', length))
    else:
        header.append(0x80 | 127)
        header.extend(struct.pack('!Q', length))
    mask = b'\x01\x02\x03\x04'
    encoded = bytes(byte ^ mask[index % 4] for index, byte in enumerate(body))
    sock.sendall(bytes(header) + mask + encoded)


def _websocket_read_json(sock: socket.socket) -> dict[str, object]:
    sock.settimeout(2)
    first = _recv_exact(sock, 2)
    opcode = first[0] & 0x0F
    length = first[1] & 0x7F
    if length == 126:
        length = struct.unpack('!H', _recv_exact(sock, 2))[0]
    elif length == 127:
        length = struct.unpack('!Q', _recv_exact(sock, 8))[0]
    payload = _recv_exact(sock, length)
    if opcode == 0x8:
        return {'type': 'closed', 'reason': 'websocket_closed'}
    decoded = json.loads(payload.decode('utf-8'))
    assert isinstance(decoded, dict)
    return {str(key): value for key, value in decoded.items()}


def _websocket_read_until(sock: socket.socket, frame_type: str) -> dict[str, object]:
    deadline = time.time() + 2
    while time.time() < deadline:
        frame = _websocket_read_json(sock)
        if frame.get('type') == frame_type:
            return frame
    raise AssertionError(f'websocket frame not received: {frame_type}')


def _recv_exact(sock: socket.socket, length: int) -> bytes:
    data = b''
    while len(data) < length:
        chunk = sock.recv(length - len(data))
        if not chunk:
            raise AssertionError('socket closed before expected bytes')
        data += chunk
    return data


def _wait_for(predicate) -> None:
    deadline = time.time() + 2
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError('condition was not reached')
