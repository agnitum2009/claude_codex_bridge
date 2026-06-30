import 'package:ccb_mobile/features/agent_chat/agent_chat_controller.dart';
import 'package:ccb_mobile/features/agent_chat/selected_agent_workspace_model.dart';
import 'package:ccb_mobile/models/ccb_agent.dart';
import 'package:ccb_mobile/models/ccb_agent_conversation.dart';
import 'package:ccb_mobile/models/ccb_conversation_item.dart';
import 'package:ccb_mobile/models/ccb_project.dart';
import 'package:ccb_mobile/models/ccb_project_view.dart';
import 'package:ccb_mobile/models/readable_terminal_history.dart';
import 'package:test/test.dart';

void main() {
  test('keeps comms updates out of visible conversation timeline', () {
    final chatController = AgentChatController();
    final view = _view();
    final agent = _agent();
    chatController.applyRemoteConversation(
      agentName: agent.name,
      shouldScroll: true,
      conversation: CcbAgentConversation(
        projectId: view.project.id,
        agentName: agent.name,
        namespaceEpoch: view.namespaceEpoch!,
        items: [
          const CcbConversationItem(
            id: 'reply-1',
            agentName: 'mobile',
            kind: CcbConversationItemKind.agentReply,
            title: 'Agent reply',
            body: 'real answer',
            source: 'completion_snapshot',
          ),
          const CcbConversationItem(
            id: 'comms-1',
            agentName: 'mobile',
            kind: CcbConversationItemKind.commsItem,
            title: 'Comms',
            body: 'project view updated',
            source: 'project_view',
          ),
        ],
        generatedAt: DateTime.utc(2026, 6, 24),
      ),
    );

    final model = selectedAgentWorkspaceModel(
      view: view,
      agent: agent,
      chatController: chatController,
      isAwaitingAgentResponse: false,
    );

    expect(model.timelineItems.map((item) => item.id), ['reply-1']);
    expect(model.commsItems.map((item) => item.id), ['comms-1']);
    expect(model.hasOlderConversation, isFalse);
  });

  test('reports older conversation availability from next cursor', () {
    final chatController = AgentChatController();
    final view = _view();
    final agent = _agent();
    chatController.applyRemoteConversation(
      agentName: agent.name,
      shouldScroll: true,
      conversation: CcbAgentConversation(
        projectId: view.project.id,
        agentName: agent.name,
        namespaceEpoch: view.namespaceEpoch!,
        items: const [],
        nextCursor: '8',
        generatedAt: DateTime.utc(2026, 6, 24),
      ),
    );

    final model = selectedAgentWorkspaceModel(
      view: view,
      agent: agent,
      chatController: chatController,
      isAwaitingAgentResponse: true,
    );

    expect(model.hasOlderConversation, isTrue);
    expect(model.isAwaitingAgentResponse, isTrue);
  });

  test('keeps refreshed pane history out of provider native transcript', () {
    final chatController = AgentChatController();
    final view = _view();
    final agent = _agent();
    chatController.applyRemoteConversation(
      agentName: agent.name,
      shouldScroll: true,
      conversation: CcbAgentConversation(
        projectId: view.project.id,
        agentName: agent.name,
        namespaceEpoch: view.namespaceEpoch!,
        items: [
          const CcbConversationItem(
            id: 'native-reply',
            agentName: 'mobile',
            kind: CcbConversationItemKind.agentReply,
            title: 'Agent reply',
            body: 'native transcript answer',
            source: 'provider_native/codex',
          ),
        ],
        generatedAt: DateTime.utc(2026, 6, 24),
      ),
    );
    chatController.setRefreshedTerminalHistory(
      agent.name,
      const ReadableTerminalHistory(
        agentName: 'mobile',
        historyScope: 'tmux_scrollback',
        blocks: [
          ReadableTerminalBlock(
            id: 'status-output',
            type: 'log',
            title: 'Terminal output',
            text: 'Credits remaining: 42%',
          ),
        ],
      ),
    );

    final model = selectedAgentWorkspaceModel(
      view: view,
      agent: agent,
      chatController: chatController,
      isAwaitingAgentResponse: false,
    );

    expect(model.timelineItems.map((item) => item.body), [
      'native transcript answer',
    ]);
    expect(model.timelineItems.single.source, 'provider_native/codex');
  });

  test('reports working execution status from project view activity', () {
    final chatController = AgentChatController();
    final agent = _agent(
      activityState: 'active',
      activitySource: 'codex_runtime',
      activityReason: 'codex_session_task_started',
    );

    final model = selectedAgentWorkspaceModel(
      view: _view(agent: agent),
      agent: agent,
      chatController: chatController,
      isAwaitingAgentResponse: false,
    );

    expect(model.executionStatus?.label, 'Working');
    expect(model.executionStatus?.state, 'working');
    expect(model.executionStatus?.isRefreshing, isFalse);
  });

  test('folds reconnecting status into working', () {
    final chatController = AgentChatController();
    final agent = _agent(
      activityState: 'pending',
      activitySource: 'codex_runtime',
      activityReason: 'codex_runtime_reconnecting',
    );

    final model = selectedAgentWorkspaceModel(
      view: _view(agent: agent),
      agent: agent,
      chatController: chatController,
      isAwaitingAgentResponse: false,
    );

    expect(model.executionStatus?.label, 'Working');
    expect(model.executionStatus?.state, 'working');
    expect(model.executionStatus?.isRefreshing, isTrue);
  });

  test('reports exception status from project view activity', () {
    final chatController = AgentChatController();
    final agent = _agent(
      activityState: 'failed',
      activitySource: 'codex_runtime',
      activityReason: 'provider_api_error',
    );

    final model = selectedAgentWorkspaceModel(
      view: _view(agent: agent),
      agent: agent,
      chatController: chatController,
      isAwaitingAgentResponse: false,
    );

    expect(model.executionStatus?.label, 'Exception');
    expect(model.executionStatus?.state, 'exception');
    expect(model.executionStatus?.isRefreshing, isFalse);
  });

  test('reports interrupted codex activity as exception', () {
    final chatController = AgentChatController();
    final agent = _agent(
      activityState: 'pending',
      activitySource: 'codex_runtime',
      activityReason: 'conversation_interrupted',
    );

    final model = selectedAgentWorkspaceModel(
      view: _view(agent: agent),
      agent: agent,
      chatController: chatController,
      isAwaitingAgentResponse: false,
    );

    expect(model.executionStatus?.label, 'Exception');
    expect(model.executionStatus?.state, 'exception');
    expect(model.executionStatus?.isRefreshing, isFalse);
  });

  test('project view exception overrides local awaiting response status', () {
    final chatController = AgentChatController();
    final agent = _agent(
      activityState: 'pending',
      activitySource: 'codex_runtime',
      activityReason: 'conversation_interrupted',
    );

    final model = selectedAgentWorkspaceModel(
      view: _view(agent: agent),
      agent: agent,
      chatController: chatController,
      isAwaitingAgentResponse: true,
    );

    expect(model.executionStatus?.label, 'Exception');
    expect(model.executionStatus?.state, 'exception');
    expect(model.executionStatus?.isRefreshing, isFalse);
  });

  test('local terminal exception overrides awaiting response status', () {
    final chatController = AgentChatController();
    final agent = _agent();

    final model = selectedAgentWorkspaceModel(
      view: _view(agent: agent),
      agent: agent,
      chatController: chatController,
      isAwaitingAgentResponse: true,
      hasLocalExecutionException: true,
    );

    expect(model.executionStatus?.label, 'Exception');
    expect(model.executionStatus?.state, 'exception');
    expect(model.executionStatus?.isRefreshing, isFalse);
  });

  test('reports idle execution status when no work is visible', () {
    final chatController = AgentChatController();
    final agent = _agent(provider: 'claude');

    final model = selectedAgentWorkspaceModel(
      view: _view(agent: agent),
      agent: agent,
      chatController: chatController,
      isAwaitingAgentResponse: false,
    );

    expect(model.executionStatus?.label, 'Idle');
    expect(model.executionStatus?.state, 'idle');
    expect(model.executionStatus?.isRefreshing, isFalse);
  });

  test(
    'reports idle when provider prompt idle reason accompanies idle state',
    () {
      final chatController = AgentChatController();
      final agent = _agent(
        activityState: 'idle',
        activitySource: 'provider_pane',
        activityReason: 'provider_prompt_idle',
      );

      final model = selectedAgentWorkspaceModel(
        view: _view(agent: agent),
        agent: agent,
        chatController: chatController,
        isAwaitingAgentResponse: false,
      );

      expect(model.executionStatus?.label, 'Idle');
      expect(model.executionStatus?.state, 'idle');
      expect(model.executionStatus?.isRefreshing, isFalse);
    },
  );

  test('local awaiting response overrides stale idle project view', () {
    final chatController = AgentChatController();
    final agent = _agent(
      activityState: 'idle',
      activitySource: 'provider_pane',
      activityReason: 'provider_prompt_idle',
    );

    final model = selectedAgentWorkspaceModel(
      view: _view(agent: agent),
      agent: agent,
      chatController: chatController,
      isAwaitingAgentResponse: true,
    );

    expect(model.executionStatus?.label, 'Working');
    expect(model.executionStatus?.state, 'working');
    expect(model.executionStatus?.isRefreshing, isFalse);
  });
}

CcbProjectView _view({CcbAgent? agent}) {
  final resolvedAgent = agent ?? _agent();
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
    agents: [resolvedAgent],
    contentItems: const [],
    notifications: const [],
    terminalHistories: const {},
  );
}

CcbAgent _agent({
  String provider = 'codex',
  String? activityState,
  String? activitySource,
  String? activityReason,
}) {
  return CcbAgent(
    name: 'mobile',
    provider: provider,
    window: 'main',
    order: 0,
    active: true,
    queueDepth: 0,
    activityState: activityState,
    activitySource: activitySource,
    activityReason: activityReason,
  );
}
