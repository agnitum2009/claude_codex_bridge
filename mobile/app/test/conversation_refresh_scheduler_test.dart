import 'dart:async';

import 'package:ccb_mobile/features/agent_chat/conversation_refresh_scheduler.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('default delays start within active-send latency budget', () {
    expect(defaultConversationRefreshDelays, const [
      Duration(milliseconds: 100),
      Duration(milliseconds: 250),
      Duration(milliseconds: 500),
      Duration(seconds: 1),
      Duration(seconds: 2),
      Duration(seconds: 3),
      Duration(seconds: 5),
      Duration(seconds: 8),
      Duration(seconds: 13),
      Duration(seconds: 21),
      Duration(seconds: 34),
      Duration(seconds: 55),
      Duration(seconds: 90),
      Duration(seconds: 180),
      Duration(seconds: 300),
      Duration(seconds: 600),
      Duration(seconds: 900),
    ]);
    expect(
      defaultConversationRefreshDelays.first,
      lessThanOrEqualTo(const Duration(milliseconds: 100)),
    );
  });

  test('does not arm refresh timers until explicitly scheduled', () {
    final timers = <_FakeTimer>[];
    ConversationRefreshScheduler(
      isActive: (_) => true,
      onRefresh: (_) {},
      timerFactory: (delay, callback) {
        final timer = _FakeTimer(delay: delay, callback: callback);
        timers.add(timer);
        return timer;
      },
    );

    expect(timers, isEmpty);
  });

  test(
    'schedules the configured refresh delays for the active agent',
    () async {
      final timers = <_FakeTimer>[];
      final refreshedAgents = <String>[];
      var stateChanges = 0;
      final scheduler = ConversationRefreshScheduler(
        isActive: (agentName) => agentName == 'mobile_probe',
        onRefresh: refreshedAgents.add,
        onStateChanged: () {
          stateChanges += 1;
        },
        delays: const [Duration(milliseconds: 10), Duration(milliseconds: 20)],
        timerFactory: (delay, callback) {
          final timer = _FakeTimer(delay: delay, callback: callback);
          timers.add(timer);
          return timer;
        },
      );

      scheduler.schedule('mobile_probe');

      expect(scheduler.isPending('mobile_probe'), isTrue);
      expect(stateChanges, 1);
      expect(timers.map((timer) => timer.delay), const [
        Duration(milliseconds: 10),
        Duration(milliseconds: 20),
      ]);

      timers[0].fire();
      timers[1].fire();
      await pumpEventQueue();

      expect(refreshedAgents, const ['mobile_probe', 'mobile_probe']);
      expect(scheduler.isPending('mobile_probe'), isFalse);
      expect(stateChanges, 3);
    },
  );

  test('skips refresh when the scheduled agent is no longer active', () {
    final timers = <_FakeTimer>[];
    final refreshedAgents = <String>[];
    final scheduler = ConversationRefreshScheduler(
      isActive: (_) => false,
      onRefresh: refreshedAgents.add,
      delays: const [Duration(milliseconds: 10)],
      timerFactory: (delay, callback) {
        final timer = _FakeTimer(delay: delay, callback: callback);
        timers.add(timer);
        return timer;
      },
    );

    scheduler.schedule('mobile_probe');
    timers.single.fire();

    expect(refreshedAgents, isEmpty);
  });

  test('cancelAll cancels pending refresh timers', () {
    final timers = <_FakeTimer>[];
    final refreshedAgents = <String>[];
    final scheduler = ConversationRefreshScheduler(
      isActive: (_) => true,
      onRefresh: refreshedAgents.add,
      delays: const [Duration(milliseconds: 10), Duration(milliseconds: 20)],
      timerFactory: (delay, callback) {
        final timer = _FakeTimer(delay: delay, callback: callback);
        timers.add(timer);
        return timer;
      },
    );

    scheduler.schedule('mobile_probe');
    scheduler.cancelAll();

    expect(timers.every((timer) => !timer.isActive), isTrue);

    for (final timer in timers) {
      timer.fire();
    }

    expect(refreshedAgents, isEmpty);
  });

  test('rescheduling cancels older pending refresh timers', () {
    final timers = <_FakeTimer>[];
    final refreshedAgents = <String>[];
    final scheduler = ConversationRefreshScheduler(
      isActive: (_) => true,
      onRefresh: refreshedAgents.add,
      delays: const [Duration(milliseconds: 10), Duration(milliseconds: 20)],
      timerFactory: (delay, callback) {
        final timer = _FakeTimer(delay: delay, callback: callback);
        timers.add(timer);
        return timer;
      },
    );

    scheduler.schedule('mobile_probe');
    final firstBatch = List<_FakeTimer>.of(timers);
    scheduler.schedule('lead');

    expect(firstBatch.every((timer) => !timer.isActive), isTrue);
    expect(timers.skip(2).map((timer) => timer.delay), const [
      Duration(milliseconds: 10),
      Duration(milliseconds: 20),
    ]);

    for (final timer in firstBatch) {
      timer.fire();
    }
    for (final timer in timers.skip(2)) {
      timer.fire();
    }

    expect(refreshedAgents, const ['lead', 'lead']);
  });
}

class _FakeTimer implements Timer {
  _FakeTimer({required this.delay, required this.callback});

  final Duration delay;
  final void Function() callback;
  var _isActive = true;

  @override
  bool get isActive => _isActive;

  @override
  int get tick => 0;

  @override
  void cancel() {
    _isActive = false;
  }

  void fire() {
    if (!_isActive) {
      return;
    }
    _isActive = false;
    callback();
  }
}
