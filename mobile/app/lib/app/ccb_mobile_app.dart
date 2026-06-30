import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import '../features/project_home/project_home_screen.dart';
import '../l10n/ccb_mobile_localizations.dart';
import '../repository/fake_mobile_ccb_repository.dart';

class CcbMobileApp extends StatelessWidget {
  const CcbMobileApp({this.enableProductOnboarding = true, super.key});

  final bool enableProductOnboarding;

  @override
  Widget build(BuildContext context) {
    final repository = FakeMobileCcbRepository.demo();
    return MaterialApp(
      onGenerateTitle: (context) => CcbMobileLocalizations.of(context).appTitle,
      localizationsDelegates: GlobalMaterialLocalizations.delegates,
      supportedLocales: CcbMobileLocalizations.supportedLocales,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xff116149)),
        useMaterial3: true,
      ),
      home: ProjectHomeScreen(
        repository: repository,
        showOnboardingWhenUnpaired: enableProductOnboarding,
        autoActivateStoredProfile: enableProductOnboarding,
      ),
    );
  }
}
