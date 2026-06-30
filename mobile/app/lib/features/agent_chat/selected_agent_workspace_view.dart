import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart' show HitTestBehavior, ScrollDirection;

import '../../l10n/ccb_mobile_localizations.dart';
import '../../models/ccb_conversation_item.dart';
import '../../models/ccb_project_view.dart';
import '../../repository/mobile_ccb_repository.dart';
import 'agent_message_composer.dart';
import 'conversation_timeline.dart';
import 'selected_agent_workspace_model.dart';

class NoSelectedAgentWorkspaceView extends StatelessWidget {
  const NoSelectedAgentWorkspaceView({super.key});

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final strings = CcbMobileLocalizations.of(context);
    return DecoratedBox(
      key: const ValueKey('selected-agent-workspace'),
      decoration: BoxDecoration(
        border: Border.all(color: colorScheme.outlineVariant),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Text(strings.noAgents),
      ),
    );
  }
}

class SelectedAgentWorkspaceView extends StatelessWidget {
  const SelectedAgentWorkspaceView({
    required this.repository,
    required this.view,
    required this.model,
    required this.timelineController,
    required this.draftController,
    required this.draftFocusNode,
    required this.enableComposerCollapse,
    required this.onRetry,
    required this.onToggleExpanded,
    required this.onRefreshLatest,
    required this.onNearEnd,
    required this.onUserNearEnd,
    required this.onNearStart,
    required this.onUserScrollDirectionChanged,
    required this.onJumpToLatest,
    required this.onCollapseComposer,
    required this.onExpandComposer,
    required this.draftAttachments,
    required this.downloadingAttachmentIds,
    required this.downloadedAttachmentIds,
    required this.onPickImageAttachment,
    required this.onPickFileAttachment,
    required this.onRemoveAttachment,
    required this.onDownloadAttachment,
    required this.onSend,
    required this.onSendTab,
    required this.onSendEscape,
    super.key,
  });

  final MobileCcbRepository repository;
  final CcbProjectView view;
  final SelectedAgentWorkspaceModel model;
  final ScrollController timelineController;
  final TextEditingController draftController;
  final FocusNode draftFocusNode;
  final bool enableComposerCollapse;
  final ValueChanged<CcbConversationItem> onRetry;
  final ValueChanged<String> onToggleExpanded;
  final VoidCallback onRefreshLatest;
  final VoidCallback onNearEnd;
  final VoidCallback onUserNearEnd;
  final VoidCallback onNearStart;
  final ValueChanged<ScrollDirection> onUserScrollDirectionChanged;
  final VoidCallback onJumpToLatest;
  final VoidCallback onCollapseComposer;
  final VoidCallback onExpandComposer;
  final List<CcbMessageAttachment> draftAttachments;
  final Set<String> downloadingAttachmentIds;
  final Set<String> downloadedAttachmentIds;
  final VoidCallback onPickImageAttachment;
  final VoidCallback onPickFileAttachment;
  final ValueChanged<String> onRemoveAttachment;
  final ValueChanged<CcbMessageAttachment> onDownloadAttachment;
  final VoidCallback onSend;
  final VoidCallback onSendTab;
  final VoidCallback onSendEscape;

  @override
  Widget build(BuildContext context) {
    final strings = CcbMobileLocalizations.of(context);
    return Column(
      key: const ValueKey('selected-agent-workspace'),
      children: [
        Expanded(
          child: _ComposerDismissRegion(
            key: const ValueKey('agent-compose-dismiss-region'),
            onDismiss: onCollapseComposer,
            child: ConversationTimeline(
              key: ValueKey('agent-chat-timeline-${model.agent.name}'),
              repository: repository,
              view: view,
              agent: model.agent,
              contentItems: model.contentItems,
              initialHistory: model.initialHistory,
              items: model.timelineItems,
              isLoading: model.isLoadingConversation,
              controller: timelineController,
              expandedItemIds: model.expandedItemIds,
              downloadingAttachmentIds: downloadingAttachmentIds,
              downloadedAttachmentIds: downloadedAttachmentIds,
              onRetry: onRetry,
              onToggleExpanded: onToggleExpanded,
              onNearEnd: onNearEnd,
              onUserNearEnd: onUserNearEnd,
              onNearStart: onNearStart,
              onUserScrollDirectionChanged: onUserScrollDirectionChanged,
              hasOlderItems: model.hasOlderConversation,
              onDownloadAttachment: onDownloadAttachment,
            ),
          ),
        ),
        const SizedBox(height: 4),
        SizedBox(
          height: 36,
          child: Row(
            children: [
              IconButton(
                key: const ValueKey('agent-conversation-refresh-action'),
                tooltip: strings.refreshConversation,
                onPressed: model.isLoadingConversation ? null : onRefreshLatest,
                icon: const Icon(Icons.refresh),
                iconSize: 20,
                padding: EdgeInsets.zero,
                constraints: const BoxConstraints.tightFor(
                  width: 36,
                  height: 36,
                ),
              ),
              if (model.executionStatus != null)
                _AgentWorkingStatus(status: model.executionStatus!),
              const Spacer(),
              if (model.hasNewMessages)
                TextButton.icon(
                  key: const ValueKey('agent-new-messages-jump'),
                  onPressed: onJumpToLatest,
                  icon: const Icon(Icons.south, size: 18),
                  label: Text(strings.newMessages),
                  style: TextButton.styleFrom(
                    visualDensity: VisualDensity.compact,
                  ),
                ),
            ],
          ),
        ),
        if (model.commsItems.isNotEmpty) ...[
          const SizedBox(height: 6),
          _AgentCommsStatusStrip(item: model.commsItems.last),
        ],
        const SizedBox(height: 8),
        AgentMessageComposer(
          agentName: model.agent.name,
          controller: draftController,
          focusNode: draftFocusNode,
          isSending: model.isSending,
          collapsible: enableComposerCollapse,
          collapsed: enableComposerCollapse && model.isComposerCollapsed,
          onCollapse: onCollapseComposer,
          onExpand: onExpandComposer,
          draftAttachments: draftAttachments,
          onPickImage: onPickImageAttachment,
          onPickFile: onPickFileAttachment,
          onRemoveAttachment: onRemoveAttachment,
          onSend: onSend,
          onSendTab: onSendTab,
          onSendEscape: onSendEscape,
        ),
      ],
    );
  }
}

