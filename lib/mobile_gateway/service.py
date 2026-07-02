from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import re
import shutil
import sqlite3
import threading
import time
from typing import Callable, Mapping
from uuid import uuid4
from urllib.parse import parse_qs, unquote, urlparse

from ccbd.socket_client import CcbdClientError
from .notifications import MobileNotificationSnapshot, MobileNotificationStore, encode_sse_event
from .pairing import MobileGatewayPairingError, MobileGatewayPairingStore
from .project_registry import MobileGatewayProject, MobileGatewayProjectRegistry
from .terminal import (
    TerminalAttachTarget,
    TerminalGeometry,
    TerminalHistoryTarget,
    PaneMessageTarget,
    create_tmux_terminal_history,
    create_tmux_terminal_session,
    send_tmux_pane_message,
)
from .websocket import WebSocketConnection, WebSocketProtocolError, accept_websocket, is_websocket_upgrade

_DEFAULT_HOST = '127.0.0.1'
_DEFAULT_PORT = 8787
_SCHEMA_VERSION = 1
_BASE_CAPABILITIES = ('http_json', 'project_view')
_PAIRING_CAPABILITIES = (
    'pairing',
    'device_tokens',
    'lifecycle',
    'focus',
    'terminal_open',
    'websocket_terminal',
    'terminal_history',
    'file_upload',
    'file_download',
    'notifications',
)
_REDACTED_NAMESPACE_KEYS = ('socket_path', 'session_name')
_DEFAULT_ROUTE_PROVIDER = 'lan'
_PROJECT_LIST_HEALTH_WORKERS = 8
_DEFAULT_PAIRING_SCOPES = (
    'view',
    'content',
    'focus',
    'ask',
    'message_submit',
    'file_upload',
    'file_download',
    'notify',
    'terminal_input',
    'lifecycle',
)
_MAX_MOBILE_FILE_BYTES = 25 * 1024 * 1024
_NOTIFICATION_STREAM_POLL_SECONDS = 1.0


@dataclass(frozen=True)
class ListenAddress:
    host: str = _DEFAULT_HOST
    port: int = _DEFAULT_PORT

    @property
    def text(self) -> str:
        return f'{self.host}:{self.port}'


class MobileGatewayError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = int(status_code)


