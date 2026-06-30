import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import 'gateway_pairing.dart';

class GatewayPairingScannerScreen extends StatefulWidget {
  const GatewayPairingScannerScreen({super.key});

  @override
  State<GatewayPairingScannerScreen> createState() =>
      _GatewayPairingScannerScreenState();
}

class _GatewayPairingScannerScreenState
    extends State<GatewayPairingScannerScreen> {
  final MobileScannerController _controller = MobileScannerController(
    formats: const [BarcodeFormat.qrCode],
  );
  bool _handled = false;
  String? _error;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _handleDetect(BarcodeCapture capture) {
    if (_handled) {
      return;
    }
    final barcodes = capture.barcodes;
    if (barcodes.isEmpty) {
      return;
    }
    final raw = barcodes.first.rawValue?.trim();
    if (raw == null || raw.isEmpty) {
      return;
    }
    try {
      final pairing = GatewayPairingPayload.fromQrText(raw);
      _handled = true;
      Navigator.of(context).pop(pairing);
    } on FormatException catch (error) {
      setState(() {
        _error = error.message;
      });
    } catch (error) {
      setState(() {
        _error = error.toString();
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Scan Pairing QR')),
      body: Stack(
        fit: StackFit.expand,
        children: [
          MobileScanner(
            controller: _controller,
            onDetect: _handleDetect,
            errorBuilder: _buildScannerError,
          ),
          Align(
            alignment: Alignment.topCenter,
            child: SafeArea(
              child: Container(
                margin: const EdgeInsets.all(16),
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: colorScheme.surface.withValues(alpha: 0.92),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(
                  _error ?? 'Scan the CCB mobile pairing QR code',
                  key: const ValueKey('gateway-pairing-scan-status'),
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
              ),
            ),
          ),
          Center(
            child: IgnorePointer(
              child: Container(
                width: 260,
                height: 260,
                decoration: BoxDecoration(
                  border: Border.all(color: colorScheme.primary, width: 3),
                  borderRadius: BorderRadius.circular(8),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildScannerError(
    BuildContext context,
    MobileScannerException error,
  ) {
    final details = error.errorDetails?.message;
    final message =
        details == null || details.trim().isEmpty
            ? error.errorCode.message
            : details.trim();
    return GatewayPairingCameraErrorPanel(
      message: message,
      onUseManualSetup: () => Navigator.of(context).pop(),
    );
  }
}

class GatewayPairingCameraErrorPanel extends StatelessWidget {
  const GatewayPairingCameraErrorPanel({
    required this.message,
    required this.onUseManualSetup,
    super.key,
  });

  final String message;
  final VoidCallback onUseManualSetup;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return ColoredBox(
      color: Colors.black,
      child: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 360),
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: colorScheme.surface,
                borderRadius: BorderRadius.circular(12),
              ),
              child: Padding(
                padding: const EdgeInsets.all(20),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      Icons.no_photography_outlined,
                      color: colorScheme.error,
                      size: 44,
                    ),
                    const SizedBox(height: 12),
                    Text(
                      'Camera unavailable',
                      key: const ValueKey('gateway-pairing-scan-camera-error'),
                      style: Theme.of(context).textTheme.titleMedium,
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 8),
                    Text(
                      message,
                      textAlign: TextAlign.center,
                      style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                        color: colorScheme.onSurfaceVariant,
                      ),
                    ),
                    const SizedBox(height: 16),
                    FilledButton.icon(
                      key: const ValueKey('gateway-pairing-scan-manual-button'),
                      onPressed: onUseManualSetup,
                      icon: const Icon(Icons.keyboard_outlined),
                      label: const Text('Use manual setup'),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
