import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart' show ScrollDirection;
import 'package:flutter_test/flutter_test.dart';

import 'package:ccb_mobile/ccb_mobile.dart';
import 'package:ccb_mobile/features/project_home/project_home_scaffold_host.dart';
import 'package:ccb_mobile/features/project_home/wide_sidebar_state.dart';

import 'support/project_home_test_fakes.dart';

void main() {
  group('project home scaffold host', () {
    testWidgets('mobile host renders keys and forwards callbacks', (
      tester,
    ) async {
      final view = _view();
      final selectedAgent = view.agentByName('mobile');
      var backCalls = 0;
      var detailsCalls = 0;
      var terminalAgentName = '';
      var collapsed = false;
      var expanded = false;
      var selectedWindowName = '';
      var selectedAgentName = '';
      var scrollDirection = ScrollDirection.idle;

      await _pump(
        tester,
        ProjectHomeMobileChatScaffoldHost(
          view: view,
          selectedAgent: selectedAgent,
          repository: RecordingGatewayRepository(),
          terminalTransport: RecordingTerminalTransport(),
          usePaneInputForMessages: true,
          mobileAgentsCollapsed: false,
          onBack: () {
            backCalls += 1;
          },
          onOpenTerminal: (agentName) {
            terminalAgentName = agentName;
          },
          onOpenConnectionDetails: () {
            detailsCalls += 1;
          },
          onCollapseAgents: () {
            collapsed = true;
          },
          onExpandAgents: () {
            expanded = true;
          },
          onWindowSelected: (windowName) {
            selectedWindowName = windowName;
          },
          onAgentSelected: (agentName) {
            selectedAgentName = agentName;
          },
          onRefreshView: () async => null,
          onTimelineScrollDirectionChanged: (direction) {
            scrollDirection = direction;
          },
        ),
      );

      expect(find.byKey(const ValueKey('project-chat-screen')), findsOneWidget);
      expect(find.byKey(const ValueKey('project-chat-header')), findsOneWidget);
      expect(
        find.byKey(const ValueKey('mobile-agent-switcher-expanded')),
        findsOneWidget,
      );
      expect(
        find.descendant(
          of: find.byKey(const ValueKey('window-tab-main')),
          matching: find.byIcon(Icons.space_dashboard_rounded),
        ),
        findsOneWidget,
      );
      expect(
        find.descendant(
          of: find.byKey(const ValueKey('window-tab-review')),
          matching: find.byIcon(Icons.space_dashboard_outlined),
        ),
        findsOneWidget,
      );
      expect(
        find.descendant(
          of: find.byKey(const ValueKey('agent-mobile')),
          matching: find.byIcon(Icons.auto_awesome_rounded),
        ),
        findsOneWidget,
      );
      expect(
        find.descendant(
          of: find.byKey(const ValueKey('agent-lead')),
          matching: find.byIcon(Icons.auto_awesome_outlined),
        ),
        findsOneWidget,
      );

      tester
          .widget<IconButton>(find.byKey(const ValueKey('project-back-button')))
          .onPressed!();
      tester
          .widget<IconButton>(
            find.byKey(const ValueKey('connection-details-action')),
          )
          .onPressed!();
      tester
          .widget<IconButton>(
            find.byKey(const ValueKey('open-agent-terminal-button')),
          )
          .onPressed!();
      await tester.tap(
        find.byKey(const ValueKey('mobile-agent-switcher-collapse-action')),
      );
      await tester.tap(find.byKey(const ValueKey('window-tab-review')));
      await tester.tap(find.byKey(const ValueKey('agent-lead')));
      await tester.drag(
        find.byKey(const ValueKey('agent-chat-timeline-mobile')),
        const Offset(0, -72),
      );

      expect(backCalls, 1);
      expect(detailsCalls, 1);
      expect(terminalAgentName, 'mobile');
      expect(collapsed, isTrue);
      expect(expanded, isFalse);
      expect(selectedWindowName, 'review');
      expect(selectedAgentName, 'lead');
      expect(scrollDirection, ScrollDirection.reverse);
    });

    testWidgets('mobile host disables terminal without selected agent', (
      tester,
    ) async {
      await _pump(
        tester,
        ProjectHomeMobileChatScaffoldHost(
          view: _view(),
          selectedAgent: null,
          repository: RecordingGatewayRepository(),
          terminalTransport: RecordingTerminalTransport(),
          usePaneInputForMessages: true,
          mobileAgentsCollapsed: true,
          onBack: () {},
          onOpenTerminal: (_) {},
          onOpenConnectionDetails: () {},
          onCollapseAgents: () {},
          onExpandAgents: () {},
          onWindowSelected: (_) {},
          onAgentSelected: (_) {},
          onRefreshView: () async => null,
          onTimelineScrollDirectionChanged: (_) {},
        ),
      );

      expect(
        find.byKey(const ValueKey('mobile-agent-switcher-collapsed')),
        findsOneWidget,
      );
      expect(
        find.descendant(
          of: find.byKey(const ValueKey('mobile-agent-switcher-collapsed')),
          matching: find.byIcon(Icons.auto_awesome_rounded),
        ),
        findsOneWidget,
      );
      expect(
        tester
            .widget<IconButton>(
              find.byKey(const ValueKey('open-agent-terminal-button')),
            )
            .onPressed,
        isNull,
      );
    });

    testWidgets('wide host renders sidebar surfaces for each state', (
      tester,
    ) async {
      final view = _view();
      final selectedAgent = view.agentByName('mobile');

      await _pump(
        tester,
        _wideHost(view, selectedAgent, WideSidebarState.expanded),
        size: const Size(1200, 800),
      );
      expect(
        find.byKey(const ValueKey('wide-project-workspace')),
        findsOneWidget,
      );
      expect(find.byKey(const ValueKey('wide-project-column')), findsOneWidget);
      expect(
        find.byKey(const ValueKey('wide-collapsed-sidebar-rail')),
        findsNothing,
      );
      expect(find.byKey(const ValueKey('project-back-button')), findsNothing);

      await _pump(
        tester,
        _wideHost(view, selectedAgent, WideSidebarState.projectCollapsed),
        size: const Size(1200, 800),
      );
      expect(find.byKey(const ValueKey('wide-project-column')), findsNothing);
      expect(
        find.byKey(const ValueKey('wide-project-expand-action')),
        findsOneWidget,
      );
      expect(
        find.byKey(const ValueKey('wide-collapsed-sidebar-rail')),
        findsNothing,
      );

      await _pump(
        tester,
        _wideHost(view, selectedAgent, WideSidebarState.allCollapsed),
        size: const Size(1200, 800),
      );
      expect(find.byKey(const ValueKey('wide-project-column')), findsNothing);
      expect(
        find.byKey(const ValueKey('wide-collapsed-sidebar-rail')),
        findsOneWidget,
      );
      expect(
        find.descendant(
          of: find.byKey(const ValueKey('wide-collapsed-sidebar-rail')),
          matching: find.byIcon(Icons.auto_awesome_rounded),
        ),
        findsNWidgets(2),
      );
      expect(
        find.byKey(const ValueKey('wide-project-chat-screen')),
        findsOneWidget,
      );
    });
  });
}

