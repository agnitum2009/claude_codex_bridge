import '../../models/ccb_agent.dart';
import '../../models/ccb_agent_conversation.dart';
import '../../models/ccb_content_item.dart';
import '../../models/ccb_conversation_item.dart';
import '../../models/ccb_project_view.dart';
import '../../models/readable_terminal_history.dart';
import 'agent_chat_state_helpers.dart';
import 'terminal_history_conversation_items.dart';

List<CcbConversationItem> selectedAgentTimelineItems({
  required CcbProjectView view,
  required CcbAgent agent,
  required List<CcbContentItem> contentItems,
  required ReadableTerminalHistory? terminalHistory,
  required CcbAgentConversation? remoteConversation,
  required List<CcbConversationItem> localMessages,
  bool preferSupplementalTerminalHistoryAtEnd = false,
  bool isLoadingConversation = false,
}) {
  final remoteItems = remoteConversation?.items;
  final hasRemoteTerminalConversation =
      remoteItems?.any(isTerminalDerivedConversationItem) ?? false;
  final hasProviderNativeConversation =
      remoteItems?.any(isProviderNativeConversationItem) ?? false;
  final canSupplementTerminalHistory =
      remoteConversation != null &&
      !hasRemoteTerminalConversation &&
      !hasProviderNativeConversation;
  final supplementalTerminalItems =
      canSupplementTerminalHistory
          ? terminalHistoryConversationItems(
            agentName: agent.name,
            terminalHistory: terminalHistory,
          )
          : const <CcbConversationItem>[];
  return [
    if (remoteItems != null)
      ..._remoteItemsWithSupplementalTerminalHistory(
        remoteItems: remoteItems,
        supplementalTerminalItems: supplementalTerminalItems,
        appendSupplementalTerminalHistory:
            preferSupplementalTerminalHistoryAtEnd,
      ),
    if (remoteConversation == null && !isLoadingConversation)
      ...conversationItemsFor(
        view: view,
        agent: agent,
        contentItems: contentItems,
        terminalHistory: terminalHistory,
      ),
    ...localMessages,
  ];
}

List<CcbConversationItem> _remoteItemsWithSupplementalTerminalHistory({
  required List<CcbConversationItem> remoteItems,
  required List<CcbConversationItem> supplementalTerminalItems,
  required bool appendSupplementalTerminalHistory,
}) {
  if (supplementalTerminalItems.isEmpty) {
    return remoteItems;
  }
  if (appendSupplementalTerminalHistory) {
    return [...remoteItems, ...supplementalTerminalItems];
  }
  final firstUserMessage = remoteItems.indexWhere(
    (item) => item.kind == CcbConversationItemKind.userMessage,
  );
  if (firstUserMessage == -1) {
    return [...remoteItems, ...supplementalTerminalItems];
  }
  return [
    ...remoteItems.take(firstUserMessage),
    ...supplementalTerminalItems,
    ...remoteItems.skip(firstUserMessage),
  ];
}
