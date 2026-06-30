import 'package:flutter/material.dart';

import '../../app/app_update.dart';
import '../../l10n/ccb_mobile_localizations.dart';
import '../../platform/external_url_opener.dart';

typedef ProjectHomeUpdateUrlLauncher = Future<bool> Function(String url);

class ProjectHomeUpdatePanel extends StatelessWidget {
  const ProjectHomeUpdatePanel({
    this.updateInfo = const CcbMobileUpdateInfo(),
    this.openUpdateUrl = openExternalUrl,
    super.key,
  });

  final CcbMobileUpdateInfo updateInfo;
  final ProjectHomeUpdateUrlLauncher openUpdateUrl;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final strings = CcbMobileLocalizations.of(context);
    final colorScheme = theme.colorScheme;
    return DecoratedBox(
      key: const ValueKey('project-home-update-panel'),
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainerLow,
        border: Border.all(color: colorScheme.outlineVariant),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Icon(Icons.system_update_alt, color: colorScheme.primary),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    strings.mobileUpdates,
                    style: theme.textTheme.titleMedium,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 6),
            Text(
              strings.currentVersion(updateInfo.version),
              key: const ValueKey('project-home-update-version'),
              style: theme.textTheme.bodyMedium,
            ),
            const SizedBox(height: 6),
            Text(
              strings.mobileUpdatesDescription,
              style: theme.textTheme.bodyMedium?.copyWith(
                color: colorScheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              strings.mobileUpdateInstallNote,
              style: theme.textTheme.bodySmall?.copyWith(
                color: colorScheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: 12),
            Align(
              alignment: Alignment.centerLeft,
              child: OutlinedButton.icon(
                key: const ValueKey('project-home-update-open-apk-button'),
                onPressed: () {
                  _openDownload(context);
                },
                icon: const Icon(Icons.open_in_browser),
                label: Text(strings.openApkDownload),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _openDownload(BuildContext context) async {
    final strings = CcbMobileLocalizations.of(context);
    final opened = await openUpdateUrl(updateInfo.apkDownloadUrl);
    if (!context.mounted || opened) {
      return;
    }
    ScaffoldMessenger.of(context)
      ..clearSnackBars()
      ..showSnackBar(SnackBar(content: Text(strings.couldNotOpenUpdateUrl)));
  }
}