class _ComposerDismissRegion extends StatefulWidget {
  const _ComposerDismissRegion({
    required this.onDismiss,
    required this.child,
    super.key,
  });

  final VoidCallback onDismiss;
  final Widget child;

  @override
  State<_ComposerDismissRegion> createState() => _ComposerDismissRegionState();
}

class _ComposerDismissRegionState extends State<_ComposerDismissRegion> {
  static const double _tapSlop = 12;

  int? _pointer;
  Offset? _downPosition;

  void _handlePointerDown(PointerDownEvent event) {
    _pointer ??= event.pointer;
    if (_pointer != event.pointer) {
      return;
    }
    _downPosition = event.position;
  }

  void _handlePointerUp(PointerUpEvent event) {
    if (_pointer != event.pointer) {
      return;
    }
    final downPosition = _downPosition;
    _pointer = null;
    _downPosition = null;
    if (downPosition == null) {
      return;
    }
    if ((event.position - downPosition).distance <= _tapSlop) {
      widget.onDismiss();
    }
  }

  void _handlePointerCancel(PointerCancelEvent event) {
    if (_pointer == event.pointer) {
      _pointer = null;
      _downPosition = null;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Listener(
      behavior: HitTestBehavior.translucent,
      onPointerDown: _handlePointerDown,
      onPointerUp: _handlePointerUp,
      onPointerCancel: _handlePointerCancel,
      child: widget.child,
    );
  }
}

class _AgentWorkingStatus extends StatelessWidget {
  const _AgentWorkingStatus({required this.status});

  final AgentExecutionStatus status;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;
    final statusColor = switch (status.state) {
      'exception' => colorScheme.error,
      'idle' => colorScheme.onSurfaceVariant,
      _ => colorScheme.primary,
    };
    return Padding(
      key: const ValueKey('agent-working-status'),
      padding: const EdgeInsets.only(left: 4),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          SizedBox.square(
            dimension: 14,
            child: _statusIcon(status, statusColor),
          ),
          const SizedBox(width: 6),
          Text(
            CcbMobileLocalizations.of(context).executionStatus(status.label),
            style: textTheme.labelMedium?.copyWith(color: statusColor),
          ),
        ],
      ),
    );
  }

  Widget _statusIcon(AgentExecutionStatus status, Color color) {
    if (status.isRefreshing) {
      return CircularProgressIndicator(strokeWidth: 2, color: color);
    }
    if (status.state == 'working') {
      return Icon(Icons.hourglass_top, size: 14, color: color);
    }
    if (status.state == 'exception') {
      return Icon(Icons.error_outline, size: 14, color: color);
    }
    return Icon(Icons.check_circle_outline, size: 14, color: color);
  }
}

class _AgentCommsStatusStrip extends StatelessWidget {
  const _AgentCommsStatusStrip({required this.item});

  final CcbConversationItem item;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;
    final strings = CcbMobileLocalizations.of(context);
    final summary = _summaryText(item);
    return Padding(
      key: const ValueKey('agent-comms-status'),
      padding: const EdgeInsets.symmetric(horizontal: 4),
      child: Row(
        children: [
          Icon(Icons.forum_outlined, size: 18, color: colorScheme.primary),
          const SizedBox(width: 6),
          Text(
            strings.communicating,
            style: textTheme.labelLarge?.copyWith(color: colorScheme.primary),
          ),
          if (summary.isNotEmpty) ...[
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                summary,
                key: const ValueKey('agent-comms-status-summary'),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: textTheme.bodySmall?.copyWith(
                  color: colorScheme.onSurfaceVariant,
                ),
              ),
            ),
          ] else
            const Spacer(),
        ],
      ),
    );
  }
}

String _summaryText(CcbConversationItem item) {
  final body = item.body.trim();
  if (body.isNotEmpty) {
    return body;
  }
  final source = item.source?.trim();
  if (source != null && source.isNotEmpty) {
    return source;
  }
  return item.title.trim();
}
