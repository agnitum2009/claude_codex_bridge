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
    super.key,
  });

  final CcbProjectView view;
  final CcbAgent? selectedAgent;
  final VoidCallback onOpenProject;
  final VoidCallback onOpenNotifications;
  final VoidCallback onOpenConnectionDetails;

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
    super.key,
  });

  final CcbProjectView view;
  final CcbAgent? selectedAgent;
  final bool selected;
  final VoidCallback onOpen;

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
      leading: CircleAvatar(
        radius: 22,
        child: Icon(view.project.favorite ? Icons.star : Icons.terminal),
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
