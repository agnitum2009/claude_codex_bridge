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
  var subscribeCalls = 0;

  @override
  Stream<TaskCompletionNotificationEvent> subscribe(GatewayPairedHost host) {
    subscribeCalls += 1;
    return const Stream.empty();
  }
}

class _FakeTaskCompletionLocalNotifications
    implements TaskCompletionLocalNotifications {
  final _taps = StreamController<TaskCompletionNotificationTap>.broadcast();
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
    return true;
  }
}
