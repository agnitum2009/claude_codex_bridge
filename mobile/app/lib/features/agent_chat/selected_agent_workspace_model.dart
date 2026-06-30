import '../../models/ccb_agent.dart';
import '../../models/ccb_content_item.dart';
import '../../models/ccb_conversation_item.dart';
import '../../models/ccb_project_view.dart';
import '../../models/readable_terminal_history.dart';
import 'agent_chat_controller.dart';
import 'agent_chat_timeline_items.dart';

class SelectedAgentWorkspaceModel {
  const SelectedAgentWorkspaceModel({
    required this.agent,
    required this.contentItems,
    required this.initialHistory,
    required this.timelineItems,
    required this.commsItems,
    required this.isLoadingConversation,
    required this.hasOlderConversation,
    required this.expandedItemIds,
    required this.hasNewMessages,
    required this.isSending,
    required this.isAwaitingAgentResponse,
    required this.isComposerCollapsed,
    required this.executionStatus,
  });

  final CcbAgent agent;
  final List<CcbContentItem> contentItems;
  final ReadableTerminalHistory? initialHistory;
  final List<CcbConversationItem> timelineItems;
  final List<CcbConversationItem> commsItems;
  final bool isLoadingConversation;
  final bool hasOlderConversation;
  final Set<String> expandedItemIds;
  final bool hasNewMessages;
  final bool isSending;
  final bool isAwaitingAgentResponse;
  final bool isComposerCollapsed;
  final AgentExecutionStatus? executionStatus;
}

class AgentExecutionStatus {
  const AgentExecutionStatus({
    required this.label,
    required this.state,
    required this.isRefreshing,
  });

  final String label;
  final String state;
  final bool isRefreshing;
}

SelectedAgentWorkspaceModel selectedAgentWorkspaceModel({
  required CcbProjectView view,
  required CcbAgent agent,
  required AgentChatController chatController,
  required bool isAwaitingAgentResponse,
  bool hasLocalExecutionException = false,
}) {
  final contentItems = view.contentForAgent(agent.name);
  final refreshedTerminalHistory = chatController.refreshedTerminalHistoryFor(
    agent.name,
  );
  final terminalHistory =
      refreshedTerminalHistory ?? view.terminalHistoryForAgent(agent.name);
  final remoteConversation = chatController.remoteConversationFor(agent.name);
  final isLoadingConversation = chatController.isLoadingConversation(
    agent.name,
  );
  final allTimelineItems = selectedAgentTimelineItems(
    view: view,
    agent: agent,
    contentItems: contentItems,
    terminalHistory: terminalHistory,
    remoteConversation: remoteConversation,
    localMessages: chatController.localMessagesFor(agent.name),
    preferSupplementalTerminalHistoryAtEnd: refreshedTerminalHistory != null,
    isLoadingConversation: isLoadingConversation,
  );
  return SelectedAgentWorkspaceModel(
    agent: agent,
    contentItems: contentItems,
    initialHistory: terminalHistory,
    timelineItems: [
      for (final item in allTimelineItems)
        if (item.kind != CcbConversationItemKind.commsItem) item,
    ],
    commsItems: [
      for (final item in allTimelineItems)
        if (item.kind == CcbConversationItemKind.commsItem) item,
    ],
    isLoadingConversation: isLoadingConversation,
    hasOlderConversation: chatController.hasOlderConversation(agent.name),
    expandedItemIds: chatController.expandedItemIds(agent.name),
    hasNewMessages: chatController.hasNewMessages(agent.name),
    isSending: chatController.isSubmitting(agent.name),
    isAwaitingAgentResponse: isAwaitingAgentResponse,
    isComposerCollapsed: chatController.isComposerCollapsed(agent.name),
    executionStatus: agentExecutionStatus(
      agent: agent,
      isAwaitingAgentResponse: isAwaitingAgentResponse,
      isLoadingConversation: isLoadingConversation,
      hasLocalExecutionException: hasLocalExecutionException,
    ),
  );
}

AgentExecutionStatus? agentExecutionStatus({
  required CcbAgent agent,
  required bool isAwaitingAgentResponse,
  required bool isLoadingConversation,
  bool hasLocalExecutionException = false,
}) {
  if (hasLocalExecutionException) {
    return const AgentExecutionStatus(
      label: 'Exception',
      state: 'exception',
      isRefreshing: false,
    );
  }

  final state = _normalized(agent.activityState);
  final source = _normalized(agent.activitySource);
  final reason = _normalized(agent.activityReason);
  if (_isExceptionActivity(state: state, source: source, reason: reason)) {
    return const AgentExecutionStatus(
      label: 'Exception',
      state: 'exception',
      isRefreshing: false,
    );
  }
  if (isAwaitingAgentResponse) {
    return const AgentExecutionStatus(
      label: 'Working',
      state: 'working',
      isRefreshing: false,
    );
  }
  if (isLoadingConversation) {
    return const AgentExecutionStatus(
      label: 'Working',
      state: 'working',
      isRefreshing: true,
    );
  }
  if (_isIdleActivity(state)) {
    return const AgentExecutionStatus(
      label: 'Idle',
      state: 'idle',
      isRefreshing: false,
    );
  }
  if (_isWorkingActivity(
    state: state,
    source: source,
    reason: reason,
    queueDepth: agent.queueDepth,
  )) {
    return AgentExecutionStatus(
      label: 'Working',
      state: 'working',
      isRefreshing: state == 'pending',
    );
  }
  return const AgentExecutionStatus(
    label: 'Idle',
    state: 'idle',
    isRefreshing: false,
  );
}

bool _isIdleActivity(String? state) {
  return const {
    'idle',
    'free',
    'completed',
    'complete',
    'done',
  }.contains(state);
}

bool _isExceptionActivity({
  required String? state,
  required String? source,
  required String? reason,
}) {
  if (const {
    'failed',
    'failure',
    'error',
    'faulted',
    'offline',
    'crashed',
  }.contains(state)) {
    return true;
  }
  final text = '${source ?? ''} ${reason ?? ''}';
  return text.contains('failed') ||
      text.contains('failure') ||
      text.contains('error') ||
      text.contains('offline') ||
      text.contains('auth') ||
      text.contains('interrupt') ||
      text.contains('cancel') ||
      text.contains('abort') ||
      text.contains('dead') ||
      text.contains('timeout') ||
      text.contains('timed_out') ||
      text.contains('denied');
}

bool _isWorkingActivity({
  required String? state,
  required String? source,
  required String? reason,
  required int queueDepth,
}) {
  if (const {
    'active',
    'busy',
    'pending',
    'running',
    'start',
    'starting',
    'working',
  }.contains(state)) {
    return true;
  }
  final text = '${source ?? ''} ${reason ?? ''}';
  return queueDepth > 0 ||
      text.contains('queued') ||
      text.contains('reconnect') ||
      text.contains('running') ||
      text.contains('start') ||
      text.contains('submitted') ||
      text.contains('tool') ||
      text.contains('waiting') ||
      text.contains('working') ||
      text.contains('prompt');
}

String? _normalized(String? value) {
  final text = value?.trim().toLowerCase();
  return text == null || text.isEmpty ? null : text;
}
