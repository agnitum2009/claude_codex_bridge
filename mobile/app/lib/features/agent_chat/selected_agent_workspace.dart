import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart' show ScrollDirection;
import 'package:file_picker/file_picker.dart';
import 'package:mime/mime.dart';
import 'package:path_provider/path_provider.dart';
import 'package:open_filex/open_filex.dart';
import 'package:path/path.dart' as p;

import '../../models/ccb_agent.dart';
import '../../models/ccb_conversation_item.dart';
import '../../models/ccb_project_view.dart';
import '../../repository/mobile_ccb_repository.dart';
import '../../transport/terminal_transport.dart';
import 'agent_chat_controller.dart';
import 'agent_chat_state_helpers.dart';
import 'agent_chat_ui_controller_store.dart';
import 'agent_conversation_refresh_coordinator.dart';
import 'agent_local_message_store.dart';
import 'agent_message_submit_coordinator.dart';
import 'agent_pane_event_coordinator.dart';
import 'agent_pane_message_submitter.dart';
import 'agent_terminal_history_refresh_coordinator.dart';
import 'conversation_refresh_scheduler.dart';
import 'pane_chat_controller.dart';
import 'selected_agent_workspace_model.dart';
import 'selected_agent_workspace_view.dart';

const agentMessageMaxAttachments = 5;
const agentMessageMaxAttachmentBytes = 25 * 1024 * 1024;
const selectedAgentUserRefreshCooldown = Duration(seconds: 5);
const selectedAgentTabKeyBytes = [9];
const selectedAgentEscapeKeyBytes = [27];

class SelectedAgentWorkspace extends StatefulWidget {
  const SelectedAgentWorkspace({
    required this.repository,
    required this.terminalTransport,
    required this.usePaneInputForMessages,
    required this.view,
    required this.agent,
    required this.enableComposerCollapse,
    required this.onRefreshView,
    this.onUserScrollDirectionChanged,
    this.localMessageStore,
  });

  final MobileCcbRepository repository;
  final TerminalTransport? terminalTransport;
  final bool usePaneInputForMessages;
  final CcbProjectView view;
  final CcbAgent? agent;
  final bool enableComposerCollapse;
  final Future<CcbProjectView?> Function()? onRefreshView;
  final ValueChanged<ScrollDirection>? onUserScrollDirectionChanged;
  final AgentLocalMessageStore? localMessageStore;

  @override
  State<SelectedAgentWorkspace> createState() => _SelectedAgentWorkspaceState();
}