ProjectHomeWideScaffoldHost _wideHost(
  CcbProjectView view,
  CcbAgent? selectedAgent,
  WideSidebarState sidebarState,
) {
  return ProjectHomeWideScaffoldHost(
    view: view,
    selectedAgent: selectedAgent,
    repository: RecordingGatewayRepository(),
    terminalTransport: RecordingTerminalTransport(),
    usePaneInputForMessages: true,
    sidebarState: sidebarState,
    onOpenProject: () {},
    onOpenNotifications: () {},
    onOpenConnectionDetails: () {},
    onShowProjects: () {},
    onAgentSelected: (_) {},
    onOpenTerminal: (_) {},
    onToggleSidebar: () {},
    onHorizontalDragStart: (_) {},
    onHorizontalDragUpdate: (_) {},
    onHorizontalDragEnd: (_) {},
    onRefreshView: () async => null,
  );
}

Future<void> _pump(
  WidgetTester tester,
  Widget child, {
  Size size = const Size(390, 844),
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  await tester.pumpWidget(MaterialApp(home: child));
  await tester.pumpAndSettle();
}

CcbProjectView _view() {
  return const CcbProjectView(
    project: CcbProject(
      id: 'proj-demo',
      displayName: 'demo',
      root: '/srv/ccb/demo',
    ),
    namespaceEpoch: 4,
    tmuxSocketPath: '/tmp/ccb-demo/tmux.sock',
    tmuxSessionName: 'ccb-demo',
    activeWindow: 'main',
    activePaneId: '%2',
    windows: [
      CcbWindow(
        name: 'main',
        label: 'main',
        kind: 'agents',
        order: 0,
        active: true,
        agents: ['lead', 'mobile'],
      ),
      CcbWindow(
        name: 'review',
        label: 'review',
        kind: 'agents',
        order: 1,
        active: false,
        agents: ['reviewer'],
      ),
    ],
    agents: [
      CcbAgent(
        name: 'lead',
        provider: 'codex',
        window: 'main',
        order: 0,
        active: false,
        queueDepth: 0,
      ),
      CcbAgent(
        name: 'mobile',
        provider: 'codex',
        window: 'main',
        order: 1,
        active: true,
        queueDepth: 1,
      ),
      CcbAgent(
        name: 'reviewer',
        provider: 'codex',
        window: 'review',
        order: 0,
        active: false,
        queueDepth: 0,
      ),
    ],
    contentItems: [],
    notifications: [],
    terminalHistories: {},
  );
}
