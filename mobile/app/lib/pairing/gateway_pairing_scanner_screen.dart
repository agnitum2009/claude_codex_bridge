import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import 'gateway_pairing.dart';

typedef GatewayPairingScannerPreviewBuilder =
    Widget Function(BuildContext context, ValueChanged<String> onQrText);

class GatewayPairingScannerScreen extends StatefulWidget {
  const GatewayPairingScannerScreen({super.key, this.scannerPreviewBuilder});

  final GatewayPairingScannerPreviewBuilder? scannerPreviewBuilder;

  @override
  State<GatewayPairingScannerScreen> createState() =>
      _GatewayPairingScannerScreenState();
}

class _GatewayPairingScannerScreenState
    extends State<GatewayPairingScannerScreen> {
  final MobileScannerController _controller = MobileScannerController(
    formats: const [BarcodeFormat.qrCode],
  );
  final TextEditingController _qrTextController = TextEditingController();
  bool _handled = false;
  String? _error;

  @override
  void dispose() {
    _qrTextController.dispose();
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
    _handleQrText(raw);
  }

  void _handleQrText(String raw) {
    if (_handled) {
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

  void _submitPastedQrText() {
    final text = _qrTextController.text.trim();
    if (text.isEmpty) {
      setState(() {
        _error = 'Paste a CCB mobile pairing QR payload first';
      });
      return;
    }
    _handleQrText(text);
  }

  Widget _buildScannerPreview() {
    final scannerPreviewBuilder = widget.scannerPreviewBuilder;
    if (scannerPreviewBuilder != null) {
      return scannerPreviewBuilder(context, _handleQrText);
    }
    return MobileScanner(
      controller: _controller,
      onDetect: _handleDetect,
      errorBuilder: _buildCameraError,
    );
  }

  Widget _buildCameraError(BuildContext context, MobileScannerException error) {
    final textTheme = Theme.of(context).textTheme;
    return ColoredBox(
      color: Colors.black,
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 240),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.error_outline, color: Colors.white, size: 40),
              const SizedBox(height: 16),
              Text(
                'Camera scanner is unavailable on this device.',
                key: const ValueKey('gateway-pairing-camera-error'),
                textAlign: TextAlign.center,
                style: textTheme.bodyLarge?.copyWith(color: Colors.white),
              ),
              const SizedBox(height: 8),
              Text(
                'Paste the QR payload below or go back to manual pairing.',
                textAlign: TextAlign.center,
                style: textTheme.bodyMedium?.copyWith(color: Colors.white70),
              ),
            ],
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Scan Pairing QR')),
      body: Stack(
        fit: StackFit.expand,
        children: [
          _buildScannerPreview(),
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
          Align(
            alignment: Alignment.bottomCenter,
            child: SafeArea(
              minimum: const EdgeInsets.all(16),
              child: DecoratedBox(
                decoration: BoxDecoration(
                  color: colorScheme.surface.withValues(alpha: 0.94),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      TextField(
                        key: const ValueKey('gateway-pairing-qr-text-field'),
                        controller: _qrTextController,
                        minLines: 1,
                        maxLines: 3,
                        decoration: const InputDecoration(
                          labelText: 'Paste QR payload',
                          border: OutlineInputBorder(),
                        ),
                      ),
                      const SizedBox(height: 8),
                      Wrap(
                        spacing: 8,
                        runSpacing: 8,
                        alignment: WrapAlignment.end,
                        children: [
                          TextButton(
                            key: const ValueKey(
                              'gateway-pairing-manual-back-button',
                            ),
                            onPressed: () => Navigator.of(context).pop(),
                            child: const Text('Manual pairing'),
                          ),
                          FilledButton(
                            key: const ValueKey(
                              'gateway-pairing-qr-submit-button',
                            ),
                            onPressed: _submitPastedQrText,
                            child: const Text('Use QR payload'),
                          ),
                        ],
                      ),
                    ],
                  ),
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
}
