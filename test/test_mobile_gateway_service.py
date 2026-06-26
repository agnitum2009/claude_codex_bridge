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
from urllib.request import Request, urlopen

import pytest

from mobile_gateway import (
    MobileGatewayError,
    MobileGatewayPairingError,
    MobileGatewayPairingStore,
    MobileGatewayProject,
    MobileGatewayProjectRegistry,
    MobileGatewayService,
    build_mobile_gateway_server,
    parse_listen_address,
)


class _FakeCcbdClient:
    def __init__(
        self,
        *,
        project_id: str = 'proj-demo',
        project_root: str = '/srv/demo',
        display_name: str = 'demo',
    ) -> None:
        self.project_id = project_id
        self.project_root = project_root
        self.display_name = display_name
        self.calls: list[tuple[object, ...]] = []

    def ping(self, target: str = 'ccbd') -> dict[str, object]:
        self.calls.append(('ping', target))
        return {
            'project_id': self.project_id,
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
                    'id': self.project_id,
                    'root': self.project_root,
                    'display_name': self.display_name,
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
                'content': {
                    'items': [
                        {
                            'id': 'content-1',
                            'kind': 'markdown',
                            'format': 'markdown',
                            'agent': 'mobile',
                            'title': 'Agent reply',
                            'text': 'Ready for the next task.',
                            'source': 'reply',
                        }
                    ],
                },
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

    def stop_all(self, *, force: bool = False) -> dict[str, object]:
        self.calls.append(('stop_all', force))
        return {
            'stopped': True,
            'force': force,
            'summary': {'agents': ['mobile']},
        }

    def submit(self, request) -> dict[str, object]:
        record = request.to_record()
        self.calls.append(('submit', record))
        return {
            'job_id': 'job_mobile_1',
            'agent_name': record['to_agent'],
            'status': 'queued',
            'accepted_at': '2026-06-18T00:00:01Z',
        }


class _FailingCcbdClient:
    def __init__(self, message: str = 'ccbd unavailable at /tmp/private.sock') -> None:
        self.message = message
        self.calls: list[tuple[object, ...]] = []

    def ping(self, target: str = 'ccbd') -> dict[str, object]:
        self.calls.append(('ping', target))
        raise RuntimeError(self.message)

    def project_view(self, *, schema_version: int = 1) -> dict[str, object]:
        self.calls.append(('project_view', schema_version))
        raise RuntimeError(self.message)


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


class _FakeCcbdClientWithConversationComms(_FakeCcbdClient):
    def project_view(self, *, schema_version: int = 1) -> dict[str, object]:
        payload = super().project_view(schema_version=schema_version)
        payload['view']['comms'] = [
            {
                'id': 'job_mobile_reply',
                'sender': 'user',
                'target': 'mobile',
                'status': 'completed',
                'business_status': 'replied',
                'created_at': '2026-06-18T00:00:02Z',
                'body_preview': 'question from phone',
                'attachments': [
                    {
                        'file_id': 'mobile-file-1',
                        'file_name': 'probe.txt',
                        'mime_type': 'text/plain',
                        'size_bytes': 11,
                        'kind': 'document',
                    }
                ],
            },
            {
                'id': 'job_mobile_old_reply',
                'sender': 'user',
                'target': 'mobile',
                'status': 'completed',
                'business_status': 'replied',
                'created_at': '2026-06-18T00:00:01Z',
                'body_preview': 'older question from phone',
            },
            {
                'id': 'job_other_reply',
                'sender': 'user',
                'target': 'other',
                'status': 'completed',
                'business_status': 'replied',
                'body_preview': 'wrong target',
            },
        ]
        return payload


def _service(
    fake: _FakeCcbdClient,
    *,
    project_root: Path | None = None,
    mobile_dir: Path | None = None,
    project_registry: MobileGatewayProjectRegistry | None = None,
    terminal_session_factory=None,
    terminal_history_factory=None,
) -> MobileGatewayService:
    return MobileGatewayService(
        project_id='proj-demo',
        project_root=project_root or Path('/srv/demo'),
        ccbd_client_factory=lambda: fake,
        mobile_dir=mobile_dir,
        project_registry=project_registry,
        clock=lambda: '2026-06-18T00:00:00Z',
        terminal_session_factory=terminal_session_factory,
        terminal_history_factory=terminal_history_factory,
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


def test_projects_payload_lists_registry_projects_without_exposing_tmux_socket() -> None:
    first = _FakeCcbdClient(
        project_id='proj-one',
        project_root='/srv/one',
        display_name='one',
    )
    second = _FakeCcbdClient(
        project_id='proj-two',
        project_root='/srv/two',
        display_name='two',
    )
    service = _service(
        first,
        project_registry=MobileGatewayProjectRegistry(
            [
                MobileGatewayProject(
                    project_id='proj-one',
                    project_root=Path('/srv/one'),
                    ccbd_client_factory=lambda: first,
                ),
                MobileGatewayProject(
                    project_id='proj-two',
                    project_root=Path('/srv/two'),
                    ccbd_client_factory=lambda: second,
                ),
            ]
        ),
    )

    projects = service.projects_payload()

    assert [item['id'] for item in projects['projects']] == [
        'proj-one',
        'proj-two',
    ]
    assert projects['projects'][0]['display_name'] == 'one'
    assert projects['projects'][0]['root'] == '/srv/one'
    assert projects['projects'][1]['display_name'] == 'two'
    assert projects['projects'][1]['root'] == '/srv/two'
    assert 'tmux.sock' not in json.dumps(projects)
    assert first.calls == [('ping', 'ccbd')]
    assert second.calls == [('ping', 'ccbd')]


def test_projects_payload_keeps_healthy_projects_when_registry_has_unreachable_project() -> None:
    healthy = _FakeCcbdClient(
        project_id='proj-one',
        project_root='/srv/one',
        display_name='one',
    )
    stale = _FailingCcbdClient()
    service = _service(
        healthy,
        project_registry=MobileGatewayProjectRegistry(
            [
                MobileGatewayProject(
                    project_id='proj-one',
                    project_root=Path('/srv/one'),
                    ccbd_client_factory=lambda: healthy,
                ),
                MobileGatewayProject(
                    project_id='proj-stale',
                    project_root=Path('/srv/stale'),
                    display_name='stale',
                    ccbd_client_factory=lambda: stale,
                ),
            ]
        ),
    )

    projects = service.projects_payload()

    assert [item['id'] for item in projects['projects']] == [
        'proj-one',
        'proj-stale',
    ]
    assert projects['projects'][0]['health'] == 'healthy'
    assert projects['projects'][0]['mount_state'] == 'mounted'
    assert projects['projects'][1]['display_name'] == 'stale'
    assert projects['projects'][1]['root'] == '/srv/stale'
    assert projects['projects'][1]['health'] == 'unreachable'
    assert projects['projects'][1]['mount_state'] == 'unavailable'
    assert projects['projects'][1]['error'] == 'project unavailable'
    assert '/tmp/private.sock' not in json.dumps(projects)
    assert healthy.calls == [('ping', 'ccbd')]
    assert stale.calls == [('ping', 'ccbd')]


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


def test_project_view_routes_to_matching_registry_project() -> None:
    first = _FakeCcbdClient(
        project_id='proj-one',
        project_root='/srv/one',
        display_name='one',
    )
    second = _FakeCcbdClient(
        project_id='proj-two',
        project_root='/srv/two',
        display_name='two',
    )
    service = _service(
        first,
        project_registry=MobileGatewayProjectRegistry(
            [
                MobileGatewayProject(
                    project_id='proj-one',
                    project_root=Path('/srv/one'),
                    ccbd_client_factory=lambda: first,
                ),
                MobileGatewayProject(
                    project_id='proj-two',
                    project_root=Path('/srv/two'),
                    ccbd_client_factory=lambda: second,
                ),
            ]
        ),
    )

    payload = service.project_view_payload('proj-two')

    assert payload['view']['project']['id'] == 'proj-two'
    assert payload['view']['project']['root'] == '/srv/two'
    assert 'socket_path' not in payload['view']['namespace']
    assert first.calls == []
    assert second.calls == [('project_view', 1)]


def test_terminal_history_reads_selected_agent_scrollback_without_leaking_tmux_evidence(tmp_path: Path) -> None:
    targets = []

    def history_factory(target):
        targets.append(target)
        return {
            'history_scope': 'tmux_scrollback',
            'source_pane_id': target.pane_id,
            'blocks': [
                {
                    'id': 'history-1',
                    'type': 'command',
                    'title': 'Command',
                    'text': '$ flutter test',
                },
                {
                    'id': 'history-2',
                    'type': 'log',
                    'title': 'Log',
                    'text': '54 tests passed',
                },
            ],
        }

    service = _service(
        _FakeCcbdClient(),
        mobile_dir=tmp_path / 'mobile',
        terminal_history_factory=history_factory,
    )
    pairing = service.create_pairing_payload(gateway_url='http://127.0.0.1:8787')
    _, claim = service.dispatch_post(
        '/v1/pairing/claim',
        {'pairing_code': str(pairing['pairing_code']), 'device_name': 'Pixel Fold'},
    )

    status, payload = service.dispatch_get(
        '/v1/projects/proj-demo/terminal-history?agent=mobile&namespace_epoch=4&max_lines=120',
        {'Authorization': f'Bearer {claim["device_token"]}'},
    )

    assert status == 200
    assert payload['status'] == 'ok'
    history = payload['terminal_history']
    assert history['agent'] == 'mobile'
    assert history['history_scope'] == 'tmux_scrollback'
    assert history['source_pane_id'] == '%2'
    assert history['generated_at'] == '2026-06-18T00:00:00Z'
    assert history['blocks'][0]['type'] == 'command'
    assert targets[0].project_id == 'proj-demo'
    assert targets[0].namespace_epoch == 4
    assert targets[0].agent == 'mobile'
    assert targets[0].window == 'main'
    assert targets[0].pane_id == '%2'
    assert targets[0].socket_path == '/tmp/ccb-demo/tmux.sock'
    assert targets[0].session_name == 'ccb-demo'
    assert targets[0].max_lines == 120
    public_json = json.dumps(payload)
    assert '/tmp/ccb-demo/tmux.sock' not in public_json
    assert 'ccb-demo' not in public_json


def test_terminal_history_requires_view_auth_and_fresh_epoch(tmp_path: Path) -> None:
    service = _service(_FakeCcbdClient(), mobile_dir=tmp_path / 'mobile')

    with pytest.raises(MobileGatewayError) as missing_auth:
        service.dispatch_get('/v1/projects/proj-demo/terminal-history?agent=mobile&namespace_epoch=4')
    assert missing_auth.value.status_code == 401

    pairing = service.create_pairing_payload(gateway_url='http://127.0.0.1:8787')
    _, claim = service.dispatch_post(
        '/v1/pairing/claim',
        {'pairing_code': str(pairing['pairing_code'])},
    )
    token = str(claim['device_token'])
    with pytest.raises(MobileGatewayError) as stale:
        service.dispatch_get(
            '/v1/projects/proj-demo/terminal-history?agent=mobile&namespace_epoch=3',
            {'Authorization': f'Bearer {token}'},
        )
    assert stale.value.status_code == 409

    with pytest.raises(MobileGatewayError) as bad_epoch:
        service.dispatch_get(
            '/v1/projects/proj-demo/terminal-history?agent=mobile&namespace_epoch=bad',
            {'Authorization': f'Bearer {token}'},
        )
    assert bad_epoch.value.status_code == 400


def test_agent_conversation_reads_project_view_without_terminal_scope(tmp_path: Path) -> None:
    fake = _FakeCcbdClient()
    service = _service(fake, mobile_dir=tmp_path / 'mobile')
    pairing = service.create_pairing_payload(
        gateway_url='http://127.0.0.1:8787',
        scopes=('view',),
    )
    _, claim = service.dispatch_post('/v1/pairing/claim', {'pairing_code': str(pairing['pairing_code'])})

    status, payload = service.dispatch_get(
        '/v1/projects/proj-demo/agents/mobile/conversation?namespace_epoch=4&limit=20',
        {'Authorization': f'Bearer {claim["device_token"]}'},
    )

    assert status == 200
    conversation = payload['conversation']
    assert conversation['project_id'] == 'proj-demo'
    assert conversation['agent'] == 'mobile'
    assert conversation['namespace_epoch'] == 4
    assert [item['kind'] for item in conversation['items']] == [
        'status_event',
        'agent_reply',
    ]
    assert conversation['items'][1]['body'] == 'Ready for the next task.'
    public_json = json.dumps(payload)
    assert 'terminal_input' not in public_json
    assert 'tmux.sock' not in public_json
    assert 'ccb-demo' not in public_json
    assert fake.calls == [('project_view', 1)]


def test_agent_conversation_includes_completed_comms_reply_preview(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo'
    snapshot_dir = project_root / '.ccb' / 'ccbd' / 'snapshots'
    snapshot_dir.mkdir(parents=True)
    (snapshot_dir / 'job_mobile_reply.json').write_text(
        json.dumps(
            {
                'latest_decision': {
                    'reply': 'answer from mobile_probe',
                },
                'latest_reply_preview': 'preview fallback',
            }
        ),
        encoding='utf-8',
    )
    (snapshot_dir / 'job_mobile_old_reply.json').write_text(
        json.dumps(
            {
                'latest_decision': {
                    'reply': 'older answer from mobile_probe',
                },
            }
        ),
        encoding='utf-8',
    )
    service = _service(
        _FakeCcbdClientWithConversationComms(),
        project_root=project_root,
        mobile_dir=tmp_path / 'mobile',
    )
    pairing = service.create_pairing_payload(
        gateway_url='http://127.0.0.1:8787',
        scopes=('view',),
    )
    _, claim = service.dispatch_post(
        '/v1/pairing/claim',
        {'pairing_code': str(pairing['pairing_code'])},
    )

    status, payload = service.dispatch_get(
        '/v1/projects/proj-demo/agents/mobile/conversation?namespace_epoch=4&limit=20',
        {'Authorization': f'Bearer {claim["device_token"]}'},
    )

    assert status == 200
    items = payload['conversation']['items']
    assert [item['id'] for item in items] == [
        'status-mobile',
        'reply-content-1',
        'user-job_mobile_old_reply',
        'reply-job_mobile_old_reply',
        'user-job_mobile_reply',
        'reply-job_mobile_reply',
    ]
    assert items[2]['kind'] == 'user_message'
    assert items[2]['body'] == 'older question from phone'
    assert items[3]['kind'] == 'agent_reply'
    assert items[3]['body'] == 'older answer from mobile_probe'
    assert items[4]['kind'] == 'user_message'
    assert items[4]['body'] == 'question from phone'
    assert items[4]['attachments'][0]['file_id'] == 'mobile-file-1'
    assert items[4]['attachments'][0]['file_name'] == 'probe.txt'
    assert items[5]['kind'] == 'agent_reply'
    assert items[5]['body'] == 'answer from mobile_probe'
    assert 'wrong target' not in json.dumps(payload)


def test_agent_conversation_maps_artifact_links_to_download_attachments(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo'
    snapshot_dir = project_root / '.ccb' / 'ccbd' / 'snapshots'
    snapshot_dir.mkdir(parents=True)
    file_id = 'mobile-file-backend-artifact'
    (snapshot_dir / 'job_mobile_reply.json').write_text(
        json.dumps(
            {
                'latest_decision': {
                    'reply': (
                        'Generated files:\n'
                        f'- [artifact.txt](ccb-artifact://{file_id})'
                    ),
                },
            }
        ),
        encoding='utf-8',
    )
    file_dir = (
        project_root
        / '.ccb'
        / 'ccbd'
        / 'mobile'
        / 'files'
        / 'proj-demo'
        / 'mobile'
        / file_id
    )
    file_dir.mkdir(parents=True)
    (file_dir / 'metadata.json').write_text(
        json.dumps(
            {
                'file_id': file_id,
                'file_name': 'artifact.txt',
                'mime_type': 'text/plain',
                'size_bytes': 12,
            }
        ),
        encoding='utf-8',
    )
    service = _service(
        _FakeCcbdClientWithConversationComms(),
        project_root=project_root,
        mobile_dir=tmp_path / 'mobile',
    )
    pairing = service.create_pairing_payload(
        gateway_url='http://127.0.0.1:8787',
        scopes=('view',),
    )
    _, claim = service.dispatch_post(
        '/v1/pairing/claim',
        {'pairing_code': str(pairing['pairing_code'])},
    )

    status, payload = service.dispatch_get(
        '/v1/projects/proj-demo/agents/mobile/conversation?namespace_epoch=4&limit=20',
        {'Authorization': f'Bearer {claim["device_token"]}'},
    )

    assert status == 200
    reply = next(
        item
        for item in payload['conversation']['items']
        if item['id'] == 'reply-job_mobile_reply'
    )
    assert reply['attachments'] == [
        {
            'file_id': file_id,
            'file_name': 'artifact.txt',
            'mime_type': 'text/plain',
            'size_bytes': 12,
            'kind': 'document',
        }
    ]


def test_agent_conversation_maps_artifact_links_from_gateway_file_store(tmp_path: Path) -> None:
    project_root = tmp_path / 'repo'
    snapshot_dir = project_root / '.ccb' / 'ccbd' / 'snapshots'
    snapshot_dir.mkdir(parents=True)
    jobs_dir = project_root / '.ccb' / 'agents' / 'mobile'
    jobs_dir.mkdir(parents=True)
    file_store = tmp_path / 'server-mobile' / 'files'
    file_id = 'mobile-file-shared-artifact'
    (snapshot_dir / 'job_mobile_reply.json').write_text(
        json.dumps(
            {
                'latest_decision': {
                    'reply': (
                        'Generated files:\n'
                        f'- [artifact.txt](ccb-artifact://{file_id})'
                    ),
                },
            }
        ),
        encoding='utf-8',
    )
    (jobs_dir / 'jobs.jsonl').write_text(
        json.dumps(
            {
                'job_id': 'job_mobile_reply',
                'request': {
                    'route_options': {
                        'mobile_files_dir': str(file_store),
                    },
                },
            }
        )
        + '\n',
        encoding='utf-8',
    )
    file_dir = file_store / 'proj-demo' / 'mobile' / file_id
    file_dir.mkdir(parents=True)
    (file_dir / 'metadata.json').write_text(
        json.dumps(
            {
                'file_id': file_id,
                'file_name': 'artifact.txt',
                'mime_type': 'text/plain',
                'size_bytes': 12,
            }
        ),
        encoding='utf-8',
    )
    service = _service(
        _FakeCcbdClientWithConversationComms(),
        project_root=project_root,
        mobile_dir=tmp_path / 'mobile',
    )
    pairing = service.create_pairing_payload(
        gateway_url='http://127.0.0.1:8787',
        scopes=('view',),
    )
    _, claim = service.dispatch_post(
        '/v1/pairing/claim',
        {'pairing_code': str(pairing['pairing_code'])},
    )

    status, payload = service.dispatch_get(
        '/v1/projects/proj-demo/agents/mobile/conversation?namespace_epoch=4&limit=20',
        {'Authorization': f'Bearer {claim["device_token"]}'},
    )

    assert status == 200
    reply = next(
        item
        for item in payload['conversation']['items']
        if item['id'] == 'reply-job_mobile_reply'
    )
    assert reply['attachments'][0]['file_id'] == file_id
    assert reply['attachments'][0]['file_name'] == 'artifact.txt'


def test_agent_conversation_requires_view_auth_and_fresh_epoch(tmp_path: Path) -> None:
    service = _service(_FakeCcbdClient(), mobile_dir=tmp_path / 'mobile')
    pairing = service.create_pairing_payload(
        gateway_url='http://127.0.0.1:8787',
        scopes=('message_submit',),
    )
    _, claim = service.dispatch_post(
        '/v1/pairing/claim',
        {'pairing_code': str(pairing['pairing_code'])},
    )

    with pytest.raises(MobileGatewayError) as missing_auth:
        service.dispatch_get('/v1/projects/proj-demo/agents/mobile/conversation?namespace_epoch=4')
    assert missing_auth.value.status_code == 401

    with pytest.raises(MobileGatewayError) as denied:
        service.dispatch_get(
            '/v1/projects/proj-demo/agents/mobile/conversation?namespace_epoch=4',
            {'Authorization': f'Bearer {claim["device_token"]}'},
        )
    assert denied.value.status_code == 403

    view_pairing = service.create_pairing_payload(
        gateway_url='http://127.0.0.1:8787',
        scopes=('view',),
    )
    _, view_claim = service.dispatch_post(
        '/v1/pairing/claim',
        {'pairing_code': str(view_pairing['pairing_code'])},
    )
    with pytest.raises(MobileGatewayError) as stale:
        service.dispatch_get(
            '/v1/projects/proj-demo/agents/mobile/conversation?namespace_epoch=3',
            {'Authorization': f'Bearer {view_claim["device_token"]}'},
        )
    assert stale.value.status_code == 409


def test_agent_message_submit_uses_ccbd_submit_without_terminal_scope(tmp_path: Path) -> None:
    fake = _FakeCcbdClient()
    service = _service(fake, mobile_dir=tmp_path / 'mobile')
    pairing = service.create_pairing_payload(
        gateway_url='http://127.0.0.1:8787',
        scopes=('view', 'message_submit'),
    )
    _, claim = service.dispatch_post(
        '/v1/pairing/claim',
        {'pairing_code': str(pairing['pairing_code'])},
    )

    status, payload = service.dispatch_post(
        '/v1/projects/proj-demo/agents/mobile/messages',
        {
            'schema_version': 1,
            'project_id': 'proj-demo',
            'agent': 'mobile',
            'namespace_epoch': 4,
            'idempotency_key': 'mobile-msg-1',
            'body': 'continue with the next step',
            'format': 'markdown',
        },
        {'Authorization': f'Bearer {claim["device_token"]}'},
    )

    assert status == 202
    result = payload['message_submit']
    assert result['accepted'] is True
    assert result['idempotency_key'] == 'mobile-msg-1'
    assert result['job_id'] == 'job_mobile_1'
    assert result['message_id'] == 'job_mobile_1'
    assert result['state'] == 'queued'
    submit = next(call for call in fake.calls if call[0] == 'submit')[1]
    assert submit['project_id'] == 'proj-demo'
    assert submit['to_agent'] == 'mobile'
    assert submit['from_actor'] == 'user'
    assert submit['body'] == 'continue with the next step'
    assert submit['message_type'] == 'ask'
    assert submit['delivery_scope'] == 'single'
    assert submit['route_options']['idempotency_key'] == 'mobile-msg-1'
    assert submit['route_options']['source'] == 'mobile_gateway'
    assert submit['route_options']['mobile_files_dir'] == str(
        tmp_path / 'mobile' / 'files'
    )
    response_json = json.dumps(payload)
    assert 'terminal_input' not in response_json
    assert 'tmux.sock' not in response_json


def test_agent_message_submit_accepts_attachment_only_message(tmp_path: Path) -> None:
    fake = _FakeCcbdClient()
    service = _service(fake, mobile_dir=tmp_path / 'mobile')
    pairing = service.create_pairing_payload(
        gateway_url='http://127.0.0.1:8787',
        scopes=('view', 'message_submit'),
    )
    _, claim = service.dispatch_post(
        '/v1/pairing/claim',
        {'pairing_code': str(pairing['pairing_code'])},
    )

    status, payload = service.dispatch_post(
        '/v1/projects/proj-demo/agents/mobile/messages',
        {
            'schema_version': 1,
            'project_id': 'proj-demo',
            'agent': 'mobile',
            'namespace_epoch': 4,
            'idempotency_key': 'mobile-file-msg-1',
            'body': '',
            'format': 'markdown',
            'attachments': [
                {
                    'file_id': 'mobile-file-1',
                    'file_name': 'probe.txt',
                    'mime_type': 'text/plain',
                    'size_bytes': 11,
                    'kind': 'document',
                }
            ],
        },
        {'Authorization': f'Bearer {claim["device_token"]}'},
    )

    assert status == 202
    message = payload['message_submit']['message']
    assert message['body'] == ''
    assert message['attachments'][0]['file_id'] == 'mobile-file-1'
    submit = next(call for call in fake.calls if call[0] == 'submit')[1]
    assert submit['body'] == 'Uploaded attachment: probe.txt'
    assert submit['route_options']['attachments'][0]['file_name'] == 'probe.txt'


def test_agent_message_submit_requires_chat_scope_not_terminal_input(tmp_path: Path) -> None:
    service = _service(_FakeCcbdClient(), mobile_dir=tmp_path / 'mobile')
    pairing = service.create_pairing_payload(
        gateway_url='http://127.0.0.1:8787',
        scopes=('view', 'terminal_input'),
    )
    _, claim = service.dispatch_post(
        '/v1/pairing/claim',
        {'pairing_code': str(pairing['pairing_code'])},
    )

    with pytest.raises(MobileGatewayError) as denied:
        service.dispatch_post(
            '/v1/projects/proj-demo/agents/mobile/messages',
            {
                'project_id': 'proj-demo',
                'agent': 'mobile',
                'namespace_epoch': 4,
                'idempotency_key': 'mobile-msg-1',
                'body': 'continue',
            },
            {'Authorization': f'Bearer {claim["device_token"]}'},
        )
    assert denied.value.status_code == 403

    ask_pairing = service.create_pairing_payload(
        gateway_url='http://127.0.0.1:8787',
        scopes=('view', 'ask'),
    )
    _, ask_claim = service.dispatch_post(
        '/v1/pairing/claim',
        {'pairing_code': str(ask_pairing['pairing_code'])},
    )
    status, payload = service.dispatch_post(
        '/v1/projects/proj-demo/agents/mobile/messages',
        {
            'project_id': 'proj-demo',
            'agent': 'mobile',
            'namespace_epoch': 4,
            'idempotency_key': 'mobile-msg-2',
            'body': 'continue',
        },
        {'Authorization': f'Bearer {ask_claim["device_token"]}'},
    )
    assert status == 202
    assert payload['message_submit']['idempotency_key'] == 'mobile-msg-2'


def test_agent_file_upload_download_round_trips_bytes_over_http(tmp_path: Path) -> None:
    service = _service(_FakeCcbdClient(), mobile_dir=tmp_path / 'mobile')
    pairing = service.create_pairing_payload(gateway_url='http://127.0.0.1:8787')
    _, claim = service.dispatch_post(
        '/v1/pairing/claim',
        {'pairing_code': str(pairing['pairing_code'])},
    )
    token = str(claim['device_token'])
    server = build_mobile_gateway_server(parse_listen_address('127.0.0.1:0'), service)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    try:
        thread.start()
        host, port = server.server_address[:2]
        base = f'http://{host}:{port}'
        data = b'hello from mobile file route\n'
        upload_request = Request(
            f'{base}/v1/projects/proj-demo/agents/mobile/files',
            data=data,
            method='POST',
            headers={
                'Authorization': f'Bearer {token}',
                'Content-Type': 'text/plain',
                'X-Ccb-File-Name': 'probe%20file.txt',
                'Accept': 'application/json',
            },
        )

        with urlopen(upload_request) as response:
            upload = json.loads(response.read().decode('utf-8'))
        file_id = upload['file_id']
        assert upload['file_name'] == 'probe file.txt'
        assert upload['mime_type'] == 'text/plain'
        assert upload['size_bytes'] == len(data)

        download_request = Request(
            f'{base}/v1/projects/proj-demo/agents/mobile/files/{file_id}',
            headers={'Authorization': f'Bearer {token}', 'Accept': '*/*'},
        )
        with urlopen(download_request) as response:
            downloaded = response.read()
            content_type = response.headers.get('content-type')
            file_name = response.headers.get('x-ccb-file-name')

        assert downloaded == data
        assert content_type == 'text/plain'
        assert file_name == 'probe file.txt'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_agent_file_routes_use_registry_project_id(tmp_path: Path) -> None:
    first = _FakeCcbdClient(
        project_id='proj-one',
        project_root='/srv/one',
        display_name='one',
    )
    second = _FakeCcbdClient(
        project_id='proj-two',
        project_root='/srv/two',
        display_name='two',
    )
    service = _service(
        first,
        mobile_dir=tmp_path / 'mobile',
        project_registry=MobileGatewayProjectRegistry(
            [
                MobileGatewayProject(
                    project_id='proj-one',
                    project_root=Path('/srv/one'),
                    ccbd_client_factory=lambda: first,
                ),
                MobileGatewayProject(
                    project_id='proj-two',
                    project_root=Path('/srv/two'),
                    ccbd_client_factory=lambda: second,
                ),
            ]
        ),
    )
    pairing = service.create_pairing_payload(gateway_url='http://127.0.0.1:8787')
    _, claim = service.dispatch_post(
        '/v1/pairing/claim',
        {'pairing_code': str(pairing['pairing_code'])},
    )
    token = str(claim['device_token'])
    data = b'server-wide file route\n'

    status, upload = service.dispatch_file_upload(
        '/v1/projects/proj-two/agents/mobile/files',
        data,
        {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'text/plain',
            'X-Ccb-File-Name': 'server-wide.txt',
        },
    )

    assert status == 201
    file_id = str(upload['file_id'])
    metadata_path = (
        tmp_path
        / 'mobile'
        / 'files'
        / 'proj-two'
        / 'mobile'
        / file_id
        / 'metadata.json'
    )
    metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
    assert metadata['project_id'] == 'proj-two'
    assert not (tmp_path / 'mobile' / 'files' / 'proj-demo' / 'mobile' / file_id).exists()

    download_status, downloaded, headers = service.dispatch_file_download(
        f'/v1/projects/proj-two/agents/mobile/files/{file_id}',
        {'Authorization': f'Bearer {token}'},
    )

    assert download_status == 200
    assert downloaded == data
    assert headers['x-ccb-file-name'] == 'server-wide.txt'
    with pytest.raises(MobileGatewayError) as wrong_project:
        service.dispatch_file_download(
            f'/v1/projects/proj-one/agents/mobile/files/{file_id}',
            {'Authorization': f'Bearer {token}'},
        )
    assert wrong_project.value.status_code == 404
    assert first.calls == []
    assert second.calls == [('project_view', 1)]


def test_agent_file_routes_require_file_scopes(tmp_path: Path) -> None:
    service = _service(_FakeCcbdClient(), mobile_dir=tmp_path / 'mobile')
    pairing = service.create_pairing_payload(
        gateway_url='http://127.0.0.1:8787',
        scopes=('view',),
    )
    _, claim = service.dispatch_post(
        '/v1/pairing/claim',
        {'pairing_code': str(pairing['pairing_code'])},
    )
    token = str(claim['device_token'])

    with pytest.raises(MobileGatewayError) as denied:
        service.dispatch_file_upload(
            '/v1/projects/proj-demo/agents/mobile/files',
            b'hello',
            {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'text/plain',
                'X-Ccb-File-Name': 'probe.txt',
            },
        )
    assert denied.value.status_code == 403


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
    assert claim['host_profile']['scopes'] == [
        'ask',
        'content',
        'file_download',
        'file_upload',
        'focus',
        'lifecycle',
        'message_submit',
        'terminal_input',
        'view',
    ]
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
    with pytest.raises(MobileGatewayError) as denied_view:
        service.dispatch_get(
            '/v1/projects/proj-demo/view',
            {'Authorization': f'Bearer {device_token}'},
        )
    assert denied_view.value.status_code == 401


def test_host_local_device_revoke_lists_devices_and_revokes_terminal_handles(tmp_path: Path) -> None:
    store = MobileGatewayPairingStore(tmp_path / 'mobile')
    pairing = store.create_pairing_payload(
        project_id='proj-demo',
        gateway_url='https://mobile.example.com',
        route_provider='cloudflare_tunnel',
        scopes=('view', 'terminal_input'),
    )
    claim = store.claim_pairing(
        pairing_code=str(pairing['pairing_code']),
        device_name='Lost phone',
    )
    device_id = str(claim['device']['device_id'])
    handle = store.create_terminal_handle(
        project_id='proj-demo',
        device_id=device_id,
        target_epoch=4,
        target_summary={'project_id': 'proj-demo', 'agent': 'mobile'},
        geometry={'columns': 80, 'rows': 24},
    )

    assert store.list_devices()[0]['device_id'] == device_id

    result = store.revoke_device_locally(device_id=device_id)

    assert result['device']['revoked'] is True
    assert result['revoked_terminal_count'] == 1
    with pytest.raises(MobileGatewayPairingError) as denied:
        store.authenticate_terminal_token(
            terminal_id=str(handle['terminal_id']),
            terminal_token=str(handle['terminal_token']),
        )
    assert denied.value.reason == 'revoked'
    audit = (tmp_path / 'mobile' / 'audit.jsonl').read_text(encoding='utf-8')
    assert 'device_revoked' in audit
    assert 'terminal_revoked' in audit
    assert str(handle['terminal_token']) not in audit


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


def test_lifecycle_route_uses_lifecycle_scope_and_ccbd_stop_authority(tmp_path: Path) -> None:
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

    status, opened = service.dispatch_post(
        '/v1/projects/proj-demo/lifecycle',
        {'action': 'open', 'project_id': 'proj-demo'},
        {'Authorization': f'Bearer {token}'},
    )
    assert status == 200
    assert opened['lifecycle']['action'] == 'open'
    assert opened['lifecycle']['effect'] == 'opened'
    assert opened['lifecycle']['ccb_authority'] is True
    assert opened['lifecycle']['tmux_kill_server'] is False
    assert opened['view']['namespace']['epoch'] == 4
    assert 'socket_path' not in opened['view']['namespace']

    status, closed = service.dispatch_post(
        '/v1/projects/proj-demo/lifecycle',
        {'action': 'close'},
        {'Authorization': f'Bearer {token}'},
    )
    assert status == 200
    assert closed['lifecycle']['effect'] == 'mobile_view_closed'
    assert ('stop_all', False) not in fake.calls

    status, stopped = service.dispatch_post(
        '/v1/projects/proj-demo/lifecycle',
        {'action': 'stop'},
        {'Authorization': f'Bearer {token}'},
    )
    assert status == 200
    assert stopped['lifecycle']['effect'] == 'ccbd_stop_requested'
    assert stopped['lifecycle']['forced'] is False
    assert stopped['lifecycle']['result']['force'] is False
    assert stopped['lifecycle']['tmux_kill_server'] is False
    assert ('stop_all', False) in fake.calls


def test_lifecycle_route_rejects_missing_scope_and_force_stop(tmp_path: Path) -> None:
    service = _service(_FakeCcbdClient(), mobile_dir=tmp_path / 'mobile')
    pairing = service.create_pairing_payload(
        gateway_url='http://127.0.0.1:8787',
        scopes=('view', 'focus', 'terminal_input'),
    )
    _, claim = service.dispatch_post(
        '/v1/pairing/claim',
        {
            'pairing_code': str(pairing['pairing_code']),
            'device_name': 'Pixel Fold',
        },
    )
    token = str(claim['device_token'])

    with pytest.raises(MobileGatewayError) as denied:
        service.dispatch_post(
            '/v1/projects/proj-demo/lifecycle',
            {'action': 'open'},
            {'Authorization': f'Bearer {token}'},
        )
    assert denied.value.status_code == 403

    pairing = service.create_pairing_payload(
        gateway_url='http://127.0.0.1:8787',
        scopes=('view', 'lifecycle'),
    )
    _, claim = service.dispatch_post(
        '/v1/pairing/claim',
        {
            'pairing_code': str(pairing['pairing_code']),
            'device_name': 'Pixel Fold Admin',
        },
    )
    lifecycle_token = str(claim['device_token'])
    with pytest.raises(MobileGatewayError) as unsupported:
        service.dispatch_post(
            '/v1/projects/proj-demo/lifecycle',
            {'action': 'force_stop'},
            {'Authorization': f'Bearer {lifecycle_token}'},
        )
    assert unsupported.value.status_code == 400


def test_http_server_exposes_g1_get_endpoints(tmp_path: Path) -> None:
    fake = _FakeCcbdClient()
    service = _service(fake, mobile_dir=tmp_path / 'mobile')
    pairing = service.create_pairing_payload(gateway_url='http://127.0.0.1:8787')
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
        claim_request = Request(
            f'{base}/v1/pairing/claim',
            data=json.dumps({'pairing_code': pairing['pairing_code']}).encode('utf-8'),
            method='POST',
            headers={'Content-Type': 'application/json'},
        )
        with urlopen(claim_request) as response:
            claim = json.loads(response.read().decode('utf-8'))
        token = str(claim['device_token'])
        view_request = Request(
            f'{base}/v1/projects/proj-demo/view',
            headers={'Authorization': f'Bearer {token}'},
        )
        with urlopen(view_request) as response:
            view = json.loads(response.read().decode('utf-8'))

        assert health['status'] == 'ok'
        assert projects['projects'][0]['id'] == 'proj-demo'
        assert 'socket_path' not in view['view']['namespace']
        with pytest.raises(HTTPError) as excinfo:
            urlopen(
                Request(
                    f'{base}/v1/projects/other/view',
                    headers={'Authorization': f'Bearer {token}'},
                )
            )
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
