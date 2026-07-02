import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';

import '../pairing/gateway_pairing.dart';

const taskCompletionNotificationChannelId = 'ccb_task_completion';
const defaultGatewayTaskCompletionNotificationStreamPath =
    '/v1/mobile/notifications';
const taskCompletionMissingNotifyScopeMessage =
    'Re-pair gateway to enable task completion notifications';

class TaskCompletionNotificationEvent {
  const TaskCompletionNotificationEvent({
    required this.id,
    required this.kind,
    required this.projectId,
    required this.projectShortName,
    required this.agent,
    required this.completedAt,
    required this.dedupeKey,
  });

  static const taskCompletedKind = 'task_completed';

  final String id;
  final String kind;
  final String projectId;
  final String projectShortName;
  final String agent;
  final DateTime completedAt;
  final String dedupeKey;

  bool get isTaskCompleted => kind == taskCompletedKind;

  int get notificationId => stableTaskCompletionNotificationId(dedupeKey);

  String get title => 'CCB Mobile';

  String get body => '$projectShortName / $agent 任务完成';

  TaskCompletionNotificationTap get tap {
    return TaskCompletionNotificationTap(projectId: projectId, agent: agent);
  }

  factory TaskCompletionNotificationEvent.fromJson(Map<String, Object?> json) {
    return TaskCompletionNotificationEvent(
      id: _requiredText(json['id'], 'id'),
      kind: _requiredText(json['kind'], 'kind'),
      projectId: _requiredText(json['project_id'], 'project_id'),
      projectShortName: _requiredText(
        json['project_short_name'],
        'project_short_name',
      ),
      agent: _requiredText(json['agent'], 'agent'),
      completedAt: _requiredDateTime(json['completed_at'], 'completed_at'),
      dedupeKey: _requiredText(json['dedupe_key'], 'dedupe_key'),
    );
  }

  Map<String, Object?> toJson() {
    return {
      'id': id,
      'kind': kind,
      'project_id': projectId,
      'project_short_name': projectShortName,
      'agent': agent,
      'completed_at': completedAt.toUtc().toIso8601String(),
      'dedupe_key': dedupeKey,
    };
  }
}

class TaskCompletionNotificationTap {
  const TaskCompletionNotificationTap({
    required this.projectId,
    required this.agent,
  });

  final String projectId;
  final String agent;

  factory TaskCompletionNotificationTap.fromJson(Map<String, Object?> json) {
    return TaskCompletionNotificationTap(
      projectId: _requiredText(json['project_id'], 'project_id'),
      agent: _requiredText(json['agent'], 'agent'),
    );
  }

  Map<String, Object?> toJson() {
    return {'project_id': projectId, 'agent': agent};
  }
}

int stableTaskCompletionNotificationId(String dedupeKey) {
  var hash = 0x811c9dc5;
  for (final byte in utf8.encode(dedupeKey)) {
    hash ^= byte;
    hash = (hash * 0x01000193) & 0xffffffff;
  }
  return hash >= 0x80000000 ? hash - 0x100000000 : hash;
}

class TaskCompletionSeenDedupeStore {
  TaskCompletionSeenDedupeStore({
    GatewaySecureStore? secureStore,
    int maxKeys = 256,
    String key = _defaultKey,
  }) : _secureStore = secureStore ?? FlutterGatewaySecureStore(),
       _maxKeys = maxKeys < 1 ? 1 : maxKeys,
       _key = key;

  static const _defaultKey = 'ccb_mobile.task_completion.seen_dedupe_keys';

  final GatewaySecureStore _secureStore;
  final int _maxKeys;
  final String _key;

  Future<bool> markSeenIfNew(String dedupeKey) async {
    final keys = await readSeenKeys();
    if (keys.contains(dedupeKey)) {
      return false;
    }
    final next = [...keys, dedupeKey];
    final bounded =
        next.length <= _maxKeys ? next : next.sublist(next.length - _maxKeys);
    await _secureStore.write(key: _key, value: jsonEncode(bounded));
    return true;
  }

