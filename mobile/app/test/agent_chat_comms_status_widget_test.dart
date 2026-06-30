import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:ccb_mobile/ccb_mobile.dart';
import 'package:ccb_mobile/features/agent_chat/selected_agent_workspace_model.dart';
import 'package:ccb_mobile/features/agent_chat/selected_agent_workspace_view.dart';

void main() {
  testWidgets('comms updates render as status instead of timeline card', (
    tester,
  ) async {
    final scrollController = ScrollController();
    final draftController = TextEditingController();
    final focusNode = FocusNode();
    addTearDown(scrollController.dispose);
    addTearDown(draftController.dispose);
    addTearDown(focusNode.dispose);

    final agent = _agent();
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SizedBox(
            height: 520,
            child: SelectedAgentWorkspaceView(
              repository: FakeMobileCcbRepository.demo(),
              view: _view(),
              model: SelectedAgentWorkspaceModel(
                agent: agent,
                contentItems: const [],
                initialHistory: null,
                timelineItems: [
                  CcbConversationItem(
                    id: 'reply-1',
                    agentName: agent.name,
                    kind: CcbConversationItemKind.agentReply,
                    title: 'Agent reply',
                    body: 'real backend answer',
                    source: 'completion_snapshot',
                  ),
                ],
                commsItems: [
                  CcbConversationItem(
                    id: 'comms-1',
                    agentName: agent.name,
                    kind: CcbConversationItemKind.commsItem,
                    title: 'Comms',
                    body: 'project view updated',
                    source: 'project_view',
                  ),
                ],
                isLoadingConversation: false,
                hasOlderConversation: false,
                expandedItemIds: const {},
                hasNewMessages: false,
                isSending: false,
                isAwaitingAgentResponse: true,
                isComposerCollapsed: false,
                executionStatus: agentExecutionStatus(
                  agent: _agent(),
                  isAwaitingAgentResponse: true,
                  isLoadingConversation: false,
                ),
              ),
              timelineController: scrollController,
              draftController: draftController,
              draftFocusNode: focusNode,
              enableComposerCollapse: false,
              onRetry: (_) {},
              onToggleExpanded: (_) {},
              onRefreshLatest: () {},
              onNearEnd: () {},
              onUserNearEnd: () {},
              onNearStart: () {},
              onUserScrollDirectionChanged: (_) {},
              onJumpToLatest: () {},
              onCollapseComposer: () {},
              onExpandComposer: () {},
              draftAttachments: const [],
              downloadingAttachmentIds: const {},
              downloadedAttachmentIds: const {},
              onPickImageAttachment: () {},
              onPickFileAttachment: () {},
              onRemoveAttachment: (_) {},
              onDownloadAttachment: (_) {},
              onSend: () {},
              onSendTab: () {},
              onSendEscape: () {},
            ),
          ),
        ),
      ),
    );

    expect(find.byKey(const ValueKey('agent-comms-status')), findsOneWidget);
    expect(find.text('Communicating'), findsOneWidget);
    expect(find.byKey(const ValueKey('agent-working-status')), findsOneWidget);
    expect(find.text('Working'), findsOneWidget);
    expect(find.text('project view updated'), findsOneWidget);
    expect(
      find.byKey(const ValueKey('conversation-item-comms-1')),
      findsNothing,
    );
    expect(
      find.byKey(const ValueKey('conversation-item-reply-1')),
      findsOneWidget,
    );
  });
}

CcbProjectView _view() {
  return CcbProjectView(
    project: const CcbProject(
      id: 'proj',
      displayName: 'Project',
      root: '/tmp/proj',
    ),
    namespaceEpoch: 7,
    tmuxSocketPath: null,
    tmuxSessionName: null,
    activeWindow: 'main',
    activePaneId: null,
    windows: const [],
    agents: [_agent()],
    contentItems: const [],
    notifications: const [],
    terminalHistories: const {},
  );
}

CcbAgent _agent() {
  return const CcbAgent(
    name: 'mobile',
    provider: 'codex',
    window: 'main',
    order: 0,
    active: true,
    queueDepth: 0,
  );
}
