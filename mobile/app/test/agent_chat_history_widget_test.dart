import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:xterm/xterm.dart';

import 'package:ccb_mobile/ccb_mobile.dart';
import 'package:ccb_mobile/features/agent_chat/conversation_timeline.dart';

import 'support/project_home_test_driver.dart';
import 'support/project_home_test_fakes.dart';

void main() {
  testWidgets('readable terminal history scrolls through retained blocks', (
    tester,
  ) async {
    await tester.pumpWidget(const CcbMobileApp(enableProductOnboarding: false));
    await tester.pumpAndSettle();
    await openCurrentProject(tester);

    expect(
      find.byKey(const ValueKey('terminal-history-block-mobile-checkpoint-09')),
      findsNothing,
    );

    await tapVisible(
      tester,
      const ValueKey('conversation-expand-terminal-history-mobile'),
    );
    final historyScroll = find.byKey(
      const ValueKey('readable-terminal-history-scroll'),
    );
    expect(historyScroll, findsOneWidget);
    await tester.ensureVisible(historyScroll);
    await tester.pumpAndSettle();
    await tester.drag(historyScroll, const Offset(0, -900));
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey('terminal-history-block-mobile-checkpoint-09')),
      findsOneWidget,
    );
    expect(find.text('Checkpoint 09'), findsWidgets);
    expect(
      find.text('Long retained scrollback stays reachable by drag.'),
      findsWidgets,
    );
    expect(find.byType(TerminalView), findsNothing);
  });

  testWidgets('tmux history input and output appear as compact chat bubbles', (
    tester,
  ) async {
    await tester.pumpWidget(const CcbMobileApp(enableProductOnboarding: false));
    await tester.pumpAndSettle();
    await openCurrentProject(tester);

    const inputId = 'terminal-history-input-mobile-mobile-command-adb';
    await dragUntilVisible(
      tester,
      const ValueKey('conversation-item-$inputId'),
      const Offset(0, 700),
    );
    expect(
      find.byKey(const ValueKey('conversation-item-$inputId')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('conversation-preview-$inputId')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('conversation-expand-$inputId')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('conversation-body-$inputId')),
      findsNothing,
    );
    expect(find.text(r'$ adb reverse tcp:8787 tcp:8787'), findsOneWidget);

    await tapVisible(tester, const ValueKey('conversation-expand-$inputId'));

    expect(
      find.byKey(const ValueKey('conversation-body-$inputId')),
      findsOneWidget,
    );

    const outputId = 'terminal-history-output-mobile-mobile-diff-content';
    await dragUntilVisible(
      tester,
      const ValueKey('conversation-item-$outputId'),
      const Offset(0, -700),
    );
    expect(
      find.byKey(const ValueKey('conversation-item-$outputId')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('conversation-preview-$outputId')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('conversation-expand-$outputId')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('conversation-body-$outputId')),
      findsNothing,
    );

    await tapVisible(tester, const ValueKey('conversation-preview-$outputId'));

    expect(
      find.byKey(const ValueKey('conversation-body-$outputId')),
      findsOneWidget,
    );
    expect(renderedTextContaining('terminal-first default page'), findsWidgets);
    expect(find.byType(TerminalView), findsNothing);
  });

  testWidgets('chat timeline virtualizes long histories and keeps expansion', (
    tester,
  ) async {
    final repository = LongConversationRepository(messageCount: 160);
    await tester.pumpWidget(
      MaterialApp(home: ProjectHomeScreen(repository: repository)),
    );
    await tester.pumpAndSettle();
    await openCurrentProject(tester);

    expect(
      find.byKey(const ValueKey('conversation-item-long-000')),
      findsNothing,
    );
    await dragUntilVisible(
      tester,
      const ValueKey('conversation-item-long-159'),
      const Offset(0, -700),
    );
    expect(
      find.byKey(const ValueKey('conversation-item-long-159')),
      findsOneWidget,
    );

    await dragUntilVisible(
      tester,
      const ValueKey('conversation-expand-long-000'),
      const Offset(0, 700),
    );
    await tapVisible(tester, const ValueKey('conversation-expand-long-000'));

    expect(
      find.byKey(const ValueKey('markdown-body-conversation-long-000')),
      findsOneWidget,
    );

    await dragUntilVisible(
      tester,
      const ValueKey('conversation-item-long-159'),
      const Offset(0, -700),
    );

    expect(
      find.byKey(const ValueKey('markdown-body-conversation-long-000')),
      findsNothing,
    );

    await dragUntilVisible(
      tester,
      const ValueKey('conversation-item-long-000'),
      const Offset(0, 700),
    );

    expect(
      find.byKey(const ValueKey('markdown-body-conversation-long-000')),
      findsOneWidget,
    );
  });

  testWidgets(
    'expanding bottom bubble scrolls it to top and collapse restores',
    (tester) async {
      await setTestSurfaceSize(tester, const Size(390, 844));
      await tester.pumpWidget(
        MaterialApp(
          home: ProjectHomeScreen(
            repository: LongConversationRepository(messageCount: 160),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await openCurrentProject(tester);

      await dragUntilVisible(
        tester,
        const ValueKey('conversation-expand-long-159'),
        const Offset(0, -700),
      );
      final timeline = tester.widget<ListView>(
        find.byKey(const ValueKey('agent-chat-timeline')),
      );
      final controller = timeline.controller!;
      final beforeExpandOffset = controller.position.pixels;

      await tester.tap(
        find.byKey(const ValueKey('conversation-expand-long-159')),
      );
      await tester.pumpAndSettle();

      final timelineTop =
          tester
              .getTopLeft(find.byKey(const ValueKey('agent-chat-timeline')))
              .dy;
      final itemTop =
          tester
              .getTopLeft(find.byKey(conversationTimelineItemKey('long-159')))
              .dy;

      expect((itemTop - timelineTop).abs(), lessThan(24));
      expect(
        tester
            .getSize(
              find.byKey(const ValueKey('conversation-body-viewport-long-159')),
            )
            .height,
        greaterThan(420),
      );
      expect(
        find.byKey(const ValueKey('markdown-body-conversation-long-159')),
        findsOneWidget,
      );

      await tester.tap(
        find.byKey(const ValueKey('conversation-expand-long-159')),
      );
      await tester.pumpAndSettle();

      expect(controller.position.pixels, closeTo(beforeExpandOffset, 1));
    },
  );

  testWidgets('user send scrolls to latest while reading older history', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: ProjectHomeScreen(
          repository: LongConversationRepository(messageCount: 120),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await openCurrentProject(tester);

    await dragUntilVisible(
      tester,
      const ValueKey('conversation-item-long-020'),
      const Offset(0, 700),
    );
    expect(find.byKey(const ValueKey('agent-new-messages-jump')), findsNothing);

    await tester.enterText(
      find.byKey(const ValueKey('agent-message-composer')),
      'history safe send',
    );
    await tester.tap(find.byKey(const ValueKey('agent-message-send-button')));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('agent-new-messages-jump')), findsNothing);
    expect(find.text('history safe send'), findsOneWidget);
    expect(
      find.byKey(const ValueKey('conversation-item-long-020')),
      findsNothing,
    );
  });
}
