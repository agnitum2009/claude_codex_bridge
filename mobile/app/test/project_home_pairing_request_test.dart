import 'package:ccb_mobile/features/project_home/project_home_pairing_request.dart';
import 'package:ccb_mobile/pairing/gateway_pairing.dart';
import 'package:ccb_mobile/transport/route_provider.dart';
import 'package:test/test.dart';

void main() {
  group('project home pairing request', () {
    test('rejects invalid manual gateway URL', () {
      for (final gatewayUrlText in ['', '127.0.0.1:8787', 'https:/']) {
        expect(
          () => buildProjectHomePairingRequest(
            gatewayUrlText: gatewayUrlText,
            pairingCodeText: 'pair-code',
            deviceNameText: 'Pixel Fold',
            routeKind: RouteProviderKind.lan,
          ),
          throwsA(
            isA<ProjectHomePairingRequestException>().having(
              (error) => error.message,
              'message',
              'Gateway URL is required',
            ),
          ),
          reason: gatewayUrlText,
        );
      }
    });

    test('rejects missing manual pairing code', () {
      expect(
        () => buildProjectHomePairingRequest(
          gatewayUrlText: 'http://127.0.0.1:8787',
          pairingCodeText: '   ',
          deviceNameText: 'Pixel Fold',
          routeKind: RouteProviderKind.lan,
        ),
        throwsA(
          isA<ProjectHomePairingRequestException>().having(
            (error) => error.message,
            'message',
            'Pairing code is required',
          ),
        ),
      );
    });

    test('defaults blank device name to Phone', () {
      final request = buildProjectHomePairingRequest(
        gatewayUrlText: 'http://127.0.0.1:8787',
        pairingCodeText: 'pair-code',
        deviceNameText: '   ',
        routeKind: RouteProviderKind.lan,
      );

      expect(request.deviceName, 'Phone');
    });

    test('builds manual scopes and claim endpoint exactly', () {
      final request = buildProjectHomePairingRequest(
        gatewayUrlText: 'http://127.0.0.1:8787',
        pairingCodeText: ' pair-code ',
        deviceNameText: ' Pixel Fold ',
        routeKind: RouteProviderKind.relay,
      );

      expect(request.deviceName, 'Pixel Fold');
      expect(request.pairing.pairingCode, 'pair-code');
      expect(
        request.pairing.claimEndpoint,
        Uri.parse('http://127.0.0.1:8787/v1/pairing/claim'),
      );
      expect(request.pairing.gatewayUrl, Uri.parse('http://127.0.0.1:8787'));
      expect(request.pairing.routeProvider, RouteProviderKind.relay);
      expect(request.pairing.scopes, {
        'view',
        'content',
        'focus',
        'message_submit',
        'file_upload',
        'file_download',
        'terminal_input',
        'lifecycle',
        'notify',
      });
    });

    test('passes QR pairing override through without rebuilding fields', () {
      final expiresAt = DateTime.utc(2026, 6, 18, 0, 10);
      final override = GatewayPairingPayload(
        pairingCode: 'qr-code',
        claimEndpoint: Uri.parse('https://mobile.example.com/pair/claim'),
        routeProvider: RouteProviderKind.cloudflareTunnel,
        gatewayUrl: Uri.parse('https://mobile.example.com/base'),
        projectId: 'proj-qr',
        expiresAt: expiresAt,
        scopes: const {'view', 'focus', 'terminal_input'},
      );

      final request = buildProjectHomePairingRequest(
        gatewayUrlText: '',
        pairingCodeText: '',
        deviceNameText: '',
        routeKind: RouteProviderKind.lan,
        pairingOverride: override,
      );

      expect(request.pairing, same(override));
      expect(request.deviceName, 'Phone');
      expect(request.pairing.projectId, 'proj-qr');
      expect(request.pairing.expiresAt, expiresAt);
      expect(request.pairing.scopes, {'view', 'focus', 'terminal_input'});
      expect(
        request.pairing.gatewayUrl,
        Uri.parse('https://mobile.example.com/base'),
      );
      expect(
        request.pairing.claimEndpoint,
        Uri.parse('https://mobile.example.com/pair/claim'),
      );
      expect(request.pairing.routeProvider, RouteProviderKind.cloudflareTunnel);
    });
  });
}
