import '../../pairing/gateway_pairing.dart';
import '../../transport/route_provider.dart';

const projectHomePairingDefaultDeviceName = 'Phone';
const projectHomeManualPairingScopes = {
  'view',
  'content',
  'focus',
  'message_submit',
  'file_upload',
  'file_download',
  'terminal_input',
  'lifecycle',
  'notify',
};

class ProjectHomePairingRequest {
  const ProjectHomePairingRequest({
    required this.pairing,
    required this.deviceName,
  });

  final GatewayPairingPayload pairing;
  final String deviceName;
}

class ProjectHomePairingRequestException implements Exception {
  const ProjectHomePairingRequestException(this.message);

  final String message;

  @override
  String toString() {
    return message;
  }
}

ProjectHomePairingRequest buildProjectHomePairingRequest({
  required String gatewayUrlText,
  required String pairingCodeText,
  required String deviceNameText,
  required RouteProviderKind routeKind,
  GatewayPairingPayload? pairingOverride,
}) {
  final deviceName = _deviceNameOrDefault(deviceNameText);
  if (pairingOverride != null) {
    return ProjectHomePairingRequest(
      pairing: pairingOverride,
      deviceName: deviceName,
    );
  }

  final gatewayUrl = _manualGatewayUrl(gatewayUrlText);
  final pairingCode = pairingCodeText.trim();
  if (pairingCode.isEmpty) {
    throw const ProjectHomePairingRequestException('Pairing code is required');
  }

  return ProjectHomePairingRequest(
    pairing: GatewayPairingPayload(
      pairingCode: pairingCode,
      claimEndpoint: gatewayUrl.resolve('/v1/pairing/claim'),
      routeProvider: routeKind,
      gatewayUrl: gatewayUrl,
      scopes: projectHomeManualPairingScopes,
    ),
    deviceName: deviceName,
  );
}

Uri _manualGatewayUrl(String text) {
  final gatewayUrl = Uri.tryParse(text.trim());
  if (gatewayUrl == null || !gatewayUrl.hasScheme || !gatewayUrl.hasAuthority) {
    throw const ProjectHomePairingRequestException('Gateway URL is required');
  }
  return gatewayUrl;
}

String _deviceNameOrDefault(String text) {
  final deviceName = text.trim();
  return deviceName.isEmpty ? projectHomePairingDefaultDeviceName : deviceName;
}
