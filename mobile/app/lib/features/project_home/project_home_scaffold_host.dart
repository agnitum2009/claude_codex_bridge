import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart' show ScrollDirection;

import '../../l10n/ccb_mobile_localizations.dart';
import '../../models/ccb_agent.dart';
import '../../models/ccb_project.dart';
import '../../models/ccb_project_view.dart';
import '../../repository/mobile_ccb_repository.dart';
import '../../transport/terminal_transport.dart';
import '../agent_chat/selected_agent_workspace.dart';
import 'project_shell_widgets.dart';

class ProjectHomeProjectListHost extends StatelessWidget {
  const ProjectHomeProjectListHost({
    required this.view,
    required this.selectedAgent,
    required this.onOpenProject,
    required this.onOpenNotifications,
    required this.onOpenConnectionDetails,
    this.hasUnreadTaskCompletion = false,
    this.hasWorkingAgents = false,
    super.key,
  });

  final CcbProjectView view;
  final CcbAgent? selectedAgent;
  final VoidCallback onOpenProject;
  final VoidCallback onOpenNotifications;
  final VoidCallback onOpenConnectionDetails;
  final bool hasUnreadTaskCompletion;
  final bool hasWorkingAgents;

  @override
  Widget build(BuildContext context) {
    return ProjectListScaffold(
      view: view,
      selectedAgent: selectedAgent,
      onOpenProject: onOpenProject,
      onOpenNotifications: onOpenNotifications,
      onOpenConnectionDetails: onOpenConnectionDetails,
      hasUnreadTaskCompletion: hasUnreadTaskCompletion,
      hasWorkingAgents: hasWorkingAgents,
    );
  }
}

class ProjectHomeServerProjectListHost extends StatelessWidget {
  const ProjectHomeServerProjectListHost({
    required this.projects,
    required this.onRefreshProjects,
    required this.onOpenSettings,
    required this.onOpenProject,
    this.unreadProjectIds = const {},
    this.workingProjectIds = const {},
    super.key,
  });

  final List<CcbProject> projects;
  final VoidCallback onRefreshProjects;
  final VoidCallback onOpenSettings;
  final ValueChanged<CcbProject> onOpenProject;
  final Set<String> unreadProjectIds;
  final Set<String> workingProjectIds;