  Future<List<String>> readSeenKeys() async {
    final raw = await _secureStore.read(key: _key);
    if (raw == null || raw.trim().isEmpty) {
      return [];
    }
    final Object? decoded;
    try {
      decoded = jsonDecode(raw);
    } on FormatException {
      return [];
    }
    if (decoded is Iterable) {
      return [for (final item in decoded) item.toString()];
    }
    return [];
  }
}

class TaskCompletionUnreadItem {
  const TaskCompletionUnreadItem({
    required this.projectId,
    required this.projectShortName,
    required this.agent,
    required this.completedAt,
    required this.dedupeKey,
  });

  final String projectId;
  final String projectShortName;
  final String agent;
  final DateTime completedAt;
  final String dedupeKey;

  factory TaskCompletionUnreadItem.fromEvent(
    TaskCompletionNotificationEvent event,
  ) {
    return TaskCompletionUnreadItem(
      projectId: event.projectId,
      projectShortName: event.projectShortName,
      agent: event.agent,
      completedAt: event.completedAt,
      dedupeKey: event.dedupeKey,
    );
  }

  factory TaskCompletionUnreadItem.fromJson(Map<String, Object?> json) {
    return TaskCompletionUnreadItem(
      projectId: _requiredText(json['project_id'], 'project_id'),
      projectShortName: _requiredText(
        json['project_short_name'],
        'project_short_name',
      ),
      agent: _requiredText(json['agent'], 'agent'),
      completedAt: _requiredDateTime(json['completed_at'], 'completed_at'),
      dedupeKey: _requiredText(json['dedupe_key'], 'dedupe_key'),
    );
  }

  Map<String, Object?> toJson() {
    return {
      'project_id': projectId,
      'project_short_name': projectShortName,
      'agent': agent,
      'completed_at': completedAt.toUtc().toIso8601String(),
      'dedupe_key': dedupeKey,
    };
  }
}

class TaskCompletionUnreadStore {
  TaskCompletionUnreadStore({
    GatewaySecureStore? secureStore,
    int maxItems = 256,
    String key = _defaultKey,
  }) : _secureStore = secureStore ?? FlutterGatewaySecureStore(),
       _maxItems = maxItems < 1 ? 1 : maxItems,
       _key = key;

  static const _defaultKey = 'ccb_mobile.task_completion.unread_items';

  final GatewaySecureStore _secureStore;
  final int _maxItems;
  final String _key;

  Future<List<TaskCompletionUnreadItem>> addIfNew(
    TaskCompletionNotificationEvent event,
  ) async {
    final items = await readUnreadItems();
    if (items.any((item) => item.dedupeKey == event.dedupeKey)) {
      return items;
    }
    final next = [...items, TaskCompletionUnreadItem.fromEvent(event)];
    final bounded =
        next.length <= _maxItems ? next : next.sublist(next.length - _maxItems);
    await _writeItems(bounded);
    return bounded;
  }

  Future<List<TaskCompletionUnreadItem>> clearAgent({
    required String projectId,
    required String agent,
  }) async {
    final wantedProject = projectId.trim();
    final wantedAgent = agent.trim();
    final next = [
      for (final item in await readUnreadItems())
        if (item.projectId != wantedProject || item.agent != wantedAgent) item,
    ];
    await _writeItems(next);
    return next;
  }

  Future<List<TaskCompletionUnreadItem>> readUnreadItems() async {
    final String? raw;
    try {
      raw = await _secureStore.read(key: _key);
    } on MissingPluginException {
      return [];
    } on PlatformException {
      return [];
    }
    if (raw == null || raw.trim().isEmpty) {
      return [];
    }
    final decoded = jsonDecode(raw);
    if (decoded is! Iterable) {
      return [];
    }
    final items = <TaskCompletionUnreadItem>[];
    for (final item in decoded) {
      if (item is! Map) {
        continue;
      }
      try {
        items.add(
          TaskCompletionUnreadItem.fromJson({
            for (final entry in item.entries) entry.key.toString(): entry.value,
          }),
        );
      } on FormatException {
        continue;
      }
    }
    return items;
  }

