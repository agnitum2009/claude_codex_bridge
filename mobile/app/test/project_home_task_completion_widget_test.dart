import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:ccb_mobile/ccb_mobile.dart';

import 'support/project_home_test_fakes.dart';

void main() {
  testWidgets(
    'missing notify scope shows re-pair prompt and does not subscribe',
    (tester) async {
      final streamClient = _FakeTaskCompletionStreamClient();
      final localNotifications = _FakeTaskCompletionLocalNotifications();
      final profileStore = await _profileStoreWith([
        _pairedHost(scopes: const {'view', 'focus'}),
      ]);

      await tester.pumpWidget(
        MaterialApp(
          home: ProjectHomeScreen(
            repository: FakeMobileCcbRepository.demo(),
            profileStore: profileStore,
            autoActivateStoredProfile: true,
            taskNotificationStreamClient: streamClient,
            taskCompletionLocalNotifications: localNotifications,
            taskCompletionSeenStore: TaskCompletionSeenDedupeStore(
              secureStore: MemorySecureStore(),
            ),
            taskCompletionUnreadStore: TaskCompletionUnreadStore(
              secureStore: MemorySecureStore(),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(
        find.text(taskCompletionMissingNotifyScopeMessage),
        findsOneWidget,
      );
      expect(localNotifications.permissionRequests, 0);
      expect(streamClient.subscribeCalls, 0);
    },
  );

  testWidgets('notification tap opens target project agent when present', (
    tester,
  ) async {
    final streamClient = _FakeTaskCompletionStreamClient();
    final localNotifications = _FakeTaskCompletionLocalNotifications();
    final profileStore = await _profileStoreWith([
      _pairedHost(scopes: const {'view', 'focus', 'notify'}),
    ]);

    await tester.pumpWidget(
      MaterialApp(
        home: ProjectHomeScreen(
          repository: FakeMobileCcbRepository.demo(),
          profileStore: profileStore,
          autoActivateStoredProfile: true,
          gatewayRepositoryFactory: (_) => RecordingGatewayRepository(),
          gatewayTerminalTransportFactory: (_) => RecordingTerminalTransport(),
          taskNotificationStreamClient: streamClient,
          taskCompletionLocalNotifications: localNotifications,
          taskCompletionSeenStore: TaskCompletionSeenDedupeStore(
            secureStore: MemorySecureStore(),
          ),
          taskCompletionUnreadStore: TaskCompletionUnreadStore(
            secureStore: MemorySecureStore(),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(streamClient.subscribeCalls, 1);
    expect(localNotifications.permissionRequests, 1);
    expect(find.byKey(const ValueKey('project-list')), findsOneWidget);

    localNotifications.addTap(
      const TaskCompletionNotificationTap(
        projectId: 'proj-demo',
        agent: 'mobile',
      ),
    );
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey('selected-agent-workspace')),
      findsOneWidget,
    );
  });

  testWidgets(
    'retained old completion does not notify or mark project unread',
    (tester) async {
      final streamClient = _FakeTaskCompletionStreamClient();
      final localNotifications = _FakeTaskCompletionLocalNotifications();
      final profileStore = await _profileStoreWith([
        _pairedHost(scopes: const {'view', 'focus', 'notify'}),
      ]);

      await tester.pumpWidget(
        MaterialApp(
          home: ProjectHomeScreen(
            repository: FakeMobileCcbRepository.demo(),
            profileStore: profileStore,
            autoActivateStoredProfile: true,
            gatewayRepositoryFactory: (_) => RecordingGatewayRepository(),
            gatewayTerminalTransportFactory:
                (_) => RecordingTerminalTransport(),
            taskNotificationStreamClient: streamClient,
            taskCompletionLocalNotifications: localNotifications,
            taskCompletionSeenStore: TaskCompletionSeenDedupeStore(
              secureStore: MemorySecureStore(),
            ),
            taskCompletionUnreadStore: TaskCompletionUnreadStore(
              secureStore: MemorySecureStore(),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      streamClient.add(
        _completionEvent(
          dedupeKey: 'old-lead',
          agent: 'lead',
          completedAt: DateTime.utc(2020),
        ),
      );
      await tester.pumpAndSettle();

      expect(localNotifications.shown, isEmpty);
      expect(
        find.byKey(const ValueKey('project-unread-star-proj-demo')),
        findsNothing,
      );
    },
  );

  testWidgets('live completion marks project unread and shows notification', (
    tester,
  ) async {
    final streamClient = _FakeTaskCompletionStreamClient();
    final localNotifications = _FakeTaskCompletionLocalNotifications();
    final profileStore = await _profileStoreWith([
      _pairedHost(scopes: const {'view', 'focus', 'notify'}),
    ]);

    await tester.pumpWidget(
      MaterialApp(
        home: ProjectHomeScreen(
          repository: FakeMobileCcbRepository.demo(),
          profileStore: profileStore,
          autoActivateStoredProfile: true,
          gatewayRepositoryFactory: (_) => RecordingGatewayRepository(),
          gatewayTerminalTransportFactory: (_) => RecordingTerminalTransport(),
          taskNotificationStreamClient: streamClient,
          taskCompletionLocalNotifications: localNotifications,
          taskCompletionSeenStore: TaskCompletionSeenDedupeStore(
            secureStore: MemorySecureStore(),
          ),
          taskCompletionUnreadStore: TaskCompletionUnreadStore(
            secureStore: MemorySecureStore(),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    streamClient.add(_completionEvent(dedupeKey: 'live-lead', agent: 'lead'));
    await tester.pumpAndSettle();

    expect(localNotifications.shown.map((event) => event.dedupeKey), [
      'live-lead',
    ]);
    expect(
      find.byKey(const ValueKey('project-unread-star-proj-demo')),
      findsOneWidget,
    );
  });

  testWidgets('visible target completion is consumed without notification', (
    tester,
  ) async {
    final streamClient = _FakeTaskCompletionStreamClient();
    final localNotifications = _FakeTaskCompletionLocalNotifications();
    final profileStore = await _profileStoreWith([
      _pairedHost(scopes: const {'view', 'focus', 'notify'}),
    ]);

    await tester.pumpWidget(
      MaterialApp(
        home: ProjectHomeScreen(
          repository: FakeMobileCcbRepository.demo(),
          profileStore: profileStore,
          autoActivateStoredProfile: true,
          gatewayRepositoryFactory: (_) => RecordingGatewayRepository(),
          gatewayTerminalTransportFactory: (_) => RecordingTerminalTransport(),
          taskNotificationStreamClient: streamClient,
          taskCompletionLocalNotifications: localNotifications,
          taskCompletionSeenStore: TaskCompletionSeenDedupeStore(
            secureStore: MemorySecureStore(),
          ),
          taskCompletionUnreadStore: TaskCompletionUnreadStore(
            secureStore: MemorySecureStore(),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('project-open-proj-demo')));
    await tester.pumpAndSettle();

    streamClient.add(
      _completionEvent(dedupeKey: 'visible-mobile', agent: 'mobile'),
    );
    await tester.pumpAndSettle();

    expect(localNotifications.shown, isEmpty);
    expect(
      find.byKey(const ValueKey('agent-unread-star-mobile')),
      findsNothing,
    );
  });

  testWidgets('unread agent marker clears when target agent is selected', (
    tester,
  ) async {
    final streamClient = _FakeTaskCompletionStreamClient();
    final localNotifications = _FakeTaskCompletionLocalNotifications();
    final profileStore = await _profileStoreWith([
      _pairedHost(scopes: const {'view', 'focus', 'notify'}),
    ]);

    await tester.pumpWidget(
      MaterialApp(
        home: ProjectHomeScreen(
          repository: FakeMobileCcbRepository.demo(),
          profileStore: profileStore,
          autoActivateStoredProfile: true,
          gatewayRepositoryFactory: (_) => RecordingGatewayRepository(),
          gatewayTerminalTransportFactory: (_) => RecordingTerminalTransport(),
          taskNotificationStreamClient: streamClient,
          taskCompletionLocalNotifications: localNotifications,
          taskCompletionSeenStore: TaskCompletionSeenDedupeStore(
            secureStore: MemorySecureStore(),
          ),
          taskCompletionUnreadStore: TaskCompletionUnreadStore(
            secureStore: MemorySecureStore(),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('project-open-proj-demo')));
    await tester.pumpAndSettle();

    streamClient.add(_completionEvent(dedupeKey: 'lead-unread', agent: 'lead'));
    await tester.pumpAndSettle();

    expect(localNotifications.shown.map((event) => event.dedupeKey), [
      'lead-unread',
    ]);
    expect(
      find.byKey(const ValueKey('agent-unread-star-lead')),
      findsOneWidget,
    );

    await tester.tap(find.byKey(const ValueKey('agent-lead')));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('agent-unread-star-lead')), findsNothing);
  });

  testWidgets(
    'default selected agent unread marker clears when project opens',
    (tester) async {
      final streamClient = _FakeTaskCompletionStreamClient();
      final localNotifications = _FakeTaskCompletionLocalNotifications();
      final profileStore = await _profileStoreWith([
        _pairedHost(scopes: const {'view', 'focus', 'notify'}),
      ]);

      await tester.pumpWidget(
        MaterialApp(
          home: ProjectHomeScreen(
            repository: FakeMobileCcbRepository.demo(),
            profileStore: profileStore,
            autoActivateStoredProfile: true,
            gatewayRepositoryFactory: (_) => RecordingGatewayRepository(),
            gatewayTerminalTransportFactory:
                (_) => RecordingTerminalTransport(),
            taskNotificationStreamClient: streamClient,
            taskCompletionLocalNotifications: localNotifications,
            taskCompletionSeenStore: TaskCompletionSeenDedupeStore(
              secureStore: MemorySecureStore(),
            ),
            taskCompletionUnreadStore: TaskCompletionUnreadStore(
              secureStore: MemorySecureStore(),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      streamClient.add(
        _completionEvent(dedupeKey: 'mobile-unread', agent: 'mobile'),
      );
      await tester.pumpAndSettle();

      expect(
        find.byKey(const ValueKey('project-unread-star-proj-demo')),
        findsOneWidget,
      );

      await tester.tap(find.byKey(const ValueKey('project-open-proj-demo')));
      await tester.pumpAndSettle();

      expect(
        find.byKey(const ValueKey('agent-unread-star-mobile')),
        findsNothing,
      );
      expect(
        find.byKey(const ValueKey('project-unread-star-proj-demo')),
        findsNothing,
      );
    },
  );
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

GatewayPairedHost _pairedHost({required Set<String> scopes}) {
  return GatewayPairedHost(
    profile: GatewayHostProfile(
      hostId: 'proj-demo',
      deviceId: 'phone',
      routeProvider: RouteProvider(
        kind: RouteProviderKind.lan,
        gatewayUrl: Uri.parse('http://127.0.0.1:8787'),
      ),
      scopes: scopes,
    ),
    deviceToken: 'token-proj-demo-phone',
    projectId: 'proj-demo',
  );
}

class _FakeTaskCompletionStreamClient
    implements GatewayTaskCompletionNotificationStreamClient {
  final _controller =
      StreamController<TaskCompletionNotificationEvent>.broadcast();
  var subscribeCalls = 0;

  void add(TaskCompletionNotificationEvent event) {
    _controller.add(event);
  }

  @override
  Stream<TaskCompletionNotificationEvent> subscribe(GatewayPairedHost host) {
    subscribeCalls += 1;
    return _controller.stream;
  }
}

class _FakeTaskCompletionLocalNotifications
    implements TaskCompletionLocalNotifications {
  final _taps = StreamController<TaskCompletionNotificationTap>.broadcast();
  final shown = <TaskCompletionNotificationEvent>[];
  var permissionRequests = 0;

  void addTap(TaskCompletionNotificationTap tap) {
    _taps.add(tap);
  }

  @override
  Stream<TaskCompletionNotificationTap> get taps => _taps.stream;

  @override
  Future<TaskCompletionLocalNotificationPermissionStatus>
  requestPermissionIfNeeded() async {
    permissionRequests += 1;
    return TaskCompletionLocalNotificationPermissionStatus.granted;
  }

  @override
  Future<bool> showTaskCompletion(TaskCompletionNotificationEvent event) async {
    shown.add(event);
    return true;
  }
}

TaskCompletionNotificationEvent _completionEvent({
  required String dedupeKey,
  required String agent,
  DateTime? completedAt,
}) {
  return TaskCompletionNotificationEvent(
    id: 'event-$dedupeKey',
    kind: TaskCompletionNotificationEvent.taskCompletedKind,
    projectId: 'proj-demo',
    projectShortName: 'demo',
    agent: agent,
    completedAt:
        completedAt ?? DateTime.now().toUtc().add(const Duration(seconds: 5)),
    dedupeKey: dedupeKey,
  );
}
