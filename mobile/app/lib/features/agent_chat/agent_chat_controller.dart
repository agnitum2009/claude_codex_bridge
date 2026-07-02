import '../../models/ccb_agent_conversation.dart';
import '../../models/ccb_conversation_item.dart';
import '../../models/readable_terminal_history.dart';
import 'agent_chat_state_helpers.dart';

class AgentChatConversationUpdate {
  const AgentChatConversationUpdate({required this.changed});

  final bool changed;
}

class AgentChatController {
  final Map<String, List<CcbConversationItem>> _localMessages = {};
  final Map<String, CcbAgentConversation> _remoteConversations = {};
  final Map<String, ReadableTerminalHistory> _refreshedTerminalHistories = {};
  final Map<String, String> _conversationErrors = {};
  final Map<String, Set<String>> _expandedConversationItems = {};
  final Set<String> _loadingConversations = {};
  final Set<String> _submittingAgents = {};
  final Set<String> _collapsedComposers = {};
  final Set<String> _agentsWithNewMessages = {};
  var _messageCounter = 0;

  String nextLocalMessageId(String agentName) {
    return 'local-$agentName-${_messageCounter++}';
  }

  String nextTerminalLiveOutputId(String agentName) {
    return 'terminal-live-output-$agentName-${_messageCounter++}';
  }

  CcbAgentConversation? remoteConversationFor(String agentName) {
    return _remoteConversations[agentName];
  }

  List<CcbConversationItem> localMessagesFor(String agentName) {
    return _localMessages[agentName] ?? const <CcbConversationItem>[];
  }

  ReadableTerminalHistory? refreshedTerminalHistoryFor(String agentName) {
    return _refreshedTerminalHistories[agentName];
  }

  String? conversationErrorFor(String agentName) {
    return _conversationErrors[agentName];
  }

  Set<String> expandedItemIds(String agentName) {
    return _expandedConversationItems[agentName] ?? const <String>{};
  }

  bool isLoadingConversation(String agentName) {
    return _loadingConversations.contains(agentName);
  }

  bool isSubmitting(String agentName) {
    return _submittingAgents.contains(agentName);
  }

  bool isComposerCollapsed(String agentName) {
    return _collapsedComposers.contains(agentName);
  }

  bool hasNewMessages(String agentName) {
    return _agentsWithNewMessages.contains(agentName);
  }

  bool hasOlderConversation(String agentName) {
    return _remoteConversations[agentName]?.nextCursor != null;
  }

  String? olderConversationCursor(String agentName) {
    return _remoteConversations[agentName]?.nextCursor;
  }

  void beginLoadingConversation(String agentName) {
    _loadingConversations.add(agentName);
    _conversationErrors.remove(agentName);
  }

  void finishLoadingConversation(String agentName) {
    _loadingConversations.remove(agentName);
  }

  void setConversationError(String agentName, Object error) {
    _conversationErrors[agentName] = error.toString();
  }

  void beginSubmitting(String agentName) {
    _submittingAgents.add(agentName);
  }

  void finishSubmitting(String agentName) {
    _submittingAgents.remove(agentName);
  }

  void collapseComposer(String agentName) {
    _collapsedComposers.add(agentName);
  }

  void expandComposer(String agentName) {
    _collapsedComposers.remove(agentName);
  }

  void toggleExpandedItem(String agentName, String itemId) {
    final expanded = _expandedConversationItems.putIfAbsent(
      agentName,
      () => <String>{},
    );
    if (!expanded.add(itemId)) {
      expanded.remove(itemId);
    }
    if (expanded.isEmpty) {
      _expandedConversationItems.remove(agentName);
    }
  }

  void clearNewMessageFlag(String agentName) {
    _agentsWithNewMessages.remove(agentName);
  }

  void recordTimelineAppendState({
    required String agentName,
    required bool changed,
    required bool shouldScroll,
  }) {
    if (!changed) {
      return;
    }
    if (shouldScroll) {
      _agentsWithNewMessages.remove(agentName);
    } else {
      _agentsWithNewMessages.add(agentName);
    }
  }

