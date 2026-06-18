from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from typing import Callable, Mapping
from urllib.parse import unquote, urlparse

from ccbd.socket_client import CcbdClientError
from .pairing import MobileGatewayPairingError, MobileGatewayPairingStore

_DEFAULT_HOST = '127.0.0.1'
_DEFAULT_PORT = 8787
_SCHEMA_VERSION = 1
_BASE_CAPABILITIES = ('http_json', 'project_view')
_PAIRING_CAPABILITIES = ('pairing', 'device_tokens')
_REDACTED_NAMESPACE_KEYS = ('socket_path', 'session_name')
_DEFAULT_ROUTE_PROVIDER = 'lan'
_DEFAULT_PAIRING_SCOPES = ('view',)


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
    ) -> None:
        self._project_id = str(project_id)
        self._project_root = Path(project_root)
        self._ccbd_client_factory = ccbd_client_factory
        self._clock = clock or _utc_now
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

    def _client(self):
        return self._ccbd_client_factory()

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
