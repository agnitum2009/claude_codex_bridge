import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:ccb_mobile/ccb_mobile.dart';

import 'support/project_home_test_fakes.dart';

void main() {
  testWidgets('settings theme selector switches to dark theme and persists', (
    tester,
  ) async {
    final store = MemoryThemePreferenceStore();

    await tester.pumpWidget(
      CcbMobileApp(
        enableProductOnboarding: true,
        themePreferenceStore: store,
        profileStore: GatewayHostProfileStore(secureStore: MemorySecureStore()),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(
      find.byKey(const ValueKey('theme-preference-segments')),
      findsOneWidget,
    );

    final segments = tester.widget<SegmentedButton<CcbThemePreference>>(
      find.byKey(const ValueKey('theme-preference-segments')),
    );
    segments.onSelectionChanged?.call({CcbThemePreference.dark});
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(await store.read(), CcbThemePreference.dark);
    expect(
      tester.widget<MaterialApp>(find.byType(MaterialApp)).themeMode,
      ThemeMode.dark,
    );
    expect(
      Theme.of(
        tester.element(find.byKey(const ValueKey('project-home-onboarding'))),
      ).colorScheme.brightness,
      Brightness.dark,
    );

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pumpWidget(
      CcbMobileApp(
        enableProductOnboarding: true,
        themePreferenceStore: store,
        profileStore: GatewayHostProfileStore(secureStore: MemorySecureStore()),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(
      Theme.of(
        tester.element(find.byKey(const ValueKey('project-home-onboarding'))),
      ).colorScheme.brightness,
      Brightness.dark,
    );
  });
}

class MemoryThemePreferenceStore implements CcbThemePreferenceStore {
  CcbThemePreference _preference = CcbThemePreference.system;

  @override
  Future<CcbThemePreference> read() async {
    return _preference;
  }

  @override
  Future<void> write(CcbThemePreference preference) async {
    _preference = preference;
  }
}
