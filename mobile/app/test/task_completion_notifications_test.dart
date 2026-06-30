import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:ccb_mobile/ccb_mobile.dart';
import 'package:ccb_mobile/features/project_home/project_home_task_completion_notifications.dart';
import 'package:test/test.dart';

import 'support/project_home_test_fakes.dart';

void main() {
  group('task completion notifications', () {
    test('event shows local notification with stable id and copy', () async {
      final streamClient = _FakeTaskCompletionStreamClient();
      final localNotifications = _FakeTaskCompletionLocalNotifications();
      final controller = _controller(
        streamClient: streamClient,
        localNotifications: localNotifications,
      );
      final event = _event(dedupeKey: 'proj-demo:mobile:1');

      final status = await controller.start(_host(scopes: const {'notify'}));
      streamClient.add(event);
      await _drain();

      expect(status, TaskCompletionNotificationSubscriptionStatus.subscribed);
      expect(localNotifications.permissionRequests, 1);
      expect(localNotifications.shown, hasLength(1));
      expect(
        localNotifications.shown.single.notificationId,
        event.notificationId,
      );
      expect(localNotifications.shown.single.title, 'CCB Mobile');
      expect(localNotifications.shown.single.body, 'demo / mobile 任务完成');

      await controller.dispose();
    });

    test(
      'dedupe key is persisted and suppresses duplicate notifications',
      () async {
        final secureStore = MemorySecureStore();
        final streamClient = _FakeTaskCompletionStreamClient();
        final localNotifications = _FakeTaskCompletionLocalNotifications();
        final controller = _controller(
          streamClient: streamClient,
          localNotifications: localNotifications,
          seenStore: TaskCompletionSeenDedupeStore(secureStore: secureStore),
        );
        final event = _event(dedupeKey: 'same-key');

        await controller.start(_host(scopes: const {'notify'}));
        streamClient
          ..add(event)
          ..add(event);
        await _drain();

        expect(localNotifications.shown, hasLength(1));
        expect(
          await TaskCompletionSeenDedupeStore(
            secureStore: secureStore,
          ).readSeenKeys(),
          ['same-key'],
        );

        await controller.dispose();
      },
    );

    test('seen store keeps a bounded recent dedupe set', () async {
      final store = TaskCompletionSeenDedupeStore(
        secureStore: MemorySecureStore(),
        maxKeys: 2,
      );

      expect(await store.markSeenIfNew('a'), isTrue);
      expect(await store.markSeenIfNew('b'), isTrue);
      expect(await store.markSeenIfNew('c'), isTrue);

      expect(await store.readSeenKeys(), ['b', 'c']);
      expect(await store.markSeenIfNew('a'), isTrue);
    });

    test('stable notification id is deterministic signed 32-bit hash', () {
      final first = stableTaskCompletionNotificationId('proj-demo:mobile:1');
      final second = stableTaskCompletionNotificationId('proj-demo:mobile:1');
      final different = stableTaskCompletionNotificationId('proj-demo:lead:1');

      expect(first, second);
      expect(first, isNot(different));
      expect(first, inInclusiveRange(-0x80000000, 0x7fffffff));
      expect(first, 1840802715);
    });

    test(
      'missing notify scope does not request permission or subscribe',
      () async {
        final streamClient = _FakeTaskCompletionStreamClient();
        final localNotifications = _FakeTaskCompletionLocalNotifications();
        final controller = _controller(
          streamClient: streamClient,
          localNotifications: localNotifications,
        );

        final status = await controller.start(_host(scopes: const {'view'}));

        expect(
          status,
          TaskCompletionNotificationSubscriptionStatus.missingNotifyScope,
        );
        expect(localNotifications.permissionRequests, 0);
        expect(streamClient.subscribeCalls, 0);

        await controller.dispose();
      },
    );

    test(
      'permission denied still consumes stream without showing OS notification',
      () async {
        final streamClient = _FakeTaskCompletionStreamClient();
        final localNotifications = _FakeTaskCompletionLocalNotifications(
          permissionStatus:
              TaskCompletionLocalNotificationPermissionStatus.denied,
        );
        final controller = _controller(
          streamClient: streamClient,
          localNotifications: localNotifications,
        );

        final status = await controller.start(_host(scopes: const {'notify'}));
        streamClient.add(_event(dedupeKey: 'denied'));
        await _drain();

        expect(
          status,
          TaskCompletionNotificationSubscriptionStatus.permissionDenied,
        );
        expect(localNotifications.shown, isEmpty);
        expect(streamClient.subscribeCalls, 1);

        await controller.dispose();
      },
    );

    test('HTTP client uses gateway notification SSE contract', () async {
      final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
      addTearDown(() => server.close(force: true));
      final requestSeen = Completer<HttpRequest>();
      unawaited(
        server.first.then((request) async {
          requestSeen.complete(request);
          request.response
            ..statusCode = HttpStatus.ok
            ..headers.contentType = ContentType(
              'text',
              'event-stream',
              charset: 'utf-8',
            )
            ..write('id: event-demo\n')
            ..write('event: task_completed\n')
            ..write('data: ${jsonEncode(_event(dedupeKey: 'sse').toJson())}\n')
            ..write('\n');
          await request.response.close();
        }),
      );
      final client = HttpGatewayTaskCompletionNotificationStreamClient(
        timeout: const Duration(seconds: 2),
      );
      addTearDown(client.close);

      final event =
          await client
              .subscribe(
                GatewayPairedHost(
                  profile: GatewayHostProfile(
                    hostId: 'host-demo',
                    deviceId: 'device-demo',
                    routeProvider: RouteProvider(
                      kind: RouteProviderKind.lan,
                      gatewayUrl: Uri.parse(
                        'http://${server.address.address}:${server.port}',
                      ),
                    ),
                    scopes: const {'notify'},
                  ),
                  deviceToken: 'device-token',
                  projectId: 'proj-demo',
                ),
              )
              .first;
      final request = await requestSeen.future;

      expect(request.uri.path, '/v1/mobile/notifications');
      expect(
        request.headers.value(HttpHeaders.authorizationHeader),
        'Bearer device-token',
      );
      expect(event.dedupeKey, 'sse');
    });

    test(
      'tap routing opens target agent when project view still contains it',
      () {
        final route = resolveProjectHomeTaskCompletionNotificationTap(
          tap: const TaskCompletionNotificationTap(
            projectId: 'proj-demo',
            agent: 'mobile',
          ),
          targetView: _view(),
        );

        expect(
          route.kind,
          ProjectHomeTaskCompletionNotificationRouteKind.openProjectAgent,
        );
        expect(route.projectId, 'proj-demo');
        expect(route.agentName, 'mobile');
        expect(route.view?.project.id, 'proj-demo');
      },
    );

    test('tap routing falls back to project list for missing target', () {
      final route = resolveProjectHomeTaskCompletionNotificationTap(
        tap: const TaskCompletionNotificationTap(
          projectId: 'proj-demo',
          agent: 'missing',
        ),
        targetView: _view(),
      );
      final missingProjectRoute =
          resolveProjectHomeTaskCompletionNotificationTap(
            tap: const TaskCompletionNotificationTap(
              projectId: 'missing',
              agent: 'mobile',
            ),
            targetView: null,
          );

      expect(
        route.kind,
        ProjectHomeTaskCompletionNotificationRouteKind.projectList,
      );
      expect(
        missingProjectRoute.kind,
        ProjectHomeTaskCompletionNotificationRouteKind.projectList,
      );
    });
  });
}

