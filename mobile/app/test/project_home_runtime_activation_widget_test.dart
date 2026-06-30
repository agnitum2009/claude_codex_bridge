import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:xterm/xterm.dart';

import 'package:ccb_mobile/ccb_mobile.dart';

import 'support/project_home_test_driver.dart';
import 'support/project_home_test_fakes.dart';

void main() {
  testWidgets('paired no-profile shows snack and does not call factories', (
    tester,
  ) async {
    var repositoryFactoryCalls = 0;
    var terminalFactoryCalls = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: ProjectHomeScreen(
          repository: RecordingGatewayRepository(),
          profileStore: GatewayHostProfileStore(
            secureStore: MemorySecureStore(),
          ),
          gatewayRepositoryFactory: (_) {
            repositoryFactoryCalls += 1;
            return RecordingGatewayRepository();
          },
          gatewayTerminalTransportFactory: (_) {
            terminalFactoryCalls += 1;
            return RecordingTerminalTransport();
          },
        ),
      ),
    );
    await tester.pumpAndSettle();

    await openConnectionDetails(tester);
    await expandTile(tester, const ValueKey('runtime-mode-panel'));
    _runtimeSegments(
      tester,
    ).onSelectionChanged?.call({AppRuntimeMode.pairedGateway});
    await tester.pumpAndSettle();

    expect(find.text('Pair a gateway profile first'), findsOneWidget);
    expect(repositoryFactoryCalls, 0);
    expect(terminalFactoryCalls, 0);
    expect(find.byKey(const ValueKey('runtime-mode-status')), findsOneWidget);
    expect(find.text('Fake'), findsWidgets);
  });

  testWidgets('profile load failure clears loading state', (tester) async {
    var repositoryFactoryCalls = 0;
    var terminalFactoryCalls = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: ProjectHomeScreen(
          repository: RecordingGatewayRepository(),
          profileStore: _FailingProfileStore(),
          gatewayRepositoryFactory: (_) {
            repositoryFactoryCalls += 1;
            return RecordingGatewayRepository();
          },
          gatewayTerminalTransportFactory: (_) {
            terminalFactoryCalls += 1;
            return RecordingTerminalTransport();
          },
        ),
      ),
    );
    await tester.pumpAndSettle();

    await openConnectionDetails(tester);
    await expandTile(tester, const ValueKey('runtime-mode-panel'));

    expect(find.byType(CircularProgressIndicator), findsNothing);
    expect(_profileValue(tester), isNull);
    _runtimeSegments(
      tester,
    ).onSelectionChanged?.call({AppRuntimeMode.pairedGateway});
    await tester.pumpAndSettle();

    expect(find.text('Pair a gateway profile first'), findsOneWidget);
    expect(repositoryFactoryCalls, 0);
    expect(terminalFactoryCalls, 0);
  });

  testWidgets('stored profile activation calls factories with same profile', (
    tester,
  ) async {
    final profile = _pairedHost(
      hostId: 'proj-demo',
      deviceId: 'phone',
      routeKind: RouteProviderKind.cloudflareTunnel,
    );
    final profileStore = await _profileStoreWith([profile]);
    final seenRepositoryProfiles = <GatewayPairedHost>[];
    final seenTerminalProfiles = <GatewayPairedHost>[];

    await tester.pumpWidget(
      MaterialApp(
        home: ProjectHomeScreen(
          repository: RecordingGatewayRepository(),
          profileStore: profileStore,
          gatewayRepositoryFactory: (profile) {
            seenRepositoryProfiles.add(profile);
            return RecordingGatewayRepository();
          },
          gatewayTerminalTransportFactory: (profile) {
            seenTerminalProfiles.add(profile);
            return RecordingTerminalTransport();
          },
        ),
      ),
    );
    await tester.pumpAndSettle();

    await openConnectionDetails(tester);
    await expandTile(tester, const ValueKey('runtime-mode-panel'));
    final loadedProfile = _profileValue(tester)!;
    _runtimeSegments(
      tester,
    ).onSelectionChanged?.call({AppRuntimeMode.pairedGateway});
    await tester.pumpAndSettle();

    expect(loadedProfile.profile.hostId, profile.profile.hostId);
    expect(loadedProfile.profile.deviceId, profile.profile.deviceId);
    expect(seenRepositoryProfiles, [same(loadedProfile)]);
    expect(seenTerminalProfiles, [same(loadedProfile)]);
    expect(find.text('Pair a gateway profile first'), findsNothing);
  });

  testWidgets('activation syncs gateway settings on project list', (
    tester,
  ) async {
    final profile = _pairedHost(
      hostId: 'proj-demo',
      deviceId: 'phone',
      gatewayUrl: Uri.parse('https://mobile.example.com'),
      routeKind: RouteProviderKind.cloudflareTunnel,
    );
    final profileStore = await _profileStoreWith([profile]);

    await tester.pumpWidget(
      MaterialApp(
        home: ProjectHomeScreen(
          repository: RecordingGatewayRepository(),
          profileStore: profileStore,
          gatewayRepositoryFactory: (_) => RecordingGatewayRepository(),
          gatewayTerminalTransportFactory: (_) => RecordingTerminalTransport(),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await openConnectionDetails(tester);
    await expandTile(tester, const ValueKey('runtime-mode-panel'));
    _runtimeSegments(
      tester,
    ).onSelectionChanged?.call({AppRuntimeMode.pairedGateway});
    await tester.pumpAndSettle();
    await dismissConnectionDetails(tester);

    expect(find.byKey(const ValueKey('project-list')), findsOneWidget);
    expect(
      find.byKey(const ValueKey('project-list-settings-action')),
      findsOneWidget,
    );
    await tester.tap(
      find.byKey(const ValueKey('project-list-settings-action')),
    );
    await tester.pumpAndSettle();
    await expandTile(tester, const ValueKey('gateway-pairing-panel'));
    expect(_routeKindValue(tester), RouteProviderKind.cloudflareTunnel);
    expect(
      _textField(tester, const ValueKey('gateway-url-field')).controller?.text,
      'https://mobile.example.com',
    );
  });

  testWidgets('profile dropdown selection activates without snack', (
    tester,
  ) async {
    final first = _pairedHost(
      hostId: 'proj-demo',
      deviceId: 'phone',
      routeKind: RouteProviderKind.lan,
    );
    final second = _pairedHost(
      hostId: 'proj-demo',
      deviceId: 'tablet',
      gatewayUrl: Uri.parse('https://other.example.com'),
      routeKind: RouteProviderKind.relay,
    );
    final profileStore = await _profileStoreWith([first, second]);
    final seenRepositoryProfiles = <GatewayPairedHost>[];

    await tester.pumpWidget(
      MaterialApp(
        home: ProjectHomeScreen(
          repository: RecordingGatewayRepository(),
          profileStore: profileStore,
          gatewayRepositoryFactory: (profile) {
            seenRepositoryProfiles.add(profile);
            return RecordingGatewayRepository();
          },
          gatewayTerminalTransportFactory: (_) => RecordingTerminalTransport(),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await openConnectionDetails(tester);
    await expandTile(tester, const ValueKey('runtime-mode-panel'));
    _runtimeSegments(
      tester,
    ).onSelectionChanged?.call({AppRuntimeMode.pairedGateway});
    await tester.pumpAndSettle();
    final loadedFirst = _profileValue(tester)!;
    await tester.tap(find.byType(DropdownButtonFormField<GatewayPairedHost>));
    await tester.pumpAndSettle();
    await tester.tap(find.text('proj-demo / tablet / relay').last);
    await tester.pumpAndSettle();
    final loadedSecond = _profileValue(tester)!;

    expect(loadedFirst.profile.deviceId, first.profile.deviceId);
    expect(loadedSecond.profile.deviceId, second.profile.deviceId);
    expect(seenRepositoryProfiles.first, same(loadedFirst));
    expect(seenRepositoryProfiles.last, same(loadedSecond));
    expect(find.text('Pair a gateway profile first'), findsNothing);
    expect(find.text('proj-demo / tablet / relay'), findsWidgets);
  });

  testWidgets('switching back fake clears gateway terminal path', (
    tester,
  ) async {
    final profile = _pairedHost(hostId: 'proj-demo', deviceId: 'phone');
    final profileStore = await _profileStoreWith([profile]);
    final fakeRepository = RecordingGatewayRepository();
    final gatewayRepository = RecordingGatewayRepository();
    final gatewayTerminalTransport = RecordingTerminalTransport();

    await tester.pumpWidget(
      MaterialApp(
        home: ProjectHomeScreen(
          repository: fakeRepository,
          profileStore: profileStore,
          gatewayRepositoryFactory: (_) => gatewayRepository,
          gatewayTerminalTransportFactory: (_) => gatewayTerminalTransport,
        ),
      ),
    );
    await tester.pumpAndSettle();

    await openConnectionDetails(tester);
    await expandTile(tester, const ValueKey('runtime-mode-panel'));
    _runtimeSegments(
      tester,
    ).onSelectionChanged?.call({AppRuntimeMode.pairedGateway});
    await tester.pumpAndSettle();
    _runtimeSegments(tester).onSelectionChanged?.call({AppRuntimeMode.fake});
    await tester.pumpAndSettle();
    await dismissConnectionDetails(tester);
    await openCurrentProject(tester);

    await tester.tap(find.byKey(const ValueKey('open-agent-terminal-button')));
    await tester.pumpAndSettle();

    expect(gatewayTerminalTransport.requests, isEmpty);
    expect(gatewayRepository.focusAgentCalls, isEmpty);
    expect(find.byType(TerminalView), findsOneWidget);
    expect(fakeRepository.conversationCalls, isNotEmpty);
  });
}

SegmentedButton<AppRuntimeMode> _runtimeSegments(WidgetTester tester) {
  return tester.widget<SegmentedButton<AppRuntimeMode>>(
    find.byKey(const ValueKey('runtime-mode-segments')),
  );
}

GatewayPairedHost? _profileValue(WidgetTester tester) {
  return tester
      .state<FormFieldState<GatewayPairedHost>>(
        find.byType(DropdownButtonFormField<GatewayPairedHost>),
      )
      .value;
}

RouteProviderKind? _routeKindValue(WidgetTester tester) {
  return tester
      .state<FormFieldState<RouteProviderKind>>(
        find.byType(DropdownButtonFormField<RouteProviderKind>),
      )
      .value;
}

TextField _textField(WidgetTester tester, ValueKey<String> key) {
  return tester.widget<TextField>(find.byKey(key));
}

Future<GatewayHostProfileStore> _profileStoreWith(
  List<GatewayPairedHost> profiles,
) async {
  final store = GatewayHostProfileStore(secureStore: MemorySecureStore());
  for (final profile in profiles) {
    await store.save(profile);
  }
  return store;
}

class _FailingProfileStore extends GatewayHostProfileStore {
  _FailingProfileStore() : super(secureStore: MemorySecureStore());

  @override
  Future<List<GatewayPairedHost>> list() {
    throw StateError('profile load failed');
  }
}

GatewayPairedHost _pairedHost({
  required String hostId,
  required String deviceId,
  Uri? gatewayUrl,
  RouteProviderKind routeKind = RouteProviderKind.lan,
}) {
  return GatewayPairedHost(
    profile: GatewayHostProfile(
      hostId: hostId,
      deviceId: deviceId,
      routeProvider: RouteProvider(
        kind: routeKind,
        gatewayUrl: gatewayUrl ?? Uri.parse('http://$hostId.local:8787'),
      ),
      scopes: const {'view', 'focus', 'terminal_input', 'lifecycle'},
    ),
    deviceToken: 'token-$hostId-$deviceId',
    projectId: hostId,
  );
}
