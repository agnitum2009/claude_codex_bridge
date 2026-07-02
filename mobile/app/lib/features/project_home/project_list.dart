import 'package:flutter/material.dart';

import '../../l10n/ccb_mobile_localizations.dart';
import '../../models/ccb_agent.dart';
import '../../models/ccb_project_view.dart';

class ProjectListScaffold extends StatelessWidget {
  const ProjectListScaffold({
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
                      key: const ValueKey('notification-center-action'),
                      tooltip: strings.notifications,
                      onPressed: onOpenNotifications,
                      icon: Icon(
                        view.notifications.isEmpty
                            ? Icons.notifications_none
                            : Icons.notifications_active,
                      ),
                    ),
                    IconButton(
                      key: const ValueKey('connection-details-action'),
                      tooltip: strings.diagnostics,
                      onPressed: onOpenConnectionDetails,
                      icon: const Icon(Icons.more_horiz),
                    ),
                  ],
                ),
              ),
              Expanded(
                child: ListView.separated(
                  key: const ValueKey('project-list'),
                  itemCount: 1,
                  separatorBuilder:
                      (context, index) => const Divider(height: 1),
                  itemBuilder: (context, index) {
                    return ProjectListTile(
                      view: view,
                      selectedAgent: selectedAgent,
                      selected: false,
                      hasUnreadTaskCompletion: hasUnreadTaskCompletion,
                      hasWorkingAgents: hasWorkingAgents,
                      onOpen: onOpenProject,
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

class ProjectListTile extends StatelessWidget {
  const ProjectListTile({
    required this.view,
    required this.selectedAgent,
    required this.selected,
    required this.onOpen,
    this.hasUnreadTaskCompletion = false,
    this.hasWorkingAgents = false,
    super.key,
  });

  final CcbProjectView view;
  final CcbAgent? selectedAgent;
  final bool selected;
  final VoidCallback onOpen;
  final bool hasUnreadTaskCompletion;
  final bool hasWorkingAgents;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final strings = CcbMobileLocalizations.of(context);
    final activeAgent = selectedAgent?.name ?? strings.noAgent;
    final activeWindow = view.activeWindow ?? selectedAgent?.window ?? 'main';
    final root = view.project.root.trim();
    return ListTile(
      key: const ValueKey('project-open-current'),
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      selected: selected,
      selectedTileColor: Theme.of(context).colorScheme.secondaryContainer,
      leading: ProjectAttentionAvatar(
        projectId: view.project.id,
        favorite: view.project.favorite,
        hasUnreadTaskCompletion: hasUnreadTaskCompletion,
        hasWorkingAgents: hasWorkingAgents,
      ),
      title: Text(
        view.project.displayName,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: textTheme.titleMedium,
      ),
      subtitle: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (root.isNotEmpty)
            Text(root, maxLines: 1, overflow: TextOverflow.ellipsis),
          const SizedBox(height: 4),
          Text(
            'cmd $activeWindow · $activeAgent',
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: textTheme.bodySmall?.copyWith(
              color: Theme.of(context).colorScheme.onSurfaceVariant,
            ),
          ),
        ],
      ),
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text('${view.agents.length}'),
          const SizedBox(width: 6),
          const Icon(Icons.chevron_right),
        ],
      ),
      onTap: onOpen,
    );
  }
}

class ProjectAttentionAvatar extends StatelessWidget {
  const ProjectAttentionAvatar({
    required this.projectId,
    required this.favorite,
    required this.hasUnreadTaskCompletion,
    required this.hasWorkingAgents,
    super.key,
  });

  final String projectId;
  final bool favorite;
  final bool hasUnreadTaskCompletion;
  final bool hasWorkingAgents;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return SizedBox(
      width: 52,
      height: 52,
      child: Stack(
        clipBehavior: Clip.none,
        children: [
          Center(
            child: Container(
              key:
                  hasWorkingAgents
                      ? ValueKey('project-working-ring-$projectId')
                      : null,
              padding: const EdgeInsets.all(3),
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                border:
                    hasWorkingAgents
                        ? Border.all(color: colorScheme.tertiary, width: 2)
                        : null,
              ),
              child: CircleAvatar(
                radius: 22,
                child: Icon(favorite ? Icons.star : Icons.terminal),
              ),
            ),
          ),
          if (hasUnreadTaskCompletion)
            Positioned(
              key: ValueKey('project-unread-star-$projectId'),
              right: 0,
              top: 0,
              child: Icon(Icons.star, size: 15, color: colorScheme.error),
            ),
        ],
      ),
    );
  }
}
