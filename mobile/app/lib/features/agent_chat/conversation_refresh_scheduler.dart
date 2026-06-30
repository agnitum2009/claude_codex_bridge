import 'dart:async';

typedef ConversationRefreshCallback = FutureOr<void> Function(String agentName);
typedef ConversationRefreshIsActive = bool Function(String agentName);
typedef ConversationRefreshTimerFactory =
    Timer Function(Duration delay, void Function() callback);
typedef ConversationRefreshStateChanged = void Function();

Timer _defaultTimerFactory(Duration delay, void Function() callback) {
  return Timer(delay, callback);
}

const defaultConversationRefreshDelays = [
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
];

class ConversationRefreshScheduler {
  ConversationRefreshScheduler({
    required ConversationRefreshCallback onRefresh,
    required ConversationRefreshIsActive isActive,
    ConversationRefreshStateChanged? onStateChanged,
    ConversationRefreshTimerFactory timerFactory = _defaultTimerFactory,
    List<Duration> delays = defaultConversationRefreshDelays,
  }) : _onRefresh = onRefresh,
       _isActive = isActive,
       _onStateChanged = onStateChanged,
       _timerFactory = timerFactory,
       _delays = List.unmodifiable(delays);

  final ConversationRefreshCallback _onRefresh;
  final ConversationRefreshIsActive _isActive;
  final ConversationRefreshStateChanged? _onStateChanged;
  final ConversationRefreshTimerFactory _timerFactory;
  final List<Duration> _delays;
  final List<Timer> _timers = [];
  String? _pendingAgentName;
  var _pendingRefreshCount = 0;

  bool isPending(String agentName) {
    return _pendingAgentName == agentName && _pendingRefreshCount > 0;
  }

  void schedule(String agentName) {
    _cancelAll(notify: false);
    if (_delays.isEmpty) {
      return;
    }
    _pendingAgentName = agentName;
    _pendingRefreshCount = _delays.length;
    _notifyStateChanged();
    for (final delay in _delays) {
      _timers.add(
        _timerFactory(delay, () {
          if (!_isActive(agentName)) {
            _markRefreshComplete(agentName);
            return;
          }
          unawaited(
            Future.sync(
              () => _onRefresh(agentName),
            ).whenComplete(() => _markRefreshComplete(agentName)),
          );
        }),
      );
    }
  }

  void cancelAll({bool notify = true}) {
    _cancelAll(notify: notify);
  }

  void _cancelAll({bool notify = true}) {
    final hadPending = _pendingRefreshCount > 0;
    for (final timer in _timers) {
      timer.cancel();
    }
    _timers.clear();
    _pendingAgentName = null;
    _pendingRefreshCount = 0;
    if (notify && hadPending) {
      _notifyStateChanged();
    }
  }

  void _markRefreshComplete(String agentName) {
    if (_pendingAgentName != agentName || _pendingRefreshCount <= 0) {
      return;
    }
    _pendingRefreshCount -= 1;
    if (_pendingRefreshCount == 0) {
      _pendingAgentName = null;
    }
    _notifyStateChanged();
  }

  void _notifyStateChanged() {
    _onStateChanged?.call();
  }
}