  void addLocalMessage(String agentName, CcbConversationItem message) {
    _localMessages.update(
      agentName,
      (items) => [...items, message],
      ifAbsent: () => [message],
    );
    _syncMessageCounter(message.id);
  }

  void restoreLocalMessages(
    String agentName,
    List<CcbConversationItem> messages,
  ) {
    if (messages.isEmpty) {
      _localMessages.remove(agentName);
      return;
    }
    _localMessages[agentName] = List<CcbConversationItem>.unmodifiable(
      messages,
    );
    for (final message in messages) {
      _syncMessageCounter(message.id);
    }
  }

  void updateLocalMessages(
    String agentName,
    List<CcbConversationItem> Function(List<CcbConversationItem> items) update,
  ) {
    final next = update(localMessagesFor(agentName));
    if (next.isEmpty) {
      _localMessages.remove(agentName);
    } else {
      _localMessages[agentName] = next;
    }
  }

  void replaceLocalMessage(
    String agentName,
    String id,
    CcbConversationItem replacement,
  ) {
    updateLocalMessages(agentName, (items) {
      return [for (final item in items) item.id == id ? replacement : item];
    });
  }

  void removeLocalMessage(String agentName, String id) {
    updateLocalMessages(agentName, (items) {
      return [
        for (final item in items)
          if (item.id != id) item,
      ];
    });
  }

  bool setRefreshedTerminalHistory(
    String agentName,
    ReadableTerminalHistory history,
  ) {
    final previousSignature = terminalHistorySignature(
      _refreshedTerminalHistories[agentName],
    );
    final nextSignature = terminalHistorySignature(history);
    if (previousSignature == nextSignature) {
      return false;
    }
    _refreshedTerminalHistories[agentName] = history;
    return true;
  }

  void clearRefreshedTerminalHistories() {
    _refreshedTerminalHistories.clear();
  }

  AgentChatConversationUpdate applyRemoteConversation({
    required String agentName,
    required CcbAgentConversation conversation,
    required bool shouldScroll,
  }) {
    final nextConversation = _conversationWithLocalTimingFallback(
      agentName,
      conversation,
    );
    final previousSignature = conversationSignature(
      _remoteConversations[agentName],
    );
    final nextSignature = conversationSignature(nextConversation);
    final changed = previousSignature != nextSignature;
    _remoteConversations[agentName] = nextConversation;
    _conversationErrors.remove(agentName);
    _pruneLocalMessagesCoveredByRemote(agentName, nextConversation);
    recordTimelineAppendState(
      agentName: agentName,
      changed: changed,
      shouldScroll: shouldScroll,
    );
    return AgentChatConversationUpdate(changed: changed);
  }

  AgentChatConversationUpdate prependRemoteConversationPage({
    required String agentName,
    required CcbAgentConversation conversation,
  }) {
    final previous = _remoteConversations[agentName];
    if (previous == null) {
      return applyRemoteConversation(
        agentName: agentName,
        conversation: conversation,
        shouldScroll: false,
      );
    }
    final previousSignature = conversationSignature(previous);
    final seenIds = <String>{};
    final mergedItems = <CcbConversationItem>[];
    for (final item in [...conversation.items, ...previous.items]) {
      if (seenIds.add(item.id)) {
        mergedItems.add(item);
      }
    }
    final merged = CcbAgentConversation(
      projectId: previous.projectId,
      agentName: previous.agentName,
      namespaceEpoch: previous.namespaceEpoch,
      items: mergedItems,
      nextCursor: conversation.nextCursor,
      generatedAt: previous.generatedAt,
    );
    final next = _conversationWithLocalTimingFallback(agentName, merged);
    final nextSignature = conversationSignature(next);
    _remoteConversations[agentName] = next;
    _conversationErrors.remove(agentName);
    _pruneLocalMessagesCoveredByRemote(agentName, next);
    return AgentChatConversationUpdate(
      changed: previousSignature != nextSignature,
    );
  }