  @override
  Widget build(BuildContext context) {
    final strings = CcbMobileLocalizations.of(context);
    return Scaffold(
      body: SafeArea(
        child: Padding(
          key: const ValueKey('project-list-screen'),
          padding: const EdgeInsets.fromLTRB(12, 4, 12, 8),
          child: Column(
            children: [
              Align(
                alignment: Alignment.centerRight,
                child: Wrap(
                  spacing: 2,
                  children: [
                    IconButton(
                      key: const ValueKey('project-list-refresh-action'),
                      tooltip: strings.refreshProjects,
                      onPressed: onRefreshProjects,
                      icon: const Icon(Icons.refresh),
                    ),
                    IconButton(
                      key: const ValueKey('project-list-settings-action'),
                      tooltip: strings.settings,
                      onPressed: onOpenSettings,
                      icon: const Icon(Icons.settings_outlined),
                    ),
                  ],
                ),
              ),
              Expanded(
                child:
                    projects.isEmpty
                        ? Center(
                          key: const ValueKey('project-list-empty'),
                          child: Text(strings.noCcbProjectsFound),
                        )
                        : ListView.separated(
                          key: const ValueKey('project-list'),
                          itemCount: projects.length,
                          separatorBuilder:
                              (context, index) => const Divider(height: 1),
                          itemBuilder: (context, index) {
                            final project = projects[index];
                            return _ServerProjectListTile(
                              project: project,
                              hasUnreadTaskCompletion: unreadProjectIds
                                  .contains(project.id),
                              hasWorkingAgents:
                                  project.hasWorkingAgents ||
                                  workingProjectIds.contains(project.id),
                              onOpen: () {
                                onOpenProject(project);
                              },
                            );
                          },
                        ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ServerProjectListTile extends StatelessWidget {
  const _ServerProjectListTile({
    required this.project,
    required this.onOpen,
    required this.hasUnreadTaskCompletion,
    required this.hasWorkingAgents,
  });

  final CcbProject project;
  final VoidCallback onOpen;
  final bool hasUnreadTaskCompletion;
  final bool hasWorkingAgents;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final root = project.root.trim();
    final health = project.health.trim();
    return ListTile(
      key: ValueKey('project-open-${project.id}'),
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      leading: ProjectAttentionAvatar(
        projectId: project.id,
        favorite: project.favorite,
        hasUnreadTaskCompletion: hasUnreadTaskCompletion,
        hasWorkingAgents: hasWorkingAgents,
      ),
      title: Text(
        project.displayName,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: textTheme.titleMedium,
      ),
      subtitle: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (root.isNotEmpty)
            Text(root, maxLines: 1, overflow: TextOverflow.ellipsis),
          if (health.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(
              health,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: textTheme.bodySmall?.copyWith(
                color: Theme.of(context).colorScheme.onSurfaceVariant,
              ),
            ),
          ],
        ],
      ),
      trailing: const Icon(Icons.chevron_right),
      onTap: onOpen,
    );
  }
}

class ProjectHomeMobileChatScaffoldHost extends StatelessWidget {
  const ProjectHomeMobileChatScaffoldHost({
    required this.view,
    required this.selectedAgent,
    required this.repository,
    required this.terminalTransport,
    required this.usePaneInputForMessages,
    required this.mobileAgentsCollapsed,
    required this.onBack,
    required this.onOpenTerminal,
    required this.onOpenConnectionDetails,
    required this.onCollapseAgents,
    required this.onExpandAgents,
    required this.onWindowSelected,
    required this.onAgentSelected,
    required this.onRefreshView,
    required this.onTimelineScrollDirectionChanged,
    this.unreadAgentNames = const {},
    super.key,
  });

  final CcbProjectView view;
  final CcbAgent? selectedAgent;
  final MobileCcbRepository repository;
  final TerminalTransport? terminalTransport;
  final bool usePaneInputForMessages;
  final bool mobileAgentsCollapsed;
  final VoidCallback onBack;
  final ValueChanged<String> onOpenTerminal;
  final VoidCallback onOpenConnectionDetails;
  final VoidCallback onCollapseAgents;
  final VoidCallback onExpandAgents;
  final ValueChanged<String> onWindowSelected;
  final ValueChanged<String> onAgentSelected;
  final Future<CcbProjectView?> Function() onRefreshView;
  final ValueChanged<ScrollDirection> onTimelineScrollDirectionChanged;
  final Set<String> unreadAgentNames;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Padding(
          key: const ValueKey('project-chat-screen'),
          padding: const EdgeInsets.fromLTRB(8, 4, 8, 8),
          child: Column(
            children: [
              ProjectChatHeader(
                view: view,
                onBack: onBack,
                onOpenTerminal:
                    selectedAgent == null
                        ? null
                        : () {
                          onOpenTerminal(selectedAgent!.name);
                        },
                onOpenConnectionDetails: onOpenConnectionDetails,
              ),
              const SizedBox(height: 4),
              MobileAgentSwitcherPanel(
                view: view,
                selectedAgent: selectedAgent,
                collapsed: mobileAgentsCollapsed,
                unreadAgentNames: unreadAgentNames,
                onCollapse: onCollapseAgents,
                onExpand: onExpandAgents,
                onWindowSelected: onWindowSelected,
                onAgentSelected: onAgentSelected,
              ),
              const SizedBox(height: 4),
              Expanded(
                child: SelectedAgentWorkspace(
                  repository: repository,
                  terminalTransport: terminalTransport,
                  usePaneInputForMessages: usePaneInputForMessages,
                  view: view,
                  agent: selectedAgent,
                  enableComposerCollapse: true,
                  onRefreshView: onRefreshView,
                  onUserScrollDirectionChanged:
                      onTimelineScrollDirectionChanged,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class ProjectHomeWideScaffoldHost extends StatelessWidget {
  const ProjectHomeWideScaffoldHost({
    required this.view,
    required this.selectedAgent,
    required this.repository,
    required this.terminalTransport,
    required this.usePaneInputForMessages,
    required this.sidebarState,
    required this.onOpenProject,
    required this.onOpenNotifications,
    required this.onOpenConnectionDetails,
    required this.onShowProjects,
    required this.onAgentSelected,
    required this.onOpenTerminal,
    required this.onToggleSidebar,
    required this.onHorizontalDragStart,
    required this.onHorizontalDragUpdate,
    required this.onHorizontalDragEnd,
    required this.onRefreshView,
    this.unreadAgentNames = const {},
    this.hasUnreadTaskCompletion = false,
    this.hasWorkingAgents = false,
    super.key,
  });

  final CcbProjectView view;
  final CcbAgent? selectedAgent;
  final MobileCcbRepository repository;
  final TerminalTransport? terminalTransport;
  final bool usePaneInputForMessages;
  final WideSidebarState sidebarState;
  final VoidCallback onOpenProject;
  final VoidCallback onOpenNotifications;
  final VoidCallback onOpenConnectionDetails;
  final VoidCallback onShowProjects;
  final ValueChanged<CcbAgent> onAgentSelected;
  final ValueChanged<String> onOpenTerminal;
  final VoidCallback onToggleSidebar;
  final GestureDragStartCallback onHorizontalDragStart;
  final GestureDragUpdateCallback onHorizontalDragUpdate;
  final GestureDragEndCallback onHorizontalDragEnd;
  final Future<CcbProjectView?> Function() onRefreshView;
  final Set<String> unreadAgentNames;
  final bool hasUnreadTaskCompletion;
  final bool hasWorkingAgents;

  @override
  Widget build(BuildContext context) {
    final sidebars = switch (sidebarState) {
      WideSidebarState.expanded => <Widget>[
        SizedBox(
          width: projectHomeWideProjectColumnWidth,
          child: WideProjectColumn(
            view: view,
            selectedAgent: selectedAgent,
            onProjectSelected: onOpenProject,
            onOpenNotifications: onOpenNotifications,
            onOpenConnectionDetails: onOpenConnectionDetails,
            hasUnreadTaskCompletion: hasUnreadTaskCompletion,
            hasWorkingAgents: hasWorkingAgents,
          ),
        ),
        const VerticalDivider(width: 1),
        SizedBox(
          width: projectHomeWideAgentColumnWidth,
          child: WideAgentColumn(
            view: view,
            selectedAgentName: selectedAgent?.name,
            unreadAgentNames: unreadAgentNames,
            onAgentSelected: onAgentSelected,
          ),
        ),
      ],
      WideSidebarState.projectCollapsed => <Widget>[
        SizedBox(
          width: projectHomeWideAgentColumnWidth,
          child: WideAgentColumn(
            view: view,
            selectedAgentName: selectedAgent?.name,
            unreadAgentNames: unreadAgentNames,
            onShowProjects: onShowProjects,
            onAgentSelected: onAgentSelected,
          ),
        ),
      ],
      WideSidebarState.allCollapsed => <Widget>[
        SizedBox(
          width: projectHomeWideCollapsedSidebarWidth,
          child: WideCollapsedSidebarRail(
            view: view,
            selectedAgent: selectedAgent,
            onExpand: onShowProjects,
            onOpenNotifications: onOpenNotifications,
            onOpenConnectionDetails: onOpenConnectionDetails,
          ),
        ),
      ],
    };
    return Scaffold(
      body: SafeArea(
        child: Row(
          key: const ValueKey('wide-project-workspace'),
          children: [
            ...sidebars,
            WideSidebarDragHandle(
              sidebarState: sidebarState,
              onToggle: onToggleSidebar,
              onHorizontalDragStart: onHorizontalDragStart,
              onHorizontalDragUpdate: onHorizontalDragUpdate,
              onHorizontalDragEnd: onHorizontalDragEnd,
            ),
            Expanded(
              child: Padding(
                key: const ValueKey('wide-project-chat-screen'),
                padding: const EdgeInsets.fromLTRB(8, 4, 8, 8),
                child: Column(
                  children: [
                    ProjectChatHeader(
                      view: view,
                      onBack: null,
                      onOpenTerminal:
                          selectedAgent == null
                              ? null
                              : () {
                                onOpenTerminal(selectedAgent!.name);
                              },
                      onOpenConnectionDetails: onOpenConnectionDetails,
                    ),
                    const SizedBox(height: 4),
                    Expanded(
                      child: SelectedAgentWorkspace(
                        repository: repository,
                        terminalTransport: terminalTransport,
                        usePaneInputForMessages: usePaneInputForMessages,
                        view: view,
                        agent: selectedAgent,
                        enableComposerCollapse: false,
                        onRefreshView: onRefreshView,
                        onUserScrollDirectionChanged: null,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
