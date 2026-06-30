import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../../l10n/ccb_mobile_localizations.dart';
import '../../transport/route_provider.dart';
import 'gateway_pairing_panel.dart';

const projectHomeTailscaleDownloadUrl = 'https://tailscale.com/download';

class ProjectHomeOnboardingScaffold extends StatelessWidget {
  const ProjectHomeOnboardingScaffold({
    required this.gatewayUrlController,
    required this.pairingCodeController,
    required this.deviceNameController,
    required this.routeKindListenable,
    required this.claiming,
    required this.loadingProfiles,
    required this.onRouteKindChanged,
    required this.onScan,
    required this.onClaim,
    super.key,
  });

  final TextEditingController gatewayUrlController;
  final TextEditingController pairingCodeController;
  final TextEditingController deviceNameController;
  final ValueListenable<RouteProviderKind> routeKindListenable;
  final bool claiming;
  final bool loadingProfiles;
  final ValueChanged<RouteProviderKind> onRouteKindChanged;
  final VoidCallback onScan;
  final VoidCallback onClaim;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final strings = CcbMobileLocalizations.of(context);
    return Scaffold(
      body: SafeArea(
        child: ListView(
          key: const ValueKey('project-home-onboarding'),
          padding: const EdgeInsets.fromLTRB(20, 20, 20, 28),
          children: [
            Icon(
              Icons.mobile_friendly,
              size: 54,
              color: theme.colorScheme.primary,
            ),
            const SizedBox(height: 16),
            Text(
              strings.connectTitle,
              key: const ValueKey('project-home-onboarding-title'),
              style: theme.textTheme.headlineSmall,
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 8),
            Text(
              strings.connectDescription,
              style: theme.textTheme.bodyMedium?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 24),
            _OnboardingStep(
              icon: Icons.vpn_key_outlined,
              title: strings.installTailscaleTitle,
              body: strings.installTailscaleBody,
              code: projectHomeTailscaleDownloadUrl,
            ),
            _OnboardingStep(
              icon: Icons.terminal,
              title: strings.runComputerCommandTitle,
              body: strings.runComputerCommandBody,
              code: 'ccb update mobile',
            ),
            _OnboardingStep(
              icon: Icons.qr_code_scanner,
              title: strings.scanQrTitle,
              body: strings.scanQrBody,
            ),
            const SizedBox(height: 12),
            FilledButton.icon(
              key: const ValueKey('project-home-onboarding-scan-button'),
              onPressed: claiming || loadingProfiles ? null : onScan,
              icon:
                  claiming
                      ? const SizedBox.square(
                        dimension: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                      : const Icon(Icons.qr_code_scanner),
              label: Text(claiming ? strings.pairing : strings.scanComputerQr),
            ),
            const SizedBox(height: 16),
            ValueListenableBuilder<RouteProviderKind>(
              valueListenable: routeKindListenable,
              builder: (context, routeKind, _) {
                return GatewayPairingPanel(
                  gatewayUrlController: gatewayUrlController,
                  pairingCodeController: pairingCodeController,
                  deviceNameController: deviceNameController,
                  routeKind: routeKind,
                  claiming: claiming,
                  onRouteKindChanged: onRouteKindChanged,
                  onScan: onScan,
                  onClaim: onClaim,
                );
              },
            ),
          ],
        ),
      ),
    );
  }
}

class ProjectHomeOnboardingLoadingScaffold extends StatelessWidget {
  const ProjectHomeOnboardingLoadingScaffold({super.key});

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      body: SafeArea(
        child: Center(
          key: ValueKey('project-home-onboarding-loading'),
          child: CircularProgressIndicator(),
        ),
      ),
    );
  }
}

class _OnboardingStep extends StatelessWidget {
  const _OnboardingStep({
    required this.icon,
    required this.title,
    required this.body,
    this.code,
  });

  final IconData icon;
  final String title;
  final String body;
  final String? code;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final codeText = code;
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: theme.colorScheme.primary),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: theme.textTheme.titleMedium),
                const SizedBox(height: 2),
                Text(
                  body,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
                if (codeText != null) ...[
                  const SizedBox(height: 6),
                  SelectableText(
                    codeText,
                    style: theme.textTheme.bodyMedium?.copyWith(
                      fontFamily: 'monospace',
                    ),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}
