import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:ccb_mobile/ccb_mobile.dart';

void main() {
  testWidgets('camera error panel offers manual setup fallback', (
    tester,
  ) async {
    var manualSelected = false;

    await tester.pumpWidget(
      MaterialApp(
        home: GatewayPairingCameraErrorPanel(
          message: 'Camera permission denied.',
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
    expect(find.text('Camera permission denied.'), findsOneWidget);

    await tester.tap(
      find.byKey(const ValueKey('gateway-pairing-scan-manual-button')),
    );

    expect(manualSelected, isTrue);
  });
}
