from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import threading
from typing import Callable, Mapping
from uuid import uuid4
from urllib.parse import parse_qs, unquote, urlparse

from ccbd.api_models import DeliveryScope, MessageEnvelope
from ccbd.socket_client import CcbdClientError
from .pairing import MobileGatewayPairingError, MobileGatewayPairingStore
from .project_registry import MobileGatewayProject, MobileGatewayProjectRegistry
from .terminal import (
    TerminalAttachTarget,
    TerminalGeometry,
    TerminalHistoryTarget,
    create_tmux_terminal_history,
    create_tmux_terminal_session,
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
)
_REDACTED_NAMESPACE_KEYS = ('socket_path', 'session_name')
_DEFAULT_ROUTE_PROVIDER = 'lan'
_DEFAULT_PAIRING_SCOPES = (
    'view',
    'content',
    'focus',
    'ask',
    'message_submit',
    'file_upload',
    'file_download',
    'terminal_input',
    'lifecycle',
)
_MAX_MOBILE_FILE_BYTES = 25 * 1024 * 1024


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
        self._mobile_dir = Path(mobile_dir) if mobile_dir is not None else None
        self._pairing_store = pairing_store
        if self._pairing_store is None and mobile_dir is not None:
            self._pairing_store = MobileGatewayPairingStore(self._mobile_dir)

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
        for project in self._project_registry.projects():
            ccbd = self._ping_or_unavailable(project)
            projects.append(
                {
                    'id': project.project_id,
                    'display_name': project.public_display_name,
                    'root': str(project.project_root),
                    'health': str(ccbd.get('health') or 'unknown'),
                    'mount_state': str(ccbd.get('mount_state') or ''),
                    'capabilities': self._capabilities(),
                }
            )
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
        items = _agent_conversation_items(
            view_payload,
            project_id=self._project_id,
            agent=target['agent'],
            namespace_epoch=int(target['namespace_epoch']),
            limit=limit,
            project_root=project.project_root,
        )
        return {
            'schema_version': _SCHEMA_VERSION,
            'status': 'ok',
            'conversation': {
                'project_id': project.project_id,
                'agent': target['agent'],
                'namespace_epoch': target['namespace_epoch'],
                'generated_at': self._clock(),
                'items': items,
            },
        }

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
        self._require_current_project(project_id)
        auth = self._authenticate_any_scope(
            headers,
            allowed_scopes=('file_upload', 'message_submit', 'ask'),
        )
        if len(body) > _MAX_MOBILE_FILE_BYTES:
            raise MobileGatewayError('file too large', status_code=413)
        view_payload = self._request_project_view()
        view = _map(view_payload.get('view'))
        namespace = _map(view.get('namespace'))
        target_record = _validate_agent_conversation_target(
            project_id=self._project_id,
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
            'project_id': self._project_id,
            'agent': target_record['agent'],
            'device_id': auth.device_id,
            'file_name': file_name,
            'mime_type': mime_type,
            'size_bytes': len(body),
            'sha256': digest,
            'created_at': self._clock(),
        }
        directory = self._mobile_file_dir(self._project_id, str(target_record['agent']), file_id)
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
        self._require_current_project(project_id)
        self._authenticate_any_scope(
            headers,
            allowed_scopes=('file_download', 'content', 'view'),
        )
        directory = self._mobile_file_dir(self._project_id, agent, file_id)
        metadata = _read_file_metadata(directory)
        if not metadata:
            raise MobileGatewayError('unknown file', status_code=404)
        if str(metadata.get('project_id') or '') != self._project_id:
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
        auth = self._authenticate_any_scope(
            headers,
            allowed_scopes=('ask', 'message_submit'),
        )
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
        try:
            receipt = project.client().submit(
                MessageEnvelope(
                    project_id=project.project_id,
                    to_agent=target['agent'],
                    from_actor='user',
                    body=submit_body,
                    task_id=None,
                    reply_to=None,
                    message_type='ask',
                    delivery_scope=DeliveryScope.SINGLE,
                    silence_on_success=False,
                    route_options={
                        'source': 'mobile_gateway',
                        'device_id': auth.device_id,
                        'idempotency_key': idempotency_key,
                        'format': message_format,
                        'attachments': attachments,
                        'mobile_files_dir': str(self._mobile_files_dir()),
                    },
                    body_artifact=None,
                )
            )
        except CcbdClientError as exc:
            raise MobileGatewayError(str(exc), status_code=503) from exc
        except Exception as exc:
            raise MobileGatewayError(_error_text(exc), status_code=503) from exc
        result = dict(receipt or {}) if isinstance(receipt, Mapping) else {}
        job_id = str(result.get('job_id') or '')
        state = str(result.get('status') or 'queued')
        message_id = str(result.get('message_id') or job_id or idempotency_key)
        return {
            'schema_version': _SCHEMA_VERSION,
            'status': 'ok',
            'project_id': project.project_id,
            'agent': target['agent'],
            'message_submit': {
                'accepted': True,
                'idempotency_key': idempotency_key,
                'message_id': message_id,
                'job_id': job_id or None,
                'state': state,
                'created_at': result.get('accepted_at') or self._clock(),
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

    def _request_project_view(self, project: MobileGatewayProject) -> dict[str, object]:
        try:
            payload = project.client().project_view(schema_version=1)
        except CcbdClientError as exc:
            raise MobileGatewayError(str(exc), status_code=503) from exc
        except Exception as exc:
            raise MobileGatewayError(_error_text(exc), status_code=503) from exc
        return dict(payload or {}) if isinstance(payload, dict) else {}

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
            self.wfile.write(body)

        def _send_bytes(self, status: int, body: bytes, headers: dict[str, str]) -> None:
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.send_header('content-length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

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


def _ccbd_health_summary(payload: dict[str, object]) -> dict[str, object]:
    return {
        'reachable': True,
        'project_id': payload.get('project_id'),
        'mount_state': payload.get('mount_state'),
        'health': payload.get('health'),
        'namespace_epoch': payload.get('namespace_epoch'),
        'namespace_ui_attachable': payload.get('namespace_ui_attachable'),
    }


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
    limit: int,
    project_root: Path,
) -> list[dict[str, object]]:
    view = _map(view_payload.get('view'))
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
        items.append(
            {
                'id': f'reply-{content_id}',
                'agent': agent,
                'kind': 'agent_reply',
                'title': _optional_text(content_item.get('title')) or 'Agent reply',
                'body': body,
                'format': _optional_text(content_item.get('format')) or 'plain',
                'content_id': content_id,
                'source': _optional_text(content_item.get('source')) or 'content',
            }
        )
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
        if reply:
            comm_id = str(comm.get('id') or f'comms-{len(items)}')
            if body:
                items.append(
                    {
                        'id': f'user-{comm_id}',
                        'agent': agent,
                        'kind': 'user_message',
                        'title': 'You',
                        'body': body,
                        'format': _optional_text(comm.get('format')) or 'markdown',
                        'source': 'mobile',
                        'state': 'sent',
                        'attachments': attachments,
                    }
                )
            items.append(
                {
                    'id': f'reply-{comm_id}',
                    'agent': agent,
                    'kind': 'agent_reply',
                    'title': _optional_text(comm.get('title')) or 'Agent reply',
                    'body': reply,
                    'format': 'markdown',
                    'source': 'completion_snapshot',
                    'attachments': reply_attachments,
                }
            )
            continue
        if not body:
            continue
        comm_id = str(comm.get('id') or f'comms-{len(items)}')
        items.append(
            {
                'id': f'comms-{comm_id}',
                'agent': agent,
                'kind': 'comms_item',
                'title': _optional_text(comm.get('title')) or 'Comms',
                'body': body,
                'format': _optional_text(comm.get('format')) or 'plain',
                'source': _optional_text(comm.get('source')) or 'project_view',
                'attachments': attachments,
            }
        )
    if len(items) > limit:
        return items[:limit]
    return items


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
    
    attachments = []
    payload_obj = _map(latest_decision.get('payload'))
    if 'attachments' in payload_obj:
        attachments = _attachment_records(payload_obj.get('attachments'))
    if not attachments:
        attachments = _artifact_link_attachments(
            body,
            project_root=project_root,
            project_id=project_id,
            agent=agent,
        )
    return {'body': body, 'attachments': attachments}


def _artifact_link_attachments(
    body: str,
    *,
    project_root: Path,
    project_id: str,
    agent: str,
) -> list[dict[str, object]]:
    attachments: list[dict[str, object]] = []
    seen: set[str] = set()
    for file_id in _artifact_file_ids(body):
        if file_id in seen:
            continue
        seen.add(file_id)
        directory = (
            project_root
            / '.ccb'
            / 'ccbd'
            / 'mobile'
            / 'files'
            / _safe_path_segment(project_id)
            / _safe_path_segment(agent)
            / _safe_path_segment(file_id)
        )
        metadata = _read_file_metadata(directory)
        if not metadata:
            continue
        attachments.extend(_attachment_records([metadata]))
    return attachments


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
        return {
            'target_epoch': actual_epoch,
            'target_summary': {
                'project_id': project_id,
                'agent': agent,
                'window': matched_window,
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
