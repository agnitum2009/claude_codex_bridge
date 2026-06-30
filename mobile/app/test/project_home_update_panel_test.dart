import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:ccb_mobile/app/app_update.dart';
import 'package:ccb_mobile/features/project_home/project_home_update_panel.dart';

void main() {
  test('default update info exposes current version and release URL', () {
    const info = CcbMobileUpdateInfo();

    expect(info.version, ccbMobileDefaultVersion);
    expect(info.apkDownloadUrl, ccbMobileDefaultApkDownloadUrl);
    expect(Uri.parse(info.apkDownloadUrl).scheme, 'https');
  });

  testWidgets('update panel shows version and opens configured download URL', (
    tester,
  ) async {
    final openedUrls = <String>[];

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ProjectHomeUpdatePanel(
            updateInfo: const CcbMobileUpdateInfo(
              version: '9.1.0+9010000',
              apkDownloadUrl: 'https://example.com/ccb-mobile.apk',
            ),
            openUpdateUrl: (url) async {
              openedUrls.add(url);
              return true;
            },
          ),
        ),
      ),
    );

    expect(
      find.byKey(const ValueKey('project-home-update-panel')),
      findsOneWidget,
    );
    expect(find.text('Current version: 9.1.0+9010000'), findsOneWidget);
    expect(find.text('Open APK download'), findsOneWidget);

    await tester.tap(
      find.byKey(const ValueKey('project-home-update-open-apk-button')),
    );
    await tester.pumpAndSettle();

    expect(openedUrls, ['https://example.com/ccb-mobile.apk']);
  });

  testWidgets('update panel reports failed browser handoff', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ProjectHomeUpdatePanel(
            updateInfo: const CcbMobileUpdateInfo(
              apkDownloadUrl: 'https://example.com/ccb-mobile.apk',
            ),
            openUpdateUrl: (_) async => false,
          ),
        ),
      ),
    );

    await tester.tap(
      find.byKey(const ValueKey('project-home-update-open-apk-button')),
    );
    await tester.pumpAndSettle();

    expect(find.text('Could not open update download'), findsOneWidget);
  });
}
