from __future__ import annotations

from dataclasses import dataclass

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
    gateway_url = f'http://{host}:{port}'
    pairing = service.create_pairing_payload(gateway_url=gateway_url)
    return MobileGatewayServeHandle(
        summary={
            'mobile_status': 'serving',
            'listen': f'{host}:{port}',
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
            ],
        },
        server=server,
    )


__all__ = ['MobileGatewayServeHandle', 'prepare_mobile_gateway']