  Future<void> _writeItems(List<TaskCompletionUnreadItem> items) async {
    try {
      await _secureStore.write(
        key: _key,
        value: jsonEncode([for (final item in items) item.toJson()]),
      );
    } on MissingPluginException {
      return;
    } on PlatformException {
      return;
    }
  }
}

enum TaskCompletionLocalNotificationPermissionStatus {
  granted,
  denied,
  unsupported,
}

abstract interface class TaskCompletionLocalNotifications {
  Stream<TaskCompletionNotificationTap> get taps;

  Future<TaskCompletionLocalNotificationPermissionStatus>
  requestPermissionIfNeeded();

  Future<bool> showTaskCompletion(TaskCompletionNotificationEvent event);
}

class MethodChannelTaskCompletionLocalNotifications
    implements TaskCompletionLocalNotifications {
  MethodChannelTaskCompletionLocalNotifications({
    MethodChannel channel = const MethodChannel(
      'io.ccb.mobile/local_notifications',
    ),
  }) : _channel = channel {
    _channel.setMethodCallHandler(_handleMethodCall);
    unawaited(_registerNotificationTapHandler());
  }

  final MethodChannel _channel;
  final _taps = StreamController<TaskCompletionNotificationTap>.broadcast();

  @override
  Stream<TaskCompletionNotificationTap> get taps => _taps.stream;

  @override
  Future<TaskCompletionLocalNotificationPermissionStatus>
  requestPermissionIfNeeded() async {
    try {
      final granted = await _channel.invokeMethod<bool>(
        'requestPostNotificationsPermission',
      );
      return granted == true
          ? TaskCompletionLocalNotificationPermissionStatus.granted
          : TaskCompletionLocalNotificationPermissionStatus.denied;
    } on MissingPluginException {
      return TaskCompletionLocalNotificationPermissionStatus.unsupported;
    } on PlatformException {
      return TaskCompletionLocalNotificationPermissionStatus.denied;
    }
  }

  @override
  Future<bool> showTaskCompletion(TaskCompletionNotificationEvent event) async {
    try {
      return await _channel.invokeMethod<bool>('showTaskCompletion', {
            'channel_id': taskCompletionNotificationChannelId,
            'notification_id': event.notificationId,
            'title': event.title,
            'body': event.body,
            'payload': jsonEncode(event.tap.toJson()),
          }) ??
          false;
    } on MissingPluginException {
      return false;
    } on PlatformException {
      return false;
    }
  }

  Future<void> dispose() async {
    await _taps.close();
  }

  Future<void> _registerNotificationTapHandler() async {
    try {
      await _channel.invokeMethod<bool>('registerNotificationTapHandler');
    } on MissingPluginException {
      // The web/desktop test fallback has no Android local notification plugin.
    } on PlatformException {
      // Notification taps are best effort; event delivery still works on Android.
    }
  }

  Future<void> _handleMethodCall(MethodCall call) async {
    if (call.method != 'notificationTap') {
      return;
    }
    final payload = call.arguments;
    if (payload is! String || payload.trim().isEmpty) {
      return;
    }
    final decoded = jsonDecode(payload);
    if (decoded is Map) {
      _taps.add(
        TaskCompletionNotificationTap.fromJson({
          for (final entry in decoded.entries)
            entry.key.toString(): entry.value,
        }),
      );
    }
  }
}

abstract interface class GatewayTaskCompletionNotificationStreamClient {
  Stream<TaskCompletionNotificationEvent> subscribe(GatewayPairedHost host);
}

