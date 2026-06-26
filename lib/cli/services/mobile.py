from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import socket
from urllib.parse import urlparse, urlunsplit

from ccbd.socket_client import CcbdClient
from mobile_gateway import (
    MobileGatewayProjectRegistry,
    MobileGatewayPairingStore,
    MobileGatewayService,
    build_mobile_gateway_server,
    load_mobile_gateway_project_registry,
    mobile_host_state_dir,
    parse_listen_address,
)
from mobile_gateway.relay import LocalRelayServerHarness, MobileGatewayRelayOutboundClient


@dataclass(frozen=True)
class MobileGatewayServeHandle:
    summary: dict[str, object]
    server: object

    def serve_forever(self) -> None:
        self.server.serve_forever()

    def close(self) -> None:
        self.server.server_close()


def prepare_mobile_gateway(context, command) -> MobileGatewayServeHandle:
    listen = parse_listen_address(command.listen)
    service = MobileGatewayService(
        project_id=context.project.project_id,
        project_root=context.project.project_root,
        ccbd_client_factory=lambda: CcbdClient(context.paths.ccbd_socket_path),
        mobile_dir=context.paths.ccbd_mobile_dir,
    )
    server = build_mobile_gateway_server(listen, service)
    host, port = server.server_address[:2]
    local_gateway_url = f'http://{host}:{port}'
    gateway_url = _public_gateway_url(command.public_url, fallback=local_gateway_url)
    route_provider = str(command.route_provider or 'lan')
    pairing = service.create_pairing_payload(gateway_url=gateway_url, route_provider=route_provider)
    relay_outbound = _relay_outbound_summary(context.project.project_id) if route_provider == 'relay' else None
    summary = {
        'mobile_status': 'serving',
        'listen': f'{host}:{port}',
        'gateway_url': gateway_url,
        'local_gateway_url': local_gateway_url,
        'route_provider': route_provider,
        'project_id': context.project.project_id,
        'project_root': str(context.project.project_root),
        'mode': 'loopback_current_project',
        'pairing': pairing,
        'endpoints': [
            '/v1/health',
            '/v1/projects',
            '/v1/projects/{project_id}/view',
            '/v1/pairing/claim',
            '/v1/devices/me',
            '/v1/devices/{device_id}/revoke',
            '/v1/projects/{project_id}/lifecycle',
            '/v1/projects/{project_id}/focus-agent',
            '/v1/projects/{project_id}/focus-window',
            '/v1/projects/{project_id}/terminals',
            '/v1/terminals/{terminal_id}',
        ],
    }
    if relay_outbound is not None:
        summary['relay_outbound'] = relay_outbound
    return MobileGatewayServeHandle(
        summary=summary,
        server=server,
    )


def prepare_server_mobile_gateway(
    command,
    *,
    project_registry: MobileGatewayProjectRegistry | None = None,
    host_id: str | None = None,
) -> MobileGatewayServeHandle:
    registry = project_registry or load_mobile_gateway_project_registry()
    listen = parse_listen_address(command.listen)
    resolved_host_id = str(host_id or '').strip() or _server_host_id()
    state_dir = mobile_host_state_dir()
    default_project = registry.default_project
    service = MobileGatewayService(
        project_id=resolved_host_id,
        project_root=state_dir,
        ccbd_client_factory=default_project.client,
        mobile_dir=state_dir,
        project_registry=registry,
        mode='loopback_server_registry',
    )
    projects = service.projects_payload().get('projects')
    project_summaries = list(projects) if isinstance(projects, list) else []
    server = build_mobile_gateway_server(listen, service)
    try:
        host, port = server.server_address[:2]
        local_gateway_url = f'http://{host}:{port}'
        gateway_url = _public_gateway_url(command.public_url, fallback=local_gateway_url)
        route_provider = str(command.route_provider or 'lan')
        pairing = service.create_pairing_payload(gateway_url=gateway_url, route_provider=route_provider)
        relay_outbound = _relay_outbound_summary(resolved_host_id) if route_provider == 'relay' else None
    except Exception:
        server.server_close()
        raise
    summary = {
        'mobile_status': 'serving',
        'listen': f'{host}:{port}',
        'gateway_url': gateway_url,
        'local_gateway_url': local_gateway_url,
        'route_provider': route_provider,
        'host_id': resolved_host_id,
        'project_id': resolved_host_id,
        'project_root': '',
        'mobile_state_dir': str(state_dir),
        'mode': 'loopback_server_registry',
        'project_count': len(project_summaries),
        'projects': project_summaries,
        'pairing': pairing,
        'endpoints': [
            '/v1/health',
            '/v1/projects',
            '/v1/projects/{project_id}/view',
            '/v1/pairing/claim',
            '/v1/devices/me',
            '/v1/devices/{device_id}/revoke',
            '/v1/projects/{project_id}/lifecycle',
            '/v1/projects/{project_id}/focus-agent',
            '/v1/projects/{project_id}/focus-window',
            '/v1/projects/{project_id}/terminals',
            '/v1/terminals/{terminal_id}',
        ],
    }
    if relay_outbound is not None:
        summary['relay_outbound'] = relay_outbound
    return MobileGatewayServeHandle(
        summary=summary,
        server=server,
    )


