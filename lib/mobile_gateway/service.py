from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from typing import Callable, Mapping
from urllib.parse import unquote, urlparse

from ccbd.socket_client import CcbdClientError
from .pairing import MobileGatewayPairingError, MobileGatewayPairingStore
from .terminal import TerminalAttachTarget, TerminalGeometry, create_tmux_terminal_session
from .websocket import WebSocketConnection, WebSocketProtocolError, accept_websocket, is_websocket_upgrade

_DEFAULT_HOST = '127.0.0.1'
_DEFAULT_PORT = 8787
_SCHEMA_VERSION = 1
_BASE_CAPABILITIES = ('http_json', 'project_view')
_PAIRING_CAPABILITIES = ('pairing', 'device_tokens', 'focus', 'terminal_open', 'websocket_terminal')
_REDACTED_NAMESPACE_KEYS = ('socket_path', 'session_name')
_DEFAULT_ROUTE_PROVIDER = 'lan'
_DEFAULT_PAIRING_SCOPES = ('view', 'focus', 'terminal_input')


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
        clock: Callable[[], str] | None = None,
        terminal_session_factory: Callable[[TerminalAttachTarget], object] | None = None,
    ) -> None:
        self._project_id = str(project_id)
        self._project_root = Path(project_root)
        self._ccbd_client_factory = ccbd_client_factory
        self._clock = clock or _utc_now
        self._terminal_session_factory = terminal_session_factory or create_tmux_terminal_session
        self._pairing_store = pairing_store
        if self._pairing_store is None and mobile_dir is not None:
            self._pairing_store = MobileGatewayPairingStore(Path(mobile_dir))

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
                'mode': 'loopback_current_project',
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
            'mode': 'loopback_current_project',
            'project_id': self._project_id,
            'capabilities': self._capabilities(),
            'ccbd': _ccbd_health_summary(ccbd),
        }

    def projects_payload(self) -> dict[str, object]:
        ccbd = self._ping_or_unavailable()
        return {
            'schema_version': _SCHEMA_VERSION,
            'projects': [
                {
                    'id': self._project_id,
                    'display_name': self._project_root.name,
                    'health': str(ccbd.get('health') or 'unknown'),
                    'capabilities': self._capabilities(),
                }
            ],
        }

    def project_view_payload(self, project_id: str) -> dict[str, object]:
        requested = str(project_id or '').strip()
        if requested != self._project_id:
            raise MobileGatewayError('unknown project', status_code=404)
        payload = self._request_project_view()
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
            return 200, self.project_view_payload(project_id)
        if route == '/v1/devices/me':
            device = self._authenticate(headers, required_scopes=('view',))
            return 200, {
                'schema_version': _SCHEMA_VERSION,
                'status': 'ok',
                'device': device.public_payload(),
            }
        raise MobileGatewayError('not found', status_code=404)

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
            if action == 'terminals':
                return 201, self._open_terminal(
                    project_id=project_id,
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
        self._require_current_project(project_id)
        self._authenticate(headers, required_scopes=('focus',))
        if not str(agent or '').strip():
            raise MobileGatewayError('agent is required', status_code=400)
        try:
            focus = self._client().project_focus_agent(agent=agent, namespace_epoch=namespace_epoch)
        except CcbdClientError as exc:
            raise MobileGatewayError(str(exc), status_code=_ccbd_focus_status(exc)) from exc
        except Exception as exc:
            raise MobileGatewayError(_error_text(exc), status_code=503) from exc
        return self._focused_project_view_payload(focus)

    def _focus_window(
        self,
        *,
        project_id: str,
        window: str,
        namespace_epoch: int | None,
        headers: Mapping[str, object] | None,
    ) -> dict[str, object]:
        self._require_current_project(project_id)
        self._authenticate(headers, required_scopes=('focus',))
        if not str(window or '').strip():
            raise MobileGatewayError('window is required', status_code=400)
        try:
            focus = self._client().project_focus_window(window=window, namespace_epoch=namespace_epoch)
        except CcbdClientError as exc:
            raise MobileGatewayError(str(exc), status_code=_ccbd_focus_status(exc)) from exc
        except Exception as exc:
            raise MobileGatewayError(_error_text(exc), status_code=503) from exc
        return self._focused_project_view_payload(focus)

    def _open_terminal(
        self,
        *,
        project_id: str,
        payload: Mapping[str, object],
        headers: Mapping[str, object] | None,
    ) -> dict[str, object]:
        self._require_current_project(project_id)
        auth = self._authenticate(headers, required_scopes=('terminal_input',))
        body_project_id = str(payload.get('project_id') or '').strip()
        if body_project_id and body_project_id != self._project_id:
            raise MobileGatewayError('request project_id does not match route', status_code=400)
        target = _map(payload.get('target'))
        geometry = _map(payload.get('geometry'))
        view_payload = self._request_project_view()
        target_payload = _validate_terminal_target(
            self._project_id,
            view_payload,
            target=target,
            namespace_epoch=_optional_int(payload.get('namespace_epoch')),
        )
        handle = self._require_pairing_store().create_terminal_handle(
            project_id=self._project_id,
            device_id=auth.device_id,
            target_epoch=int(target_payload['target_epoch']),
            target_summary=target_payload['target_summary'],
            geometry=geometry,
        )
        terminal_id = str(handle.get('terminal_id') or '')
        handle['websocket_url'] = _terminal_websocket_url(headers, terminal_id=terminal_id)
        return handle

    def _focused_project_view_payload(self, focus: dict[str, object]) -> dict[str, object]:
        payload = self._request_project_view()
        redacted = _redact_project_view_payload(payload)
        redacted['focus'] = dict(focus or {}) if isinstance(focus, dict) else {}
        return redacted

    def _require_current_project(self, project_id: str) -> None:
        requested = str(project_id or '').strip()
        if requested != self._project_id:
            raise MobileGatewayError('unknown project', status_code=404)

    def _require_pairing_store(self) -> MobileGatewayPairingStore:
        if self._pairing_store is None:
            raise MobileGatewayError('mobile pairing store is not configured', status_code=503)
        return self._pairing_store

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

    def _ping_or_unavailable(self) -> dict[str, object]:
        try:
            payload = self._client().ping('ccbd')
        except CcbdClientError as exc:
            raise MobileGatewayError(str(exc), status_code=503) from exc
        except Exception as exc:
            raise MobileGatewayError(_error_text(exc), status_code=503) from exc
        return dict(payload or {}) if isinstance(payload, dict) else {}

    def _request_project_view(self) -> dict[str, object]:
        try:
            payload = self._client().project_view(schema_version=1)
        except CcbdClientError as exc:
            raise MobileGatewayError(str(exc), status_code=503) from exc
        except Exception as exc:
            raise MobileGatewayError(_error_text(exc), status_code=503) from exc
        return dict(payload or {}) if isinstance(payload, dict) else {}

    def _terminal_attach_target(self, record: dict[str, object]) -> TerminalAttachTarget:
        view_payload = self._request_project_view()
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


def _map(value: object) -> dict[str, object]:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    return {}


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
    if action not in {'focus-agent', 'focus-window', 'terminals'}:
        return None
    return unquote(project_id), action


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


def _iterable(value: object):
    return value if isinstance(value, list) else []


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
