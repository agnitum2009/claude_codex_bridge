import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:ccb_mobile/ccb_mobile.dart';

void main() {
  testWidgets('pasted QR payload returns parsed pairing', (tester) async {
    GatewayPairingPayload? result;

    await tester.pumpWidget(
      MaterialApp(
        home: _ScannerLauncher(
          onResult: (pairing) => result = pairing,
          scannerPreviewBuilder:
              (context, onQrText) =>
                  const ColoredBox(color: Colors.black, child: SizedBox()),
        ),
      ),
    );

    await tester.tap(find.text('Open scanner'));
    await tester.pumpAndSettle();

    await tester.enterText(
      find.byKey(const ValueKey('gateway-pairing-qr-text-field')),
      _qrText(),
    );
    await tester.tap(
      find.byKey(const ValueKey('gateway-pairing-qr-submit-button')),
    );
    await tester.pumpAndSettle();

    expect(result?.pairingCode, 'qr-code');
    expect(result?.routeProvider, RouteProviderKind.tailnet);
    expect(result?.gatewayUrl, Uri.parse('https://desktop.tailnet.ts.net'));
  });

  testWidgets(
    'invalid pasted QR payload keeps scanner open with status error',
    (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: _ScannerLauncher(
            scannerPreviewBuilder:
                (context, onQrText) =>
                    const ColoredBox(color: Colors.black, child: SizedBox()),
          ),
        ),
      );

      await tester.tap(find.text('Open scanner'));
      await tester.pumpAndSettle();

      await tester.enterText(
        find.byKey(const ValueKey('gateway-pairing-qr-text-field')),
        '"not an object"',
      );
      await tester.tap(
        find.byKey(const ValueKey('gateway-pairing-qr-submit-button')),
      );
      await tester.pumpAndSettle();

      expect(
        find.text('pairing QR payload must be a JSON object'),
        findsOneWidget,
      );
      expect(
        find.byKey(const ValueKey('gateway-pairing-qr-text-field')),
        findsOneWidget,
      );
    },
  );

  testWidgets('scanner preview callback still returns parsed pairing', (
    tester,
  ) async {
    GatewayPairingPayload? result;

    await tester.pumpWidget(
      MaterialApp(
        home: _ScannerLauncher(
          onResult: (pairing) => result = pairing,
          scannerPreviewBuilder:
              (context, onQrText) => TextButton(
                key: const ValueKey('fake-camera-detect-button'),
                onPressed: () => onQrText(_qrText()),
                child: const Text('Detect QR'),
              ),
        ),
      ),
    );

    await tester.tap(find.text('Open scanner'));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const ValueKey('fake-camera-detect-button')));
    await tester.pumpAndSettle();

    expect(result?.pairingCode, 'qr-code');
  });
}

class _ScannerLauncher extends StatelessWidget {
  const _ScannerLauncher({this.onResult, required this.scannerPreviewBuilder});

  final ValueChanged<GatewayPairingPayload?>? onResult;
  final GatewayPairingScannerPreviewBuilder scannerPreviewBuilder;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: TextButton(
          onPressed: () async {
            final result = await Navigator.of(
              context,
            ).push<GatewayPairingPayload>(
              MaterialPageRoute(
                builder:
                    (context) => GatewayPairingScannerScreen(
                      scannerPreviewBuilder: scannerPreviewBuilder,
                    ),
              ),
            );
            onResult?.call(result);
          },
          child: const Text('Open scanner'),
        ),
      ),
    );
  }
}

String _qrText() {
  return jsonEncode({
    'pairing_code': 'qr-code',
    'claim_endpoint': 'https://desktop.tailnet.ts.net/v1/pairing/claim',
    'route_provider': 'tailnet',
    'gateway_url': 'https://desktop.tailnet.ts.net',
    'scopes': ['view', 'focus', 'terminal_input'],
  });
}