def mobile_devices_status(context, command) -> dict[str, object]:
    store = MobileGatewayPairingStore(context.paths.ccbd_mobile_dir)
    return {
        'mobile_status': 'devices',
        'project_id': context.project.project_id,
        'project_root': str(context.project.project_root),
        'mobile_state_dir': str(context.paths.ccbd_mobile_dir),
        'devices': store.list_devices(),
    }


def revoke_mobile_device(context, command) -> dict[str, object]:
    device_id = str(getattr(command, 'device_id', '') or '').strip()
    store = MobileGatewayPairingStore(context.paths.ccbd_mobile_dir)
    result = store.revoke_device_locally(device_id=device_id)
    return {
        'mobile_status': 'revoked',
        'project_id': context.project.project_id,
        'project_root': str(context.project.project_root),
        'mobile_state_dir': str(context.paths.ccbd_mobile_dir),
        **result,
    }


def _public_gateway_url(value: str | None, *, fallback: str) -> str:
    text = str(value or '').strip()
    if not text:
        return fallback
    parsed = urlparse(text)
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc or not parsed.hostname:
        raise ValueError('--public-url must be an absolute http(s) origin URL')
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError('--public-url port must be valid') from exc
    if parsed.username or parsed.password:
        raise ValueError('--public-url must not include credentials')
    if parsed.path not in {'', '/'}:
        raise ValueError('--public-url must not include a path')
    if parsed.params or parsed.query or parsed.fragment:
        raise ValueError('--public-url must not include params, query, or fragment')
    return urlunsplit((parsed.scheme, parsed.netloc, '', '', ''))


def _relay_outbound_summary(project_id: str) -> dict[str, object]:
    host_id = str(project_id or '').strip()
    relay = LocalRelayServerHarness()
    client = MobileGatewayRelayOutboundClient(
        relay=relay,
        host_id=host_id,
        server_fingerprint=f'local-relay-fp:{host_id}',
        host_pubkey_b64=_relay_demo_pubkey(host_id),
        diagnostics={'relay_mode': 'local_harness', 'relay_host_id': host_id},
    )
    registration = client.connect()
    return {
        'status': registration['status'],
        'mode': 'local_harness',
        'host_id': registration['host_id'],
        'server_fingerprint': registration['server_fingerprint'],
        'capabilities': registration['capabilities'],
        'diagnostics': client.diagnostics(),
    }


def _relay_demo_pubkey(host_id: str) -> str:
    return base64.urlsafe_b64encode(f'ccb-mobile-relay:{host_id}:public-key'.encode('utf-8')).decode('ascii')


def _server_host_id() -> str:
    seed = f'{socket.gethostname()}:{mobile_host_state_dir()}'
    digest = hashlib.sha256(seed.encode('utf-8')).hexdigest()[:16]
    return f'host-{digest}'


__all__ = [
    'MobileGatewayServeHandle',
    'mobile_devices_status',
    'prepare_mobile_gateway',
    'prepare_server_mobile_gateway',
    'revoke_mobile_device',
]
