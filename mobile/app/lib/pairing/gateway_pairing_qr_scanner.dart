import 'package:flutter/services.dart';

abstract interface class GatewayPairingQrScanner {
  bool get usesNativeCamera;

  Future<String?> scanCamera();

  Future<String?> scanImage(String path);
}

class MethodChannelGatewayPairingQrScanner implements GatewayPairingQrScanner {
  const MethodChannelGatewayPairingQrScanner({
    MethodChannel channel = const MethodChannel(
      'io.ccb.mobile/pairing_scanner',
    ),
  }) : _channel = channel;

  final MethodChannel _channel;

  @override
  bool get usesNativeCamera => true;

  @override
  Future<String?> scanCamera() {
    return _channel.invokeMethod<String>('scanPairingQr');
  }

  @override
  Future<String?> scanImage(String path) {
    return _channel.invokeMethod<String>('scanPairingQrImage', {'path': path});
  }
}