class _SelectedAgentWorkspaceState extends State<SelectedAgentWorkspace> {
  final AgentChatController _chatController = AgentChatController();
  final AgentChatUiControllerStore _uiControllers =
      AgentChatUiControllerStore();
  late final AgentLocalMessageStore _localMessageStore =
      widget.localMessageStore ?? AgentLocalMessageStore();
  late final AgentConversationRefreshCoordinator
  _conversationRefreshCoordinator = AgentConversationRefreshCoordinator(
    chatController: _chatController,
    isMounted: () => mounted,
    mutateState: _mutateChatState,
    isTimelineNearEnd: _isTimelineNearEnd,
    scrollTimelineToEnd: _scrollTimelineToEnd,
  );
  late final AgentPaneEventCoordinator _paneEventCoordinator =
      AgentPaneEventCoordinator(
        chatController: _chatController,
        isMounted: () => mounted,
        mutateState: _mutateChatState,
        isTimelineNearEnd: _isTimelineNearEnd,
        scrollTimelineToEnd: _scrollTimelineToEnd,
      );
  late final AgentPaneMessageSubmitter _paneMessageSubmitter =
      AgentPaneMessageSubmitter(onEvent: _handlePaneChatEvent);
  late final AgentTerminalHistoryRefreshCoordinator
  _terminalHistoryRefreshCoordinator = AgentTerminalHistoryRefreshCoordinator(
    chatController: _chatController,
    isMounted: () => mounted,
    mutateState: _mutateChatState,
    isTimelineNearEnd: _isTimelineNearEnd,
    scrollTimelineToEnd: _scrollTimelineToEnd,
  );
  late final AgentMessageSubmitCoordinator _messageSubmitCoordinator =
      AgentMessageSubmitCoordinator(
        chatController: _chatController,
        isMounted: () => mounted,
        mutateState: _mutateChatState,
        isTimelineNearEnd: _isTimelineNearEnd,
        scrollTimelineToEnd: _scrollTimelineToEnd,
        loadConversation: _loadConversation,
        scheduleConversationRefresh: _scheduleConversationRefresh,
        paneSubmitter: _paneMessageSubmitter,
      );
  late final ConversationRefreshScheduler _conversationRefreshScheduler =
      ConversationRefreshScheduler(
        onRefresh: _refreshScheduledConversation,
        isActive: (agentName) => mounted && widget.agent?.name == agentName,
        onStateChanged: _handleRefreshScheduleChanged,
      );
  final Set<String> _downloadingAttachmentIds = {};
  final Map<String, String> _downloadedAttachmentPaths = {};
  final Set<String> _awaitingPaneResponseAgentNames = {};
  final Set<String> _localExceptionStatusAgentNames = {};
  final Map<String, String> _recentPaneOutputText = {};
  final Map<String, DateTime> _lastUserRefreshAt = {};
  final Set<String> _pendingClearNewMessageAgents = {};
  var _nextDraftAttachmentIndex = 0;
  var _refreshingTerminalHistory = false;

  @override
  void initState() {
    super.initState();
    _restoreLocalMessagesForSelectedAgent();
    _loadSelectedAgentConversation();
  }

  @override
  void didUpdateWidget(covariant SelectedAgentWorkspace oldWidget) {
    super.didUpdateWidget(oldWidget);
    final projectOrAgentChanged =
        oldWidget.view.project.id != widget.view.project.id ||
        oldWidget.agent?.name != widget.agent?.name;
    if (oldWidget.repository != widget.repository ||
        oldWidget.terminalTransport != widget.terminalTransport ||
        oldWidget.view.project.id != widget.view.project.id ||
        oldWidget.view.namespaceEpoch != widget.view.namespaceEpoch ||
        oldWidget.agent?.name != widget.agent?.name) {
      if (oldWidget.terminalTransport != widget.terminalTransport ||
          oldWidget.view.project.id != widget.view.project.id ||
          oldWidget.view.namespaceEpoch != widget.view.namespaceEpoch) {
        unawaited(_paneMessageSubmitter.closeSessions());
        _chatController.clearRefreshedTerminalHistories();
      }
      if (projectOrAgentChanged) {
        _restoreLocalMessagesForSelectedAgent();
      }
      _loadSelectedAgentConversation();
    }
  }

  @override
  void dispose() {
    unawaited(_paneMessageSubmitter.closeSessions());
    _uiControllers.dispose();
    _conversationRefreshScheduler.cancelAll(notify: false);
    super.dispose();
  }

  TextEditingController _draftController(String agentName) {
    return _uiControllers.draftController(agentName);
  }

  FocusNode _draftFocusNode(String agentName) {
    return _uiControllers.draftFocusNode(agentName);
  }

  List<CcbMessageAttachment> _draftAttachments(String agentName) {
    return _uiControllers.draftAttachments(agentName);
  }

  void _mutateChatState(void Function() update) {
    if (!mounted) {
      return;
    }
    setState(update);
    final agentName = widget.agent?.name;
    if (agentName != null) {
      unawaited(_persistLocalMessages(agentName));
    }
  }

