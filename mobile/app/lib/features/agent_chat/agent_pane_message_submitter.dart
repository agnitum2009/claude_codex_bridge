import 'dart:async';

import '../../models/ccb_agent.dart';
import '../../models/ccb_conversation_item.dart';
import '../../models/ccb_project_view.dart';
import '../../transport/terminal_transport.dart';
import 'agent_chat_state_helpers.dart';
import 'agent_conversation_loader.dart';
import 'pane_chat_controller.dart';

typedef PaneChatEventSink = void Function(PaneChatEvent event);

class AgentPaneMessageSubmitter {
  AgentPaneMessageSubmitter({required PaneChatEventSink onEvent})
    : _onEvent = onEvent;

  final PaneChatEventSink _onEvent;
  PaneChatController? _controller;
  StreamSubscription<PaneChatEvent>? _events;

  Future<AgentPaneMessageSubmitOutcome> submit({
    required TerminalTransport? transport,
    required CcbAgent agent,
    required CcbConversationItem message,
    required CcbProjectView view,
    required AgentViewRefresh? refreshView,
    String? paneBody,
    bool allowStaleRefresh = true,
  }) async {
    try {
      final readyTransport = transport;
      if (readyTransport == null) {
        throw const TerminalTransportException(
          'selected-agent terminal transport is not ready',
        );
      }
      await _controllerFor(
        readyTransport,
      ).send(agent: agent, view: view, body: paneBody ?? message.body);
      return AgentPaneMessageSubmitOutcome.sent(
        message.copyWith(state: CcbConversationDeliveryState.sent),
        terminalHistoryView: view,
      );
    } catch (error) {
      if (allowStaleRefresh &&
          !paneInputMayHaveReachedPane(error) &&
          isStaleNamespaceEpochError(error)) {
        final refreshed = await refreshView?.call();
        if (refreshed != null && refreshed.agentByName(agent.name) != null) {
          return submit(
            transport: transport,
            agent: agent,
            message: message,
            view: refreshed,
            refreshView: refreshView,
            paneBody: paneBody,
            allowStaleRefresh: false,
          );
        }
      }
      return AgentPaneMessageSubmitOutcome.replaceLocalMessage(
        message.copyWith(state: paneFailureDeliveryState(error)),
      );
    }
  }

  Future<AgentPaneKeySubmitOutcome> sendKey({
    required TerminalTransport? transport,
    required CcbAgent agent,
    required CcbProjectView view,
    required AgentViewRefresh? refreshView,
    required List<int> bytes,
    bool allowStaleRefresh = true,
  }) async {
    try {
      final readyTransport = transport;
      if (readyTransport == null) {
        throw const TerminalTransportException(
          'selected-agent terminal transport is not ready',
        );
      }
      await _controllerFor(
        readyTransport,
      ).sendKey(agent: agent, view: view, bytes: bytes);
      return const AgentPaneKeySubmitOutcome.sent();
    } catch (error) {
      if (allowStaleRefresh &&
          !paneInputMayHaveReachedPane(error) &&
          isStaleNamespaceEpochError(error)) {
        final refreshed = await refreshView?.call();
        if (refreshed != null && refreshed.agentByName(agent.name) != null) {
          return sendKey(
            transport: transport,
            agent: agent,
            view: refreshed,
            refreshView: refreshView,
            bytes: bytes,
            allowStaleRefresh: false,
          );
        }
      }
      return AgentPaneKeySubmitOutcome.failed(error);
    }
  }

  Future<AgentPaneKeySubmitOutcome> sendTextThenKey({
    required TerminalTransport? transport,
    required CcbAgent agent,
    required CcbProjectView view,
    required AgentViewRefresh? refreshView,
    required String body,
    required List<int> bytes,
    bool allowStaleRefresh = true,
  }) async {
    try {
      final readyTransport = transport;
      if (readyTransport == null) {
        throw const TerminalTransportException(
          'selected-agent terminal transport is not ready',
        );
      }
      await _controllerFor(
        readyTransport,
      ).sendTextThenKey(agent: agent, view: view, body: body, bytes: bytes);
      return const AgentPaneKeySubmitOutcome.sent();
    } catch (error) {
      if (allowStaleRefresh &&
          !paneInputMayHaveReachedPane(error) &&
          isStaleNamespaceEpochError(error)) {
        final refreshed = await refreshView?.call();
        if (refreshed != null && refreshed.agentByName(agent.name) != null) {
          return sendTextThenKey(
            transport: transport,
            agent: agent,
            view: refreshed,
            refreshView: refreshView,
            body: body,
            bytes: bytes,
            allowStaleRefresh: false,
          );
        }
      }
      return AgentPaneKeySubmitOutcome.failed(error);
    }
  }

  Future<void> closeSessions() async {
    final events = _events;
    _events = null;
    if (events != null) {
      await events.cancel();
    }
    final controller = _controller;
    _controller = null;
    if (controller != null) {
      await controller.dispose();
    }
  }

  PaneChatController _controllerFor(TerminalTransport transport) {
    final existing = _controller;
    if (existing != null) {
      return existing;
    }
    final controller = PaneChatController(transport: transport);
    _controller = controller;
    _events = controller.events.listen(_onEvent);
    return controller;
  }
}

class AgentPaneKeySubmitOutcome {
  const AgentPaneKeySubmitOutcome._({required this.sent, this.error});

  const AgentPaneKeySubmitOutcome.sent() : this._(sent: true);

  const AgentPaneKeySubmitOutcome.failed(Object error)
    : this._(sent: false, error: error);

  final bool sent;
  final Object? error;
}

class AgentPaneMessageSubmitOutcome {
  const AgentPaneMessageSubmitOutcome._({
    required this.replacement,
    this.terminalHistoryView,
  });

  factory AgentPaneMessageSubmitOutcome.sent(
    CcbConversationItem replacement, {
    required CcbProjectView terminalHistoryView,
  }) {
    return AgentPaneMessageSubmitOutcome._(
      replacement: replacement,
      terminalHistoryView: terminalHistoryView,
    );
  }

  factory AgentPaneMessageSubmitOutcome.replaceLocalMessage(
    CcbConversationItem replacement,
  ) {
    return AgentPaneMessageSubmitOutcome._(replacement: replacement);
  }

  final CcbConversationItem replacement;
  final CcbProjectView? terminalHistoryView;

  bool get shouldRefreshTerminalHistory => terminalHistoryView != null;
}
