import 'dart:async';
import 'dart:io' show Platform;

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import 'gateway_pairing.dart';
import 'gateway_pairing_qr_scanner.dart';

class GatewayPairingScannerScreen extends StatefulWidget {
  const GatewayPairingScannerScreen({super.key, this.qrScanner});

  final GatewayPairingQrScanner? qrScanner;

  @override
  State<GatewayPairingScannerScreen> createState() =>
      _GatewayPairingScannerScreenState();
}

@visibleForTesting
MobileScannerController gatewayPairingScannerController() {
  return MobileScannerController(formats: const [BarcodeFormat.qrCode]);
}

class _GatewayPairingScannerScreenState
    extends State<GatewayPairingScannerScreen>
    with WidgetsBindingObserver {
  final MobileScannerController _controller = gatewayPairingScannerController();
  late final GatewayPairingQrScanner _qrScanner =
      widget.qrScanner ?? const MethodChannelGatewayPairingQrScanner();
  bool _handled = false;
  String? _error;
  bool _scanningWithNativeCamera = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    if (_usesNativeScanner) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) {
          unawaited(_scanWithNativeCamera());
        }
      });
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _controller.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (_usesNativeScanner) {
      return;
    }
    switch (gatewayPairingScannerLifecycleAction(
      state: state,
      isStarting: _controller.value.isStarting,
      hasCameraPermission: _controller.value.hasCameraPermission,
    )) {
      case GatewayPairingScannerLifecycleAction.start:
        unawaited(_controller.start());
      case GatewayPairingScannerLifecycleAction.stop:
        unawaited(_controller.stop());
      case GatewayPairingScannerLifecycleAction.ignore:
        return;
    }
  }

  bool get _usesNativeScanner =>
      _qrScanner.usesNativeCamera &&
      (Platform.isAndroid || widget.qrScanner != null);

  void _retryScanner() {
    if (_usesNativeScanner) {
      unawaited(_scanWithNativeCamera());
      return;
    }
    setState(() {
      _error = null;
    });
    unawaited(_controller.start());
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

  void _handleRawQrText(String raw) {
    if (_handled) {
      return;
    }
    try {
      final pairing = GatewayPairingPayload.fromQrText(raw.trim());
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

  Future<void> _scanWithNativeCamera() async {
    setState(() {
      _error = null;
      _scanningWithNativeCamera = true;
    });
    try {
      final raw = await _qrScanner.scanCamera();
      if (!mounted || _handled) {
        return;
      }
      if (raw == null || raw.trim().isEmpty) {
        setState(() {
          _error =
              'Scan canceled. Try camera, choose an image, or use manual setup.';
        });
        return;
      }
      _handleRawQrText(raw);
    } on PlatformException catch (error) {
      if (!mounted || _handled) {
        return;
      }
      setState(() {
        _error = gatewayPairingNativeScannerErrorMessage(error);
      });
    } catch (error) {
      if (!mounted || _handled) {
        return;
      }
      setState(() {
        _error = gatewayPairingNativeScannerErrorMessage(error);
      });
    } finally {
      if (mounted) {
        setState(() {
          _scanningWithNativeCamera = false;
        });
      }
    }
  }

  Future<void> _scanFromImage() async {
    try {
      final result = await FilePicker.pickFiles(
        allowMultiple: false,
        type: FileType.image,
      );
      final file =
          result == null || result.files.isEmpty ? null : result.files.single;
      final path = file?.path;
      if (path == null || path.isEmpty) {
        return;
      }
      setState(() {
        _error = null;
      });
      final raw = await _qrScanner.scanImage(path);
      if (!mounted || _handled) {
        return;
      }
      if (raw == null || raw.trim().isEmpty) {
        setState(() {
          _error = 'No pairing QR code was found in that image.';
        });
        return;
      }
      _handleRawQrText(raw);
    } on PlatformException catch (error) {
      if (!mounted || _handled) {
        return;
      }
      setState(() {
        _error = gatewayPairingNativeScannerErrorMessage(error);
      });
    } catch (error) {
      if (!mounted || _handled) {
        return;
      }
      setState(() {
        _error = gatewayPairingNativeScannerErrorMessage(error);
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_usesNativeScanner) {
      return _buildNativeScanner(context);
    }
    return _buildEmbeddedScanner(context);
  }

  Widget _buildEmbeddedScanner(BuildContext context) {
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
            placeholderBuilder:
                (context) => const ColoredBox(color: Colors.black),
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

  Widget _buildNativeScanner(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Scan Pairing QR')),
      body: SafeArea(
        child: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Icon(
                    Icons.qr_code_scanner,
                    color: colorScheme.primary,
                    size: 56,
                  ),
                  const SizedBox(height: 16),
                  Text(
                    'Scan the CCB mobile pairing QR code',
                    textAlign: TextAlign.center,
                    style: textTheme.titleMedium,
                  ),
                  const SizedBox(height: 12),
                  Text(
                    _error ??
                        'Camera scanning uses the Android system scanner first, then an embedded scanner if needed.',
                    key: const ValueKey('gateway-pairing-native-scan-status'),
                    textAlign: TextAlign.center,
                    style: textTheme.bodyMedium?.copyWith(
                      color:
                          _error == null
                              ? colorScheme.onSurfaceVariant
                              : colorScheme.error,
                    ),
                  ),
                  const SizedBox(height: 24),
                  FilledButton.icon(
                    key: const ValueKey('gateway-pairing-native-scan-button'),
                    onPressed:
                        _scanningWithNativeCamera
                            ? null
                            : _scanWithNativeCamera,
                    icon:
                        _scanningWithNativeCamera
                            ? SizedBox.square(
                              dimension: 18,
                              child: CircularProgressIndicator(
                                strokeWidth: 2,
                                color: colorScheme.onPrimary,
                              ),
                            )
                            : const Icon(Icons.qr_code_scanner),
                    label: Text(
                      _scanningWithNativeCamera ? 'Opening scanner' : 'Scan QR',
                    ),
                  ),
                  const SizedBox(height: 12),
                  OutlinedButton.icon(
                    key: const ValueKey('gateway-pairing-image-scan-button'),
                    onPressed: _scanFromImage,
                    icon: const Icon(Icons.image_search),
                    label: const Text('Scan QR from image'),
                  ),
                  const SizedBox(height: 12),
                  TextButton.icon(
                    key: const ValueKey('gateway-pairing-scan-manual-button'),
                    onPressed: () => Navigator.of(context).pop(),
                    icon: const Icon(Icons.keyboard),
                    label: const Text('Use manual setup'),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildScannerError(
    BuildContext context,
    MobileScannerException error,
  ) {
    return GatewayPairingCameraErrorPanel(
      message: gatewayPairingCameraErrorMessage(error),
      onRetry: _retryScanner,
      onUseManualSetup: () => Navigator.of(context).pop(),
    );
  }
}

@visibleForTesting
String gatewayPairingNativeScannerErrorMessage(Object error) {
  if (error is PlatformException) {
    switch (error.code) {
      case 'scanner_busy':
        return 'Scanner is already open.';
      case 'scanner_unavailable':
        return 'Android scanner could not be opened. Try image scan or manual setup.';
      case 'image_no_qr':
        return 'No pairing QR code was found in that image.';
      case 'image_decode_failed':
        return 'That image could not be decoded.';
    }
  }
  return 'Scanner could not start. Try image scan or manual setup.';
}

@visibleForTesting
enum GatewayPairingScannerLifecycleAction { start, stop, ignore }

@visibleForTesting
GatewayPairingScannerLifecycleAction gatewayPairingScannerLifecycleAction({
  required AppLifecycleState state,
  required bool isStarting,
  required bool hasCameraPermission,
}) {
  if (isStarting || !hasCameraPermission) {
    return GatewayPairingScannerLifecycleAction.ignore;
  }
  return switch (state) {
    AppLifecycleState.resumed => GatewayPairingScannerLifecycleAction.start,
    AppLifecycleState.inactive => GatewayPairingScannerLifecycleAction.stop,
    AppLifecycleState.detached ||
    AppLifecycleState.hidden ||
    AppLifecycleState.paused => GatewayPairingScannerLifecycleAction.ignore,
  };
}

@visibleForTesting
String gatewayPairingCameraErrorMessage(Object error) {
  if (error is MobileScannerException) {
    return switch (error.errorCode) {
      MobileScannerErrorCode.permissionDenied =>
        'Camera permission denied. Enable camera access for CCB Mobile or use manual setup.',
      MobileScannerErrorCode.unsupported =>
        'This device does not expose a usable camera. Use manual setup instead.',
      MobileScannerErrorCode.controllerInitializing =>
        'Camera is still starting. Try again, or use manual setup.',
      _ => 'Camera could not be opened. Try again or use manual setup.',
    };
  }
  final text = error.toString().toLowerCase();
  if (text.contains('camera') ||
      text.contains('null object reference') ||
      text.contains('permission')) {
    return 'Camera could not be opened. Try again or use manual setup.';
  }
  return 'Scanner could not start. Try again or use manual setup.';
}

class GatewayPairingCameraErrorPanel extends StatelessWidget {
  const GatewayPairingCameraErrorPanel({
    required this.message,
    this.onRetry,
    required this.onUseManualSetup,
    super.key,
  });

  final String message;
  final VoidCallback? onRetry;
  final VoidCallback onUseManualSetup;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final mediaQuery = MediaQuery.of(context);
    return ColoredBox(
      color: Colors.black,
      child: Center(
        child: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: BoxConstraints(
                maxWidth: 360,
                maxHeight: mediaQuery.size.height - 48,
              ),
              child: DecoratedBox(
                decoration: BoxDecoration(
                  color: colorScheme.surface,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: SingleChildScrollView(
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
                          key: const ValueKey(
                            'gateway-pairing-scan-camera-error',
                          ),
                          style: Theme.of(context).textTheme.titleMedium,
                          textAlign: TextAlign.center,
                        ),
                        const SizedBox(height: 8),
                        Text(
                          message,
                          key: const ValueKey(
                            'gateway-pairing-scan-camera-message',
                          ),
                          textAlign: TextAlign.center,
                          style: Theme.of(context).textTheme.bodyMedium
                              ?.copyWith(color: colorScheme.onSurfaceVariant),
                        ),
                        const SizedBox(height: 16),
                        Wrap(
                          spacing: 12,
                          runSpacing: 8,
                          alignment: WrapAlignment.center,
                          children: [
                            if (onRetry != null)
                              OutlinedButton.icon(
                                key: const ValueKey(
                                  'gateway-pairing-scan-retry-button',
                                ),
                                onPressed: onRetry,
                                icon: const Icon(Icons.refresh),
                                label: const Text('Try camera again'),
                              ),
                            FilledButton.icon(
                              key: const ValueKey(
                                'gateway-pairing-scan-manual-button',
                              ),
                              onPressed: onUseManualSetup,
                              icon: const Icon(Icons.keyboard_outlined),
                              label: const Text('Use manual setup'),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