  Future<void> _restoreLocalMessagesForSelectedAgent() async {
    final agentName = widget.agent?.name;
    if (agentName == null) {
      return;
    }
    final projectId = widget.view.project.id;
    final List<CcbConversationItem> messages;
    try {
      messages = await _localMessageStore.load(
        projectId: projectId,
        agentName: agentName,
      );
    } catch (_) {
      return;
    }
    if (!mounted ||
        widget.view.project.id != projectId ||
        widget.agent?.name != agentName) {
      return;
    }
    setState(() {
      _chatController.restoreLocalMessages(agentName, messages);
    });
  }

  Future<void> _persistLocalMessages(String agentName) async {
    try {
      await _localMessageStore.save(
        projectId: widget.view.project.id,
        agentName: agentName,
        messages: _chatController.localMessagesFor(agentName),
      );
    } catch (_) {
      // Local retry state is best-effort; chat flow should continue.
    }
  }

  void _addAttachments(
    String agentName,
    List<CcbMessageAttachment> attachments,
  ) {
    setState(() {
      _uiControllers.addDraftAttachments(agentName, attachments);
    });
  }

  void _removeAttachment(String agentName, String localId) {
    setState(() {
      _uiControllers.removeDraftAttachment(agentName, localId);
    });
  }

  ScrollController _scrollController(String agentName) {
    return _uiControllers.timelineScrollController(agentName);
  }

  void _toggleExpandedItem(String agentName, String itemId) {
    setState(() {
      _chatController.toggleExpandedItem(agentName, itemId);
    });
  }

  void _loadSelectedAgentConversation() {
    if (!mounted) {
      return;
    }
    final agent = widget.agent;
    if (agent == null) {
      return;
    }
    unawaited(_refreshSelectedAgentConversationAndHistory(agent));
  }

  Future<void> _refreshSelectedAgentConversationAndHistory(
    CcbAgent agent, {
    CcbProjectView? viewOverride,
  }) async {
    if (!mounted || widget.agent?.name != agent.name) {
      return;
    }
    final view = viewOverride ?? widget.view;
    final targetAgent = view.agentByName(agent.name) ?? agent;
    await _loadConversation(agent.name, viewOverride: view);
    if (!mounted || widget.agent?.name != agent.name) {
      return;
    }
    final remoteConversation = _chatController.remoteConversationFor(
      agent.name,
    );
    if (conversationHasTerminalDerivedItems(remoteConversation) ||
        conversationHasProviderNativeItems(remoteConversation)) {
      return;
    }
    await _refreshTerminalHistory(targetAgent, viewOverride: view);
  }

  Future<void> _refreshSelectedAgentConversationAndPaneHistory(
    CcbAgent agent, {
    CcbProjectView? viewOverride,
  }) async {
    if (!mounted || widget.agent?.name != agent.name) {
      return;
    }
    final view = viewOverride ?? widget.view;
    final targetAgent = view.agentByName(agent.name) ?? agent;
    await _loadConversation(agent.name, viewOverride: view);
    if (!mounted || widget.agent?.name != agent.name) {
      return;
    }
    await _refreshTerminalHistory(targetAgent, viewOverride: view);
  }

  void _collapseComposer(String agentName) {
    if (!widget.enableComposerCollapse) {
      return;
    }
    _draftFocusNode(agentName).unfocus();
    setState(() {
      _chatController.collapseComposer(agentName);
    });
  }

  void _expandComposer(String agentName) {
    setState(() {
      _chatController.expandComposer(agentName);
    });
    _draftFocusNode(agentName).requestFocus();
  }

  Future<void> _loadConversation(
    String agentName, {
    CcbProjectView? viewOverride,
  }) async {
    await _conversationRefreshCoordinator.load(
      repository: widget.repository,
      view: viewOverride ?? widget.view,
      agentName: agentName,
      refreshView: widget.onRefreshView,
    );
  }