TaskCompletionNotificationController _controller({
  required _FakeTaskCompletionStreamClient streamClient,
  required _FakeTaskCompletionLocalNotifications localNotifications,
  TaskCompletionSeenDedupeStore? seenStore,
}) {
  return TaskCompletionNotificationController(
    streamClient: streamClient,
    localNotifications: localNotifications,
    seenStore:
        seenStore ??
        TaskCompletionSeenDedupeStore(secureStore: MemorySecureStore()),
    onTap: (_) {},
  );
}

TaskCompletionNotificationEvent _event({required String dedupeKey}) {
  return TaskCompletionNotificationEvent(
    id: 'event-$dedupeKey',
    kind: TaskCompletionNotificationEvent.taskCompletedKind,
    projectId: 'proj-demo',
    projectShortName: 'demo',
    agent: 'mobile',
    completedAt: DateTime.utc(2026, 6, 30, 12),
    dedupeKey: dedupeKey,
  );
}

GatewayPairedHost _host({required Set<String> scopes}) {
  return GatewayPairedHost(
    profile: GatewayHostProfile(
      hostId: 'host-demo',
      deviceId: 'device-demo',
      routeProvider: RouteProvider(
        kind: RouteProviderKind.lan,
        gatewayUrl: Uri.parse('http://127.0.0.1:8787'),
      ),
      scopes: scopes,
    ),
    deviceToken: 'device-token',
    projectId: 'proj-demo',
  );
}

CcbProjectView _view() {
  return const CcbProjectView(
    project: CcbProject(
      id: 'proj-demo',
      displayName: 'demo',
      root: '/srv/demo',
    ),
    namespaceEpoch: 4,
    tmuxSocketPath: '/tmp/tmux.sock',
    tmuxSessionName: 'ccb-demo',
    activeWindow: 'main',
    activePaneId: '%1',
    windows: [
      CcbWindow(
        name: 'main',
        label: 'main',
        kind: 'agents',
        order: 0,
        active: true,
        agents: ['mobile'],
      ),
    ],
    agents: [
      CcbAgent(
        name: 'mobile',
        provider: 'codex',
        window: 'main',
        order: 0,
        active: true,
        queueDepth: 0,
      ),
    ],
    contentItems: [],
    notifications: [],
    terminalHistories: {},
  );
}

Future<void> _drain() async {
  await Future<void>.delayed(Duration.zero);
  await Future<void>.delayed(Duration.zero);
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
  _FakeTaskCompletionLocalNotifications({
    this.permissionStatus =
        TaskCompletionLocalNotificationPermissionStatus.granted,
  });

  final TaskCompletionLocalNotificationPermissionStatus permissionStatus;
  final shown = <TaskCompletionNotificationEvent>[];
  final _taps = StreamController<TaskCompletionNotificationTap>.broadcast();
  var permissionRequests = 0;

  @override
  Stream<TaskCompletionNotificationTap> get taps => _taps.stream;

  @override
  Future<TaskCompletionLocalNotificationPermissionStatus>
  requestPermissionIfNeeded() async {
    permissionRequests += 1;
    return permissionStatus;
  }

  @override
  Future<bool> showTaskCompletion(TaskCompletionNotificationEvent event) async {
    shown.add(event);
    return true;
  }
}