  CcbAgentConversation _conversationWithLocalTimingFallback(
    String agentName,
    CcbAgentConversation conversation,
  ) {
    final localItems = _localMessages[agentName];
    if (localItems == null || localItems.isEmpty) {
      return conversation;
    }
    final localById = <String, CcbConversationItem>{};
    final localByBody = <String, List<CcbConversationItem>>{};
    for (final item in localItems) {
      if (item.kind != CcbConversationItemKind.userMessage ||
          !_hasConversationTiming(item)) {
        continue;
      }
      localById[item.id] = item;
      final bodyKey = messageBodyKey(item.body);
      if (bodyKey.isNotEmpty) {
        localByBody.putIfAbsent(bodyKey, () => []).add(item);
      }
    }
    if (localById.isEmpty && localByBody.isEmpty) {
      return conversation;
    }
    var changed = false;
    final nextItems = <CcbConversationItem>[];
    for (final item in conversation.items) {
      if (item.kind != CcbConversationItemKind.userMessage ||
          _hasConversationTiming(item)) {
        nextItems.add(item);
        continue;
      }
      final idFallback = localById[item.id];
      final fallback =
          idFallback ?? _takeLocalTimingForBody(localByBody, item.body);
      if (fallback == null) {
        nextItems.add(item);
        continue;
      }
      if (idFallback != null) {
        _removeLocalTimingForBody(localByBody, idFallback);
      }
      changed = true;
      nextItems.add(
        item.copyWith(
          sentAt: fallback.sentAt,
          startedAt: fallback.startedAt,
          completedAt: fallback.completedAt,
          durationMs: fallback.durationMs,
        ),
      );
    }
    if (!changed) {
      return conversation;
    }
    return CcbAgentConversation(
      projectId: conversation.projectId,
      agentName: conversation.agentName,
      namespaceEpoch: conversation.namespaceEpoch,
      items: nextItems,
      nextCursor: conversation.nextCursor,
      generatedAt: conversation.generatedAt,
    );
  }

  CcbConversationItem? _takeLocalTimingForBody(
    Map<String, List<CcbConversationItem>> localByBody,
    String body,
  ) {
    final candidates = localByBody[messageBodyKey(body)];
    if (candidates == null || candidates.isEmpty) {
      return null;
    }
    return candidates.removeAt(0);
  }

  void _removeLocalTimingForBody(
    Map<String, List<CcbConversationItem>> localByBody,
    CcbConversationItem item,
  ) {
    final bodyKey = messageBodyKey(item.body);
    final candidates = localByBody[bodyKey];
    if (candidates == null) {
      return;
    }
    candidates.removeWhere((candidate) => candidate.id == item.id);
    if (candidates.isEmpty) {
      localByBody.remove(bodyKey);
    }
  }

  bool _hasConversationTiming(CcbConversationItem item) {
    return item.sentAt != null ||
        item.startedAt != null ||
        item.completedAt != null ||
        item.durationMs != null;
  }

  void _pruneLocalMessagesCoveredByRemote(
    String agentName,
    CcbAgentConversation conversation,
  ) {
    final current = _localMessages[agentName];
    if (current == null || current.isEmpty) {
      return;
    }
    final next = pruneLocalMessagesCoveredByRemote(
      localItems: current,
      remoteConversation: conversation,
    );
    if (next.isEmpty) {
      _localMessages.remove(agentName);
    } else {
      _localMessages[agentName] = next;
    }
  }

  void _syncMessageCounter(String id) {
    final match = RegExp(r'-(\d+)$').firstMatch(id);
    final value = match == null ? null : int.tryParse(match.group(1)!);
    if (value != null && value >= _messageCounter) {
      _messageCounter = value + 1;
    }
  }
}