  Future<void> _refreshTerminalHistory(
    CcbAgent agent, {
    CcbProjectView? viewOverride,
  }) async {
    if (_refreshingTerminalHistory) {
      return;
    }
    _refreshingTerminalHistory = true;
    try {
      await _terminalHistoryRefreshCoordinator.refresh(
        repository: widget.repository,
        agent: agent,
        view: viewOverride ?? widget.view,
      );
    } finally {
      _refreshingTerminalHistory = false;
    }
  }

  Future<void> _sendMessage(CcbAgent agent) async {
    final controller = _draftController(agent.name);
    final attachments = _draftAttachments(agent.name);
    var acceptedPaneMessage = false;

    await _messageSubmitCoordinator.send(
      agent: agent,
      body: controller.text,
      attachments: attachments,
      view: widget.view,
      repository: widget.repository,
      terminalTransport: widget.terminalTransport,
      usePaneInput: widget.usePaneInputForMessages,
      refreshView: widget.onRefreshView,
      onAccepted: () {
        controller.clear();
        _uiControllers.clearDraftAttachments(agent.name);
        _localExceptionStatusAgentNames.remove(agent.name);
        _recentPaneOutputText.remove(agent.name);
        if (widget.usePaneInputForMessages) {
          acceptedPaneMessage = true;
          _awaitingPaneResponseAgentNames.add(agent.name);
        }
      },
    );
    if (!acceptedPaneMessage ||
        !mounted ||
        widget.agent?.name != agent.name ||
        _conversationRefreshScheduler.isPending(agent.name)) {
      return;
    }
    setState(() {
      _awaitingPaneResponseAgentNames.remove(agent.name);
    });
  }

  Future<void> _sendPaneKey(
    CcbAgent agent, {
    required List<int> bytes,
    required String label,
  }) async {
    final outcome = await _paneMessageSubmitter.sendKey(
      transport: widget.terminalTransport,
      agent: agent,
      view: widget.view,
      refreshView: widget.onRefreshView,
      bytes: bytes,
    );
    if (!mounted || widget.agent?.name != agent.name) {
      return;
    }
    if (!outcome.sent) {
      _showSnack('Could not send $label: ${outcome.error}');
      return;
    }
    _refreshLatest(agent.name);
    _scheduleConversationRefresh(agent.name);
  }

  Future<void> _sendDraftThenPaneKey(
    CcbAgent agent, {
    required List<int> bytes,
    required String label,
  }) async {
    final controller = _draftController(agent.name);
    final body = controller.text;
    if (body.isEmpty) {
      await _sendPaneKey(agent, bytes: bytes, label: label);
      return;
    }
    final outcome = await _paneMessageSubmitter.sendTextThenKey(
      transport: widget.terminalTransport,
      agent: agent,
      view: widget.view,
      refreshView: widget.onRefreshView,
      body: body,
      bytes: bytes,
    );
    if (!mounted || widget.agent?.name != agent.name) {
      return;
    }
    if (!outcome.sent) {
      _showSnack('Could not send $label: ${outcome.error}');
      return;
    }
    setState(() {
      controller.clear();
      _awaitingPaneResponseAgentNames.add(agent.name);
    });
    _refreshLatest(agent.name);
    _scheduleConversationRefresh(agent.name);
  }