class HttpGatewayTaskCompletionNotificationStreamClient
    implements GatewayTaskCompletionNotificationStreamClient {
  HttpGatewayTaskCompletionNotificationStreamClient({
    HttpClient? httpClient,
    this.streamPath = defaultGatewayTaskCompletionNotificationStreamPath,
    this.timeout = const Duration(seconds: 10),
  }) : _httpClient = httpClient ?? HttpClient();

  final HttpClient _httpClient;
  final String streamPath;
  final Duration timeout;

  @override
  Stream<TaskCompletionNotificationEvent> subscribe(
    GatewayPairedHost host,
  ) async* {
    final uri = host.profile.routeProvider.gatewayUrl.resolve(streamPath);
    final request = await _httpClient.getUrl(uri).timeout(timeout);
    request.headers.set(
      HttpHeaders.acceptHeader,
      'application/x-ndjson, text/event-stream, application/json',
    );
    request.headers.set(
      HttpHeaders.authorizationHeader,
      'Bearer ${host.deviceToken}',
    );
    final response = await request.close().timeout(timeout);
    if (response.statusCode < 200 || response.statusCode >= 300) {
      final body = await utf8
          .decodeStream(response)
          .timeout(timeout)
          .catchError((_) => '');
      throw GatewayTaskCompletionNotificationStreamException(
        uri,
        response.statusCode,
        body,
      );
    }
    await for (final line in response
        .transform(utf8.decoder)
        .transform(const LineSplitter())) {
      final event = _eventFromStreamLine(line);
      if (event != null) {
        yield event;
      }
    }
  }

  void close({bool force = false}) {
    _httpClient.close(force: force);
  }
}

class GatewayTaskCompletionNotificationStreamException implements Exception {
  const GatewayTaskCompletionNotificationStreamException(
    this.uri,
    this.statusCode,
    this.message,
  );

  final Uri uri;
  final int statusCode;
  final String message;

  @override
  String toString() {
    return 'GatewayTaskCompletionNotificationStreamException'
        '($statusCode $uri: $message)';
  }
}

enum TaskCompletionNotificationSubscriptionStatus {
  subscribed,
  missingNotifyScope,
  permissionDenied,
}

typedef TaskCompletionNotificationEventHandler =
    FutureOr<void> Function(TaskCompletionNotificationEvent event);

typedef TaskCompletionNotificationPredicate =
    bool Function(TaskCompletionNotificationEvent event);

class TaskCompletionNotificationController {
  TaskCompletionNotificationController({
    required GatewayTaskCompletionNotificationStreamClient streamClient,
    required TaskCompletionLocalNotifications localNotifications,
    required TaskCompletionSeenDedupeStore seenStore,
    required void Function(TaskCompletionNotificationTap tap) onTap,
    TaskCompletionNotificationEventHandler? onLiveEvent,
    TaskCompletionNotificationPredicate? shouldShowNotification,
    DateTime Function()? clock,
    Duration initialReconnectDelay = const Duration(seconds: 1),
    Duration maxReconnectDelay = const Duration(seconds: 30),
  }) : _streamClient = streamClient,
       _localNotifications = localNotifications,
       _seenStore = seenStore,
       _onLiveEvent = onLiveEvent,
       _shouldShowNotification = shouldShowNotification,
       _clock = clock ?? DateTime.now,
       _initialReconnectDelay = initialReconnectDelay,
       _maxReconnectDelay = maxReconnectDelay {
    _tapSubscription = _localNotifications.taps.listen(onTap);
  }

  final GatewayTaskCompletionNotificationStreamClient _streamClient;
  final TaskCompletionLocalNotifications _localNotifications;
  final TaskCompletionSeenDedupeStore _seenStore;
  final TaskCompletionNotificationEventHandler? _onLiveEvent;
  final TaskCompletionNotificationPredicate? _shouldShowNotification;
  final DateTime Function() _clock;
  final Duration _initialReconnectDelay;
  final Duration _maxReconnectDelay;
  StreamSubscription<TaskCompletionNotificationEvent>? _eventSubscription;
  late final StreamSubscription<TaskCompletionNotificationTap> _tapSubscription;
  TaskCompletionLocalNotificationPermissionStatus? _permissionStatus;
  GatewayPairedHost? _activeHost;
  DateTime? _liveBaselineCompletedAt;
  Timer? _reconnectTimer;
  late Duration _nextReconnectDelay = _initialReconnectDelay;
  bool _started = false;

