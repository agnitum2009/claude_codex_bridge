import 'package:ccb_mobile/features/agent_chat/agent_chat_controller.dart';
import 'package:ccb_mobile/models/ccb_agent_conversation.dart';
import 'package:ccb_mobile/models/ccb_conversation_item.dart';
import 'package:ccb_mobile/models/readable_terminal_history.dart';
import 'package:test/test.dart';

void main() {
  group('AgentChatController', () {
    test('owns message ids and per-agent transient flags', () {
      final controller = AgentChatController();

      expect(controller.nextLocalMessageId('lead'), 'local-lead-0');
      expect(
        controller.nextTerminalLiveOutputId('lead'),
        'terminal-live-output-lead-1',
      );

      controller.beginLoadingConversation('lead');
      controller.beginSubmitting('lead');
      controller.collapseComposer('lead');
      controller.toggleExpandedItem('lead', 'item-1');

      expect(controller.isLoadingConversation('lead'), isTrue);
      expect(controller.isSubmitting('lead'), isTrue);
      expect(controller.isComposerCollapsed('lead'), isTrue);
      expect(controller.expandedItemIds('lead'), {'item-1'});

      controller.finishLoadingConversation('lead');
      controller.finishSubmitting('lead');
      controller.expandComposer('lead');
      controller.toggleExpandedItem('lead', 'item-1');

      expect(controller.isLoadingConversation('lead'), isFalse);
      expect(controller.isSubmitting('lead'), isFalse);
      expect(controller.isComposerCollapsed('lead'), isFalse);
      expect(controller.expandedItemIds('lead'), isEmpty);
    });

    test('applies remote conversations and prunes covered local messages', () {
      final controller = AgentChatController();
      final pending = _user(id: 'local-pending', body: 'same');
      final failed = _user(
        id: 'local-failed',
        body: 'same',
        state: CcbConversationDeliveryState.failed,
      );
      controller.addLocalMessage('lead', pending);
      controller.addLocalMessage('lead', failed);
      controller.setConversationError('lead', Exception('refresh failed'));

      final update = controller.applyRemoteConversation(
        agentName: 'lead',
        conversation: _conversation([
          _user(
            id: 'remote-user',
            body: 'same',
            state: CcbConversationDeliveryState.sent,
          ),
          _agentReply(id: 'remote-reply', body: 'done'),
        ]),
        shouldScroll: false,
      );

      expect(update.changed, isTrue);
      expect(controller.conversationErrorFor('lead'), isNull);
      expect(controller.remoteConversationFor('lead')!.items, hasLength(2));
      expect(controller.localMessagesFor('lead').map((item) => item.id), [
        'local-failed',
      ]);
      expect(controller.hasNewMessages('lead'), isTrue);

      controller.clearNewMessageFlag('lead');
      final unchanged = controller.applyRemoteConversation(
        agentName: 'lead',
        conversation: _conversation([
          _user(
            id: 'remote-user',
            body: 'same',
            state: CcbConversationDeliveryState.sent,
          ),
          _agentReply(id: 'remote-reply', body: 'done'),
        ]),
        shouldScroll: true,
      );

      expect(unchanged.changed, isFalse);
      expect(controller.hasNewMessages('lead'), isFalse);
    });

    test(
      'keeps local send time when matching remote user message lacks timing',
      () {
        final controller = AgentChatController();
        final sentAt = DateTime.utc(2026, 7, 1, 3, 42);
        final pending = _user(
          id: 'local-pending',
          body: 'same',
          sentAt: sentAt,
        );
        controller.addLocalMessage('lead', pending);

        controller.applyRemoteConversation(
          agentName: 'lead',
          conversation: _conversation([
            _user(
              id: 'remote-user',
              body: 'same',
              state: CcbConversationDeliveryState.sent,
            ),
          ]),
          shouldScroll: true,
        );

        expect(controller.localMessagesFor('lead'), isEmpty);
        expect(
          controller.remoteConversationFor('lead')!.items.single.sentAt,
          sentAt,
        );
      },
    );

    test('prepends older remote page and dedupes overlapping items', () {
      final controller = AgentChatController();
      controller.applyRemoteConversation(
        agentName: 'lead',
        conversation: _conversation([
          _agentReply(id: 'reply-new', body: 'new'),
        ], nextCursor: '2'),
        shouldScroll: true,
      );
      controller.setConversationError('lead', Exception('stale'));

      final update = controller.prependRemoteConversationPage(
        agentName: 'lead',
        conversation: _conversation([
          _agentReply(id: 'reply-old', body: 'old'),
          _agentReply(id: 'reply-new', body: 'new'),
        ]),
      );

      expect(update.changed, isTrue);
      expect(controller.conversationErrorFor('lead'), isNull);
      expect(
        controller.remoteConversationFor('lead')?.items.map((item) => item.id),
        ['reply-old', 'reply-new'],
      );
      expect(controller.hasOlderConversation('lead'), isFalse);
      expect(controller.hasNewMessages('lead'), isFalse);
    });

    test('replaces removes and bulk-updates local messages', () {
      final controller = AgentChatController();
      final first = _user(id: 'local-1', body: 'one');
      final second = _user(id: 'local-2', body: 'two');

      controller.addLocalMessage('lead', first);
      controller.addLocalMessage('lead', second);
      controller.replaceLocalMessage(
        'lead',
        'local-1',
        first.copyWith(state: CcbConversationDeliveryState.sent),
      );
      controller.updateLocalMessages(
        'lead',
        (items) => items.reversed.toList(),
      );

      expect(controller.localMessagesFor('lead').map((item) => item.id), [
        'local-2',
        'local-1',
      ]);
      expect(
        controller.localMessagesFor('lead').last.state,
        CcbConversationDeliveryState.sent,
      );

      controller.removeLocalMessage('lead', 'local-2');
      controller.removeLocalMessage('lead', 'local-1');

      expect(controller.localMessagesFor('lead'), isEmpty);
    });

    test('restores local messages and advances local message ids', () {
      final controller = AgentChatController();
      controller.restoreLocalMessages('lead', [
        _user(id: 'local-lead-4', body: 'retry later'),
      ]);

      expect(controller.localMessagesFor('lead').single.body, 'retry later');
      expect(controller.nextLocalMessageId('lead'), 'local-lead-5');

      controller.restoreLocalMessages('lead', const []);

      expect(controller.localMessagesFor('lead'), isEmpty);
      expect(controller.nextLocalMessageId('lead'), 'local-lead-6');
    });

    test('stores and clears refreshed terminal history', () {
      final controller = AgentChatController();
      const history = ReadableTerminalHistory(
        agentName: 'lead',
        historyScope: 'tmux_scrollback',
        blocks: [
          ReadableTerminalBlock(id: 'cmd', type: 'command', text: 'ccb status'),
        ],
      );

      controller.setRefreshedTerminalHistory('lead', history);

      expect(controller.refreshedTerminalHistoryFor('lead'), same(history));

      controller.clearRefreshedTerminalHistories();

      expect(controller.refreshedTerminalHistoryFor('lead'), isNull);
    });
  });
}

CcbAgentConversation _conversation(
  List<CcbConversationItem> items, {
  String? nextCursor,
}) {
  return CcbAgentConversation(
    projectId: 'proj',
    agentName: 'lead',
    namespaceEpoch: 7,
    items: items,
    nextCursor: nextCursor,
    generatedAt: DateTime.utc(2026, 6, 22),
  );
}

CcbConversationItem _user({
  required String id,
  required String body,
  CcbConversationDeliveryState state = CcbConversationDeliveryState.pending,
  DateTime? sentAt,
}) {
  return CcbConversationItem.userMessage(
    id: id,
    agentName: 'lead',
    body: body,
    state: state,
    sentAt: sentAt,
  );
}

CcbConversationItem _agentReply({required String id, required String body}) {
  return CcbConversationItem(
    id: id,
    agentName: 'lead',
    kind: CcbConversationItemKind.agentReply,
    title: 'Agent reply',
    body: body,
  );
}