  Future<void> _pickAttachments({
    required String agentName,
    required FileType type,
  }) async {
    try {
      final result = await FilePicker.pickFiles(
        allowMultiple: true,
        type: type,
        allowedExtensions:
            type == FileType.custom
                ? const ['pdf', 'txt', 'md', 'doc', 'docx']
                : null,
      );
      if (result == null || result.files.isEmpty) {
        return;
      }
      final current = _draftAttachments(agentName);
      final remainingSlots = agentMessageMaxAttachments - current.length;
      if (remainingSlots <= 0) {
        _showSnack('Attach up to $agentMessageMaxAttachments files');
        return;
      }
      final accepted = <CcbMessageAttachment>[];
      for (final file in result.files.take(remainingSlots)) {
        final path = file.path;
        if (path == null || path.isEmpty) {
          continue;
        }
        final size = file.size;
        if (size > agentMessageMaxAttachmentBytes) {
          _showSnack('${file.name} is larger than 25 MB');
          continue;
        }
        final fileName = file.name.isEmpty ? p.basename(path) : file.name;
        final extension = _attachmentExtension(
          pickerExtension: file.extension,
          fileName: fileName,
          path: path,
        );
        final mimeType =
            lookupMimeType(path) ??
            _mimeTypeForExtension(extension) ??
            'application/octet-stream';
        if (!_isSupportedAttachment(
          type: type,
          extension: extension,
          mimeType: mimeType,
        )) {
          _showSnack('$fileName is not a supported attachment type');
          continue;
        }
        final localId = 'draft-$agentName-${_nextDraftAttachmentIndex++}';
        final storedPath = await _copyDraftAttachmentFile(
          sourcePath: path,
          localId: localId,
          fileName: fileName,
        );
        accepted.add(
          CcbMessageAttachment(
            fileId: localId,
            fileName: fileName,
            mimeType: mimeType,
            sizeBytes: size,
            localPath: storedPath,
            kind:
                mimeType.startsWith('image/')
                    ? CcbMessageAttachmentKind.image
                    : CcbMessageAttachmentKind.document,
            state: CcbMessageAttachmentState.queued,
          ),
        );
      }
      if (accepted.isNotEmpty) {
        _addAttachments(agentName, accepted);
        _focusComposer(agentName);
      }
      if (result.files.length > remainingSlots) {
        _showSnack('Attach up to $agentMessageMaxAttachments files');
      }
    } catch (error) {
      _showSnack('Could not pick attachment: $error');
    }
  }

  Future<String> _copyDraftAttachmentFile({
    required String sourcePath,
    required String localId,
    required String fileName,
  }) async {
    if (!Platform.isAndroid && !Platform.isIOS) {
      return sourcePath;
    }
    try {
      final dir = await getApplicationDocumentsDirectory();
      final draftDir = Directory(p.join(dir.path, 'draft_attachments'));
      await draftDir.create(recursive: true);
      final safeName = _safeFileName(fileName);
      final target = File(
        p.join(draftDir.path, '${_safeFileName(localId)}-$safeName'),
      );
      return (await File(sourcePath).copy(target.path)).path;
    } catch (_) {
      return sourcePath;
    }
  }

  Future<void> _downloadAndOpenAttachment(
    CcbAgent agent,
    CcbMessageAttachment attachment,
  ) async {
    try {
      final localPath = attachment.localPath;
      if (localPath != null && localPath.isNotEmpty) {
        await _openAttachmentFile(localPath);
        return;
      }
      final downloadedPath = _downloadedAttachmentPaths[attachment.fileId];
      if (downloadedPath != null) {
        await _openAttachmentFile(downloadedPath);
        return;
      }
      if (_downloadingAttachmentIds.contains(attachment.fileId)) {
        return;
      }
      setState(() {
        _downloadingAttachmentIds.add(attachment.fileId);
      });
      final bytes = await widget.repository.downloadFile(
        projectId: widget.view.project.id,
        agentName: agent.name,
        fileId: attachment.fileId,
      );
      final dir = await getApplicationDocumentsDirectory();
      final file = File(p.join(dir.path, _safeFileName(attachment.fileName)));
      await file.writeAsBytes(bytes);
      if (!mounted) {
        return;
      }
      setState(() {
        _downloadedAttachmentPaths[attachment.fileId] = file.path;
      });
      _showSnack('Saved ${attachment.fileName}');
    } catch (error) {
      _showSnack('Failed to open file: $error');
    } finally {
      if (mounted) {
        setState(() {
          _downloadingAttachmentIds.remove(attachment.fileId);
        });
      }
    }
  }

  Future<void> _openAttachmentFile(String path) async {
    await OpenFilex.open(path);
  }

