import 'package:flutter/material.dart';

import '../../l10n/ccb_mobile_localizations.dart';
import '../../transport/route_provider.dart';

class GatewayPairingPanel extends StatelessWidget {
  const GatewayPairingPanel({
    required this.gatewayUrlController,
    required this.pairingCodeController,
    required this.deviceNameController,
    required this.routeKind,
    required this.claiming,
    required this.onRouteKindChanged,
    required this.onScan,
    required this.onClaim,
    super.key,
  });

  final TextEditingController gatewayUrlController;
  final TextEditingController pairingCodeController;
  final TextEditingController deviceNameController;
  final RouteProviderKind routeKind;
  final bool claiming;
  final ValueChanged<RouteProviderKind> onRouteKindChanged;
  final VoidCallback onScan;
  final VoidCallback onClaim;

  @override
  Widget build(BuildContext context) {
    final strings = CcbMobileLocalizations.of(context);
    return ExpansionTile(
      key: const ValueKey('gateway-pairing-panel'),
      tilePadding: EdgeInsets.zero,
      childrenPadding: const EdgeInsets.only(top: 8, bottom: 8),
      leading: const Icon(Icons.qr_code_scanner),
      title: Text(strings.pairGateway),
      subtitle: Text(
        gatewayUrlController.text,
        key: const ValueKey('gateway-pairing-status'),
      ),
      children: [
        TextField(
          key: const ValueKey('gateway-url-field'),
          controller: gatewayUrlController,
          keyboardType: TextInputType.url,
          textInputAction: TextInputAction.next,
          decoration: InputDecoration(
            labelText: strings.gatewayUrl,
            prefixIcon: const Icon(Icons.link),
          ),
        ),
        const SizedBox(height: 8),
        TextField(
          key: const ValueKey('pairing-code-field'),
          controller: pairingCodeController,
          textInputAction: TextInputAction.next,
          decoration: InputDecoration(
            labelText: strings.pairingCode,
            prefixIcon: const Icon(Icons.pin),
          ),
        ),
        const SizedBox(height: 8),
        Row(
          children: [
            Expanded(
              child: TextField(
                key: const ValueKey('pairing-device-name-field'),
                controller: deviceNameController,
                textInputAction: TextInputAction.done,
                decoration: InputDecoration(
                  labelText: strings.deviceName,
                  prefixIcon: const Icon(Icons.phone_android),
                ),
              ),
            ),
            const SizedBox(width: 12),
            SizedBox(
              width: 154,
              child: DropdownButtonFormField<RouteProviderKind>(
                key: ValueKey('pairing-route-kind-field-${routeKind.wireName}'),
                initialValue: routeKind,
                items: [
                  for (final item in RouteProviderKind.values)
                    DropdownMenuItem(
                      value: item,
                      child: Text(_routeProviderLabel(item)),
                    ),
                ],
                isExpanded: true,
                onChanged: (value) {
                  if (value != null) {
                    onRouteKindChanged(value);
                  }
                },
                decoration: InputDecoration(labelText: strings.route),
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            OutlinedButton.icon(
              key: const ValueKey('gateway-pairing-scan-button'),
              onPressed: claiming ? null : onScan,
              icon: const Icon(Icons.qr_code_scanner),
              label: Text(strings.scanQr),
            ),
            const SizedBox(width: 12),
            FilledButton.icon(
              key: const ValueKey('gateway-pairing-claim-button'),
              onPressed: claiming ? null : onClaim,
              icon:
                  claiming
                      ? const SizedBox.square(
                        dimension: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                      : const Icon(Icons.add_link),
              label: Text(strings.claim),
            ),
          ],
        ),
      ],
    );
  }
}

String _routeProviderLabel(RouteProviderKind kind) {
  return switch (kind) {
    RouteProviderKind.lan => 'LAN',
    RouteProviderKind.tailnet => 'Tailnet',
    RouteProviderKind.cloudflareTunnel => 'Cloudflare',
    RouteProviderKind.relay => 'Relay',
  };
}
