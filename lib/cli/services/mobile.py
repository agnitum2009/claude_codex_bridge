from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from ccbd.socket_client import CcbdClient
from mobile_gateway import MobileGatewayService, build_mobile_gateway_server, parse_listen_address


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
    return MobileGatewayServeHandle(
        summary={
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
                '/v1/projects/{project_id}/focus-agent',
                '/v1/projects/{project_id}/focus-window',
                '/v1/projects/{project_id}/terminals',
                '/v1/terminals/{terminal_id}',
            ],
        },
        server=server,
    )


def _public_gateway_url(value: str | None, *, fallback: str) -> str:
    text = str(value or '').strip().rstrip('/')
    if not text:
        return fallback
    parsed = urlparse(text)
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        raise ValueError('--public-url must be an absolute http(s) URL')
    return text


__all__ = ['MobileGatewayServeHandle', 'prepare_mobile_gateway']