  void _showSnack(String message) {
    if (!mounted) {
      return;
    }
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(message)));
  }

  String _appendRecentPaneOutput({
    required String agentName,
    required String output,
  }) {
    final previous = _recentPaneOutputText[agentName];
    final combined =
        previous == null || previous.isEmpty ? output : '$previous $output';
    final start = combined.length > 1000 ? combined.length - 1000 : 0;
    final recent = combined.substring(start);
    _recentPaneOutputText[agentName] = recent;
    return recent;
  }

  Future<void> _retryMessage(CcbConversationItem item) async {
    await _messageSubmitCoordinator.retry(
      item: item,
      view: widget.view,
      repository: widget.repository,
      terminalTransport: widget.terminalTransport,
      usePaneInput: widget.usePaneInputForMessages,
      refreshView: widget.onRefreshView,
    );
  }

  void _handlePaneChatEvent(PaneChatEvent event) {
    if (event.kind == PaneChatEventKind.output) {
      if (!mounted) {
        return;
      }
      setState(() {
        final recentOutput = _appendRecentPaneOutput(
          agentName: event.agentName,
          output: event.body,
        );
        if (_paneOutputHasTerminalException(recentOutput)) {
          _awaitingPaneResponseAgentNames.remove(event.agentName);
          _localExceptionStatusAgentNames.add(event.agentName);
        } else {
          _awaitingPaneResponseAgentNames.add(event.agentName);
        }
      });
      return;
    }
    final wasAwaiting = _awaitingPaneResponseAgentNames.remove(event.agentName);
    final changed = _paneEventCoordinator.apply(event);
    if (wasAwaiting && mounted && !changed) {
      setState(() {});
    }
  }

  void _scheduleConversationRefresh(String agentName) {
    _localExceptionStatusAgentNames.remove(agentName);
    _recentPaneOutputText.remove(agentName);
    _awaitingPaneResponseAgentNames.add(agentName);
    _conversationRefreshScheduler.schedule(agentName);
  }

  Future<void> _refreshScheduledConversation(String agentName) async {
    final agent = widget.agent;
    if (agent == null || agent.name != agentName) {
      return;
    }
    await _refreshLatestForAgent(agent, refreshViewFirst: true);
  }

  void _handleRefreshScheduleChanged() {
    if (!mounted) {
      return;
    }
    final selectedAgentName = widget.agent?.name;
    if (selectedAgentName != null &&
        !_conversationRefreshScheduler.isPending(selectedAgentName)) {
      _awaitingPaneResponseAgentNames.remove(selectedAgentName);
    }
    setState(() {});
  }

  void _refreshLatest(String agentName) {
    final agent = widget.agent;
    if (agent == null || agent.name != agentName) {
      return;
    }
    unawaited(_refreshLatestForAgent(agent, refreshViewFirst: true));
  }

  Future<void> _refreshLatestForAgent(
    CcbAgent agent, {
    required bool refreshViewFirst,
  }) async {
    var view = widget.view;
    if (refreshViewFirst) {
      final refreshed = await widget.onRefreshView?.call();
      if (!mounted || widget.agent?.name != agent.name) {
        return;
      }
      if (refreshed != null) {
        view = refreshed;
        _syncLocalExecutionStateFromView(
          view: refreshed,
          agentName: agent.name,
        );
      }
    }
    await (widget.usePaneInputForMessages
        ? _refreshSelectedAgentConversationAndPaneHistory(
          agent,
          viewOverride: view,
        )
        : _refreshSelectedAgentConversationAndHistory(
          agent,
          viewOverride: view,
        ));
  }

  void _refreshLatestFromUserScroll(String agentName) {
    if (_chatController.isLoadingConversation(agentName)) {
      return;
    }
    final now = DateTime.now();
    final previous = _lastUserRefreshAt[agentName];
    if (previous != null &&
        now.difference(previous) < selectedAgentUserRefreshCooldown) {
      return;
    }
    _lastUserRefreshAt[agentName] = now;
    _refreshLatest(agentName);
  }

  void _syncLocalExecutionStateFromView({
    required CcbProjectView view,
    required String agentName,
  }) {
    final refreshedAgent = view.agentByName(agentName);
    if (refreshedAgent == null) {
      return;
    }
    final status = agentExecutionStatus(
      agent: refreshedAgent,
      isAwaitingAgentResponse: false,
      isLoadingConversation: false,
    );
    if (status?.state == 'working') {
      return;
    }
    _awaitingPaneResponseAgentNames.remove(agentName);
    if (status?.state == 'idle') {
      _localExceptionStatusAgentNames.remove(agentName);
    }
  }

  bool _isTimelineNearEnd(String agentName) {
    return _uiControllers.isTimelineNearEnd(agentName);
  }

  Future<void> _loadOlderConversation(String agentName) async {
    if (!_chatController.hasOlderConversation(agentName) ||
        _chatController.isLoadingConversation(agentName)) {
      return;
    }
    final controller = _scrollController(agentName);
    final beforeMax =
        controller.hasClients ? controller.position.maxScrollExtent : null;
    final beforePixels =
        controller.hasClients ? controller.position.pixels : null;
    final changed = await _conversationRefreshCoordinator.loadOlder(
      repository: widget.repository,
      view: widget.view,
      agentName: agentName,
      refreshView: widget.onRefreshView,
    );
    if (!changed || beforeMax == null || beforePixels == null) {
      return;
    }
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted ||
          widget.agent?.name != agentName ||
          !controller.hasClients) {
        return;
      }
      final delta = controller.position.maxScrollExtent - beforeMax;
      final target = (beforePixels + delta).clamp(
        controller.position.minScrollExtent,
        controller.position.maxScrollExtent,
      );
      controller.jumpTo(target);
    });
  }

  void _clearNewMessageFlag(String agentName) {
    if (!_chatController.hasNewMessages(agentName)) {
      return;
    }
    if (!_pendingClearNewMessageAgents.add(agentName)) {
      return;
    }
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _pendingClearNewMessageAgents.remove(agentName);
      if (!mounted ||
          widget.agent?.name != agentName ||
          !_chatController.hasNewMessages(agentName)) {
        return;
      }
      setState(() {
        _chatController.clearNewMessageFlag(agentName);
      });
    });
  }

  void _jumpToLatest(String agentName) {
    setState(() {
      _chatController.clearNewMessageFlag(agentName);
    });
    _scrollTimelineToEnd(agentName);
  }

  void _scrollTimelineToEnd(String agentName, {int attempt = 0}) {
    _uiControllers.scrollTimelineToEnd(
      agentName,
      isActive: (agentName) => mounted && widget.agent?.name == agentName,
      attempt: attempt,
    );
  }

  @override
  Widget build(BuildContext context) {
    final selectedAgent = widget.agent;
    if (selectedAgent == null) {
      return const NoSelectedAgentWorkspaceView();
    }
    final model = selectedAgentWorkspaceModel(
      view: widget.view,
      agent: selectedAgent,
      chatController: _chatController,
      isAwaitingAgentResponse: _awaitingPaneResponseAgentNames.contains(
        selectedAgent.name,
      ),
      hasLocalExecutionException: _localExceptionStatusAgentNames.contains(
        selectedAgent.name,
      ),
    );
    return SelectedAgentWorkspaceView(
      repository: widget.repository,
      view: widget.view,
      model: model,
      timelineController: _scrollController(selectedAgent.name),
      draftController: _draftController(selectedAgent.name),
      draftFocusNode: _draftFocusNode(selectedAgent.name),
      enableComposerCollapse: widget.enableComposerCollapse,
      draftAttachments: _draftAttachments(selectedAgent.name),
      downloadingAttachmentIds: _downloadingAttachmentIds,
      downloadedAttachmentIds: _downloadedAttachmentPaths.keys.toSet(),
      onPickImageAttachment: () {
        _pickAttachments(agentName: selectedAgent.name, type: FileType.image);
      },
      onPickFileAttachment: () {
        _pickAttachments(agentName: selectedAgent.name, type: FileType.custom);
      },
      onRemoveAttachment: (localId) {
        _removeAttachment(selectedAgent.name, localId);
      },
      onDownloadAttachment: (attachment) {
        _downloadAndOpenAttachment(selectedAgent, attachment);
      },
      onRetry: _retryMessage,
      onToggleExpanded: (itemId) {
        _toggleExpandedItem(selectedAgent.name, itemId);
      },
      onRefreshLatest: () {
        _refreshLatest(selectedAgent.name);
      },
      onNearEnd: () {
        _clearNewMessageFlag(selectedAgent.name);
      },
      onUserNearEnd: () {
        _refreshLatestFromUserScroll(selectedAgent.name);
      },
      onUserScrollDirectionChanged: (direction) {
        widget.onUserScrollDirectionChanged?.call(direction);
      },
      onNearStart: () {
        _loadOlderConversation(selectedAgent.name);
      },
      onJumpToLatest: () {
        _jumpToLatest(selectedAgent.name);
      },
      onCollapseComposer: () {
        _collapseComposer(selectedAgent.name);
      },
      onExpandComposer: () {
        _expandComposer(selectedAgent.name);
      },
      onSend: () {
        _sendMessage(selectedAgent);
      },
      onSendTab: () {
        _sendDraftThenPaneKey(
          selectedAgent,
          bytes: selectedAgentTabKeyBytes,
          label: 'Tab',
        );
      },
      onSendEscape: () {
        _sendPaneKey(
          selectedAgent,
          bytes: selectedAgentEscapeKeyBytes,
          label: 'Esc',
        );
      },
    );
  }

  void _focusComposer(String agentName) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || widget.agent?.name != agentName) {
        return;
      }
      _draftFocusNode(agentName).requestFocus();
    });
  }
}

