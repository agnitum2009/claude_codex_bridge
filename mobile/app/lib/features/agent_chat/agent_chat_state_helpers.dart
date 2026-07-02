import '../../models/ccb_agent_conversation.dart';
import '../../models/ccb_conversation_item.dart';
import '../../models/readable_terminal_history.dart';
import '../../transport/http_gateway_transport.dart';
import 'pane_chat_controller.dart';

String messageBodyKey(String body) => body.trim();

bool paneInputMayHaveReachedPane(Object error) {
  return error is PaneChatSendException && error.inputMayHaveReachedPane;
}

CcbConversationDeliveryState paneFailureDeliveryState(Object error) {
  return paneInputMayHaveReachedPane(error)
      ? CcbConversationDeliveryState.unconfirmed
      : CcbConversationDeliveryState.failed;
}

String conversationSignature(CcbAgentConversation? conversation) {
  final items = conversation?.items;
  if (items == null || items.isEmpty) {
    return '';
  }
  return [
    for (final item in items)
      [
        item.id,
        item.kind.wireName,
        item.state?.wireName ?? '',
        item.sentAt?.toUtc().toIso8601String() ?? '',
        item.startedAt?.toUtc().toIso8601String() ?? '',
        item.completedAt?.toUtc().toIso8601String() ?? '',
        item.durationMs?.toString() ?? '',
        item.body.hashCode,
      ].join(':'),
  ].join('|');
}

String terminalHistorySignature(ReadableTerminalHistory? history) {
  if (history == null || history.blocks.isEmpty) {
    return '';
  }
  return [
    history.agentName,
    history.historyScope,
    history.sourcePaneId ?? '',
    history.stale.toString(),
    for (final block in history.blocks)
      [
        block.id,
        block.type,
        block.title ?? '',
        block.text.hashCode,
        block.language ?? '',
        block.status ?? '',
      ].join(':'),
  ].join('|');
}

bool conversationHasTerminalDerivedItems(CcbAgentConversation? conversation) {
  final items = conversation?.items;
  if (items == null) {
    return false;
  }
  return items.any(isTerminalDerivedConversationItem);
}

bool conversationHasProviderNativeItems(CcbAgentConversation? conversation) {
  final items = conversation?.items;
  if (items == null) {
    return false;
  }
  return items.any(isProviderNativeConversationItem);
}

bool isProviderNativeConversationItem(CcbConversationItem item) {
  return item.source?.startsWith('provider_native/') ?? false;
}

bool isTerminalDerivedConversationItem(CcbConversationItem item) {
  final source = item.source ?? '';
  return source.startsWith('terminal input') ||
      source.startsWith('tmux output') ||
      source.startsWith('tmux scrollback') ||
      source.startsWith('terminal journal') ||
      source.startsWith('current screen');
}

bool isTerminalInputConversationItem(CcbConversationItem item) {
  return item.source?.startsWith('terminal input') ?? false;
}

bool isStaleNamespaceEpochError(Object error) {
  if (error is GatewayHttpException) {
    return error.statusCode == 409 &&
        error.message.contains('stale namespace epoch');
  }
  return error.toString().contains('stale namespace epoch');
}

List<CcbConversationItem> pruneLocalMessagesCoveredByRemote({
  required List<CcbConversationItem> localItems,
  required CcbAgentConversation remoteConversation,
}) {
  if (localItems.isEmpty) {
    return localItems;
  }
  final remoteUserBodyCounts = <String, int>{};
  final remoteUserAttachmentCounts = <String, int>{};
  for (final item in remoteConversation.items) {
    if (item.kind != CcbConversationItemKind.userMessage) {
      continue;
    }
    final key = messageBodyKey(item.body);
    if (key.isNotEmpty) {
      remoteUserBodyCounts.update(key, (value) => value + 1, ifAbsent: () => 1);
    } else {
      final attachKey = _attachmentCoverageKey(item.attachments);
      if (attachKey.isNotEmpty) {
        remoteUserAttachmentCounts.update(
          attachKey,
          (value) => value + 1,
          ifAbsent: () => 1,
        );
      }
    }
  }
  if (remoteUserBodyCounts.isEmpty && remoteUserAttachmentCounts.isEmpty) {
    return localItems;
  }
  final next = <CcbConversationItem>[];
  for (final item in localItems) {
    if (item.state == CcbConversationDeliveryState.failed) {
      next.add(item);
      continue;
    }
    final bodyKey = messageBodyKey(item.body);
    if (bodyKey.isNotEmpty) {
      final coveredCount = remoteUserBodyCounts[bodyKey] ?? 0;
      if (coveredCount <= 0) {
        next.add(item);
      } else {
        remoteUserBodyCounts[bodyKey] = coveredCount - 1;
      }
    } else {
      final attachKey = _attachmentCoverageKey(item.attachments);
      if (attachKey.isNotEmpty) {
        final coveredCount = remoteUserAttachmentCounts[attachKey] ?? 0;
        if (coveredCount <= 0) {
          next.add(item);
        } else {
          remoteUserAttachmentCounts[attachKey] = coveredCount - 1;
        }
      } else {
        next.add(item);
      }
    }
  }
  return next;
}

bool remoteConversationCoversUserMessage({
  required CcbAgentConversation remoteConversation,
  required CcbConversationItem message,
}) {
  if (message.kind != CcbConversationItemKind.userMessage) {
    return false;
  }
  for (final remote in remoteConversation.items) {
    if (remote.kind != CcbConversationItemKind.userMessage) {
      continue;
    }
    if (remote.id == message.id) {
      return true;
    }
    final bodyKey = messageBodyKey(message.body);
    if (bodyKey.isNotEmpty && messageBodyKey(remote.body) == bodyKey) {
      return true;
    }
    final attachmentKey = _attachmentCoverageKey(message.attachments);
    if (bodyKey.isEmpty &&
        attachmentKey.isNotEmpty &&
        _attachmentCoverageKey(remote.attachments) == attachmentKey) {
      return true;
    }
  }
  return false;
}

String _attachmentCoverageKey(List<CcbMessageAttachment> attachments) {
  if (attachments.isEmpty) {
    return '';
  }
  return [
    for (final attachment in attachments)
      [
        attachment.fileName,
        attachment.mimeType,
        attachment.sizeBytes,
      ].join(':'),
  ].join('|');
}