  Future<TaskCompletionNotificationSubscriptionStatus> start(
    GatewayPairedHost host,
  ) async {
    await stop();
    if (!host.profile.scopes.contains('notify')) {
      return TaskCompletionNotificationSubscriptionStatus.missingNotifyScope;
    }
    _started = true;
    _activeHost = host;
    _liveBaselineCompletedAt = _clock().toUtc();
    _nextReconnectDelay = _initialReconnectDelay;
    _permissionStatus = await _localNotifications.requestPermissionIfNeeded();
    _connect();
    return _permissionStatus ==
            TaskCompletionLocalNotificationPermissionStatus.granted
        ? TaskCompletionNotificationSubscriptionStatus.subscribed
        : TaskCompletionNotificationSubscriptionStatus.permissionDenied;
  }

  Future<void> stop() async {
    _started = false;
    _activeHost = null;
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    await _eventSubscription?.cancel();
    _eventSubscription = null;
  }

  Future<void> dispose() async {
    await stop();
    await _tapSubscription.cancel();
  }

  void _connect() {
    final host = _activeHost;
    if (!_started || host == null) {
      return;
    }
    try {
      _eventSubscription = _streamClient
          .subscribe(host)
          .listen(
            (event) => unawaited(_handleEvent(event)),
            onError: (_, _) {
              _scheduleReconnect();
            },
            onDone: _scheduleReconnect,
          );
    } catch (_) {
      _scheduleReconnect();
    }
  }

  void _scheduleReconnect() {
    if (!_started || _reconnectTimer != null) {
      return;
    }
    unawaited(_eventSubscription?.cancel());
    _eventSubscription = null;
    final delay = _nextReconnectDelay;
    _nextReconnectDelay = _nextDelayAfter(delay);
    _reconnectTimer = Timer(delay, () {
      _reconnectTimer = null;
      _connect();
    });
  }

  Duration _nextDelayAfter(Duration current) {
    final doubled = current * 2;
    return doubled > _maxReconnectDelay ? _maxReconnectDelay : doubled;
  }

  Future<void> _handleEvent(TaskCompletionNotificationEvent event) async {
    if (!event.isTaskCompleted) {
      return;
    }
    _nextReconnectDelay = _initialReconnectDelay;
    if (_isBaselineEvent(event)) {
      await _seenStore.markSeenIfNew(event.dedupeKey);
      return;
    }
    final fresh = await _seenStore.markSeenIfNew(event.dedupeKey);
    if (!fresh) {
      return;
    }
    await _onLiveEvent?.call(event);
    if (_permissionStatus !=
            TaskCompletionLocalNotificationPermissionStatus.granted ||
        _shouldShowNotification?.call(event) == false) {
      return;
    }
    await _localNotifications.showTaskCompletion(event);
  }

  bool _isBaselineEvent(TaskCompletionNotificationEvent event) {
    final baseline = _liveBaselineCompletedAt;
    return baseline != null && !event.completedAt.isAfter(baseline);
  }
}

TaskCompletionNotificationEvent? _eventFromStreamLine(String line) {
  final trimmed = line.trim();
  if (trimmed.isEmpty || trimmed.startsWith(':')) {
    return null;
  }
  if (trimmed.startsWith('id:') ||
      trimmed.startsWith('event:') ||
      trimmed.startsWith('retry:')) {
    return null;
  }
  final payload =
      trimmed.startsWith('data:')
          ? trimmed.substring('data:'.length).trim()
          : trimmed;
  if (payload.isEmpty || payload == '[DONE]') {
    return null;
  }
  final decoded = jsonDecode(payload);
  if (decoded is Map) {
    return TaskCompletionNotificationEvent.fromJson({
      for (final entry in decoded.entries) entry.key.toString(): entry.value,
    });
  }
  throw const FormatException('notification stream event is not a JSON object');
}

String _requiredText(Object? value, String field) {
  final text = (value ?? '').toString().trim();
  if (text.isEmpty) {
    throw FormatException('notification payload missing text field: $field');
  }
  return text;
}

DateTime _requiredDateTime(Object? value, String field) {
  final parsed = DateTime.tryParse((value ?? '').toString());
  if (parsed == null) {
    throw FormatException(
      'notification payload missing datetime field: $field',
    );
  }
  return parsed.toUtc();
}
