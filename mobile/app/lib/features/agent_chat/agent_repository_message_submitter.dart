import 'dart:io';

import '../../models/ccb_agent.dart';
import '../../models/ccb_agent_conversation.dart';
import '../../models/ccb_conversation_item.dart';
import '../../models/ccb_project_view.dart';
import '../../repository/mobile_ccb_repository.dart';
import 'agent_chat_state_helpers.dart';
import 'agent_conversation_loader.dart';

class AgentRepositoryMessageSubmitter {
  const AgentRepositoryMessageSubmitter({
    required MobileCcbRepository repository,
    AgentViewRefresh? refreshView,
  }) : _repository = repository,
       _refreshView = refreshView;

  final MobileCcbRepository _repository;
  final AgentViewRefresh? _refreshView;

  Future<AgentRepositoryMessageSubmitOutcome> submit({
    required CcbAgent agent,
    required CcbConversationItem message,
    required CcbProjectView view,
    bool allowStaleRefresh = true,
  }) async {
    final namespaceEpoch = view.namespaceEpoch;
    if (namespaceEpoch == null) {
      return AgentRepositoryMessageSubmitOutcome.replaceLocalMessage(
        message.copyWith(state: CcbConversationDeliveryState.failed),
      );
    }
    try {
      final uploadedAttachments = await uploadAttachments(
        agent: agent,
        message: message,
        view: view,
      );
      final result = await _repository.submitAgentMessage(
        CcbAgentMessageSubmitRequest(
          projectId: view.project.id,
          agentName: agent.name,
          namespaceEpoch: namespaceEpoch,
          idempotencyKey: message.id,
          body: message.body,
          attachments: uploadedAttachments,
        ),
      );
      final resultMessage = result.message;
      final replacementBase =
          resultMessage == null
              ? message
              : resultMessage.copyWith(
                sentAt: resultMessage.sentAt ?? message.sentAt,
                startedAt: resultMessage.startedAt ?? message.startedAt,
                completedAt: resultMessage.completedAt ?? message.completedAt,
                durationMs: resultMessage.durationMs ?? message.durationMs,
              );
      final replacement = replacementBase.copyWith(
        state: result.state,
        attachments:
            resultMessage?.attachments.isNotEmpty == true
                ? null
                : uploadedAttachments,
      );
      final conversation = result.conversation;
      if (conversation != null) {
        return AgentRepositoryMessageSubmitOutcome.remoteConversation(
          conversation,
          replacement: replacement,
        );
      }
      return AgentRepositoryMessageSubmitOutcome.replaceLocalMessage(
        replacement,
        shouldRefreshConversation: true,
      );
    } catch (error) {
      if (allowStaleRefresh && isStaleNamespaceEpochError(error)) {
        final refreshed = await _refreshView?.call();
        if (refreshed != null && refreshed.agentByName(agent.name) != null) {
          return submit(
            agent: agent,
            message: message,
            view: refreshed,
            allowStaleRefresh: false,
          );
        }
      }
      return AgentRepositoryMessageSubmitOutcome.replaceLocalMessage(
        _failedMessage(message, error),
      );
    }
  }

  Future<List<CcbMessageAttachment>> uploadAttachments({
    required CcbAgent agent,
    required CcbConversationItem message,
    required CcbProjectView view,
  }) async {
    if (message.attachments.isEmpty) {
      return const [];
    }
    final uploaded = <CcbMessageAttachment>[];
    for (final attachment in message.attachments) {
      final path = attachment.localPath;
      if (path == null || path.isEmpty) {
        uploaded.add(
          attachment.copyWith(
            state: CcbMessageAttachmentState.available,
            clearLocalPath: true,
            clearErrorMessage: true,
          ),
        );
        continue;
      }
      final fileUploader = _repository;
      final result =
          fileUploader is MobileCcbRepositoryFileUploader
              ? await (fileUploader as MobileCcbRepositoryFileUploader)
                  .uploadFileFromPath(
                    projectId: view.project.id,
                    agentName: agent.name,
                    fileName: attachment.fileName,
                    mimeType: attachment.mimeType,
                    path: path,
                  )
              : await _repository.uploadFile(
                projectId: view.project.id,
                agentName: agent.name,
                fileName: attachment.fileName,
                mimeType: attachment.mimeType,
                bytes: await File(path).readAsBytes(),
              );
      uploaded.add(
        CcbMessageAttachment(
          fileId: result.fileId,
          fileName:
              result.fileName.isEmpty ? attachment.fileName : result.fileName,
          mimeType: result.mimeType ?? attachment.mimeType,
          sizeBytes: result.sizeBytes ?? attachment.sizeBytes,
          kind: attachment.effectiveKind,
          state: CcbMessageAttachmentState.available,
        ),
      );
    }
    return uploaded;
  }

  CcbConversationItem _failedMessage(
    CcbConversationItem message,
    Object error,
  ) {
    return message.copyWith(
      state: CcbConversationDeliveryState.failed,
      attachments: [
        for (final attachment in message.attachments)
          attachment.copyWith(
            state:
                attachment.state == CcbMessageAttachmentState.available
                    ? attachment.state
                    : CcbMessageAttachmentState.failed,
            errorMessage: error.toString(),
          ),
      ],
    );
  }
}

class AgentRepositoryMessageSubmitOutcome {
  const AgentRepositoryMessageSubmitOutcome._({
    this.conversation,
    this.replacement,
    this.shouldRefreshConversation = false,
  });

  factory AgentRepositoryMessageSubmitOutcome.remoteConversation(
    CcbAgentConversation conversation, {
    required CcbConversationItem replacement,
  }) {
    return AgentRepositoryMessageSubmitOutcome._(
      conversation: conversation,
      replacement: replacement,
    );
  }

  factory AgentRepositoryMessageSubmitOutcome.replaceLocalMessage(
    CcbConversationItem replacement, {
    bool shouldRefreshConversation = false,
  }) {
    return AgentRepositoryMessageSubmitOutcome._(
      replacement: replacement,
      shouldRefreshConversation: shouldRefreshConversation,
    );
  }

  final CcbAgentConversation? conversation;
  final CcbConversationItem? replacement;
  final bool shouldRefreshConversation;

  bool get hasRemoteConversation => conversation != null;
}