String? _mimeTypeForExtension(String? extension) {
  return switch (extension?.toLowerCase()) {
    'pdf' => 'application/pdf',
    'txt' => 'text/plain',
    'md' => 'text/markdown',
    'doc' => 'application/msword',
    'docx' =>
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    _ => null,
  };
}

String? _attachmentExtension({
  required String? pickerExtension,
  required String fileName,
  required String path,
}) {
  if (pickerExtension != null && pickerExtension.isNotEmpty) {
    return pickerExtension.toLowerCase();
  }
  final fileNameExtension = p.extension(fileName);
  if (fileNameExtension.isNotEmpty) {
    return fileNameExtension.substring(1).toLowerCase();
  }
  final pathExtension = p.extension(path);
  if (pathExtension.isNotEmpty) {
    return pathExtension.substring(1).toLowerCase();
  }
  return null;
}

bool _isSupportedAttachment({
  required FileType type,
  required String? extension,
  required String mimeType,
}) {
  if (type == FileType.image) {
    return mimeType.startsWith('image/');
  }
  return _mimeTypeForExtension(extension) != null;
}

bool _paneOutputHasTerminalException(String output) {
  final text = output.trim().toLowerCase();
  if (text.isEmpty || text.contains('esc to interrupt')) {
    return false;
  }
  return text.contains('conversation interrupted') ||
      text.contains('request interrupted') ||
      text.contains('interrupted by user') ||
      text.contains('cancelled') ||
      text.contains('canceled') ||
      text.contains('aborted');
}

String _safeFileName(String fileName) {
  final cleaned = fileName.replaceAll(RegExp(r'[\\/:*?"<>|]+'), '_').trim();
  return cleaned.isEmpty ? 'attachment' : cleaned;
}