class MobileGatewayService:
    def __init__(
        self,
        *,
        project_id: str,
        project_root: Path,
        ccbd_client_factory: Callable[[], object],
        mobile_dir: Path | None = None,
        pairing_store: MobileGatewayPairingStore | None = None,
        project_registry: MobileGatewayProjectRegistry | None = None,
        mode: str = 'loopback_current_project',
        clock: Callable[[], str] | None = None,
        terminal_session_factory: Callable[[TerminalAttachTarget], object] | None = None,
        terminal_history_factory: Callable[[TerminalHistoryTarget], dict[str, object]] | None = None,
        terminal_message_sender: Callable[[PaneMessageTarget, str], dict[str, object]] | None = None,
    ) -> None:
        self._project_id = str(project_id)
        self._project_root = Path(project_root)
        self._ccbd_client_factory = ccbd_client_factory
        self._project_registry = project_registry or MobileGatewayProjectRegistry.current_project(
            project_id=self._project_id,
            project_root=self._project_root,
            ccbd_client_factory=self._ccbd_client_factory,
        )
        self._mode = str(mode or 'loopback_current_project').strip() or 'loopback_current_project'
        self._clock = clock or _utc_now
        self._terminal_session_factory = terminal_session_factory or create_tmux_terminal_session
        self._terminal_history_factory = terminal_history_factory or create_tmux_terminal_history
        self._terminal_message_sender = terminal_message_sender or send_tmux_pane_message
        self._mobile_dir = Path(mobile_dir) if mobile_dir is not None else None
        self._pairing_store = pairing_store
        if self._pairing_store is None and mobile_dir is not None:
            self._pairing_store = MobileGatewayPairingStore(self._mobile_dir)
        self._notification_store = MobileNotificationStore(self._mobile_dir) if mobile_dir is not None else None

    @property
    def project_id(self) -> str:
        return self._project_id

    def health_payload(self) -> dict[str, object]:
        try:
            ccbd = self._client().ping('ccbd')
        except Exception as exc:
            return {
                'schema_version': _SCHEMA_VERSION,
                'status': 'degraded',
                'server_time': self._clock(),
                'mode': self._mode,
                'project_id': self._project_id,
                'capabilities': self._capabilities(),
                'ccbd': {
                    'reachable': False,
                    'error': _error_text(exc),
                },
            }
        return {
            'schema_version': _SCHEMA_VERSION,
            'status': 'ok',
            'server_time': self._clock(),
            'mode': self._mode,
            'project_id': self._project_id,
            'capabilities': self._capabilities(),
            'ccbd': _ccbd_health_summary(ccbd),
        }

    def projects_payload(self) -> dict[str, object]:
        projects: list[dict[str, object]] = []
        registry_projects = self._project_registry.projects()
        health_by_project = self._project_list_health_by_project(registry_projects)
        capabilities = self._capabilities()
        for project in registry_projects:
            ccbd = health_by_project[project.project_id]
            if not _project_available_for_mobile_list(ccbd):
                continue
            item = {
                'id': project.project_id,
                'display_name': project.public_display_name,
                'root': str(project.project_root),
                'health': str(ccbd.get('health') or 'unknown'),
                'mount_state': str(ccbd.get('mount_state') or ''),
                'capabilities': capabilities,
            }
            if ccbd.get('error'):
                item['error'] = str(ccbd.get('error') or '')
            projects.append(item)
        return {
            'schema_version': _SCHEMA_VERSION,
            'projects': projects,
        }

    def project_view_payload(self, project_id: str) -> dict[str, object]:
        project = self._require_project(project_id)
        payload = self._request_project_view(project)
        return _redact_project_view_payload(payload)

    def create_pairing_payload(
        self,
        *,
        gateway_url: str,
        route_provider: str = _DEFAULT_ROUTE_PROVIDER,
        scopes: tuple[str, ...] = _DEFAULT_PAIRING_SCOPES,
        expires_seconds: int = 10 * 60,
    ) -> dict[str, object]:
        store = self._require_pairing_store()
        store.write_gateway_state(
            project_id=self._project_id,
            gateway_url=gateway_url,
            route_provider=route_provider,
            capabilities=self._capabilities(),
        )
        return store.create_pairing_payload(
            project_id=self._project_id,
            gateway_url=gateway_url,
            route_provider=route_provider,
            scopes=scopes,
            expires_seconds=expires_seconds,
        )

    def dispatch_get(self, path: str, headers: Mapping[str, object] | None = None) -> tuple[int, dict[str, object]]:
        parsed = urlparse(path)
        route = parsed.path.rstrip('/') or '/'
        if route == '/v1/health':
            status = 200
            payload = self.health_payload()
            if payload.get('status') == 'degraded':
                status = 503
            return status, payload
        if route == '/v1/projects':
            return 200, self.projects_payload()
        prefix = '/v1/projects/'
        suffix = '/view'
        if route.startswith(prefix) and route.endswith(suffix):
            project_id = unquote(route[len(prefix):-len(suffix)].strip('/'))
            self._authenticate(headers, required_scopes=('view',))
            return 200, self.project_view_payload(project_id)
        history_suffix = '/terminal-history'
        if route.startswith(prefix) and route.endswith(history_suffix):
            project_id = unquote(route[len(prefix):-len(history_suffix)].strip('/'))
            return 200, self.terminal_history_payload(
                project_id,
                query=parse_qs(parsed.query, keep_blank_values=True),
                headers=headers,
            )
        conversation_route = _parse_project_agent_route(route, suffix='conversation')
        if conversation_route is not None:
            project_id, agent = conversation_route
            return 200, self.agent_conversation_payload(
                project_id,
                agent=agent,
                query=parse_qs(parsed.query, keep_blank_values=True),
                headers=headers,
            )
        if route == '/v1/devices/me':
            device = self._authenticate(headers, required_scopes=('view',))
            return 200, {
                'schema_version': _SCHEMA_VERSION,
                'status': 'ok',
                'device': device.public_payload(),
            }
        raise MobileGatewayError('not found', status_code=404)

    def notification_stream_target_from_path(self, path: str) -> bool:
        parsed = urlparse(path)
        route = parsed.path.rstrip('/') or '/'
        return route == '/v1/mobile/notifications'

    def notification_stream_once_from_path(self, path: str) -> bool:
        parsed = urlparse(path)
        query = parse_qs(parsed.query, keep_blank_values=True)
        once = str(_query_text(query, 'once') or '').strip().lower()
        return once in {'1', 'true', 'yes'}

    def notification_events_since(
        self,
        path: str = '/v1/mobile/notifications',
        headers: Mapping[str, object] | None = None,
        *,
        last_event_id: str | None = None,
    ) -> list[dict[str, object]]:
        if not self.notification_stream_target_from_path(path):
            raise MobileGatewayError('not found', status_code=404)
        parsed = urlparse(path)
        query = parse_qs(parsed.query, keep_blank_values=True)
        self._authenticate(headers, required_scopes=('notify',))
        store = self._require_notification_store()
        store.sync_snapshots(self._notification_snapshots())
        cursor = (
            last_event_id
            if last_event_id is not None
            else _query_text(query, 'last_event_id') or _header_value(headers, 'last-event-id')
        )
        return [event.to_payload() for event in store.events_since(cursor)]

    def terminal_history_payload(
        self,
        project_id: str,
        *,
        query: Mapping[str, object],
        headers: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        project = self._require_project(project_id)
        self._authenticate(headers, required_scopes=('view',))
        view_payload = self._request_project_view(project)
        target = _terminal_history_target(
            project_id=project.project_id,
            view_payload=view_payload,
            agent=_query_text(query, 'agent'),
            namespace_epoch=_query_int(query, 'namespace_epoch'),
            max_lines=_query_int(query, 'max_lines') or 200,
        )
        try:
            history = dict(self._terminal_history_factory(target) or {})
        except Exception as exc:
            raise MobileGatewayError(_error_text(exc), status_code=503) from exc
        history.setdefault('agent', target.agent)
        history.setdefault('history_scope', 'tmux_scrollback')
        history.setdefault('source_pane_id', target.pane_id)
        history.setdefault('generated_at', self._clock())
        history.setdefault('stale', False)
        history.setdefault('blocks', [])
        return {
            'schema_version': _SCHEMA_VERSION,
            'status': 'ok',
            'project_id': project.project_id,
            'terminal_history': history,
        }

    def agent_conversation_payload(
        self,
        project_id: str,
        *,
        agent: str,
        query: Mapping[str, object],
        headers: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        project = self._require_project(project_id)
        self._authenticate(headers, required_scopes=('view',))
        view_payload = self._request_project_view(project)
        target = _validate_agent_conversation_target(
            project_id=project.project_id,
            view_payload=view_payload,
            agent=agent,
            namespace_epoch=_query_int(query, 'namespace_epoch'),
        )
        limit = min(200, max(1, _query_int(query, 'limit') or 50))
        terminal_history = self._agent_terminal_history_for_conversation(
            project_id=project.project_id,
            view_payload=view_payload,
            agent=str(target['agent']),
            namespace_epoch=int(target['namespace_epoch']),
        )
        page = _agent_conversation_page(
            _agent_conversation_items(
                view_payload,
                project_id=project.project_id,
                agent=target['agent'],
                namespace_epoch=int(target['namespace_epoch']),
                project_root=project.project_root,
                terminal_history=terminal_history,
                mobile_files_dir=self._mobile_files_dir(),
            ),
            limit=limit,
            cursor=_query_text(query, 'cursor'),
        )
        conversation: dict[str, object] = {
            'project_id': project.project_id,
            'agent': target['agent'],
            'namespace_epoch': target['namespace_epoch'],
            'generated_at': self._clock(),
            'items': page['items'],
        }
        if page['next_cursor'] is not None:
            conversation['next_cursor'] = page['next_cursor']
        return {
            'schema_version': _SCHEMA_VERSION,
            'status': 'ok',
            'conversation': conversation,
        }

    def _agent_terminal_history_for_conversation(
        self,
        *,
        project_id: str,
        view_payload: dict[str, object],
        agent: str,
        namespace_epoch: int,
    ) -> dict[str, object] | None:
        try:
            target = _terminal_history_target(
                project_id=project_id,
                view_payload=view_payload,
                agent=agent,
                namespace_epoch=namespace_epoch,
                max_lines=240,
            )
            history = dict(self._terminal_history_factory(target) or {})
        except Exception:
            return None
        history.setdefault('agent', target.agent)
        history.setdefault('history_scope', 'tmux_scrollback')
        history.setdefault('source_pane_id', target.pane_id)
        history.setdefault('generated_at', self._clock())
        history.setdefault('stale', False)
        history.setdefault('blocks', [])
        return history

    def file_upload_target_from_path(self, path: str) -> tuple[str, str] | None:
        parsed = urlparse(path)
        route = parsed.path.rstrip('/') or '/'
        return _parse_project_agent_files_route(route)

    def file_download_target_from_path(self, path: str) -> tuple[str, str, str] | None:
        parsed = urlparse(path)
        route = parsed.path.rstrip('/') or '/'
        return _parse_project_agent_file_route(route)

    def dispatch_file_upload(
        self,
        path: str,
        body: bytes,
        headers: Mapping[str, object] | None = None,
    ) -> tuple[int, dict[str, object]]:
        target = self.file_upload_target_from_path(path)
        if target is None:
            raise MobileGatewayError('not found', status_code=404)
        project_id, agent = target
        project = self._require_project(project_id)
        auth = self._authenticate_any_scope(
            headers,
            allowed_scopes=('file_upload', 'message_submit', 'ask'),
        )
        if len(body) > _MAX_MOBILE_FILE_BYTES:
            raise MobileGatewayError('file too large', status_code=413)
        view_payload = self._request_project_view(project)
        view = _map(view_payload.get('view'))
        namespace = _map(view.get('namespace'))
        target_record = _validate_agent_conversation_target(
            project_id=project.project_id,
            view_payload=view_payload,
            agent=agent,
            namespace_epoch=_optional_int(namespace.get('epoch')),
        )
        file_name = _header_file_name(headers)
        mime_type = _header_text(headers, 'content-type') or 'application/octet-stream'
        file_id = f'mobile-file-{uuid4().hex[:16]}'
        digest = hashlib.sha256(body).hexdigest()
        record = {
            'schema_version': _SCHEMA_VERSION,
            'file_id': file_id,
            'project_id': project.project_id,
            'agent': target_record['agent'],
            'device_id': auth.device_id,
            'file_name': file_name,
            'mime_type': mime_type,
            'size_bytes': len(body),
            'sha256': digest,
            'created_at': self._clock(),
        }
        directory = self._mobile_file_dir(project.project_id, str(target_record['agent']), file_id)
        directory.mkdir(parents=True, exist_ok=False)
        (directory / 'content.bin').write_bytes(body)
        (directory / 'metadata.json').write_text(
            json.dumps(record, ensure_ascii=False, sort_keys=True),
            encoding='utf-8',
        )
        return 201, {
            'schema_version': _SCHEMA_VERSION,
            'status': 'ok',
            'file_id': file_id,
            'file_name': file_name,
            'mime_type': mime_type,
            'size_bytes': len(body),
            'sha256': digest,
        }

    def dispatch_file_download(
        self,
        path: str,
        headers: Mapping[str, object] | None = None,
    ) -> tuple[int, bytes, dict[str, str]]:
        target = self.file_download_target_from_path(path)
        if target is None:
            raise MobileGatewayError('not found', status_code=404)
        project_id, agent, file_id = target
        project = self._require_project(project_id)
        self._authenticate_any_scope(
            headers,
            allowed_scopes=('file_download', 'content', 'view'),
        )
        directory = self._mobile_file_dir(project.project_id, agent, file_id)
        metadata = _read_file_metadata(directory)
        if not metadata:
            raise MobileGatewayError('unknown file', status_code=404)
        if str(metadata.get('project_id') or '') != project.project_id:
            raise MobileGatewayError('unknown file', status_code=404)
        if str(metadata.get('agent') or '') != agent:
            raise MobileGatewayError('unknown file', status_code=404)
        content_path = directory / 'content.bin'
        try:
            body = content_path.read_bytes()
        except FileNotFoundError as exc:
            raise MobileGatewayError('unknown file', status_code=404) from exc
        digest = hashlib.sha256(body).hexdigest()
        if digest != str(metadata.get('sha256') or ''):
            raise MobileGatewayError('file checksum mismatch', status_code=500)
        return 200, body, {
            'content-type': str(metadata.get('mime_type') or 'application/octet-stream'),
            'x-ccb-file-name': str(metadata.get('file_name') or 'attachment'),
            'x-ccb-file-sha256': digest,
        }

    def dispatch_post(
        self,
        path: str,
        body: Mapping[str, object] | None,
        headers: Mapping[str, object] | None = None,
    ) -> tuple[int, dict[str, object]]:
        parsed = urlparse(path)
        route = parsed.path.rstrip('/') or '/'
        payload = body if isinstance(body, Mapping) else {}
        if route == '/v1/pairing/claim':
            try:
                result = self._require_pairing_store().claim_pairing(
                    pairing_code=str(payload.get('pairing_code') or ''),
                    device_name=str(payload.get('device_name') or ''),
                    requested_device_id=_optional_text(payload.get('device_id')),
                )
            except MobileGatewayPairingError as exc:
                raise MobileGatewayError(str(exc), status_code=exc.status_code) from exc
            return 201, result
        project_route = _parse_project_action_route(route)
        if project_route is not None:
            project_id, action = project_route
            if action == 'focus-agent':
                return 200, self._focus_agent(
                    project_id=project_id,
                    agent=str(payload.get('agent') or ''),
                    namespace_epoch=_optional_int(payload.get('namespace_epoch')),
                    headers=headers,
                )
            if action == 'focus-window':
                return 200, self._focus_window(
                    project_id=project_id,
                    window=str(payload.get('window') or ''),
                    namespace_epoch=_optional_int(payload.get('namespace_epoch')),
                    headers=headers,
                )
            if action == 'lifecycle':
                return 200, self._project_lifecycle(
                    project_id=project_id,
                    payload=payload,
                    headers=headers,
                )
            if action == 'terminals':
                return 201, self._open_terminal(
                    project_id=project_id,
                    payload=payload,
                    headers=headers,
                )
        message_route = _parse_project_agent_route(route, suffix='messages')
        if message_route is not None:
            project_id, agent = message_route
            return 202, self._submit_agent_message(
                project_id=project_id,
                agent=agent,
                payload=payload,
                headers=headers,
            )
        prefix = '/v1/devices/'
        suffix = '/revoke'
        if route.startswith(prefix) and route.endswith(suffix):
            device_id = unquote(route[len(prefix):-len(suffix)].strip('/'))
            try:
                result = self._require_pairing_store().revoke_device(
                    device_id=device_id,
                    device_token=_bearer_token(headers),
                )
            except MobileGatewayPairingError as exc:
                raise MobileGatewayError(str(exc), status_code=exc.status_code) from exc
            return 200, result
        raise MobileGatewayError('not found', status_code=404)

    def _submit_agent_message(
        self,
        *,
        project_id: str,
        agent: str,
        payload: Mapping[str, object],
        headers: Mapping[str, object] | None,
    ) -> dict[str, object]:
        project = self._require_project(project_id)
        self._authenticate_any_scope(headers, allowed_scopes=('message_submit',))
        body_project_id = str(payload.get('project_id') or '').strip()
        if body_project_id and body_project_id != project.project_id:
            raise MobileGatewayError('request project_id does not match route', status_code=400)
        body_agent = str(payload.get('agent') or '').strip()
        if body_agent and body_agent != agent:
            raise MobileGatewayError('request agent does not match route', status_code=400)
        idempotency_key = str(payload.get('idempotency_key') or '').strip()
        if not idempotency_key:
            raise MobileGatewayError('idempotency_key is required', status_code=400)
        body = str(payload.get('body') or '').strip()
        attachments = _attachment_records(payload.get('attachments'))
        if not body and not attachments:
            raise MobileGatewayError('body or attachments are required', status_code=400)
        submit_body = body or _attachment_submit_body(attachments)
        message_format = str(payload.get('format') or 'markdown').strip() or 'markdown'
        view_payload = self._request_project_view(project)
        target = _validate_agent_conversation_target(
            project_id=project.project_id,
            view_payload=view_payload,
            agent=agent,
            namespace_epoch=_optional_int(payload.get('namespace_epoch')),
        )
        message_target = _pane_message_target(
            project_id=project.project_id,
            view_payload=view_payload,
            target=target,
        )
        try:
            self._terminal_message_sender(message_target, submit_body)
        except Exception as exc:
            raise MobileGatewayError(_error_text(exc), status_code=503) from exc
        message_id = idempotency_key
        return {
            'schema_version': _SCHEMA_VERSION,
            'status': 'ok',
            'project_id': project.project_id,
            'agent': target['agent'],
            'message_submit': {
                'accepted': True,
                'idempotency_key': idempotency_key,
                'message_id': message_id,
                'job_id': None,
                'state': 'sent',
                'created_at': self._clock(),
                'message': {
                    'id': message_id,
                    'agent': target['agent'],
                    'kind': 'user_message',
                    'title': 'You',
                    'body': body,
                    'format': message_format,
                    'state': 'sent',
                    'source': 'mobile',
                    'attachments': attachments,
                },
            },
        }

    def terminal_id_from_path(self, path: str) -> str | None:
        parsed = urlparse(path)
        route = parsed.path.rstrip('/') or '/'
        prefix = '/v1/terminals/'
        if not route.startswith(prefix):
            return None
        terminal_id = unquote(route[len(prefix):].strip('/'))
        return terminal_id or None

    def handle_terminal_websocket(self, terminal_id: str, connection: WebSocketConnection) -> None:
        store = self._require_pairing_store()
        terminal_token = ''
        close_reason = 'transport_disconnected'
        session = None
        output_stop = threading.Event()
        output_thread: threading.Thread | None = None
        close_state: dict[str, str] = {}
        close_handle = False
        try:
            open_frame = connection.read_json()
            if open_frame is None:
                return
            if str(open_frame.get('type') or '') != 'open':
                connection.send_json({'type': 'error', 'code': 'terminal_open_required'})
                close_reason = 'invalid_open'
                return
            if str(open_frame.get('terminal_id') or '') != terminal_id:
                connection.send_json({'type': 'error', 'code': 'terminal_id_mismatch'})
                close_reason = 'invalid_open'
                return
            terminal_token = str(open_frame.get('token') or '')
            record = store.authenticate_terminal_token(
                terminal_id=terminal_id,
                terminal_token=terminal_token,
                resume_cursor=_optional_int(open_frame.get('resume_cursor')),
            )
            attach_target = self._terminal_attach_target(record)
            session = self._terminal_session_factory(attach_target)
            connection.send_json(
                {
                    'type': 'open',
                    'terminal_id': terminal_id,
                    'resume_cursor': _int(record.get('last_output_seq'), 0),
                    'last_input_seq': _int(record.get('last_input_seq'), 0),
                }
            )
            output_thread = threading.Thread(
                target=_pump_terminal_output,
                args=(
                    connection,
                    session,
                    output_stop,
                    close_state,
                    store,
                    terminal_id,
                    terminal_token,
                    _int(record.get('last_output_seq'), 0),
                ),
                daemon=True,
            )
            output_thread.start()
            while not output_stop.is_set():
                frame = connection.read_json()
                if frame is None:
                    close_reason = close_state.get('reason') or 'transport_disconnected'
                    break
                close_reason = self._handle_terminal_frame(
                    connection=connection,
                    session=session,
                    terminal_id=terminal_id,
                    terminal_token=terminal_token,
                    frame=frame,
                )
                if close_reason:
                    close_handle = True
                    break
            if output_stop.is_set() and not close_handle:
                close_reason = close_state.get('reason') or close_reason
                close_handle = close_reason != 'transport_disconnected'
        except MobileGatewayPairingError as exc:
            close_reason = str(exc.reason or 'terminal_token_denied')
            close_handle = True
            _safe_send_json(connection, {'type': 'error', 'code': close_reason})
        except MobileGatewayError as exc:
            close_reason = _terminal_error_code(exc)
            close_handle = True
            _safe_send_json(connection, {'type': 'error', 'code': close_reason})
        except WebSocketProtocolError as exc:
            close_reason = 'protocol_error'
            close_handle = True
            _safe_send_json(connection, {'type': 'error', 'code': 'protocol_error', 'message': _error_text(exc)})
        except Exception as exc:
            close_reason = 'terminal_stream_error'
            close_handle = True
            _safe_send_json(connection, {'type': 'error', 'code': 'terminal_stream_error', 'message': _error_text(exc)})
        finally:
            output_stop.set()
            if terminal_token:
                try:
                    if close_handle:
                        store.close_terminal_handle(
                            terminal_id=terminal_id,
                            terminal_token=terminal_token,
                            reason=close_reason or 'client_closed',
                        )
                    else:
                        store.mark_terminal_disconnected(
                            terminal_id=terminal_id,
                            terminal_token=terminal_token,
                            reason=close_reason or 'transport_disconnected',
                        )
                except MobileGatewayPairingError:
                    pass
            if session is not None:
                try:
                    session.close()
                except Exception:
                    pass
            _safe_send_json(connection, {'type': 'closed', 'reason': close_reason or 'client_closed'})
            connection.close()
            if output_thread is not None:
                output_thread.join(timeout=1)

    def _client(self):
        return self._ccbd_client_factory()

    def _focus_agent(
        self,
        *,
        project_id: str,
        agent: str,
        namespace_epoch: int | None,
        headers: Mapping[str, object] | None,
    ) -> dict[str, object]:
        project = self._require_project(project_id)
        self._authenticate(headers, required_scopes=('focus',))
        if not str(agent or '').strip():
            raise MobileGatewayError('agent is required', status_code=400)
        try:
            focus = project.client().project_focus_agent(agent=agent, namespace_epoch=namespace_epoch)
        except CcbdClientError as exc:
            raise MobileGatewayError(str(exc), status_code=_ccbd_focus_status(exc)) from exc
        except Exception as exc:
            raise MobileGatewayError(_error_text(exc), status_code=503) from exc
        return self._focused_project_view_payload(project, focus)

    def _project_lifecycle(
        self,
        *,
        project_id: str,
        payload: Mapping[str, object],
        headers: Mapping[str, object] | None,
    ) -> dict[str, object]:
        project = self._require_project(project_id)
        self._authenticate(headers, required_scopes=('lifecycle',))
        body_project_id = str(payload.get('project_id') or '').strip()
        if body_project_id and body_project_id != project.project_id:
            raise MobileGatewayError('request project_id does not match route', status_code=400)
        action = str(payload.get('action') or '').strip().lower()
        if action not in {'wake', 'open', 'close', 'stop'}:
            raise MobileGatewayError('unsupported lifecycle action', status_code=400)
        if action in {'wake', 'open'}:
            result = self._lifecycle_result(
                action=action,
                state='running',
                effect='already_running' if action == 'wake' else 'opened',
                ccb_authority=True,
            )
            response = _redact_project_view_payload(self._request_project_view(project))
            response.update({
                'schema_version': _SCHEMA_VERSION,
                'status': 'ok',
                'project_id': project.project_id,
                'lifecycle': result,
            })
            return response
        if action == 'close':
            return {
                'schema_version': _SCHEMA_VERSION,
                'status': 'ok',
                'project_id': project.project_id,
                'lifecycle': self._lifecycle_result(
                    action='close',
                    state='running',
                    effect='mobile_view_closed',
                    ccb_authority=True,
                ),
            }
        try:
            stop_result = project.client().stop_all(force=False)
        except CcbdClientError as exc:
            raise MobileGatewayError(str(exc), status_code=503) from exc
        except Exception as exc:
            raise MobileGatewayError(_error_text(exc), status_code=503) from exc
        return {
            'schema_version': _SCHEMA_VERSION,
            'status': 'ok',
            'project_id': project.project_id,
            'lifecycle': self._lifecycle_result(
                action='stop',
                state='stopping',
                effect='ccbd_stop_requested',
                ccb_authority=True,
                forced=False,
                result=dict(stop_result or {}) if isinstance(stop_result, Mapping) else {},
            ),
        }

    def _lifecycle_result(
        self,
        *,
        action: str,
        state: str,
        effect: str,
        ccb_authority: bool,
        forced: bool = False,
        result: dict[str, object] | None = None,
    ) -> dict[str, object]:
        return {
            'action': action,
            'state': state,
            'effect': effect,
            'forced': forced,
            'ccb_authority': ccb_authority,
            'tmux_kill_server': False,
            'updated_at': self._clock(),
            **({'result': result} if result is not None else {}),
        }

    def _focus_window(
        self,
        *,
        project_id: str,
        window: str,
        namespace_epoch: int | None,
        headers: Mapping[str, object] | None,
    ) -> dict[str, object]:
        project = self._require_project(project_id)
        self._authenticate(headers, required_scopes=('focus',))
        if not str(window or '').strip():
            raise MobileGatewayError('window is required', status_code=400)
        try:
            focus = project.client().project_focus_window(window=window, namespace_epoch=namespace_epoch)
        except CcbdClientError as exc:
            raise MobileGatewayError(str(exc), status_code=_ccbd_focus_status(exc)) from exc
        except Exception as exc:
            raise MobileGatewayError(_error_text(exc), status_code=503) from exc
        return self._focused_project_view_payload(project, focus)

    def _open_terminal(
        self,
        *,
        project_id: str,
        payload: Mapping[str, object],
        headers: Mapping[str, object] | None,
    ) -> dict[str, object]:
        project = self._require_project(project_id)
        auth = self._authenticate(headers, required_scopes=('terminal_input',))
        body_project_id = str(payload.get('project_id') or '').strip()
        if body_project_id and body_project_id != project.project_id:
            raise MobileGatewayError('request project_id does not match route', status_code=400)
        target = _map(payload.get('target'))
        geometry = _map(payload.get('geometry'))
        view_payload = self._request_project_view(project)
        target_payload = _validate_terminal_target(
            project.project_id,
            view_payload,
            target=target,
            namespace_epoch=_optional_int(payload.get('namespace_epoch')),
        )
        handle = self._require_pairing_store().create_terminal_handle(
            project_id=project.project_id,
            device_id=auth.device_id,
            target_epoch=int(target_payload['target_epoch']),
            target_summary=target_payload['target_summary'],
            geometry=geometry,
        )
        terminal_id = str(handle.get('terminal_id') or '')
        handle['websocket_url'] = _terminal_websocket_url(headers, terminal_id=terminal_id)
        return handle

    def _focused_project_view_payload(
        self,
        project: MobileGatewayProject,
        focus: dict[str, object],
    ) -> dict[str, object]:
        payload = self._request_project_view(project)
        redacted = _redact_project_view_payload(payload)
        redacted['focus'] = dict(focus or {}) if isinstance(focus, dict) else {}
        return redacted

    def _require_project(self, project_id: str) -> MobileGatewayProject:
        requested = str(project_id or '').strip()
        project = self._project_registry.get(requested)
        if project is None:
            raise MobileGatewayError('unknown project', status_code=404)
        return project

    def _require_pairing_store(self) -> MobileGatewayPairingStore:
        if self._pairing_store is None:
            raise MobileGatewayError('mobile pairing store is not configured', status_code=503)
        return self._pairing_store

    def _require_notification_store(self) -> MobileNotificationStore:
        if self._notification_store is None:
            raise MobileGatewayError('mobile notification store is not configured', status_code=503)
        return self._notification_store

    def _mobile_file_dir(self, project_id: str, agent: str, file_id: str) -> Path:
        return (
            self._mobile_files_dir()
            / _safe_path_segment(project_id)
            / _safe_path_segment(agent)
            / _safe_path_segment(file_id)
        )

    def _mobile_files_dir(self) -> Path:
        root = (
            self._mobile_dir
            if self._mobile_dir is not None
            else self._project_root / '.ccb' / 'ccbd' / 'mobile'
        )
        return root / 'files'

    def _capabilities(self) -> list[str]:
        values = list(_BASE_CAPABILITIES)
        if self._pairing_store is not None:
            values.extend(_PAIRING_CAPABILITIES)
        return values

    def _authenticate(self, headers: Mapping[str, object] | None, *, required_scopes: tuple[str, ...]):
        try:
            return self._require_pairing_store().authenticate_device(
                _bearer_token(headers),
                required_scopes=required_scopes,
            )
        except MobileGatewayPairingError as exc:
            raise MobileGatewayError(str(exc), status_code=exc.status_code) from exc

    def _authenticate_any_scope(
        self,
        headers: Mapping[str, object] | None,
        *,
        allowed_scopes: tuple[str, ...],
    ):
        auth = self._authenticate(headers, required_scopes=())
        if auth.scopes.intersection({str(scope) for scope in allowed_scopes}):
            return auth
        raise MobileGatewayError('device scope denied', status_code=403)

    def _ping_or_unavailable(self, project: MobileGatewayProject) -> dict[str, object]:
        try:
            payload = project.client().ping('ccbd')
        except CcbdClientError as exc:
            raise MobileGatewayError(str(exc), status_code=503) from exc
        except Exception as exc:
            raise MobileGatewayError(_error_text(exc), status_code=503) from exc
        return dict(payload or {}) if isinstance(payload, dict) else {}

    def _project_list_health_by_project(
        self,
        projects: tuple[MobileGatewayProject, ...],
    ) -> dict[str, dict[str, object]]:
        if len(projects) <= 1:
            return {
                project.project_id: self._project_list_health(project)
                for project in projects
            }
        max_workers = min(_PROJECT_LIST_HEALTH_WORKERS, len(projects))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            health_items = executor.map(self._project_list_health, projects)
            return {
                project.project_id: health
                for project, health in zip(projects, health_items)
            }

    def _project_list_health(self, project: MobileGatewayProject) -> dict[str, object]:
        try:
            return self._ping_or_unavailable(project)
        except MobileGatewayError:
            return {
                'health': 'unreachable',
                'mount_state': 'unavailable',
                'error': 'project unavailable',
            }

    def _request_project_view(self, project: MobileGatewayProject) -> dict[str, object]:
        try:
            payload = project.client().project_view(schema_version=1)
        except CcbdClientError as exc:
            raise MobileGatewayError(str(exc), status_code=503) from exc
        except Exception as exc:
            raise MobileGatewayError(_error_text(exc), status_code=503) from exc
        return dict(payload or {}) if isinstance(payload, dict) else {}

    def _notification_snapshots(self) -> list[MobileNotificationSnapshot]:
        snapshots: list[MobileNotificationSnapshot] = []
        for project in self._project_registry.projects():
            try:
                payload = self._request_project_view(project)
            except MobileGatewayError:
                continue
            snapshots.extend(_notification_snapshots_for_project(project, payload, observed_at=self._clock()))
        return snapshots

    def _terminal_attach_target(self, record: dict[str, object]) -> TerminalAttachTarget:
        project = self._require_project(str(record.get('project_id') or ''))
        view_payload = self._request_project_view(project)
        view = _map(view_payload.get('view'))
        namespace = _map(view.get('namespace'))
        actual_epoch = _optional_int(namespace.get('epoch'))
        target_epoch = _optional_int(record.get('target_epoch'))
        if actual_epoch is None or target_epoch is None or actual_epoch != target_epoch:
            raise MobileGatewayError('stale namespace epoch', status_code=409)
        socket_path = _optional_text(namespace.get('socket_path'))
        session_name = _optional_text(namespace.get('session_name'))
        if not socket_path or not session_name:
            raise MobileGatewayError('ProjectView tmux evidence is not attachable', status_code=409)
        _validate_terminal_summary(record, view)
        return TerminalAttachTarget(
            terminal_id=str(record.get('terminal_id') or ''),
            socket_path=socket_path,
            session_name=session_name,
            pane_id=_optional_text(_map(record.get('target_summary')).get('pane_id')),
            geometry=TerminalGeometry.from_mapping(record.get('geometry')),
            target_summary=_map(record.get('target_summary')),
        )

    def _handle_terminal_frame(
        self,
        *,
        connection: WebSocketConnection,
        session,
        terminal_id: str,
        terminal_token: str,
        frame: Mapping[str, object],
    ) -> str:
        frame_type = str(frame.get('type') or '').strip()
        if frame_type == 'input':
            seq = _required_positive_int(frame.get('seq'), 'seq')
            data = base64.b64decode(str(frame.get('bytes_b64') or ''), validate=True)
            self._require_pairing_store().record_terminal_input_sequence(
                terminal_id=terminal_id,
                terminal_token=terminal_token,
                sequence=seq,
            )
            session.write(data)
            return ''
        if frame_type == 'paste':
            seq = _required_positive_int(frame.get('seq'), 'seq')
            self._require_pairing_store().record_terminal_input_sequence(
                terminal_id=terminal_id,
                terminal_token=terminal_token,
                sequence=seq,
            )
            session.paste(str(frame.get('text') or ''))
            return ''
        if frame_type == 'resize':
            session.resize(TerminalGeometry.from_mapping(frame))
            return ''
        if frame_type == 'closed':
            return str(frame.get('reason') or 'client_closed')
        connection.send_json({'type': 'error', 'code': 'unsupported_terminal_frame'})
        return 'unsupported_terminal_frame'


def parse_listen_address(value: str | None) -> ListenAddress:
    text = str(value or '').strip()
    if not text:
        return ListenAddress()
    if text.count(':') != 1:
        raise ValueError('listen address must be HOST:PORT')
    host, port_text = (item.strip() for item in text.rsplit(':', 1))
    if not host:
        host = _DEFAULT_HOST
    try:
        port = int(port_text)
    except ValueError as exc:
        raise ValueError('listen port must be an integer') from exc
    if port < 0 or port > 65535:
        raise ValueError('listen port must be between 0 and 65535')
    if not _is_loopback_host(host):
        raise ValueError('mobile gateway only supports loopback listen addresses')
    return ListenAddress(host=host, port=port)


def build_mobile_gateway_server(listen: ListenAddress, service: MobileGatewayService) -> ThreadingHTTPServer:
    class _Handler(BaseHTTPRequestHandler):
        server_version = 'CCBMobileGateway/1'

        def do_GET(self) -> None:  # noqa: N802 - stdlib hook
            if service.notification_stream_target_from_path(self.path):
                self._send_notification_stream()
                return
            terminal_id = service.terminal_id_from_path(self.path)
            if terminal_id is not None and is_websocket_upgrade(self.headers):
                try:
                    connection = accept_websocket(self)
                except WebSocketProtocolError as exc:
                    self._send_json(400, {
                        'schema_version': _SCHEMA_VERSION,
                        'status': 'error',
                        'error': _error_text(exc),
                    })
                    return
                service.handle_terminal_websocket(terminal_id, connection)
                return
            if service.file_download_target_from_path(self.path) is not None:
                try:
                    status, body, headers = service.dispatch_file_download(self.path, self.headers)
                except MobileGatewayError as exc:
                    self._send_json(exc.status_code, {
                        'schema_version': _SCHEMA_VERSION,
                        'status': 'error',
                        'error': _error_text(exc),
                    })
                    return
                self._send_bytes(status, body, headers)
                return
            try:
                status, payload = service.dispatch_get(self.path, self.headers)
            except MobileGatewayError as exc:
                status = exc.status_code
                payload = {
                    'schema_version': _SCHEMA_VERSION,
                    'status': 'error',
                    'error': _error_text(exc),
                }
            self._send_json(status, payload)

        def do_POST(self) -> None:  # noqa: N802 - stdlib hook
            try:
                if service.file_upload_target_from_path(self.path) is not None:
                    status, payload = service.dispatch_file_upload(
                        self.path,
                        self._read_raw_body(max_bytes=_MAX_MOBILE_FILE_BYTES),
                        self.headers,
                    )
                else:
                    status, payload = service.dispatch_post(self.path, self._read_json_body(), self.headers)
            except MobileGatewayError as exc:
                status = exc.status_code
                payload = {
                    'schema_version': _SCHEMA_VERSION,
                    'status': 'error',
                    'error': _error_text(exc),
                }
            except ValueError as exc:
                status = 400
                payload = {
                    'schema_version': _SCHEMA_VERSION,
                    'status': 'error',
                    'error': _error_text(exc),
                }
            self._send_json(status, payload)

        def log_message(self, format: str, *args) -> None:  # noqa: A002 - stdlib signature
            return

        def _send_json(self, status: int, payload: dict[str, object]) -> None:
            body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode('utf-8')
            self.send_response(status)
            self.send_header('content-type', 'application/json; charset=utf-8')
            self.send_header('content-length', str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                return

        def _send_bytes(self, status: int, body: bytes, headers: dict[str, str]) -> None:
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.send_header('content-length', str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                return

        def _send_notification_stream(self) -> None:
            once = service.notification_stream_once_from_path(self.path)
            try:
                events = service.notification_events_since(self.path, self.headers)
            except MobileGatewayError as exc:
                self._send_json(exc.status_code, {
                    'schema_version': _SCHEMA_VERSION,
                    'status': 'error',
                    'error': _error_text(exc),
                })
                return
            self.send_response(200)
            self.send_header('content-type', 'text/event-stream; charset=utf-8')
            self.send_header('cache-control', 'no-cache')
            self.send_header('connection', 'close' if once else 'keep-alive')
            self.end_headers()
            last_event_id = self._write_notification_events(events)
            if once:
                self.close_connection = True
                return
            while True:
                try:
                    time.sleep(_NOTIFICATION_STREAM_POLL_SECONDS)
                    events = service.notification_events_since(
                        self.path,
                        self.headers,
                        last_event_id=last_event_id,
                    )
                    next_id = self._write_notification_events(events)
                    if next_id is not None:
                        last_event_id = next_id
                    elif not self._write_sse_bytes(b': keepalive\n\n'):
                        return
                except (BrokenPipeError, ConnectionError, OSError):
                    return

        def _write_notification_events(self, events: list[dict[str, object]]) -> str | None:
            last_event_id = None
            for event in events:
                if not self._write_sse_bytes(encode_sse_event(event)):
                    return last_event_id
                last_event_id = str(event.get('id') or '') or last_event_id
            return last_event_id

        def _write_sse_bytes(self, body: bytes) -> bool:
            try:
                self.wfile.write(body)
                self.wfile.flush()
                return True
            except (BrokenPipeError, ConnectionError, OSError):
                return False

        def _read_json_body(self) -> dict[str, object]:
            length_text = self.headers.get('content-length') or '0'
            try:
                length = int(length_text)
            except ValueError as exc:
                raise ValueError('invalid content-length') from exc
            if length < 0 or length > 65536:
                raise ValueError('request body too large')
            raw = self.rfile.read(length) if length else b'{}'
            if not raw:
                return {}
            decoded = json.loads(raw.decode('utf-8'))
            if isinstance(decoded, dict):
                return {str(key): value for key, value in decoded.items()}
            raise ValueError('request body must be a JSON object')

        def _read_raw_body(self, *, max_bytes: int) -> bytes:
            length_text = self.headers.get('content-length') or '0'
            try:
                length = int(length_text)
            except ValueError as exc:
                raise ValueError('invalid content-length') from exc
            if length < 0 or length > max_bytes:
                raise ValueError('request body too large')
            return self.rfile.read(length) if length else b''

    return ThreadingHTTPServer((listen.host, listen.port), _Handler)


def _redact_project_view_payload(payload: dict[str, object]) -> dict[str, object]:
    redacted = json.loads(json.dumps(payload))
    view = redacted.get('view') if isinstance(redacted, dict) else None
    if isinstance(view, dict):
        namespace = view.get('namespace')
        if isinstance(namespace, dict):
            for key in _REDACTED_NAMESPACE_KEYS:
                namespace.pop(key, None)
    return redacted


def _notification_snapshots_for_project(
    project: MobileGatewayProject,
    payload: dict[str, object],
    *,
    observed_at: str,
) -> list[MobileNotificationSnapshot]:
    view = _map(payload.get('view'))
    cache = _map(payload.get('cache'))
    project_record = _map(view.get('project'))
    namespace = _map(view.get('namespace'))
    namespace_epoch = _optional_int(namespace.get('epoch'))
    generated_at = _optional_text(cache.get('generated_at')) or observed_at
    project_short_name = (
        _optional_text(project_record.get('display_name'))
        or _optional_text(project_record.get('name'))
        or project.public_display_name
    )
    snapshots: list[MobileNotificationSnapshot] = []
    for item in _iterable(view.get('agents')):
        agent = _map(item)
        agent_name = _optional_text(agent.get('name'))
        activity_state = _optional_text(agent.get('activity_state'))
        if not agent_name or not activity_state:
            continue
        snapshots.append(
            MobileNotificationSnapshot(
                project_id=project.project_id,
                project_short_name=project_short_name,
                namespace_epoch=namespace_epoch,
                agent=agent_name,
                activity_state=activity_state.lower(),
                observed_at=generated_at,
            )
        )
    return snapshots


def _ccbd_health_summary(payload: dict[str, object]) -> dict[str, object]:
    return {
        'reachable': True,
        'project_id': payload.get('project_id'),
        'mount_state': payload.get('mount_state'),
        'health': payload.get('health'),
        'namespace_epoch': payload.get('namespace_epoch'),
        'namespace_ui_attachable': payload.get('namespace_ui_attachable'),
    }


def _project_available_for_mobile_list(payload: dict[str, object]) -> bool:
    return (
        str(payload.get('health') or '').strip().lower() == 'healthy'
        and str(payload.get('mount_state') or '').strip().lower() == 'mounted'
    )


def _is_loopback_host(host: str) -> bool:
    normalized = host.strip().lower()
    return normalized in {'localhost', '127.0.0.1', '::1'}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def _error_text(exc: Exception) -> str:
    return str(exc or '').strip() or type(exc).__name__


def _optional_text(value: object) -> str | None:
    text = str(value or '').strip()
    return text or None


def _header_text(headers: Mapping[str, object] | None, name: str) -> str:
    if headers is None:
        return ''
    getter = getattr(headers, 'get', None)
    value = getter(name) if callable(getter) else headers.get(name)
    if value is None and name.lower() != name:
        value = getter(name.lower()) if callable(getter) else headers.get(name.lower())
    return str(value or '').strip()


def _header_file_name(headers: Mapping[str, object] | None) -> str:
    encoded = _header_text(headers, 'X-Ccb-File-Name')
    if encoded:
        decoded = unquote(encoded).strip()
        if decoded:
            return decoded
    return 'attachment'


def _map(value: object) -> dict[str, object]:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    return {}


def _attachment_records(value: object) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    if not isinstance(value, (list, tuple)):
        return records
    for item in value:
        record = _map(item)
        file_id = _optional_text(record.get('file_id')) or _optional_text(record.get('attachment_id'))
        if not file_id:
            continue
        file_name = _optional_text(record.get('file_name')) or _optional_text(record.get('filename')) or 'attachment'
        mime_type = _optional_text(record.get('mime_type')) or 'application/octet-stream'
        records.append(
            {
                'file_id': file_id,
                'file_name': file_name,
                'mime_type': mime_type,
                'size_bytes': _int(record.get('size_bytes'), 0),
                'kind': _optional_text(record.get('kind')) or ('image' if mime_type.startswith('image/') else 'document'),
            }
        )
    return records


def _attachment_submit_body(attachments: list[dict[str, object]]) -> str:
    names = [
        str(item.get('file_name') or 'attachment')
        for item in attachments
        if str(item.get('file_name') or '').strip()
    ]
    if not names:
        return 'Uploaded attachment'
    if len(names) == 1:
        return f'Uploaded attachment: {names[0]}'
    return f'Uploaded attachments: {", ".join(names)}'


def _safe_path_segment(value: object) -> str:
    text = str(value or '').strip()
    safe = ''.join(ch if ch.isalnum() or ch in {'-', '_', '.'} else '_' for ch in text)
    safe = safe.strip('._')
    if not safe:
        raise MobileGatewayError('invalid file identifier', status_code=400)
    return safe


def _read_file_metadata(directory: Path) -> dict[str, object]:
    try:
        payload = json.loads((directory / 'metadata.json').read_text(encoding='utf-8'))
    except Exception:
        return {}
    return _map(payload)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    return int(text) if text else None


def _int(value: object, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _parse_project_action_route(route: str) -> tuple[str, str] | None:
    prefix = '/v1/projects/'
    if not route.startswith(prefix):
        return None
    parts = route[len(prefix):].strip('/').split('/')
    if len(parts) != 2:
        return None
    project_id, action = parts
    if action not in {'focus-agent', 'focus-window', 'lifecycle', 'terminals'}:
        return None
    return unquote(project_id), action


def _parse_project_agent_route(route: str, *, suffix: str) -> tuple[str, str] | None:
    prefix = '/v1/projects/'
    if not route.startswith(prefix):
        return None
    parts = route[len(prefix):].strip('/').split('/')
    if len(parts) != 4 or parts[1] != 'agents' or parts[3] != suffix:
        return None
    project_id = unquote(parts[0]).strip()
    agent = unquote(parts[2]).strip()
    if not project_id or not agent:
        return None
    return project_id, agent


def _parse_project_agent_files_route(route: str) -> tuple[str, str] | None:
    prefix = '/v1/projects/'
    if not route.startswith(prefix):
        return None
    parts = route[len(prefix):].strip('/').split('/')
    if len(parts) != 4 or parts[1] != 'agents' or parts[3] != 'files':
        return None
    project_id = unquote(parts[0]).strip()
    agent = unquote(parts[2]).strip()
    if not project_id or not agent:
        return None
    return project_id, agent


def _parse_project_agent_file_route(route: str) -> tuple[str, str, str] | None:
    prefix = '/v1/projects/'
    if not route.startswith(prefix):
        return None
    parts = route[len(prefix):].strip('/').split('/')
    if len(parts) != 5 or parts[1] != 'agents' or parts[3] != 'files':
        return None
    project_id = unquote(parts[0]).strip()
    agent = unquote(parts[2]).strip()
    file_id = unquote(parts[4]).strip()
    if not project_id or not agent or not file_id:
        return None
    return project_id, agent, file_id


def _validate_agent_conversation_target(
    *,
    project_id: str,
    view_payload: dict[str, object],
    agent: str,
    namespace_epoch: int | None,
) -> dict[str, object]:
    view = _map(view_payload.get('view'))
    namespace = _map(view.get('namespace'))
    actual_epoch = _optional_int(namespace.get('epoch'))
    if actual_epoch is None:
        raise MobileGatewayError('ProjectView namespace epoch is required', status_code=409)
    if namespace_epoch != actual_epoch:
        raise MobileGatewayError('stale namespace epoch', status_code=409)
    agent_name = str(agent or '').strip()
    if not agent_name:
        raise MobileGatewayError('agent is required', status_code=400)
    agents = [_map(item) for item in _iterable(view.get('agents'))]
    matched = next((item for item in agents if str(item.get('name') or '') == agent_name), None)
    if matched is None:
        raise MobileGatewayError('unknown agent', status_code=404)
    return {
        'project_id': project_id,
        'agent': agent_name,
        'namespace_epoch': actual_epoch,
        'agent_record': matched,
    }


def _agent_conversation_items(
    view_payload: dict[str, object],
    *,
    project_id: str,
    agent: str,
    namespace_epoch: int,
    project_root: Path,
    terminal_history: dict[str, object] | None = None,
    mobile_files_dir: Path | None = None,
) -> list[dict[str, object]]:
    view = _map(view_payload.get('view'))
    native_items = _agent_native_conversation_items(
        project_root,
        project_id=project_id,
        agent=agent,
        mobile_files_dir=mobile_files_dir,
    )
    if native_items:
        return native_items

    agents = [_map(item) for item in _iterable(view.get('agents'))]
    agent_record = next((item for item in agents if str(item.get('name') or '') == agent), {})
    items: list[dict[str, object]] = [
        {
            'id': f'status-{agent}',
            'agent': agent,
            'kind': 'status_event',
            'title': 'Agent status',
            'body': _agent_status_summary(agent_record),
            'format': 'plain',
            'source': 'project_view',
        }
    ]
    content = _map(view.get('content'))
    for item in _iterable(content.get('items')):
        content_item = _map(item)
        if not _conversation_item_belongs_to_agent(content_item, agent):
            continue
        content_id = str(content_item.get('id') or f'content-{len(items)}')
        body = (
            _optional_text(content_item.get('text'))
            or _optional_text(content_item.get('body'))
            or ''
        )
        if not body:
            continue
        reply_item = {
            'id': f'reply-{content_id}',
            'agent': agent,
            'kind': 'agent_reply',
            'title': _optional_text(content_item.get('title')) or 'Agent reply',
            'body': body,
            'format': _optional_text(content_item.get('format')) or 'plain',
            'content_id': content_id,
            'source': _optional_text(content_item.get('source')) or 'content',
        }
        _apply_mobile_conversation_timing(
            reply_item,
            sent_at=content_item.get('sent_at') or content_item.get('created_at'),
            started_at=content_item.get('started_at') or content_item.get('execution_started_at'),
            completed_at=(
                content_item.get('completed_at')
                or content_item.get('finished_at')
                or content_item.get('execution_completed_at')
            ),
            duration_ms=content_item.get('duration_ms'),
            duration_seconds=content_item.get('duration_seconds'),
        )
        items.append(
            reply_item
        )
    seen_item_ids = {str(item.get('id') or '') for item in items}

    terminal_items = _terminal_history_conversation_items(
        terminal_history,
        agent=agent,
    )
    if terminal_items:
        return terminal_items

    for item in _agent_history_conversation_items(
        project_root,
        project_id=project_id,
        agent=agent,
    ):
        item_id = str(item.get('id') or '')
        if item_id and item_id in seen_item_ids:
            continue
        items.append(item)
        if item_id:
            seen_item_ids.add(item_id)
    comm_records = [_map(item) for item in _iterable(view.get('comms'))]
    comm_records = [
        item
        for _, item in sorted(
            enumerate(comm_records),
            key=lambda indexed: (
                _optional_text(indexed[1].get('created_at'))
                or _optional_text(indexed[1].get('updated_at'))
                or '9999',
                indexed[0],
            ),
        )
    ]
    for comm in comm_records:
        if not _conversation_item_belongs_to_agent(comm, agent):
            continue
        body = (
            _optional_text(comm.get('body'))
            or _optional_text(comm.get('text'))
            or _optional_text(comm.get('message'))
            or _optional_text(comm.get('body_preview'))
        )
        reply_dict = _completion_reply_for_job(
            project_root,
            _optional_text(comm.get('id')),
            project_id=project_id,
            agent=agent,
        )
        reply = str(reply_dict.get('body') or '')
        reply_attachments = _attachment_records(reply_dict.get('attachments'))
        attachments = _attachment_records(comm.get('attachments'))
        comm_created_at = _first_mobile_conversation_timestamp(
            comm.get('sent_at'),
            comm.get('created_at'),
            comm.get('updated_at'),
        )
        reply_completed_at = _first_mobile_conversation_timestamp(
            reply_dict.get('completed_at'),
            reply_dict.get('sent_at'),
            comm.get('completed_at'),
            comm.get('finished_at'),
            comm.get('updated_at'),
            comm_created_at,
        )
        if reply:
            comm_id = str(comm.get('id') or f'comms-{len(items)}')
            if body:
                user_id = f'user-{comm_id}'
                if user_id in seen_item_ids:
                    continue
                user_item = {
                    'id': user_id,
                    'agent': agent,
                    'kind': 'user_message',
                    'title': 'You',
                    'body': body,
                    'format': _optional_text(comm.get('format')) or 'markdown',
                    'source': 'mobile',
                    'state': 'sent',
                    'attachments': attachments,
                }
                _apply_mobile_conversation_timing(user_item, sent_at=comm_created_at)
                items.append(
                    user_item
                )
                seen_item_ids.add(user_id)
            reply_id = f'reply-{comm_id}'
            if reply_id in seen_item_ids:
                continue
            reply_item = {
                'id': reply_id,
                'agent': agent,
                'kind': 'agent_reply',
                'title': _optional_text(comm.get('title')) or 'Agent reply',
                'body': reply,
                'format': 'markdown',
                'source': 'completion_snapshot',
                'attachments': reply_attachments,
            }
            _apply_mobile_conversation_timing(
                reply_item,
                sent_at=reply_completed_at,
                started_at=reply_dict.get('started_at') or comm_created_at,
                completed_at=reply_completed_at,
                duration_ms=reply_dict.get('duration_ms'),
                duration_seconds=reply_dict.get('duration_seconds'),
            )
            items.append(
                reply_item
            )
            seen_item_ids.add(reply_id)
            continue
        if not body:
            continue
        comm_id = str(comm.get('id') or f'comms-{len(items)}')
        item_id = f'comms-{comm_id}'
        if item_id in seen_item_ids:
            continue
        comm_item = {
            'id': item_id,
            'agent': agent,
            'kind': 'comms_item',
            'title': _optional_text(comm.get('title')) or 'Comms',
            'body': body,
            'format': _optional_text(comm.get('format')) or 'plain',
            'source': _optional_text(comm.get('source')) or 'project_view',
            'attachments': attachments,
        }
        _apply_mobile_conversation_timing(comm_item, sent_at=comm_created_at)
        items.append(
            comm_item
        )
        seen_item_ids.add(item_id)
    return items


def _terminal_history_conversation_items(
    history: dict[str, object] | None,
    *,
    agent: str,
) -> list[dict[str, object]]:
    history = _map(history)
    if not history:
        return []
    history_scope = _optional_text(history.get('history_scope')) or 'tmux_scrollback'
    source_pane_id = _optional_text(history.get('source_pane_id'))
    items: list[dict[str, object]] = []
    for block in _iterable(history.get('blocks')):
        block_record = _map(block)
        text = _optional_text(block_record.get('text')) or ''
        if not text:
            continue
        block_id = _optional_text(block_record.get('id')) or f'history-{len(items) + 1}'
        block_type = _optional_text(block_record.get('type')) or 'log'
        is_input = block_type == 'command'
        items.append(
            {
                'id': f'terminal-history-{block_id}',
                'agent': agent,
                'kind': 'user_message' if is_input else 'agent_reply',
                'title': 'Terminal input'
                if is_input
                else (_optional_text(block_record.get('title')) or 'Terminal output'),
                'body': _terminal_history_body(text, is_input=is_input),
                'format': 'plain',
                'source': _terminal_conversation_source(
                    history_scope,
                    source_pane_id=source_pane_id,
                    is_input=is_input,
                ),
                'attachments': [],
            }
        )
    return items


def _terminal_history_body(text: str, *, is_input: bool) -> str:
    body = text.strip()
    if not is_input or body.startswith('$ '):
        return body
    return '$ ' + body


def _terminal_conversation_source(
    history_scope: str,
    *,
    source_pane_id: str | None,
    is_input: bool,
) -> str:
    parts = [
        'terminal input' if is_input else 'tmux output',
        history_scope,
    ]
    if source_pane_id:
        parts.append(source_pane_id)
    return ' / '.join(parts)


def _agent_native_conversation_items(
    project_root: Path,
    *,
    project_id: str,
    agent: str,
    mobile_files_dir: Path | None = None,
) -> list[dict[str, object]]:
    return _codex_native_conversation_items(
        project_root,
        project_id=project_id,
        agent=agent,
        mobile_files_dir=mobile_files_dir,
    )


def _codex_native_conversation_items(
    project_root: Path,
    *,
    project_id: str,
    agent: str,
    mobile_files_dir: Path | None = None,
) -> list[dict[str, object]]:
    home = project_root / '.ccb' / 'agents' / agent / 'provider-state' / 'codex' / 'home'
    state_path = home / 'state_5.sqlite'
    if not state_path.is_file():
        return []
    try:
        connection = sqlite3.connect(f'file:{state_path}?mode=ro', uri=True)
        connection.row_factory = sqlite3.Row
        rows = list(
            connection.execute(
                'select id, rollout_path, created_at, updated_at from threads '
                'where rollout_path is not null and rollout_path != "" '
                'order by created_at asc, updated_at asc, id asc'
            )
        )
    except Exception:
        return []
    finally:
        try:
            connection.close()  # type: ignore[possibly-undefined]
        except Exception:
            pass

    items: list[dict[str, object]] = []
    for row_index, row in enumerate(rows):
        thread_id = str(row['id'] or '').strip() or f'thread-{len(items)}'
        rollout_text = str(row['rollout_path'] or '').strip()
        if not rollout_text:
            continue
        rollout_path = Path(rollout_text)
        if not rollout_path.is_absolute():
            rollout_path = home / rollout_path
        fallback_timestamp = _codex_thread_fallback_timestamp(row)
        items.extend(
            _codex_rollout_conversation_items(
                rollout_path,
                project_root=project_root,
                project_id=project_id,
                agent=agent,
                thread_id=thread_id,
                thread_order=row_index,
                fallback_timestamp=fallback_timestamp,
                mobile_files_dir=mobile_files_dir,
                file_roots=[
                    path
                    for path in (
                        mobile_files_dir,
                        project_root / '.ccb' / 'ccbd' / 'mobile' / 'files',
                    )
                    if path is not None
                ],
            )
        )
    sorted_items = [
        item
        for _, item in sorted(
            enumerate(items),
            key=lambda indexed: (
                _optional_text(indexed[1].get('_native_sort_timestamp')) or '',
                int(indexed[1].get('_native_thread_order') or 0),
                int(indexed[1].get('_native_line_number') or 0),
                indexed[0],
            ),
        )
    ]
    return [
        _without_native_sort_fields(item)
        for item in _coalesce_codex_native_agent_replies(sorted_items)
    ]


def _codex_thread_fallback_timestamp(row: sqlite3.Row) -> str:
    timestamp = row['updated_at'] or row['created_at'] or 0
    try:
        return f'{int(timestamp):020d}'
    except Exception:
        return str(timestamp)


def _codex_rollout_conversation_items(
    rollout_path: Path,
    *,
    project_root: Path,
    project_id: str,
    agent: str,
    thread_id: str,
    thread_order: int,
    fallback_timestamp: str,
    mobile_files_dir: Path | None,
    file_roots: list[Path],
) -> list[dict[str, object]]:
    event_items: list[dict[str, object]] = []
    response_items: list[dict[str, object]] = []
    try:
        lines = rollout_path.open(encoding='utf-8')
    except Exception:
        return []
    with lines:
        for line_number, line in enumerate(lines, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = _map(json.loads(line))
            except Exception:
                continue
            payload = _map(record.get('payload'))
            if record.get('type') == 'event_msg':
                event_item = _codex_event_message_conversation_item(
                    payload,
                    project_root=project_root,
                    project_id=project_id,
                    agent=agent,
                    item_id=f'codex-{thread_id}-{line_number}',
                    mobile_files_dir=mobile_files_dir,
                    file_roots=file_roots,
                )
                if event_item is not None:
                    _set_native_sort_fields(
                        event_item,
                        record,
                        fallback_timestamp=fallback_timestamp,
                        thread_order=thread_order,
                        line_number=line_number,
                    )
                    event_items.append(event_item)
                continue
            if record.get('type') != 'response_item':
                continue
            if payload.get('type') != 'message':
                continue
            role = str(payload.get('role') or '').strip()
            if role not in {'user', 'assistant'}:
                continue
            body = _codex_message_content_text(payload.get('content'))
            body = _inject_workspace_artifacts(
                body,
                project_root=project_root,
                project_id=project_id,
                agent=agent,
                mobile_files_dir=mobile_files_dir,
            )
            body = _clean_native_message_text(body)
            if not body:
                continue
            item_id = f'codex-{thread_id}-{line_number}-{role}'
            if role == 'user':
                item = {
                    'id': item_id,
                    'agent': agent,
                    'kind': 'user_message',
                    'title': 'You',
                    'body': body,
                    'format': 'markdown',
                    'source': 'provider_native/codex',
                    'state': 'sent',
                    'attachments': [],
                }
            else:
                item = {
                    'id': item_id,
                    'agent': agent,
                    'kind': 'agent_reply',
                    'title': 'Agent reply',
                    'body': body,
                    'format': 'markdown',
                    'source': 'provider_native/codex',
                    'attachments': _artifact_link_attachments(
                        body,
                        file_roots=file_roots,
                        project_id=project_id,
                        agent=agent,
                    ),
                }
            _set_native_sort_fields(
                item,
                record,
                fallback_timestamp=fallback_timestamp,
                thread_order=thread_order,
                line_number=line_number,
            )
            response_items.append(item)
    return event_items or response_items


def _set_native_sort_fields(
    item: dict[str, object],
    record: dict[str, object],
    *,
    fallback_timestamp: str,
    thread_order: int,
    line_number: int,
) -> None:
    timestamp = _native_record_timestamp(record) or fallback_timestamp
    created_at = _mobile_conversation_timestamp(timestamp)
    item['_native_sort_timestamp'] = created_at or timestamp
    item['_native_thread_order'] = thread_order
    item['_native_line_number'] = line_number
    if created_at:
        item.setdefault('created_at', created_at)
        if item.get('kind') == 'user_message':
            item.setdefault('sent_at', created_at)
        elif item.get('kind') == 'agent_reply':
            item.setdefault('sent_at', created_at)
            item.setdefault('completed_at', created_at)


def _native_record_timestamp(record: dict[str, object]) -> str | None:
    payload = _map(record.get('payload'))
    return _optional_text(record.get('timestamp')) or _optional_text(
        payload.get('timestamp')
    )


def _mobile_conversation_timestamp(value: object) -> str | None:
    text = _optional_text(value)
    if not text:
        return None
    if re.fullmatch(r'\d+(\.\d+)?', text):
        try:
            return (
                datetime.fromtimestamp(float(text), timezone.utc)
                .isoformat()
                .replace('+00:00', 'Z')
            )
        except Exception:
            return None
    if 'T' not in text:
        return None
    return text


def _mobile_conversation_duration_ms(
    started_at: object,
    completed_at: object,
) -> int | None:
    started = _parse_mobile_conversation_timestamp(started_at)
    completed = _parse_mobile_conversation_timestamp(completed_at)
    if started is None or completed is None:
        return None
    duration_ms = int((completed - started).total_seconds() * 1000)
    return duration_ms if duration_ms >= 0 else None


def _first_mobile_conversation_timestamp(*values: object) -> str | None:
    for value in values:
        timestamp = _mobile_conversation_timestamp(value)
        if timestamp:
            return timestamp
    return None


def _explicit_mobile_conversation_duration_ms(
    *,
    duration_ms: object = None,
    duration_seconds: object = None,
) -> int | None:
    if duration_ms is not None:
        try:
            value = int(duration_ms)
        except (TypeError, ValueError):
            value = None
        if value is not None and value >= 0:
            return value
    if duration_seconds is not None:
        try:
            value = int(float(duration_seconds) * 1000)
        except (TypeError, ValueError):
            value = None
        if value is not None and value >= 0:
            return value
    return None


def _apply_mobile_conversation_timing(
    item: dict[str, object],
    *,
    sent_at: object = None,
    started_at: object = None,
    completed_at: object = None,
    duration_ms: object = None,
    duration_seconds: object = None,
) -> None:
    sent_timestamp = _mobile_conversation_timestamp(sent_at)
    started_timestamp = _mobile_conversation_timestamp(started_at)
    completed_timestamp = _mobile_conversation_timestamp(completed_at)
    if sent_timestamp:
        item.setdefault('sent_at', sent_timestamp)
    if started_timestamp:
        item.setdefault('started_at', started_timestamp)
    if completed_timestamp:
        item.setdefault('completed_at', completed_timestamp)
        if item.get('kind') == 'agent_reply':
            item.setdefault('sent_at', completed_timestamp)
    explicit_duration = _explicit_mobile_conversation_duration_ms(
        duration_ms=duration_ms,
        duration_seconds=duration_seconds,
    )
    computed_duration = _mobile_conversation_duration_ms(
        started_timestamp,
        completed_timestamp,
    )
    final_duration = explicit_duration if explicit_duration is not None else computed_duration
    if final_duration is not None:
        item.setdefault('duration_ms', final_duration)


def _parse_mobile_conversation_timestamp(value: object) -> datetime | None:
    text = _mobile_conversation_timestamp(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace('Z', '+00:00'))
    except Exception:
        return None


def _without_native_sort_fields(item: dict[str, object]) -> dict[str, object]:
    clean = dict(item)
    clean.pop('_native_sort_timestamp', None)
    clean.pop('_native_thread_order', None)
    clean.pop('_native_line_number', None)
    return clean


def _coalesce_codex_native_agent_replies(
    items: list[dict[str, object]],
) -> list[dict[str, object]]:
    grouped: list[dict[str, object]] = []
    pending: dict[str, object] | None = None

    def flush_pending() -> None:
        nonlocal pending
        if pending is not None:
            grouped.append(pending)
            pending = None

    for item in items:
        if not _is_codex_native_agent_reply(item):
            flush_pending()
            grouped.append(item)
            continue
        if pending is None:
            pending = dict(item)
            continue
        if pending.get('_native_thread_order') != item.get('_native_thread_order'):
            flush_pending()
            pending = dict(item)
            continue
        pending['body'] = _join_native_agent_reply_bodies(
            _optional_text(pending.get('body')) or '',
            _optional_text(item.get('body')) or '',
        )
        pending['attachments'] = _merge_attachment_records(
            pending.get('attachments'),
            item.get('attachments'),
        )
        started_at = (
            _optional_text(pending.get('started_at'))
            or _optional_text(pending.get('created_at'))
            or _optional_text(pending.get('sent_at'))
        )
        completed_at = (
            _optional_text(item.get('completed_at'))
            or _optional_text(item.get('sent_at'))
            or _optional_text(item.get('created_at'))
        )
        if started_at:
            pending['started_at'] = started_at
        if completed_at:
            pending['sent_at'] = completed_at
            pending['completed_at'] = completed_at
        duration_ms = _mobile_conversation_duration_ms(started_at, completed_at)
        if duration_ms is not None:
            pending['duration_ms'] = duration_ms
        pending['_native_line_number'] = item.get('_native_line_number')
        pending['_native_sort_timestamp'] = item.get('_native_sort_timestamp')
    flush_pending()
    return grouped


def _is_codex_native_agent_reply(item: dict[str, object]) -> bool:
    return (
        item.get('kind') == 'agent_reply'
        and item.get('source') == 'provider_native/codex'
    )


def _join_native_agent_reply_bodies(left: str, right: str) -> str:
    parts = [part.strip() for part in (left, right) if part.strip()]
    return '\n\n'.join(parts)


def _merge_attachment_records(*values: object) -> list[dict[str, object]]:
    merged: list[dict[str, object]] = []
    seen: set[str] = set()
    for value in values:
        for record in _attachment_records(value):
            key = (
                _optional_text(record.get('file_id'))
                or _optional_text(record.get('download_url'))
                or _optional_text(record.get('file_name'))
                or json.dumps(record, sort_keys=True)
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(record)
    return merged


def _codex_event_message_conversation_item(
    payload: dict[str, object],
    *,
    project_root: Path,
    project_id: str,
    agent: str,
    item_id: str,
    mobile_files_dir: Path | None,
    file_roots: list[Path],
) -> dict[str, object] | None:
    payload_type = str(payload.get('type') or '').strip()
    body = _optional_text(payload.get('message')) or ''
    body = _inject_workspace_artifacts(
        body,
        project_root=project_root,
        project_id=project_id,
        agent=agent,
        mobile_files_dir=mobile_files_dir,
    )
    body = _clean_native_message_text(body)
    if not body:
        return None
    if payload_type == 'user_message':
        return {
            'id': f'{item_id}-user',
            'agent': agent,
            'kind': 'user_message',
            'title': 'You',
            'body': body,
            'format': 'markdown',
            'source': 'provider_native/codex',
            'state': 'sent',
            'attachments': [],
        }
    if payload_type == 'agent_message':
        return {
            'id': f'{item_id}-assistant',
            'agent': agent,
            'kind': 'agent_reply',
            'title': 'Agent reply',
            'body': body,
            'format': 'markdown',
            'source': 'provider_native/codex',
            'attachments': _artifact_link_attachments(
                body,
                file_roots=file_roots,
                project_id=project_id,
                agent=agent,
            ),
        }
    return None


def _codex_message_content_text(value: object) -> str:
    parts: list[str] = []
    for item in _iterable(value):
        content = _map(item)
        text = (
            _optional_text(content.get('text'))
            or _optional_text(content.get('input_text'))
            or _optional_text(content.get('output_text'))
            or ''
        )
        if text:
            parts.append(text)
    return '\n\n'.join(parts)


_CCB_REQ_LINE_RE = re.compile(r'^\s*CCB_(?:REQ_ID|DONE):\s+\S+\s*$', re.IGNORECASE)


def _inject_workspace_artifacts(
    body: str,
    *,
    project_root: Path,
    project_id: str,
    agent: str,
    mobile_files_dir: Path | None,
) -> str:
    if not body:
        return body
    project_root_resolved = project_root.resolve(strict=False)
    mobile_file_root = (
        mobile_files_dir
        if mobile_files_dir is not None
        else project_root / '.ccb' / 'ccbd' / 'mobile' / 'files'
    )

    def repl(match: re.Match) -> str:
        text = match.group(1)
        url = match.group(2)
        parsed = urlparse(url)
        if parsed.scheme or parsed.netloc or url.startswith('#'):
            return match.group(0)
        try:
            link_path = unquote(parsed.path)
            if not link_path.strip():
                return match.group(0)
            target_path = Path(link_path)
            if not target_path.is_absolute():
                target_path = project_root / target_path
            target_path = target_path.resolve(strict=False)
            try:
                relative_path = target_path.relative_to(project_root_resolved)
            except ValueError:
                return match.group(0)
            if relative_path.parts and relative_path.parts[0] in {'.ccb', '.git'}:
                return match.group(0)
            if not target_path.is_file():
                return match.group(0)
            stat = target_path.stat()
            if stat.st_size > _MAX_MOBILE_FILE_BYTES:
                return match.group(0)
            content = target_path.read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            identity = '\0'.join(
                (
                    project_id,
                    agent,
                    relative_path.as_posix(),
                    str(stat.st_size),
                    digest,
                )
            ).encode('utf-8')
            file_id = f'mobile-file-{hashlib.sha256(identity).hexdigest()[:24]}'
            mobile_file_dir = (
                mobile_file_root
                / _safe_path_segment(project_id)
                / _safe_path_segment(agent)
                / file_id
            )
            if not mobile_file_dir.is_dir():
                mobile_file_dir.mkdir(parents=True, exist_ok=True)
                content_path = mobile_file_dir / 'content.bin'
                content_path.write_bytes(content)
                shutil.copystat(target_path, content_path, follow_symlinks=True)
                mime_type = (
                    mimetypes.guess_type(target_path.name)[0]
                    or 'application/octet-stream'
                )
                record = {
                    'schema_version': _SCHEMA_VERSION,
                    'file_id': file_id,
                    'project_id': project_id,
                    'agent': agent,
                    'device_id': 'auto-injected',
                    'file_name': target_path.name,
                    'mime_type': mime_type,
                    'size_bytes': stat.st_size,
                    'sha256': digest,
                    'created_at': _utc_now(),
                }
                (mobile_file_dir / 'metadata.json').write_text(
                    json.dumps(record, ensure_ascii=False, sort_keys=True),
                    encoding='utf-8',
                )
            return f'[{text}](ccb-artifact://{file_id})'
        except Exception:
            return match.group(0)

    return re.sub(r'\[([^\]]+)\]\(([^)]+)\)', repl, body)


def _clean_native_message_text(text: str) -> str:
    lines: list[str] = []
    skipping_reply_guidance = False
    for line in str(text or '').splitlines():
        stripped = line.strip()
        if _CCB_REQ_LINE_RE.match(line):
            continue
        if stripped == 'CCB reply guidance:':
            skipping_reply_guidance = True
            continue
        if skipping_reply_guidance:
            if not stripped or stripped.startswith('- '):
                continue
            skipping_reply_guidance = False
        lines.append(line)
    return '\n'.join(lines).strip()


def _agent_history_conversation_items(
    project_root: Path,
    *,
    project_id: str,
    agent: str,
) -> list[dict[str, object]]:
    latest_by_job: dict[str, dict[str, object]] = {}
    path = project_root / '.ccb' / 'agents' / agent / 'jobs.jsonl'
    try:
        lines = path.read_text(encoding='utf-8').splitlines()
    except Exception:
        return []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            record = _map(json.loads(line))
        except Exception:
            continue
        job_id = _optional_text(record.get('job_id'))
        if not job_id:
            continue
        if not _job_record_belongs_to_agent(record, agent):
            continue
        latest_by_job[job_id] = record

    records = sorted(
        latest_by_job.values(),
        key=lambda item: (
            _optional_text(item.get('created_at'))
            or _optional_text(item.get('updated_at'))
            or '',
            _optional_text(item.get('job_id')) or '',
        ),
    )
    items: list[dict[str, object]] = []
    for record in records:
        status = str(record.get('status') or '').strip().lower()
        if status not in {'completed', 'cancelled', 'failed', 'incomplete'}:
            continue
        request = _map(record.get('request'))
        body = _optional_text(request.get('body')) or ''
        job_id = _optional_text(record.get('job_id')) or f'history-{len(items)}'
        started_at = _first_mobile_conversation_timestamp(
            record.get('started_at'),
            record.get('created_at'),
        )
        completed_at = _first_mobile_conversation_timestamp(
            record.get('completed_at'),
            record.get('finished_at'),
            record.get('updated_at'),
            started_at,
        )
        if body:
            user_item = {
                'id': f'user-{job_id}',
                'agent': agent,
                'kind': 'user_message',
                'title': 'You',
                'body': body,
                'format': 'markdown',
                'source': _history_source(record),
                'state': 'sent' if status == 'completed' else status,
                'attachments': [],
            }
            _apply_mobile_conversation_timing(user_item, sent_at=started_at)
            items.append(
                user_item
            )
        reply_dict = _completion_reply_from_history_job(
            project_root,
            record,
            project_id=project_id,
            agent=agent,
        )
        reply = str(reply_dict.get('body') or '')
        if reply:
            reply_started_at = _first_mobile_conversation_timestamp(
                reply_dict.get('started_at'),
                started_at,
            )
            reply_completed_at = _first_mobile_conversation_timestamp(
                reply_dict.get('completed_at'),
                reply_dict.get('sent_at'),
                completed_at,
            )
            reply_item = {
                'id': f'reply-{job_id}',
                'agent': agent,
                'kind': 'agent_reply',
                'title': 'Agent reply',
                'body': reply,
                'format': 'markdown',
                'source': 'completion_snapshot',
                'attachments': _attachment_records(reply_dict.get('attachments')),
            }
            _apply_mobile_conversation_timing(
                reply_item,
                sent_at=reply_completed_at,
                started_at=reply_started_at,
                completed_at=reply_completed_at,
                duration_ms=reply_dict.get('duration_ms'),
                duration_seconds=reply_dict.get('duration_seconds'),
            )
            items.append(
                reply_item
            )
    return items


def _job_record_belongs_to_agent(record: dict[str, object], agent: str) -> bool:
    request = _map(record.get('request'))
    candidates = (
        _optional_text(record.get('agent_name')),
        _optional_text(record.get('target_name')),
        _optional_text(request.get('to_agent')),
    )
    return agent in {item for item in candidates if item}


def _history_source(record: dict[str, object]) -> str:
    request = _map(record.get('request'))
    route_options = _map(request.get('route_options'))
    return _optional_text(route_options.get('source')) or 'desktop'


def _completion_reply_from_history_job(
    project_root: Path,
    record: dict[str, object],
    *,
    project_id: str,
    agent: str,
) -> dict[str, object]:
    job_id = _optional_text(record.get('job_id'))
    terminal_decision = _map(record.get('terminal_decision'))
    body = _optional_text(terminal_decision.get('reply')) or ''
    reply_dict = _completion_reply_for_job(
        project_root,
        job_id,
        project_id=project_id,
        agent=agent,
    )
    if not body:
        return reply_dict
    attachments = _attachment_records(_map(terminal_decision.get('payload')).get('attachments'))
    if not attachments:
        attachments = _attachment_records(reply_dict.get('attachments'))
    if not attachments:
        attachments = _artifact_link_attachments(
            body,
            file_roots=_mobile_file_roots_for_job(project_root, agent, job_id or ''),
            project_id=project_id,
            agent=agent,
        )
    return {'body': body, 'attachments': attachments}


def _agent_conversation_page(
    items: list[dict[str, object]],
    *,
    limit: int,
    cursor: str | None,
) -> dict[str, object]:
    if cursor is None:
        end = len(items)
    else:
        try:
            end = int(cursor)
        except ValueError as exc:
            raise MobileGatewayError('cursor must be an integer', status_code=400) from exc
        if end < 0 or end > len(items):
            raise MobileGatewayError('cursor is out of range', status_code=400)
    start = max(0, end - limit)
    return {
        'items': items[start:end],
        'next_cursor': str(start) if start > 0 else None,
    }


def _conversation_item_belongs_to_agent(item: dict[str, object], agent: str) -> bool:
    item_agent = (
        _optional_text(item.get('agent'))
        or _optional_text(item.get('agent_name'))
        or _optional_text(item.get('target'))
        or _optional_text(item.get('target_agent'))
    )
    if item_agent is not None:
        return item_agent == agent
    targets = item.get('target_agents')
    if isinstance(targets, (list, tuple, set)):
        return agent in {str(target) for target in targets}
    return True


def _completion_reply_for_job(
    project_root: Path,
    job_id: str | None,
    *,
    project_id: str,
    agent: str,
) -> dict[str, object]:
    if not job_id:
        return {'body': '', 'attachments': []}
    path = project_root / '.ccb' / 'ccbd' / 'snapshots' / f'{job_id}.json'
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {'body': '', 'attachments': []}
    latest_decision = _map(payload.get('latest_decision'))
    body = (
        _optional_text(latest_decision.get('reply'))
        or _optional_text(payload.get('latest_reply_preview'))
        or ''
    )
    started_at = _first_mobile_conversation_timestamp(
        latest_decision.get('started_at'),
        latest_decision.get('execution_started_at'),
        payload.get('started_at'),
        payload.get('execution_started_at'),
        payload.get('created_at'),
    )
    completed_at = _first_mobile_conversation_timestamp(
        latest_decision.get('completed_at'),
        latest_decision.get('finished_at'),
        latest_decision.get('execution_completed_at'),
        latest_decision.get('created_at'),
        payload.get('completed_at'),
        payload.get('finished_at'),
        payload.get('execution_completed_at'),
        payload.get('updated_at'),
        payload.get('created_at'),
    )
    duration_ms = (
        _explicit_mobile_conversation_duration_ms(
            duration_ms=latest_decision.get('duration_ms') or payload.get('duration_ms'),
            duration_seconds=(
                latest_decision.get('duration_seconds')
                or payload.get('duration_seconds')
            ),
        )
        or _mobile_conversation_duration_ms(started_at, completed_at)
    )

    attachments = []
    payload_obj = _map(latest_decision.get('payload'))
    if 'attachments' in payload_obj:
        attachments = _attachment_records(payload_obj.get('attachments'))
    if not attachments:
        attachments = _artifact_link_attachments(
            body,
            file_roots=_mobile_file_roots_for_job(project_root, agent, job_id),
            project_id=project_id,
            agent=agent,
        )
    result: dict[str, object] = {'body': body, 'attachments': attachments}
    if started_at:
        result['started_at'] = started_at
    if completed_at:
        result['sent_at'] = completed_at
        result['completed_at'] = completed_at
    if duration_ms is not None:
        result['duration_ms'] = duration_ms
    return result


def _artifact_link_attachments(
    body: str,
    *,
    file_roots: list[Path],
    project_id: str,
    agent: str,
) -> list[dict[str, object]]:
    attachments: list[dict[str, object]] = []
    seen: set[str] = set()
    for file_id in _artifact_file_ids(body):
        if file_id in seen:
            continue
        seen.add(file_id)
        for file_root in file_roots:
            try:
                directory = (
                    file_root
                    / _safe_path_segment(project_id)
                    / _safe_path_segment(agent)
                    / _safe_path_segment(file_id)
                )
            except MobileGatewayError:
                continue
            metadata = _read_file_metadata(directory)
            if not metadata:
                continue
            attachments.extend(_attachment_records([metadata]))
            break
    return attachments


def _mobile_file_roots_for_job(project_root: Path, agent: str, job_id: str) -> list[Path]:
    roots: list[Path] = [project_root / '.ccb' / 'ccbd' / 'mobile' / 'files']
    jobs_path = project_root / '.ccb' / 'agents' / agent / 'jobs.jsonl'
    try:
        lines = jobs_path.read_text(encoding='utf-8').splitlines()
    except Exception:
        return roots
    for line in lines:
        try:
            record = json.loads(line)
        except Exception:
            continue
        if str(_map(record).get('job_id') or '') != job_id:
            continue
        request = _map(_map(record).get('request'))
        route_options = _map(request.get('route_options'))
        mobile_files_dir = _optional_text(route_options.get('mobile_files_dir'))
        if mobile_files_dir:
            path = Path(mobile_files_dir).expanduser()
            if path not in roots:
                roots.insert(0, path)
    return roots


def _artifact_file_ids(body: str) -> list[str]:
    if not body:
        return []
    return [
        match.group(1)
        for match in re.finditer(r'ccb-artifact://([A-Za-z0-9._-]+)', body)
    ]


def _agent_status_summary(agent: dict[str, object]) -> str:
    state = _optional_text(agent.get('state')) or 'idle'
    health = _optional_text(agent.get('runtime_health')) or 'unknown'
    queue_depth = _int(agent.get('queue_depth'), 0)
    if queue_depth > 0:
        suffix = '' if queue_depth == 1 else 's'
        return f'{state}, {health}, {queue_depth} queued item{suffix}'
    return f'{state}, {health}, no queued items'


def _validate_terminal_summary(record: dict[str, object], view: dict[str, object]) -> None:
    summary = _map(record.get('target_summary'))
    agent = _optional_text(summary.get('agent'))
    window = _optional_text(summary.get('window'))
    agents = [_map(item) for item in _iterable(view.get('agents'))]
    windows = [_map(item) for item in _iterable(view.get('windows'))]
    if agent and not any(str(item.get('name') or '') == agent for item in agents):
        raise MobileGatewayError('unknown terminal target agent', status_code=404)
    if window and not any(str(item.get('name') or '') == window for item in windows):
        raise MobileGatewayError('unknown terminal target window', status_code=404)
    pane_id = _optional_text(summary.get('pane_id'))
    if pane_id and agent:
        matched = next((item for item in agents if str(item.get('name') or '') == agent), None)
        if matched is None or _optional_text(matched.get('pane_id')) != pane_id:
            raise MobileGatewayError('unknown terminal target pane', status_code=404)


def _validate_terminal_target(
    project_id: str,
    view_payload: dict[str, object],
    *,
    target: dict[str, object],
    namespace_epoch: int | None,
) -> dict[str, object]:
    view = _map(view_payload.get('view'))
    namespace = _map(view.get('namespace'))
    actual_epoch = _optional_int(namespace.get('epoch'))
    if actual_epoch is None:
        raise MobileGatewayError('ProjectView namespace epoch is required', status_code=409)
    if namespace_epoch != actual_epoch:
        raise MobileGatewayError('stale namespace epoch', status_code=409)
    if not _optional_text(namespace.get('socket_path')) or not _optional_text(namespace.get('session_name')):
        raise MobileGatewayError('ProjectView tmux evidence is not attachable', status_code=409)

    kind = str(target.get('kind') or '').strip()
    agent = _optional_text(target.get('agent'))
    window = _optional_text(target.get('window'))
    pane_id = _optional_text(target.get('pane_id'))
    agents = [_map(item) for item in _iterable(view.get('agents'))]
    windows = [_map(item) for item in _iterable(view.get('windows'))]

    if kind == 'agent':
        if not agent:
            raise MobileGatewayError('terminal target agent is required', status_code=400)
        matched = next((item for item in agents if str(item.get('name') or '') == agent), None)
        if matched is None:
            raise MobileGatewayError('unknown terminal target agent', status_code=404)
        matched_window = _optional_text(matched.get('window')) or window
        if window and matched_window and window != matched_window:
            raise MobileGatewayError('terminal target window does not match agent', status_code=409)
        matched_pane_id = _optional_text(matched.get('pane_id')) or pane_id
        return {
            'target_epoch': actual_epoch,
            'target_summary': {
                'project_id': project_id,
                'agent': agent,
                'window': matched_window,
                **({'pane_id': matched_pane_id} if matched_pane_id else {}),
            },
        }
    if kind == 'window_active_pane':
        if not window:
            raise MobileGatewayError('terminal target window is required', status_code=400)
        if not any(str(item.get('name') or '') == window for item in windows):
            raise MobileGatewayError('unknown terminal target window', status_code=404)
        return {
            'target_epoch': actual_epoch,
            'target_summary': {
                'project_id': project_id,
                'window': window,
            },
        }
    if kind == 'pane_evidence':
        if not agent and not window:
            raise MobileGatewayError('pane evidence must include agent or window', status_code=400)
        if agent and not any(str(item.get('name') or '') == agent for item in agents):
            raise MobileGatewayError('unknown terminal target agent', status_code=404)
        if window and not any(str(item.get('name') or '') == window for item in windows):
            raise MobileGatewayError('unknown terminal target window', status_code=404)
        summary = {'project_id': project_id}
        if agent:
            summary['agent'] = agent
        if window:
            summary['window'] = window
        if pane_id:
            summary['pane_id'] = pane_id
        return {
            'target_epoch': actual_epoch,
            'target_summary': summary,
        }
    raise MobileGatewayError('unknown terminal target kind', status_code=400)


def _terminal_history_target(
    *,
    project_id: str,
    view_payload: dict[str, object],
    agent: str | None,
    namespace_epoch: int | None,
    max_lines: int,
) -> TerminalHistoryTarget:
    view = _map(view_payload.get('view'))
    namespace = _map(view.get('namespace'))
    actual_epoch = _optional_int(namespace.get('epoch'))
    if actual_epoch is None:
        raise MobileGatewayError('ProjectView namespace epoch is required', status_code=409)
    if namespace_epoch != actual_epoch:
        raise MobileGatewayError('stale namespace epoch', status_code=409)
    socket_path = _optional_text(namespace.get('socket_path'))
    session_name = _optional_text(namespace.get('session_name'))
    if not socket_path or not session_name:
        raise MobileGatewayError('ProjectView tmux evidence is not attachable', status_code=409)
    agent_name = str(agent or '').strip()
    if not agent_name:
        raise MobileGatewayError('agent is required', status_code=400)
    agents = [_map(item) for item in _iterable(view.get('agents'))]
    matched = next((item for item in agents if str(item.get('name') or '') == agent_name), None)
    if matched is None:
        raise MobileGatewayError('unknown terminal target agent', status_code=404)
    pane_id = _optional_text(matched.get('pane_id'))
    if not pane_id:
        raise MobileGatewayError('terminal history target has no pane evidence', status_code=409)
    return TerminalHistoryTarget(
        project_id=project_id,
        namespace_epoch=actual_epoch,
        agent=agent_name,
        window=_optional_text(matched.get('window')) or '',
        pane_id=pane_id,
        socket_path=socket_path,
        session_name=session_name,
        max_lines=min(2000, max(20, int(max_lines))),
    )


def _pane_message_target(
    *,
    project_id: str,
    view_payload: dict[str, object],
    target: dict[str, object],
) -> PaneMessageTarget:
    view = _map(view_payload.get('view'))
    namespace = _map(view.get('namespace'))
    socket_path = _optional_text(namespace.get('socket_path'))
    session_name = _optional_text(namespace.get('session_name'))
    if not socket_path or not session_name:
        raise MobileGatewayError('ProjectView tmux evidence is not attachable', status_code=409)
    agent_record = _map(target.get('agent_record'))
    pane_id = _optional_text(agent_record.get('pane_id'))
    if not pane_id:
        raise MobileGatewayError('message target has no pane evidence', status_code=409)
    return PaneMessageTarget(
        project_id=project_id,
        namespace_epoch=int(target.get('namespace_epoch') or 0),
        agent=str(target.get('agent') or ''),
        window=_optional_text(agent_record.get('window')) or '',
        pane_id=pane_id,
        socket_path=socket_path,
        session_name=session_name,
    )


def _iterable(value: object):
    return value if isinstance(value, list) else []


def _query_text(query: Mapping[str, object], name: str) -> str | None:
    value = query.get(name)
    if isinstance(value, list):
        return _optional_text(value[0] if value else None)
    return _optional_text(value)


def _query_int(query: Mapping[str, object], name: str) -> int | None:
    text = _query_text(query, name)
    if text is None:
        return None
    try:
        return int(text)
    except ValueError as exc:
        raise MobileGatewayError(f'{name} must be an integer', status_code=400) from exc


def _required_positive_int(value: object, name: str) -> int:
    parsed = _optional_int(value)
    if parsed is None or parsed < 1:
        raise MobileGatewayError(f'{name} must be a positive integer', status_code=400)
    return parsed


def _terminal_websocket_url(headers: Mapping[str, object] | None, *, terminal_id: str) -> str:
    proto = _header_value(headers, 'x-forwarded-proto').lower()
    scheme = 'wss' if proto == 'https' else 'ws'
    host = _header_value(headers, 'x-forwarded-host') or _header_value(headers, 'host') or '127.0.0.1:8787'
    return f'{scheme}://{host}/v1/terminals/{terminal_id}'


def _header_value(headers: Mapping[str, object] | None, name: str) -> str:
    if headers is None:
        return ''
    get = getattr(headers, 'get', None)
    if callable(get):
        value = get(name) or get(name.title())
        if value:
            return str(value).strip()
    for key, item in headers.items():
        if str(key).lower() == name.lower():
            return str(item or '').strip()
    return ''


def _ccbd_focus_status(exc: Exception) -> int:
    text = _error_text(exc)
    if text.startswith('stale_view:'):
        return 409
    if text.startswith('unknown_agent:') or text.startswith('unknown_window:'):
        return 404
    if text.startswith('invalid_request:') or text.startswith('target_missing:'):
        return 400
    return 503


def _terminal_error_code(exc: MobileGatewayError) -> str:
    text = _error_text(exc)
    if text.startswith('stale namespace epoch'):
        return 'stale_namespace_epoch'
    if text.startswith('resume_cursor is required'):
        return 'missing_resume_cursor'
    if text.startswith('terminal resume cursor is stale'):
        return 'stale_resume_cursor'
    if text.startswith('unknown terminal target agent'):
        return 'unknown_agent'
    if text.startswith('unknown terminal target window'):
        return 'unknown_window'
    if text.startswith('ProjectView tmux evidence is not attachable'):
        return 'target_not_attachable'
    return 'terminal_error'


def _pump_terminal_output(
    connection: WebSocketConnection,
    session,
    stop: threading.Event,
    close_state: dict[str, str],
    store: MobileGatewayPairingStore,
    terminal_id: str,
    terminal_token: str,
    sequence: int,
) -> None:
    try:
        while not stop.is_set():
            data = session.read(0.1)
            if data is None:
                close_state['reason'] = 'pty_closed'
                _safe_send_json(connection, {'type': 'closed', 'reason': 'pty_closed'})
                stop.set()
                return
            if data:
                sequence += 1
                try:
                    connection.send_json(
                        {
                            'type': 'output',
                            'seq': sequence,
                            'bytes_b64': base64.b64encode(data).decode('ascii'),
                        },
                    )
                except OSError:
                    close_state['reason'] = 'transport_disconnected'
                    stop.set()
                    return
                store.record_terminal_output_sequence(
                    terminal_id=terminal_id,
                    terminal_token=terminal_token,
                    sequence=sequence,
                )
    except Exception as exc:
        close_state['reason'] = 'terminal_output_error'
        _safe_send_json(connection, {'type': 'error', 'code': 'terminal_output_error', 'message': _error_text(exc)})
        stop.set()


def _safe_send_json(connection: WebSocketConnection, payload: Mapping[str, object]) -> None:
    try:
        connection.send_json(payload)
    except OSError:
        pass


def _bearer_token(headers: Mapping[str, object] | None) -> str:
    if headers is None:
        return ''
    value = ''
    get = getattr(headers, 'get', None)
    if callable(get):
        value = str(get('authorization') or get('Authorization') or '')
    if not value and isinstance(headers, Mapping):
        for key, item in headers.items():
            if str(key).lower() == 'authorization':
                value = str(item or '')
                break
    prefix = 'bearer '
    if value.lower().startswith(prefix):
        return value[len(prefix):].strip()
    return ''


__all__ = [
    'ListenAddress',
    'MobileGatewayError',
    'MobileGatewayService',
    'build_mobile_gateway_server',
    'parse_listen_address',
]
