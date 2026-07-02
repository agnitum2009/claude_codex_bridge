import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:ccb_mobile/features/project_home/agent_window_switchers.dart';
import 'package:ccb_mobile/features/project_home/wide_agent_column.dart';
import 'package:ccb_mobile/models/ccb_agent.dart';
import 'package:ccb_mobile/models/ccb_project.dart';
import 'package:ccb_mobile/models/ccb_project_view.dart';
import 'package:ccb_mobile/models/ccb_window.dart';

void main() {
  testWidgets('agent switcher highlights source-working agents with a border', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: AgentSwitcher(
            agents: [
              _agent(name: 'idle'),
              _agent(
                name: 'working',
                activityState: 'active',
                activitySource: 'codex_runtime',
                activityReason: 'codex_working_status_line',
              ),
            ],
            selectedAgentName: 'idle',
            onAgentSelected: (_) {},
          ),
        ),
      ),
    );

    final colorScheme =
        Theme.of(
          tester.element(find.byKey(const ValueKey('agent-switcher'))),
        ).colorScheme;
    final idle = tester.widget<ChoiceChip>(
      find.byKey(const ValueKey('agent-idle')),
    );
    final working = tester.widget<ChoiceChip>(
      find.byKey(const ValueKey('agent-working')),
    );

    expect(idle.side, isNull);
    expect(working.side?.color, colorScheme.tertiary);
    expect(working.side?.width, 1.6);
  });

  testWidgets(
    'wide agent list highlights source-working agents with a border',
    (tester) async {
      final view = CcbProjectView(
        project: const CcbProject(
          id: 'proj',
          displayName: 'Project',
          root: '/p',
        ),
        namespaceEpoch: 1,
        tmuxSocketPath: null,
        tmuxSessionName: null,
        activeWindow: 'main',
        activePaneId: null,
        windows: const [
          CcbWindow(
            name: 'main',
            label: 'main',
            kind: 'agents',
            order: 0,
            active: true,
            agents: ['idle', 'working'],
          ),
        ],
        agents: [
          _agent(name: 'idle'),
          _agent(
            name: 'working',
            activityState: 'running',
            activitySource: 'codex_runtime',
          ),
        ],
        contentItems: const [],
        notifications: const [],
        terminalHistories: const {},
      );

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: WideAgentColumn(
              view: view,
              selectedAgentName: 'idle',
              onAgentSelected: (_) {},
            ),
          ),
        ),
      );

      final colorScheme =
          Theme.of(
            tester.element(find.byKey(const ValueKey('agent-secondary-list'))),
          ).colorScheme;
      final idleTile = tester.widget<ListTile>(
        find.byKey(const ValueKey('agent-idle')),
      );
      final workingTile = tester.widget<ListTile>(
        find.byKey(const ValueKey('agent-working')),
      );
      final idleShape = idleTile.shape as RoundedRectangleBorder;
      final workingShape = workingTile.shape as RoundedRectangleBorder;

      expect(idleShape.side, BorderSide.none);
      expect(workingShape.side.color, colorScheme.tertiary);
      expect(workingShape.side.width, 1.6);
    },
  );
}

CcbAgent _agent({
  required String name,
  String? activityState,
  String? activitySource,
  String? activityReason,
}) {
  return CcbAgent(
    name: name,
    provider: 'codex',
    window: 'main',
    order: 0,
    active: false,
    queueDepth: 0,
    activityState: activityState,
    activitySource: activitySource,
    activityReason: activityReason,
  );
}
