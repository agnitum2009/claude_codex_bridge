import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import 'package:ccb_mobile/ccb_mobile.dart';

void main() {
  test('scanner controller uses plugin auto start for camera lifecycle', () {
    final controller = gatewayPairingScannerController();
    addTearDown(controller.dispose);

    expect(controller.autoStart, isTrue);
    expect(controller.formats, [BarcodeFormat.qrCode]);
  });

  test('scanner lifecycle ignores permission and startup transitions', () {
    expect(
      gatewayPairingScannerLifecycleAction(
        state: AppLifecycleState.inactive,
        isStarting: true,
        hasCameraPermission: false,
      ),
      GatewayPairingScannerLifecycleAction.ignore,
    );
    expect(
      gatewayPairingScannerLifecycleAction(
        state: AppLifecycleState.inactive,
        isStarting: false,
        hasCameraPermission: false,
      ),
      GatewayPairingScannerLifecycleAction.ignore,
    );
    expect(
      gatewayPairingScannerLifecycleAction(
        state: AppLifecycleState.resumed,
        isStarting: false,
        hasCameraPermission: true,
      ),
      GatewayPairingScannerLifecycleAction.start,
    );
    expect(
      gatewayPairingScannerLifecycleAction(
        state: AppLifecycleState.inactive,
        isStarting: false,
        hasCameraPermission: true,
      ),
      GatewayPairingScannerLifecycleAction.stop,
    );
  });

  testWidgets('native scanner result closes with pairing payload', (
    tester,
  ) async {
    final scanner = _FakeQrScanner(cameraResult: _validPairingQrText());
    GatewayPairingPayload? seenPairing;

    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) {
            return ElevatedButton(
              onPressed: () async {
                seenPairing = await Navigator.of(context).push(
                  MaterialPageRoute<GatewayPairingPayload>(
                    builder:
                        (context) =>
                            GatewayPairingScannerScreen(qrScanner: scanner),
                  ),
                );
              },
              child: const Text('scan'),
            );
          },
        ),
      ),
    );

    await tester.tap(find.text('scan'));
    await tester.pump();
    await tester.pumpAndSettle();

    expect(scanner.cameraCalls, 1);
    expect(seenPairing?.pairingCode, 'qr-code');
    expect(seenPairing?.gatewayUrl.toString(), 'http://127.0.0.1:8787');
  });

  testWidgets('native scanner cancel exposes image and manual paths', (
    tester,
  ) async {
    final scanner = _FakeQrScanner();

    await tester.pumpWidget(
      MaterialApp(home: GatewayPairingScannerScreen(qrScanner: scanner)),
    );
    await tester.pump();
    await tester.pumpAndSettle();

    expect(scanner.cameraCalls, 1);
    expect(
      find.text(
        'Scan canceled. Try camera, choose an image, or use manual setup.',
      ),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('gateway-pairing-image-scan-button')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('gateway-pairing-scan-manual-button')),
      findsOneWidget,
    );
  });

  testWidgets('camera error panel offers manual setup fallback', (
    tester,
  ) async {
    var manualSelected = false;

    await tester.pumpWidget(
      MaterialApp(
        home: GatewayPairingCameraErrorPanel(
          message:
              'Camera permission denied. Enable camera access for CCB Mobile or use manual setup.',
          onUseManualSetup: () {
            manualSelected = true;
          },
        ),
      ),
    );

    expect(
      find.byKey(const ValueKey('gateway-pairing-scan-camera-error')),
      findsOneWidget,
    );
    expect(find.text('Camera unavailable'), findsOneWidget);
    expect(
      find.text(
        'Camera permission denied. Enable camera access for CCB Mobile or use manual setup.',
      ),
      findsOneWidget,
    );

    await tester.tap(
      find.byKey(const ValueKey('gateway-pairing-scan-manual-button')),
    );

    expect(manualSelected, isTrue);
  });

  testWidgets('camera error panel can retry and constrains long details', (
    tester,
  ) async {
    var retried = false;
    var manualSelected = false;

    await tester.pumpWidget(
      MaterialApp(
        home: GatewayPairingCameraErrorPanel(
          message: 'Camera could not be opened. Try again or use manual setup.',
          onRetry: () {
            retried = true;
          },
          onUseManualSetup: () {
            manualSelected = true;
          },
        ),
      ),
    );

    expect(tester.takeException(), isNull);
    expect(
      find.byKey(const ValueKey('gateway-pairing-scan-retry-button')),
      findsOneWidget,
    );

    await tester.tap(
      find.byKey(const ValueKey('gateway-pairing-scan-retry-button')),
    );
    expect(retried, isTrue);

    await tester.tap(
      find.byKey(const ValueKey('gateway-pairing-scan-manual-button')),
    );
    expect(manualSelected, isTrue);
  });

  test('camera error message hides native implementation details', () {
    final message = gatewayPairingCameraErrorMessage(
      Exception(
        "Attempt to invoke virtual method 'w4.c w4.b.a(s4.b)' on a null object reference",
      ),
    );

    expect(
      message,
      'Camera could not be opened. Try again or use manual setup.',
    );
    expect(message, isNot(contains('null object reference')));
    expect(message, isNot(contains('w4.')));
  });

  test('camera permission error has actionable message', () {
    final message = gatewayPairingCameraErrorMessage(
      const MobileScannerException(
        errorCode: MobileScannerErrorCode.permissionDenied,
      ),
    );

    expect(message, contains('Camera permission denied'));
    expect(message, contains('manual setup'));
  });

  test('native scanner error message is actionable', () {
    final message = gatewayPairingNativeScannerErrorMessage(
      PlatformException(
        code: 'scanner_unavailable',
        message: 'w4 null object reference',
      ),
    );

    expect(
      message,
      'Android scanner could not be opened. Try image scan or manual setup.',
    );
    expect(message, isNot(contains('w4')));
  });
}

class _FakeQrScanner implements GatewayPairingQrScanner {
  _FakeQrScanner({this.cameraResult});

  final String? cameraResult;
  var cameraCalls = 0;
  var imageCalls = 0;

  @override
  bool get usesNativeCamera => true;

  @override
  Future<String?> scanCamera() async {
    cameraCalls += 1;
    return cameraResult;
  }

  @override
  Future<String?> scanImage(String path) async {
    imageCalls += 1;
    return null;
  }
}

String _validPairingQrText() {
  return jsonEncode({
    'pairing_code': 'qr-code',
    'claim_endpoint': 'http://127.0.0.1:8787/v1/pairing/claim',
    'route_provider': 'lan',
    'gateway_url': 'http://127.0.0.1:8787',
    'scopes': ['view', 'message_submit'],
  });
}
