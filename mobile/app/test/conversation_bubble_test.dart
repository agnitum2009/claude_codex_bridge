import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:ccb_mobile/features/agent_chat/conversation_bubble.dart';
import 'package:ccb_mobile/features/agent_chat/agent_chat_state_helpers.dart';
import 'package:ccb_mobile/features/agent_chat/conversation_item_presentation.dart';
import 'package:ccb_mobile/models/ccb_conversation_item.dart';

void main() {
  test('preview text strips common markdown markers', () {
    final preview = conversationPreviewText('''
# Heading
- first item
1. second item
> quoted value
''');

    expect(preview, 'Heading\nfirst item\nsecond item');
  });

  test('terminal derived items stay plain and compact', () {
    final item = CcbConversationItem(
      id: 'terminal-output',
      agentName: 'lead',
      kind: CcbConversationItemKind.agentReply,
      title: 'Terminal output',
      body: '# Not authoritative markdown',
      format: 'markdown',
      source: 'tmux output / foreground',
    );

    expect(isTerminalDerivedConversationItem(item), isTrue);
    expect(shouldRenderConversationMarkdown(item), isFalse);
    expect(conversationPreviewTextFor(item), '# Not authoritative markdown');
    expect(conversationPreviewMaxLines(item), 2);
    expect(conversationShouldCollapse(item, hasCustomChild: false), isTrue);
  });

  test('normal chat replies render markdown when marked as markdown', () {
    final item = CcbConversationItem(
      id: 'reply',
      agentName: 'lead',
      kind: CcbConversationItemKind.agentReply,
      title: 'Agent reply',
      body: '# Markdown reply',
      format: 'markdown',
      source: 'completion_snapshot',
    );

    expect(shouldRenderConversationMarkdown(item), isTrue);
    expect(conversationShouldCollapse(item, hasCustomChild: true), isTrue);
    expect(visibleConversationSourceLabel(item), isNull);
  });

  test('internal source labels stay hidden in chat bubbles', () {
    final terminalItem = CcbConversationItem(
      id: 'terminal-output',
      agentName: 'lead',
      kind: CcbConversationItemKind.agentReply,
      title: 'Terminal output',
      body: 'output',
      source: 'tmux output / live',
    );
    const userItem = CcbConversationItem(
      id: 'user-1',
      agentName: 'lead',
      kind: CcbConversationItemKind.userMessage,
      title: 'You',
      body: 'hello',
      source: 'mobile_gateway',
    );

    expect(visibleConversationSourceLabel(terminalItem), isNull);
    expect(visibleConversationSourceLabel(userItem), isNull);
  });

  test('terminal preview preserves literal underscores', () {
    const item = CcbConversationItem(
      id: 'terminal-output',
      agentName: 'lead',
      kind: CcbConversationItemKind.agentReply,
      title: 'Terminal output',
      body: 'MOBILE_DYNAMIC_SYNC_OK',
      source: 'tmux output / live',
    );

    expect(conversationPreviewTextFor(item), 'MOBILE_DYNAMIC_SYNC_OK');
  });

  testWidgets('normal chat bubbles do not render internal source labels', (
    tester,
  ) async {
    final item = CcbConversationItem(
      id: 'reply',
      agentName: 'lead',
      kind: CcbConversationItemKind.agentReply,
      title: 'Agent reply',
      body: 'hello',
      source: 'completion_snapshot',
    );

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ConversationBubble(
            item: item,
            expanded: true,
            onToggleExpanded: (_) {},
          ),
        ),
      ),
    );

    expect(find.text('completion_snapshot'), findsNothing);
    expect(find.text('hello'), findsOneWidget);
  });

  testWidgets('sent user messages omit redundant state chip', (tester) async {
    const item = CcbConversationItem(
      id: 'user-1',
      agentName: 'lead',
      kind: CcbConversationItemKind.userMessage,
      title: 'You',
      body: 'hello',
      state: CcbConversationDeliveryState.sent,
    );

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ConversationBubble(
            item: item,
            expanded: true,
            onToggleExpanded: (_) {},
          ),
        ),
      ),
    );

    expect(find.text('hello'), findsOneWidget);
    expect(
      find.byKey(const ValueKey('conversation-state-user-1')),
      findsNothing,
    );
    expect(find.text('Sent'), findsNothing);
  });

  testWidgets('failed user messages keep actionable state chip', (
    tester,
  ) async {
    const item = CcbConversationItem(
      id: 'user-1',
      agentName: 'lead',
      kind: CcbConversationItemKind.userMessage,
      title: 'You',
      body: 'hello',
      state: CcbConversationDeliveryState.failed,
    );

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ConversationBubble(
            item: item,
            expanded: true,
            onToggleExpanded: (_) {},
          ),
        ),
      ),
    );

    expect(
      find.descendant(
        of: find.byKey(const ValueKey('conversation-state-user-1')),
        matching: find.text('Failed'),
      ),
      findsOneWidget,
    );
  });

  testWidgets('expanded long bubbles are height limited and scrollable', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(400, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final item = CcbConversationItem(
      id: 'long-reply',
      agentName: 'lead',
      kind: CcbConversationItemKind.agentReply,
      title: 'Agent reply',
      body: List.generate(80, (index) => 'line $index').join('\n'),
      source: 'completion_snapshot',
    );

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ConversationBubble(
            item: item,
            expanded: true,
            onToggleExpanded: (_) {},
          ),
        ),
      ),
    );

    final viewportFinder = find.byKey(
      const ValueKey('conversation-body-viewport-long-reply'),
    );
    expect(viewportFinder, findsOneWidget);
    expect(
      tester.getSize(viewportFinder).height,
      conversationBodyViewportMaxHeight(const Size(400, 800)),
    );
    expect(find.byType(Scrollbar), findsOneWidget);
  });

  testWidgets('expanded bubble scrolling does not notify parent timeline', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(400, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final item = CcbConversationItem(
      id: 'long-reply',
      agentName: 'lead',
      kind: CcbConversationItemKind.agentReply,
      title: 'Agent reply',
      body: List.generate(80, (index) => 'line $index').join('\n'),
      source: 'completion_snapshot',
    );
    var parentScrollNotifications = 0;

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: NotificationListener<ScrollNotification>(
            onNotification: (_) {
              parentScrollNotifications += 1;
              return false;
            },
            child: ConversationBubble(
              item: item,
              expanded: true,
              onToggleExpanded: (_) {},
            ),
          ),
        ),
      ),
    );

    await tester.drag(
      find.byKey(const ValueKey('conversation-body-viewport-long-reply')),
      const Offset(0, -500),
    );
    await tester.pumpAndSettle();

    expect(parentScrollNotifications, 0);
  });

  test('unconfirmed pane sends use check pane label', () {
    expect(
      conversationStateLabel(CcbConversationDeliveryState.unconfirmed),
      'Check pane',
    );
  });

  testWidgets('conversation attachments expose download and progress states', (
    tester,
  ) async {
    final item = CcbConversationItem(
      id: 'msg-1',
      agentName: 'mobile',
      kind: CcbConversationItemKind.agentReply,
      title: 'Agent reply',
      body: 'See files',
      attachments: const [
        CcbMessageAttachment(
          fileId: 'file-1',
          fileName: 'notes.txt',
          mimeType: 'text/plain',
          sizeBytes: 2048,
        ),
        CcbMessageAttachment(
          fileId: 'file-2',
          fileName: 'image.png',
          mimeType: 'image/png',
          sizeBytes: 4096,
        ),
      ],
    );
    final downloads = <String>[];

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ConversationBubble(
            item: item,
            expanded: true,
            onToggleExpanded: (_) {},
            downloadingAttachmentIds: const {'file-2'},
            onDownloadAttachment: (attachment) {
              downloads.add(attachment.fileId);
            },
          ),
        ),
      ),
    );

    expect(
      find.byKey(const ValueKey('conversation-attachment-list-msg-1')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('conversation-attachment-chip-file-1')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('conversation-attachment-download-file-1')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('agent-attachment-progress-file-2')),
      findsOneWidget,
    );

    await tester.tap(
      find.byKey(const ValueKey('conversation-attachment-chip-file-1')),
    );
    await tester.pump(const Duration(milliseconds: 300));

    expect(downloads, isEmpty);
    expect(
      find.byKey(const ValueKey('conversation-attachment-actions-file-1')),
      findsOneWidget,
    );
    tester
        .widget<ListTile>(
          find.byKey(
            const ValueKey('conversation-attachment-action-download-file-1'),
          ),
        )
        .onTap!();
    await tester.pump();
    expect(downloads, ['file-1']);
  });

  testWidgets('conversation attachment tap can open through action sheet', (
    tester,
  ) async {
    final item = CcbConversationItem(
      id: 'msg-actions-tap',
      agentName: 'mobile',
      kind: CcbConversationItemKind.agentReply,
      title: 'Agent reply',
      body: 'See files',
      attachments: const [
        CcbMessageAttachment(
          fileId: 'file-1',
          fileName: 'notes.txt',
          mimeType: 'text/plain',
          sizeBytes: 2048,
        ),
      ],
    );
    final downloads = <String>[];
    final opens = <String>[];

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ConversationBubble(
            item: item,
            expanded: true,
            onToggleExpanded: (_) {},
            onDownloadAttachment: (attachment) {
              downloads.add(attachment.fileId);
            },
            onOpenAttachment: (attachment) {
              opens.add(attachment.fileId);
            },
          ),
        ),
      ),
    );

    await tester.tap(
      find.byKey(const ValueKey('conversation-attachment-chip-file-1')),
    );
    await tester.pumpAndSettle();

    expect(downloads, isEmpty);
    expect(opens, isEmpty);
    expect(
      find.byKey(const ValueKey('conversation-attachment-actions-file-1')),
      findsOneWidget,
    );
    await tester.tap(
      find.byKey(const ValueKey('conversation-attachment-action-open-file-1')),
    );
    await tester.pumpAndSettle();

    expect(downloads, isEmpty);
    expect(opens, ['file-1']);
  });

  testWidgets('conversation attachments expose long-press download and open', (
    tester,
  ) async {
    final item = CcbConversationItem(
      id: 'msg-actions',
      agentName: 'mobile',
      kind: CcbConversationItemKind.agentReply,
      title: 'Agent reply',
      body: 'See files',
      attachments: const [
        CcbMessageAttachment(
          fileId: 'file-1',
          fileName: 'notes.txt',
          mimeType: 'text/plain',
          sizeBytes: 2048,
        ),
      ],
    );
    final downloads = <String>[];
    final opens = <String>[];

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ConversationBubble(
            item: item,
            expanded: true,
            onToggleExpanded: (_) {},
            onDownloadAttachment: (attachment) {
              downloads.add(attachment.fileId);
            },
            onOpenAttachment: (attachment) {
              opens.add(attachment.fileId);
            },
          ),
        ),
      ),
    );

    await tester.longPress(
      find.byKey(const ValueKey('conversation-attachment-chip-file-1')),
    );
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey('conversation-attachment-actions-file-1')),
      findsOneWidget,
    );
    await tester.tap(
      find.byKey(
        const ValueKey('conversation-attachment-action-download-file-1'),
      ),
    );
    await tester.pumpAndSettle();
    expect(downloads, ['file-1']);
    expect(opens, isEmpty);

    await tester.longPress(
      find.byKey(const ValueKey('conversation-attachment-chip-file-1')),
    );
    await tester.pumpAndSettle();
    await tester.tap(
      find.byKey(const ValueKey('conversation-attachment-action-open-file-1')),
    );
    await tester.pumpAndSettle();
    expect(opens, ['file-1']);
  });

  testWidgets('artifact markdown links show attachment actions', (
    tester,
  ) async {
    final item = CcbConversationItem(
      id: 'artifact-reply',
      agentName: 'mobile',
      kind: CcbConversationItemKind.agentReply,
      title: 'Agent reply',
      body: '[Download artifact](ccb-artifact://artifact-1)',
      format: 'markdown',
      source: 'completion_snapshot',
      attachments: const [
        CcbMessageAttachment(
          fileId: 'artifact-1',
          fileName: 'artifact.txt',
          mimeType: 'text/plain',
          sizeBytes: 32,
        ),
      ],
    );
    CcbMessageAttachment? downloaded;
    CcbMessageAttachment? opened;

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ConversationBubble(
            item: item,
            expanded: true,
            onToggleExpanded: (_) {},
            onDownloadAttachment: (attachment) {
              downloaded = attachment;
            },
            onOpenAttachment: (attachment) {
              opened = attachment;
            },
          ),
        ),
      ),
    );

    await tester.tap(
      find.byKey(const ValueKey('markdown-body-conversation-artifact-reply')),
    );
    await tester.pumpAndSettle();

    expect(downloaded, isNull);
    expect(opened, isNull);
    expect(
      find.byKey(const ValueKey('conversation-attachment-actions-artifact-1')),
      findsOneWidget,
    );
    expect(find.text('Blocked link'), findsNothing);

    await tester.tap(
      find.byKey(
        const ValueKey('conversation-attachment-action-download-artifact-1'),
      ),
    );
    await tester.pumpAndSettle();

    expect(downloaded?.fileId, 'artifact-1');
    expect(downloaded?.fileName, 'artifact.txt');

    await tester.tap(
      find.byKey(const ValueKey('markdown-body-conversation-artifact-reply')),
    );
    await tester.pumpAndSettle();
    await tester.tap(
      find.byKey(
        const ValueKey('conversation-attachment-action-open-artifact-1'),
      ),
    );
    await tester.pumpAndSettle();

    expect(opened?.fileId, 'artifact-1');
  });

  testWidgets('http markdown links ask before opening externally', (
    tester,
  ) async {
    const channel = MethodChannel('io.ccb.mobile/external_url');
    final opened = <String>[];
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(channel, (
      call,
    ) async {
      if (call.method == 'openUrl') {
        opened.add((call.arguments as Map)['url'] as String);
        return true;
      }
      return false;
    });
    addTearDown(() {
      tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        channel,
        null,
      );
    });

    final item = CcbConversationItem(
      id: 'link-reply',
      agentName: 'mobile',
      kind: CcbConversationItemKind.agentReply,
      title: 'Agent reply',
      body: '[Open site](https://example.com/report)',
      format: 'markdown',
      source: 'completion_snapshot',
    );

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ConversationBubble(
            item: item,
            expanded: true,
            onToggleExpanded: (_) {},
          ),
        ),
      ),
    );

    await tester.tap(find.text('Open site'));
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey('open-url-confirm-action')),
      findsOneWidget,
    );
    expect(opened, isEmpty);

    await tester.tap(find.byKey(const ValueKey('open-url-confirm-action')));
    await tester.pumpAndSettle();

    expect(opened, ['https://example.com/report']);
  });
}
