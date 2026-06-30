import 'dart:async';
import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:file_picker/src/platform/file_picker_platform_interface.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:xterm/xterm.dart';

import 'package:ccb_mobile/ccb_mobile.dart';
import 'package:ccb_mobile/features/agent_chat/agent_message_composer.dart';
import 'package:ccb_mobile/features/agent_chat/selected_agent_workspace.dart';
import 'package:ccb_mobile/features/agent_chat/selected_agent_workspace_model.dart';
import 'package:ccb_mobile/features/agent_chat/selected_agent_workspace_view.dart';

import 'support/project_home_test_driver.dart';
import 'support/project_home_test_fakes.dart';

void main() {
  testWidgets('message composer sends on hardware enter', (tester) async {
    final controller = TextEditingController(text: 'hello mobile');
    var sendCount = 0;

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: AgentMessageComposer(
            agentName: 'mobile',
            controller: controller,
            isSending: false,
            collapsible: false,
            collapsed: false,
            onCollapse: () {},
            onExpand: () {},
            draftAttachments: const [],
            onPickImage: () {},
            onPickFile: () {},
            onRemoveAttachment: (_) {},
            onSend: () {
              sendCount += 1;
            },
            onSendTab: () {},
            onSendEscape: () {},
          ),
        ),
      ),
    );

    await tester.tap(find.byKey(const ValueKey('agent-message-composer')));
    await tester.pump();
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pump();

    expect(sendCount, 1);
  });

  testWidgets('message composer ignores hardware enter while sending', (
    tester,
  ) async {
    final controller = TextEditingController(text: 'hello mobile');
    var sendCount = 0;

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: AgentMessageComposer(
            agentName: 'mobile',
            controller: controller,
            isSending: true,
            collapsible: false,
            collapsed: false,
            onCollapse: () {},
            onExpand: () {},
            draftAttachments: const [],
            onPickImage: () {},
            onPickFile: () {},
            onRemoveAttachment: (_) {},
            onSend: () {
              sendCount += 1;
            },
            onSendTab: () {},
            onSendEscape: () {},
          ),
        ),
      ),
    );

    await tester.tap(find.byKey(const ValueKey('agent-message-composer')));
    await tester.pump();
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pump();

    expect(sendCount, 0);
  });

  testWidgets('agent status prioritizes working over refresh after send', (
    tester,
  ) async {
    final agent = CcbAgent(
      name: 'mobile',
      provider: 'codex',
      window: 'main',
      order: 0,
      active: true,
      queueDepth: 0,
    );
    final draftController = TextEditingController();
    final focusNode = FocusNode();
    final timelineController = ScrollController();
    addTearDown(draftController.dispose);
    addTearDown(focusNode.dispose);
    addTearDown(timelineController.dispose);

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SelectedAgentWorkspaceView(
            repository: FakeMobileCcbRepository.demo(),
            view: _workspaceView(agent),
            model: SelectedAgentWorkspaceModel(
              agent: agent,
              contentItems: const [],
              initialHistory: null,
              timelineItems: const [],
              commsItems: const [],
              isLoadingConversation: true,
              hasOlderConversation: false,
              expandedItemIds: const {},
              hasNewMessages: false,
              isSending: true,
              isAwaitingAgentResponse: true,
              isComposerCollapsed: false,
              executionStatus: agentExecutionStatus(
                agent: agent,
                isAwaitingAgentResponse: true,
                isLoadingConversation: true,
              ),
            ),
            timelineController: timelineController,
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
    );

    expect(find.byKey(const ValueKey('agent-working-status')), findsOneWidget);
    expect(find.text('Working'), findsOneWidget);
    expect(find.text('Idle'), findsNothing);
  });

  testWidgets('message composer shows focused quick key toolbar', (
    tester,
  ) async {
    await setTestSurfaceSize(tester, const Size(390, 844));

    final controller = TextEditingController();
    var tabCount = 0;
    var escapeCount = 0;

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: AgentMessageComposer(
            agentName: 'mobile',
            controller: controller,
            isSending: false,
            collapsible: false,
            collapsed: false,
            onCollapse: () {},
            onExpand: () {},
            draftAttachments: const [],
            onPickImage: () {},
            onPickFile: () {},
            onRemoveAttachment: (_) {},
            onSend: () {},
            onSendTab: () {
              tabCount += 1;
            },
            onSendEscape: () {
              escapeCount += 1;
            },
          ),
        ),
      ),
    );

    expect(find.byKey(const ValueKey('agent-quick-key-toolbar')), findsNothing);
    expect(find.byKey(const ValueKey('agent-quick-key-tab')), findsNothing);
    expect(find.byKey(const ValueKey('agent-quick-key-esc')), findsNothing);

    await tester.tap(find.byKey(const ValueKey('agent-message-composer')));
    await tester.pump();

    final toolbar = find.byKey(const ValueKey('agent-quick-key-toolbar'));
    final composer = find.byKey(const ValueKey('agent-message-composer'));
    expect(toolbar, findsOneWidget);
    expect(find.byKey(const ValueKey('agent-quick-key-tab')), findsOneWidget);
    expect(find.byKey(const ValueKey('agent-quick-key-esc')), findsOneWidget);
    expect(
      tester.getBottomLeft(toolbar).dy,
      lessThanOrEqualTo(tester.getTopLeft(composer).dy),
    );

    await tester.tap(find.byKey(const ValueKey('agent-quick-key-tab')));
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('agent-quick-key-esc')));
    await tester.pump();

    expect(tabCount, 1);
    expect(escapeCount, 1);

    FocusManager.instance.primaryFocus?.unfocus();
    await tester.pump();
    expect(find.byKey(const ValueKey('agent-quick-key-toolbar')), findsNothing);
  });

  testWidgets('workspace tap outside composer collapses input and quick keys', (
    tester,
  ) async {
    await setTestSurfaceSize(tester, const Size(390, 844));

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SelectedAgentWorkspace(
            repository: FakeMobileCcbRepository.demo(),
            terminalTransport: null,
            usePaneInputForMessages: false,
            view: _workspaceView(
              const CcbAgent(
                name: 'mobile',
                provider: 'codex',
                window: 'main',
                order: 0,
                active: true,
                queueDepth: 0,
              ),
            ),
            agent: const CcbAgent(
              name: 'mobile',
              provider: 'codex',
              window: 'main',
              order: 0,
              active: true,
              queueDepth: 0,
            ),
            enableComposerCollapse: true,
            onRefreshView: null,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const ValueKey('agent-message-composer')));
    await tester.pump();

    expect(find.byKey(const ValueKey('agent-chat-composer')), findsOneWidget);
    expect(
      find.byKey(const ValueKey('agent-quick-key-toolbar')),
      findsOneWidget,
    );

    await tester.tap(
      find.byKey(const ValueKey('agent-compose-dismiss-region')),
    );
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey('agent-chat-composer-collapsed')),
      findsOneWidget,
    );
    expect(find.byKey(const ValueKey('agent-quick-key-toolbar')), findsNothing);
  });

  testWidgets('refresh updates codex execution status from project view', (
    tester,
  ) async {
    await tester.pumpWidget(
      const MaterialApp(home: Scaffold(body: _WorkspaceRefreshStatusHarness())),
    );
    await tester.pumpAndSettle();

    expect(find.text('Idle'), findsOneWidget);
    expect(find.text('Working'), findsNothing);

    await tester.tap(
      find.byKey(const ValueKey('agent-conversation-refresh-action')),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.byKey(const ValueKey('agent-working-status')), findsOneWidget);
    expect(find.text('Working'), findsOneWidget);
  });

  testWidgets('refresh shows interrupted codex status as exception', (
    tester,
  ) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: _WorkspaceRefreshStatusHarness(
            refreshActivityReason: 'conversation_interrupted',
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Idle'), findsOneWidget);

    await tester.tap(
      find.byKey(const ValueKey('agent-conversation-refresh-action')),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.byKey(const ValueKey('agent-working-status')), findsOneWidget);
    expect(find.text('Exception'), findsOneWidget);
    expect(find.text('Working'), findsNothing);
  });

  testWidgets('message composer shows attachment tray and picker sheet', (
    tester,
  ) async {
    final controller = TextEditingController();
    var pickedFile = false;
    var pickedImage = false;
    String? removed;

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: AgentMessageComposer(
            agentName: 'mobile',
            controller: controller,
            isSending: false,
            collapsible: false,
            collapsed: false,
            onCollapse: () {},
            onExpand: () {},
            draftAttachments: const [
              CcbMessageAttachment(
                fileId: 'draft-1',
                fileName: 'very-long-notes-file-name.txt',
                mimeType: 'text/plain',
                sizeBytes: 2048,
                state: CcbMessageAttachmentState.queued,
              ),
            ],
            onPickImage: () {
              pickedImage = true;
            },
            onPickFile: () {
              pickedFile = true;
            },
            onRemoveAttachment: (localId) {
              removed = localId;
            },
            onSend: () {},
            onSendTab: () {},
            onSendEscape: () {},
          ),
        ),
      ),
    );

    expect(find.byKey(const ValueKey('agent-attachment-tray')), findsOneWidget);
    expect(
      find.byKey(const ValueKey('agent-attachment-chip-draft-1')),
      findsOneWidget,
    );

    await tester.tap(find.byKey(const ValueKey('agent-attachment-button')));
    await tester.pumpAndSettle();
    expect(
      find.byKey(const ValueKey('agent-attachment-sheet')),
      findsOneWidget,
    );

    await tester.tap(find.byKey(const ValueKey('agent-attachment-pick-file')));
    await tester.pumpAndSettle();
    expect(pickedFile, isTrue);
    expect(pickedImage, isFalse);

    await tester.tap(
      find.byKey(const ValueKey('agent-attachment-remove-draft-1')),
    );
    expect(removed, 'draft-1');
  });

  testWidgets('file picker cancel keeps attachment draft empty', (
    tester,
  ) async {
    final originalPicker = FilePickerPlatform.instance;
    FilePickerPlatform.instance = _FakeFilePicker([null]);
    addTearDown(() {
      FilePickerPlatform.instance = originalPicker;
    });

    await tester.pumpWidget(
      MaterialApp(
        home: ProjectHomeScreen(repository: FakeMobileCcbRepository.demo()),
      ),
    );
    await tester.pumpAndSettle();
    await openCurrentProject(tester);

    await tester.tap(find.byKey(const ValueKey('agent-attachment-button')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('agent-attachment-pick-file')));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('agent-attachment-tray')), findsNothing);
    expect(find.text('Attach up to 5 files'), findsNothing);
  });

  testWidgets('file picker enforces max attachments and keeps accepted files', (
    tester,
  ) async {
    final originalPicker = FilePickerPlatform.instance;
    final tempDir = Directory.systemTemp.createTempSync(
      'ccb-mobile-picker-max-',
    );
    addTearDown(() {
      FilePickerPlatform.instance = originalPicker;
      tempDir.deleteSync(recursive: true);
    });
    FilePickerPlatform.instance = _FakeFilePicker([
      FilePickerResult([
        for (var index = 0; index < 6; index += 1)
          PlatformFile(
            name: 'notes-$index.txt',
            path: _tempFile(tempDir, 'notes-$index.txt').path,
            size: 12,
          ),
      ]),
    ]);

    await tester.pumpWidget(
      MaterialApp(
        home: ProjectHomeScreen(repository: FakeMobileCcbRepository.demo()),
      ),
    );
    await tester.pumpAndSettle();
    await openCurrentProject(tester);

    await tester.tap(find.byKey(const ValueKey('agent-attachment-button')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('agent-attachment-pick-file')));
    await tester.pumpAndSettle();
    await _waitForFinder(
      tester,
      find.byKey(const ValueKey('agent-attachment-tray')),
    );

    expect(find.byKey(const ValueKey('agent-attachment-tray')), findsOneWidget);
    for (var index = 0; index < 5; index += 1) {
      expect(
        find.byKey(ValueKey('agent-attachment-chip-draft-mobile-$index')),
        findsOneWidget,
      );
    }
    expect(
      find.byKey(const ValueKey('agent-attachment-chip-draft-mobile-5')),
      findsNothing,
    );
    expect(find.text('Attach up to 5 files'), findsOneWidget);
  });

  testWidgets('oversized file rejection preserves existing attachment draft', (
    tester,
  ) async {
    final originalPicker = FilePickerPlatform.instance;
    final tempDir = Directory.systemTemp.createTempSync(
      'ccb-mobile-picker-size-',
    );
    addTearDown(() {
      FilePickerPlatform.instance = originalPicker;
      tempDir.deleteSync(recursive: true);
    });
    FilePickerPlatform.instance = _FakeFilePicker([
      FilePickerResult([
        PlatformFile(
          name: 'accepted.txt',
          path: _tempFile(tempDir, 'accepted.txt').path,
          size: 12,
        ),
      ]),
      FilePickerResult([
        PlatformFile(
          name: 'too-large.pdf',
          path: _tempFile(tempDir, 'too-large.pdf').path,
          size: agentMessageMaxAttachmentBytes + 1,
        ),
      ]),
    ]);

    await tester.pumpWidget(
      MaterialApp(
        home: ProjectHomeScreen(repository: FakeMobileCcbRepository.demo()),
      ),
    );
    await tester.pumpAndSettle();
    await openCurrentProject(tester);

    await tester.tap(find.byKey(const ValueKey('agent-attachment-button')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('agent-attachment-pick-file')));
    await tester.pumpAndSettle();
    await _waitForFinder(
      tester,
      find.byKey(const ValueKey('agent-attachment-chip-draft-mobile-0')),
    );
    expect(
      find.byKey(const ValueKey('agent-attachment-chip-draft-mobile-0')),
      findsOneWidget,
    );

    await tester.tap(find.byKey(const ValueKey('agent-attachment-button')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('agent-attachment-pick-file')));
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey('agent-attachment-chip-draft-mobile-0')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('agent-attachment-chip-draft-mobile-1')),
      findsNothing,
    );
    expect(find.text('too-large.pdf is larger than 25 MB'), findsOneWidget);
  });

  testWidgets('unsupported file rejection keeps attachment draft empty', (
    tester,
  ) async {
    final originalPicker = FilePickerPlatform.instance;
    final tempDir = Directory.systemTemp.createTempSync(
      'ccb-mobile-picker-unsupported-',
    );
    addTearDown(() {
      FilePickerPlatform.instance = originalPicker;
      tempDir.deleteSync(recursive: true);
    });
    FilePickerPlatform.instance = _FakeFilePicker([
      FilePickerResult([
        PlatformFile(
          name: 'installer.exe',
          path: _tempFile(tempDir, 'installer.exe').path,
          size: 12,
        ),
      ]),
    ]);

    await tester.pumpWidget(
      MaterialApp(
        home: ProjectHomeScreen(repository: FakeMobileCcbRepository.demo()),
      ),
    );
    await tester.pumpAndSettle();
    await openCurrentProject(tester);

    await tester.tap(find.byKey(const ValueKey('agent-attachment-button')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('agent-attachment-pick-file')));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('agent-attachment-tray')), findsNothing);
    expect(
      find.text('installer.exe is not a supported attachment type'),
      findsOneWidget,
    );
  });

  testWidgets('agent tap selects and explicit action opens fake terminal', (
    tester,
  ) async {
    await tester.pumpWidget(const CcbMobileApp(enableProductOnboarding: false));
    await tester.pumpAndSettle();
    await openCurrentProject(tester);

    await tester.tap(find.byKey(const ValueKey('agent-lead')));
    await tester.pumpAndSettle();

    expect(find.byType(TerminalView), findsNothing);
    expectAgentSelected(tester, 'lead');

    await tester.tap(find.byKey(const ValueKey('open-agent-terminal-button')));
    await tester.pumpAndSettle();

    expect(find.byType(TerminalView), findsOneWidget);
    expect(find.text('demo / lead'), findsNWidgets(2));
    expect(
      find.text('tmux -S /tmp/ccb-demo/tmux.sock attach-session -t ccb-demo'),
      findsOneWidget,
    );
  });

  testWidgets('chat composer preserves drafts per selected agent', (
    tester,
  ) async {
    await tester.pumpWidget(const CcbMobileApp(enableProductOnboarding: false));
    await tester.pumpAndSettle();
    await openCurrentProject(tester);

    expect(find.byKey(const ValueKey('agent-chat-timeline')), findsOneWidget);
    expect(find.byKey(const ValueKey('agent-chat-composer')), findsOneWidget);
    expect(
      find.byKey(const ValueKey('agent-message-composer')),
      findsOneWidget,
    );

    await tester.enterText(
      find.byKey(const ValueKey('agent-message-composer')),
      'mobile draft',
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const ValueKey('agent-lead')));
    await tester.pumpAndSettle();
    var composer = tester.widget<TextField>(
      find.byKey(const ValueKey('agent-message-composer')),
    );
    expect(composer.controller?.text, isEmpty);

    await tester.enterText(
      find.byKey(const ValueKey('agent-message-composer')),
      'lead draft',
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const ValueKey('agent-mobile')));
    await tester.pumpAndSettle();
    composer = tester.widget<TextField>(
      find.byKey(const ValueKey('agent-message-composer')),
    );
    expect(composer.controller?.text, 'mobile draft');

    await tester.tap(find.byKey(const ValueKey('agent-lead')));
    await tester.pumpAndSettle();
    composer = tester.widget<TextField>(
      find.byKey(const ValueKey('agent-message-composer')),
    );
    expect(composer.controller?.text, 'lead draft');
  });

  testWidgets('chat composer shows pending sent failed and retry states', (
    tester,
  ) async {
    final repository = ControlledSubmitRepository();
    await tester.pumpWidget(
      MaterialApp(home: ProjectHomeScreen(repository: repository)),
    );
    await tester.pumpAndSettle();
    await openCurrentProject(tester);

    await tester.enterText(
      find.byKey(const ValueKey('agent-message-composer')),
      'hello selected agent',
    );
    await tester.tap(find.byKey(const ValueKey('agent-message-send-button')));
    await tester.pump();

    var sendButton = tester.widget<IconButton>(
      find.byKey(const ValueKey('agent-message-send-button')),
    );
    expect(sendButton.onPressed, isNull);
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('agent-message-send-button')));
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pump();
    expect(repository.submittedMessages, hasLength(1));
    await dragUntilVisible(
      tester,
      const ValueKey('conversation-item-local-mobile-0'),
      const Offset(0, -700),
    );
    expect(
      find.byKey(const ValueKey('conversation-item-local-mobile-0')),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: find.byKey(const ValueKey('conversation-state-local-mobile-0')),
        matching: find.text('Pending'),
      ),
      findsOneWidget,
    );

    repository.finishFirstSubmit();
    await tester.pump(const Duration(milliseconds: 120));
    sendButton = tester.widget<IconButton>(
      find.byKey(const ValueKey('agent-message-send-button')),
    );
    expect(sendButton.onPressed, isNotNull);
    await dragUntilVisible(
      tester,
      const ValueKey('conversation-item-local-mobile-0'),
      const Offset(0, 700),
    );
    expect(
      find.descendant(
        of: find.byKey(const ValueKey('conversation-state-local-mobile-0')),
        matching: find.text('Sent'),
      ),
      findsOneWidget,
    );

    await tester.enterText(
      find.byKey(const ValueKey('agent-message-composer')),
      'please fail this fake send',
    );
    await tester.tap(find.byKey(const ValueKey('agent-message-send-button')));
    await tester.pump(const Duration(milliseconds: 120));

    await dragUntilVisible(
      tester,
      const ValueKey('conversation-item-local-mobile-1'),
      const Offset(0, -700),
    );
    expect(
      find.descendant(
        of: find.byKey(const ValueKey('conversation-state-local-mobile-1')),
        matching: find.text('Failed'),
      ),
      findsOneWidget,
    );
    final retryButton = find.byKey(
      const ValueKey('retry-message-local-mobile-1'),
    );
    await tester.ensureVisible(retryButton);
    await tester.pumpAndSettle();
    await tester.tap(retryButton);
    await tester.pump();
    expect(repository.submittedMessages, hasLength(3));
    expect(repository.submittedMessages.last.idempotencyKey, 'local-mobile-1');
    expect(
      find.byKey(const ValueKey('conversation-item-local-mobile-2')),
      findsNothing,
    );
    await dragUntilVisible(
      tester,
      const ValueKey('conversation-item-local-mobile-1'),
      const Offset(0, -700),
    );
    expect(
      find.descendant(
        of: find.byKey(const ValueKey('conversation-state-local-mobile-1')),
        matching: find.text('Pending'),
      ),
      findsOneWidget,
    );

    await tester.pump(const Duration(milliseconds: 120));
    await dragUntilVisible(
      tester,
      const ValueKey('conversation-item-local-mobile-1'),
      const Offset(0, 700),
    );
    expect(
      find.descendant(
        of: find.byKey(const ValueKey('conversation-state-local-mobile-1')),
        matching: find.text('Sent'),
      ),
      findsOneWidget,
    );
  });

  testWidgets('sent fake repository message remains visible after completion', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: ProjectHomeScreen(repository: FakeMobileCcbRepository.demo()),
      ),
    );
    await tester.pumpAndSettle();
    await openCurrentProject(tester);

    await tester.enterText(
      find.byKey(const ValueKey('agent-message-composer')),
      'visible after submit',
    );
    await tester.tap(find.byKey(const ValueKey('agent-message-send-button')));
    await tester.pump(const Duration(milliseconds: 180));

    await dragUntilVisible(
      tester,
      const ValueKey('conversation-item-local-mobile-0'),
      const Offset(0, -700),
    );
    expect(find.text('visible after submit'), findsOneWidget);
    expect(
      find.descendant(
        of: find.byKey(const ValueKey('conversation-state-local-mobile-0')),
        matching: find.text('Sent'),
      ),
      findsOneWidget,
    );
  });

  testWidgets('sent fake repository keeps consecutive button sends visible', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: ProjectHomeScreen(repository: FakeMobileCcbRepository.demo()),
      ),
    );
    await tester.pumpAndSettle();
    await openCurrentProject(tester);

    await tester.enterText(
      find.byKey(const ValueKey('agent-message-composer')),
      'button first visible',
    );
    await tester.tap(find.byKey(const ValueKey('agent-message-send-button')));
    await tester.pump(const Duration(milliseconds: 180));
    await tester.enterText(
      find.byKey(const ValueKey('agent-message-composer')),
      'button second visible',
    );
    await tester.tap(find.byKey(const ValueKey('agent-message-send-button')));
    await tester.pump(const Duration(milliseconds: 180));

    await dragUntilVisible(
      tester,
      const ValueKey('conversation-item-local-mobile-0'),
      const Offset(0, 700),
    );
    expect(find.text('button first visible'), findsOneWidget);
    expect(
      find.descendant(
        of: find.byKey(const ValueKey('conversation-state-local-mobile-0')),
        matching: find.text('Sent'),
      ),
      findsOneWidget,
    );
    await dragUntilVisible(
      tester,
      const ValueKey('conversation-item-local-mobile-1'),
      const Offset(0, -700),
    );
    expect(find.text('button second visible'), findsOneWidget);
    expect(
      find.descendant(
        of: find.byKey(const ValueKey('conversation-state-local-mobile-1')),
        matching: find.text('Sent'),
      ),
      findsOneWidget,
    );
  });

  testWidgets('sent fake repository keeps consecutive enter sends visible', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: ProjectHomeScreen(repository: FakeMobileCcbRepository.demo()),
      ),
    );
    await tester.pumpAndSettle();
    await openCurrentProject(tester);

    await tester.enterText(
      find.byKey(const ValueKey('agent-message-composer')),
      'enter first visible',
    );
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pump(const Duration(milliseconds: 180));
    await tester.enterText(
      find.byKey(const ValueKey('agent-message-composer')),
      'enter second visible',
    );
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pump(const Duration(milliseconds: 180));

    await dragUntilVisible(
      tester,
      const ValueKey('conversation-item-local-mobile-0'),
      const Offset(0, 700),
    );
    expect(find.text('enter first visible'), findsOneWidget);
    await dragUntilVisible(
      tester,
      const ValueKey('conversation-item-local-mobile-1'),
      const Offset(0, -700),
    );
    expect(find.text('enter second visible'), findsOneWidget);
  });

  testWidgets('sent fake repository preserves duplicate body counts', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: ProjectHomeScreen(repository: FakeMobileCcbRepository.demo()),
      ),
    );
    await tester.pumpAndSettle();
    await openCurrentProject(tester);

    for (var index = 0; index < 2; index += 1) {
      await tester.enterText(
        find.byKey(const ValueKey('agent-message-composer')),
        'duplicate visible body',
      );
      await tester.tap(find.byKey(const ValueKey('agent-message-send-button')));
      await tester.pump(const Duration(milliseconds: 180));
    }

    await dragUntilVisible(
      tester,
      const ValueKey('conversation-item-local-mobile-0'),
      const Offset(0, 700),
    );
    expect(
      find.descendant(
        of: find.byKey(const ValueKey('conversation-item-local-mobile-0')),
        matching: find.text('duplicate visible body'),
      ),
      findsOneWidget,
    );
    await dragUntilVisible(
      tester,
      const ValueKey('conversation-item-local-mobile-1'),
      const Offset(0, -700),
    );
    expect(
      find.descendant(
        of: find.byKey(const ValueKey('conversation-item-local-mobile-1')),
        matching: find.text('duplicate visible body'),
      ),
      findsOneWidget,
    );
  });

  testWidgets('gateway attachment download ignores duplicate pending taps', (
    tester,
  ) async {
    final repository = DownloadGateRepository();
    await tester.pumpWidget(
      MaterialApp(home: ProjectHomeScreen(repository: repository)),
    );
    await tester.pumpAndSettle();
    await openCurrentProject(tester);

    await dragUntilVisible(
      tester,
      const ValueKey('conversation-attachment-chip-gateway-file'),
      const Offset(0, -700),
    );
    final firstChip = tester.widget<ActionChip>(
      find.byKey(const ValueKey('conversation-attachment-chip-gateway-file')),
    );
    firstChip.onPressed!();
    await tester.pump();
    final busyChip = tester.widget<ActionChip>(
      find.byKey(const ValueKey('conversation-attachment-chip-gateway-file')),
    );
    expect(busyChip.onPressed, isNull);

    expect(repository.downloadCalls, 1);
    expect(
      find.byKey(const ValueKey('agent-attachment-progress-gateway-file')),
      findsOneWidget,
    );
  });

  testWidgets('manual refresh updates fallback terminal history', (
    tester,
  ) async {
    final repository = FallbackTerminalHistoryRepository();
    await tester.pumpWidget(
      MaterialApp(home: ProjectHomeScreen(repository: repository)),
    );
    await tester.pumpAndSettle();
    await openCurrentProject(tester);

    expect(repository.terminalHistoryCalls, isNotEmpty);
    final initialTerminalHistoryCalls = repository.terminalHistoryCalls.length;
    expect(find.text('Pane sync visible'), findsNothing);

    repository.terminalHistoryOverride = const ReadableTerminalHistory(
      agentName: 'mobile',
      historyScope: 'tmux_scrollback',
      sourcePaneId: '%2',
      blocks: [
        ReadableTerminalBlock(
          id: 'sync-output',
          type: 'log',
          title: 'Terminal output',
          text: 'Pane sync visible',
        ),
      ],
    );

    await tester.pump(const Duration(seconds: 10));
    await tester.pump();

    expect(repository.terminalHistoryCalls.length, initialTerminalHistoryCalls);
    expect(find.text('Pane sync visible'), findsNothing);

    await tester.tap(
      find.byKey(const ValueKey('agent-conversation-refresh-action')),
    );
    await tester.pumpAndSettle();

    expect(
      repository.terminalHistoryCalls.length,
      greaterThan(initialTerminalHistoryCalls),
    );
    await dragUntilVisible(
      tester,
      const ValueKey(
        'conversation-item-terminal-history-output-mobile-sync-output',
      ),
      const Offset(0, -700),
    );
    final preview = tester.widget<Text>(
      find.byKey(
        const ValueKey(
          'conversation-preview-terminal-history-output-mobile-sync-output',
        ),
      ),
    );
    expect(preview.data, 'Pane sync visible');
  });

  testWidgets('opened agent with pane conversation skips terminal fallback', (
    tester,
  ) async {
    final repository = PaneConversationRepository();
    await tester.pumpWidget(
      MaterialApp(home: ProjectHomeScreen(repository: repository)),
    );
    await tester.pumpAndSettle();
    await openCurrentProject(tester);

    await tester.tap(
      find.byKey(const ValueKey('agent-conversation-refresh-action')),
    );
    await tester.pump();

    expect(repository.conversationCalls, isNotEmpty);
    expect(repository.terminalHistoryCalls, isEmpty);
    expect(find.text('Pane conversation visible'), findsOneWidget);
  });

  testWidgets('opened agent with native conversation skips terminal fallback', (
    tester,
  ) async {
    final repository = NativeConversationRepository();
    await tester.pumpWidget(
      MaterialApp(home: ProjectHomeScreen(repository: repository)),
    );
    await tester.pumpAndSettle();
    await openCurrentProject(tester);

    await tester.tap(
      find.byKey(const ValueKey('agent-conversation-refresh-action')),
    );
    await tester.pump();

    expect(repository.conversationCalls, isNotEmpty);
    expect(repository.terminalHistoryCalls, isEmpty);
    expect(find.text('Native conversation visible'), findsOneWidget);
  });

  testWidgets('gateway conversation replies render markdown in chat bubbles', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: ProjectHomeScreen(repository: MarkdownGatewayRepository()),
      ),
    );
    await tester.pumpAndSettle();
    await openCurrentProject(tester);

    await tapVisible(
      tester,
      const ValueKey('conversation-expand-reply-markdown'),
    );
    expect(
      find.byKey(const ValueKey('markdown-body-conversation-reply-markdown')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('conversation-body-reply-markdown')),
      findsNothing,
    );
    expect(find.text('Markdown reply'), findsOneWidget);
    expect(find.text('first item'), findsOneWidget);
    expect(find.text('second item'), findsOneWidget);
    expect(find.text('ordered item'), findsOneWidget);
    expect(find.text('follow up item'), findsOneWidget);
    expect(find.text('done item'), findsOneWidget);
    expect(find.text('todo item'), findsOneWidget);
    expect(find.text('quoted insight'), findsOneWidget);
    expect(renderedTextContaining('inline code'), findsWidgets);
    expect(renderedTextContaining('bold text'), findsWidgets);
    expect(renderedTextContaining('italic text'), findsWidgets);
    expect(find.text('final ok = true;'), findsOneWidget);
    expect(find.text('Column'), findsOneWidget);
    expect(find.text('Value'), findsOneWidget);
    expect(find.text('alpha'), findsOneWidget);
    expect(find.text('42'), findsOneWidget);
    expect(find.text('docs link'), findsOneWidget);

    await tester.ensureVisible(find.text('docs link'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('docs link'));
    await tester.pumpAndSettle();
    expect(
      find.text('Open links from raw source: https://example.com'),
      findsOneWidget,
    );
  });

  testWidgets('paired composer submits chat through pane input', (
    tester,
  ) async {
    final secureStore = MemorySecureStore();
    final profileStore = GatewayHostProfileStore(secureStore: secureStore);
    final host = GatewayPairedHost(
      profile: GatewayHostProfile(
        hostId: 'proj-demo',
        deviceId: 'dev-partial-pane',
        routeProvider: RouteProvider(
          kind: RouteProviderKind.lan,
          gatewayUrl: Uri.parse('http://127.0.0.1:8787'),
        ),
        scopes: const {'view', 'content', 'focus', 'terminal_input'},
      ),
      deviceToken: 'device-secret',
      projectId: 'proj-demo',
    );
    await profileStore.save(host);
    final terminalTransport = RecordingTerminalTransport(
      writeError: const TerminalTransportException('enter failed'),
    );
    final repository = RecordingGatewayRepository();

    await tester.pumpWidget(
      MaterialApp(
        home: ProjectHomeScreen(
          repository: FakeMobileCcbRepository.demo(),
          profileStore: profileStore,
          gatewayRepositoryFactory: (profile) => repository,
          gatewayTerminalTransportFactory: (profile) => terminalTransport,
        ),
      ),
    );
    await tester.pumpAndSettle();
    await activateStoredGatewayProfile(tester);

    await tester.enterText(
      find.byKey(const ValueKey('agent-message-composer')),
      'partial pane send',
    );
    await tester.tap(find.byKey(const ValueKey('agent-message-send-button')));
    await tester.pumpAndSettle();

    expect(repository.submittedMessages, isEmpty);
    expect(terminalTransport.requests, hasLength(1));
    expect(terminalTransport.sessions.single.pasted, ['partial pane send']);
    expect(terminalTransport.sessions.single.written, isEmpty);
    expect(find.text('partial pane send'), findsOneWidget);
    expect(find.text('Check pane'), findsOneWidget);
  });

  testWidgets('paired composer shows working while pane input is pending', (
    tester,
  ) async {
    final secureStore = MemorySecureStore();
    final profileStore = GatewayHostProfileStore(secureStore: secureStore);
    final host = GatewayPairedHost(
      profile: GatewayHostProfile(
        hostId: 'proj-demo',
        deviceId: 'dev-working-pane',
        routeProvider: RouteProvider(
          kind: RouteProviderKind.lan,
          gatewayUrl: Uri.parse('http://127.0.0.1:8787'),
        ),
        scopes: const {'view', 'content', 'focus', 'terminal_input'},
      ),
      deviceToken: 'device-secret',
      projectId: 'proj-demo',
    );
    await profileStore.save(host);
    final terminalTransport = BlockingPasteTerminalTransport(
      writeError: const TerminalTransportException('enter failed'),
    );
    final repository = RecordingGatewayRepository();

    await tester.pumpWidget(
      MaterialApp(
        home: ProjectHomeScreen(
          repository: FakeMobileCcbRepository.demo(),
          profileStore: profileStore,
          gatewayRepositoryFactory: (profile) => repository,
          gatewayTerminalTransportFactory: (profile) => terminalTransport,
        ),
      ),
    );
    await tester.pumpAndSettle();
    await activateStoredGatewayProfile(tester);

    await tester.enterText(
      find.byKey(const ValueKey('agent-message-composer')),
      'pending pane send',
    );
    await tester.tap(find.byKey(const ValueKey('agent-message-send-button')));
    await tester.pump();

    expect(repository.submittedMessages, isEmpty);
    await dragUntilVisible(
      tester,
      const ValueKey('conversation-item-local-mobile-0'),
      const Offset(0, -700),
    );
    expect(renderedTextContaining('pending pane send'), findsOneWidget);
    expect(find.byKey(const ValueKey('agent-working-status')), findsOneWidget);
    expect(find.text('Working'), findsOneWidget);

    terminalTransport.completePaste();
    await tester.pumpAndSettle();

    expect(terminalTransport.sessions.single.pasted, ['pending pane send']);
    expect(terminalTransport.sessions.single.written, isEmpty);
    expect(find.byKey(const ValueKey('agent-working-status')), findsOneWidget);
    expect(find.text('Working'), findsOneWidget);
    expect(find.text('Check pane'), findsOneWidget);
  });

  testWidgets('paired terminal output updates status without chat bubble', (
    tester,
  ) async {
    final secureStore = MemorySecureStore();
    final profileStore = GatewayHostProfileStore(secureStore: secureStore);
    final host = GatewayPairedHost(
      profile: GatewayHostProfile(
        hostId: 'proj-demo',
        deviceId: 'dev-stream-status',
        routeProvider: RouteProvider(
          kind: RouteProviderKind.lan,
          gatewayUrl: Uri.parse('http://127.0.0.1:8787'),
        ),
        scopes: const {'view', 'content', 'focus', 'terminal_input'},
      ),
      deviceToken: 'device-secret',
      projectId: 'proj-demo',
    );
    await profileStore.save(host);
    final terminalTransport = RecordingTerminalTransport();
    final repository = RecordingGatewayRepository();

    await tester.pumpWidget(
      MaterialApp(
        home: ProjectHomeScreen(
          repository: FakeMobileCcbRepository.demo(),
          profileStore: profileStore,
          gatewayRepositoryFactory: (profile) => repository,
          gatewayTerminalTransportFactory: (profile) => terminalTransport,
        ),
      ),
    );
    await tester.pumpAndSettle();
    await activateStoredGatewayProfile(tester);

    await tester.enterText(
      find.byKey(const ValueKey('agent-message-composer')),
      'stream status only',
    );
    await tester.tap(find.byKey(const ValueKey('agent-message-send-button')));
    await tester.pump();

    expect(terminalTransport.sessions, hasLength(1));
    terminalTransport.sessions.single.addOutput('stream-only-visible-status\n');
    await tester.pump();

    expect(find.byKey(const ValueKey('agent-working-status')), findsOneWidget);
    expect(find.text('Working'), findsOneWidget);
    expect(find.text('Terminal output'), findsNothing);
    expect(find.textContaining('stream-only-visible-status'), findsNothing);
  });

  testWidgets(
    'paired terminal interrupted output updates status to exception',
    (tester) async {
      final secureStore = MemorySecureStore();
      final profileStore = GatewayHostProfileStore(secureStore: secureStore);
      final host = GatewayPairedHost(
        profile: GatewayHostProfile(
          hostId: 'proj-demo',
          deviceId: 'dev-stream-interrupted-status',
          routeProvider: RouteProvider(
            kind: RouteProviderKind.lan,
            gatewayUrl: Uri.parse('http://127.0.0.1:8787'),
          ),
          scopes: const {'view', 'content', 'focus', 'terminal_input'},
        ),
        deviceToken: 'device-secret',
        projectId: 'proj-demo',
      );
      await profileStore.save(host);
      final terminalTransport = RecordingTerminalTransport();
      final repository = RecordingGatewayRepository();

      await tester.pumpWidget(
        MaterialApp(
          home: ProjectHomeScreen(
            repository: FakeMobileCcbRepository.demo(),
            profileStore: profileStore,
            gatewayRepositoryFactory: (profile) => repository,
            gatewayTerminalTransportFactory: (profile) => terminalTransport,
          ),
        ),
      );
      await tester.pumpAndSettle();
      await activateStoredGatewayProfile(tester);

      await tester.enterText(
        find.byKey(const ValueKey('agent-message-composer')),
        'stream interrupted status',
      );
      await tester.tap(find.byKey(const ValueKey('agent-message-send-button')));
      await tester.pump();

      expect(terminalTransport.sessions, hasLength(1));
      terminalTransport.sessions.single.addOutput('Conversation ');
      await tester.pump();
      expect(find.text('Working'), findsOneWidget);

      terminalTransport.sessions.single.addOutput('interrupted\n');
      await tester.pump();

      expect(
        find.byKey(const ValueKey('agent-working-status')),
        findsOneWidget,
      );
      expect(find.text('Exception'), findsOneWidget);
      expect(find.text('Working'), findsNothing);
      expect(find.textContaining('Conversation interrupted'), findsNothing);
    },
  );

  testWidgets(
    'scheduled refresh clears working status when project view is idle',
    (tester) async {
      final terminalTransport = RecordingTerminalTransport();
      var refreshCalls = 0;
      var view = _workspaceView(
        _statusAgent(
          activityState: 'idle',
          activitySource: 'provider_pane',
          activityReason: 'provider_prompt_idle',
        ),
      );

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: StatefulBuilder(
              builder: (context, setState) {
                final agent = view.agentByName('mobile')!;
                return SelectedAgentWorkspace(
                  repository: FakeMobileCcbRepository.demo(),
                  terminalTransport: terminalTransport,
                  usePaneInputForMessages: true,
                  view: view,
                  agent: agent,
                  enableComposerCollapse: true,
                  onRefreshView: () async {
                    refreshCalls += 1;
                    final refreshed = _workspaceView(
                      _statusAgent(
                        activityState: 'idle',
                        activitySource: 'provider_pane',
                        activityReason: 'provider_prompt_idle',
                      ),
                    );
                    setState(() {
                      view = refreshed;
                    });
                    return refreshed;
                  },
                );
              },
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Idle'), findsOneWidget);

      await tester.enterText(
        find.byKey(const ValueKey('agent-message-composer')),
        'work then idle',
      );
      await tester.tap(find.byKey(const ValueKey('agent-message-send-button')));
      await tester.pump();

      expect(terminalTransport.sessions.single.pasted, ['work then idle']);
      expect(find.text('Working'), findsOneWidget);

      await tester.pump(const Duration(milliseconds: 120));
      await tester.pumpAndSettle();

      expect(refreshCalls, greaterThanOrEqualTo(1));
      expect(find.text('Idle'), findsOneWidget);
      expect(find.text('Working'), findsNothing);
    },
  );

  testWidgets('paired pane command result can render from terminal history', (
    tester,
  ) async {
    final secureStore = MemorySecureStore();
    final profileStore = GatewayHostProfileStore(secureStore: secureStore);
    final host = GatewayPairedHost(
      profile: GatewayHostProfile(
        hostId: 'proj-demo',
        deviceId: 'dev-pane-status',
        routeProvider: RouteProvider(
          kind: RouteProviderKind.lan,
          gatewayUrl: Uri.parse('http://127.0.0.1:8787'),
        ),
        scopes: const {'view', 'content', 'focus', 'terminal_input'},
      ),
      deviceToken: 'device-secret',
      projectId: 'proj-demo',
    );
    await profileStore.save(host);
    final terminalTransport = RecordingTerminalTransport();
    final repository =
        RecordingGatewayRepository()
          ..terminalHistoryOverride = const ReadableTerminalHistory(
            agentName: 'mobile',
            historyScope: 'tmux_scrollback',
            sourcePaneId: '%2',
            blocks: [
              ReadableTerminalBlock(
                id: 'status-output',
                type: 'log',
                title: 'Terminal output',
                text: 'Credits remaining: 42%',
              ),
            ],
          );

    await tester.pumpWidget(
      MaterialApp(
        home: ProjectHomeScreen(
          repository: FakeMobileCcbRepository.demo(),
          profileStore: profileStore,
          gatewayRepositoryFactory: (profile) => repository,
          gatewayTerminalTransportFactory: (profile) => terminalTransport,
        ),
      ),
    );
    await tester.pumpAndSettle();
    await activateStoredGatewayProfile(tester);

    await tester.enterText(
      find.byKey(const ValueKey('agent-message-composer')),
      '/status',
    );
    await tester.tap(find.byKey(const ValueKey('agent-message-send-button')));
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));
    await tester.pumpAndSettle();

    expect(repository.submittedMessages, isEmpty);
    expect(terminalTransport.sessions.single.pasted, ['/status']);
    expect(terminalTransport.sessions.single.written, [
      [13],
    ]);
    expect(repository.terminalHistoryCalls, isNotEmpty);
    expect(find.text('Credits remaining: 42%'), findsOneWidget);
  });

  testWidgets('paired Tab quick key types draft into pane without Enter', (
    tester,
  ) async {
    await setTestSurfaceSize(tester, const Size(390, 844));

    final secureStore = MemorySecureStore();
    final profileStore = GatewayHostProfileStore(secureStore: secureStore);
    final host = GatewayPairedHost(
      profile: GatewayHostProfile(
        hostId: 'proj-demo',
        deviceId: 'dev-tab-draft',
        routeProvider: RouteProvider(
          kind: RouteProviderKind.lan,
          gatewayUrl: Uri.parse('http://127.0.0.1:8787'),
        ),
        scopes: const {'view', 'content', 'focus', 'terminal_input'},
      ),
      deviceToken: 'device-secret',
      projectId: 'proj-demo',
    );
    await profileStore.save(host);
    final terminalTransport = RecordingTerminalTransport();
    final repository = RecordingGatewayRepository();

    await tester.pumpWidget(
      MaterialApp(
        home: ProjectHomeScreen(
          repository: FakeMobileCcbRepository.demo(),
          profileStore: profileStore,
          gatewayRepositoryFactory: (profile) => repository,
          gatewayTerminalTransportFactory: (profile) => terminalTransport,
        ),
      ),
    );
    await tester.pumpAndSettle();
    await activateStoredGatewayProfile(tester);

    await tester.tap(find.byKey(const ValueKey('agent-message-composer')));
    await tester.pump();
    await tester.enterText(
      find.byKey(const ValueKey('agent-message-composer')),
      'draft before tab',
    );
    await tester.pump();

    expect(find.byKey(const ValueKey('agent-quick-key-tab')), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('agent-quick-key-tab')));
    await tester.pump();

    expect(repository.submittedMessages, isEmpty);
    expect(terminalTransport.requests, hasLength(1));
    expect(terminalTransport.sessions.single.pasted, ['draft before tab']);
    expect(terminalTransport.sessions.single.written, [
      [9],
    ]);
    expect(
      tester
          .widget<TextField>(
            find.byKey(const ValueKey('agent-message-composer')),
          )
          .controller!
          .text,
      isEmpty,
    );
  });

  testWidgets('stale namespace epoch refreshes and retries chat send', (
    tester,
  ) async {
    final repository = StaleEpochGatewayRepository();
    await tester.pumpWidget(
      MaterialApp(home: ProjectHomeScreen(repository: repository)),
    );
    await tester.pumpAndSettle();
    await openCurrentProject(tester);

    expect(
      find.byKey(const ValueKey('agent-message-composer')),
      findsOneWidget,
    );

    await tester.enterText(
      find.byKey(const ValueKey('agent-message-composer')),
      'retry after stale epoch',
    );
    await tester.pump();
    final sendButton = tester.widget<IconButton>(
      find.byKey(const ValueKey('agent-message-send-button')),
    );
    sendButton.onPressed!();
    await tester.pumpAndSettle();

    expect(repository.getProjectViewCalls, greaterThanOrEqualTo(2));
    expect(
      [for (final item in repository.submittedMessages) item.namespaceEpoch],
      [4, 5],
    );
    expect(find.text('retry after stale epoch'), findsOneWidget);
    expect(find.text('Failed'), findsNothing);
  });
}

File _tempFile(Directory dir, String name) {
  final file = File('${dir.path}/$name');
  file.writeAsStringSync('test attachment $name');
  return file;
}

Future<void> _waitForFinder(
  WidgetTester tester,
  Finder finder, {
  Duration timeout = const Duration(seconds: 5),
}) async {
  final stopwatch = Stopwatch()..start();
  while (stopwatch.elapsed < timeout) {
    await tester.pump(const Duration(milliseconds: 50));
    if (tester.any(finder)) {
      return;
    }
  }
  expect(finder, findsOneWidget);
}

class _WorkspaceRefreshStatusHarness extends StatefulWidget {
  const _WorkspaceRefreshStatusHarness({
    this.refreshActivityReason = 'codex_runtime_reconnecting',
  });

  final String refreshActivityReason;

  @override
  State<_WorkspaceRefreshStatusHarness> createState() =>
      _WorkspaceRefreshStatusHarnessState();
}

class _WorkspaceRefreshStatusHarnessState
    extends State<_WorkspaceRefreshStatusHarness> {
  late CcbAgent _agent = _statusAgent();
  late CcbProjectView _view = _workspaceView(_agent);

  @override
  Widget build(BuildContext context) {
    return SelectedAgentWorkspace(
      repository: FakeMobileCcbRepository.demo(),
      terminalTransport: null,
      usePaneInputForMessages: false,
      view: _view,
      agent: _agent,
      enableComposerCollapse: true,
      onRefreshView: () async {
        final agent = _statusAgent(
          activityState: 'pending',
          activitySource: 'codex_runtime',
          activityReason: widget.refreshActivityReason,
        );
        final view = _workspaceView(agent);
        setState(() {
          _agent = agent;
          _view = view;
        });
        return view;
      },
    );
  }
}

CcbAgent _statusAgent({
  String? activityState,
  String? activitySource,
  String? activityReason,
}) {
  return CcbAgent(
    name: 'mobile',
    provider: 'codex',
    window: 'main',
    order: 0,
    active: true,
    queueDepth: 0,
    activityState: activityState,
    activitySource: activitySource,
    activityReason: activityReason,
  );
}

class _FakeFilePicker extends FilePickerPlatform {
  _FakeFilePicker(this.results);

  final List<FilePickerResult?> results;
  var _index = 0;

  @override
  Future<FilePickerResult?> pickFiles({
    String? dialogTitle,
    String? initialDirectory,
    FileType type = FileType.any,
    List<String>? allowedExtensions,
    Function(FilePickerStatus)? onFileLoading,
    int compressionQuality = 0,
    bool allowMultiple = false,
    bool withData = false,
    bool withReadStream = false,
    bool lockParentWindow = false,
    bool readSequential = false,
    bool cancelUploadOnWindowBlur = true,
  }) async {
    if (_index >= results.length) {
      return null;
    }
    return results[_index++];
  }
}

CcbProjectView _workspaceView(CcbAgent agent) {
  return CcbProjectView(
    project: const CcbProject(
      id: 'proj-demo',
      displayName: 'Project',
      root: '/tmp/project',
    ),
    namespaceEpoch: 7,
    tmuxSocketPath: null,
    tmuxSessionName: null,
    activeWindow: agent.window,
    activePaneId: null,
    windows: const [],
    agents: [agent],
    contentItems: const [],
    notifications: const [],
    terminalHistories: const {},
  );
}

class DownloadGateRepository extends RecordingGatewayRepository {
  final _downloadGate = Completer<List<int>>();
  var downloadCalls = 0;

  @override
  Future<CcbAgentConversation> getAgentConversation({
    required String projectId,
    required String agent,
    required int namespaceEpoch,
    int limit = 50,
    String? cursor,
  }) async {
    conversationCalls.add((projectId, agent, namespaceEpoch));
    return CcbAgentConversation(
      projectId: projectId,
      agentName: agent,
      namespaceEpoch: namespaceEpoch,
      items: const [
        CcbConversationItem(
          id: 'gateway-reply-with-file',
          agentName: 'mobile',
          kind: CcbConversationItemKind.agentReply,
          title: 'Gateway reply',
          body: 'Download the file.',
          attachments: [
            CcbMessageAttachment(
              fileId: 'gateway-file',
              fileName: 'gateway-notes.txt',
              mimeType: 'text/plain',
              sizeBytes: 16,
            ),
          ],
        ),
      ],
      generatedAt: DateTime.utc(2026, 6, 23),
    );
  }

  @override
  Future<List<int>> downloadFile({
    required String projectId,
    required String agentName,
    required String fileId,
  }) {
    downloadCalls += 1;
    return _downloadGate.future;
  }
}

class FallbackTerminalHistoryRepository extends RecordingGatewayRepository {
  @override
  Future<CcbAgentConversation> getAgentConversation({
    required String projectId,
    required String agent,
    required int namespaceEpoch,
    int limit = 50,
    String? cursor,
  }) async {
    conversationCalls.add((projectId, agent, namespaceEpoch));
    return CcbAgentConversation(
      projectId: projectId,
      agentName: agent,
      namespaceEpoch: namespaceEpoch,
      items: [
        CcbConversationItem(
          id: 'conversation-without-terminal-$agent',
          agentName: agent,
          kind: CcbConversationItemKind.agentReply,
          title: 'Agent reply',
          body: 'Conversation endpoint has no pane history.',
          source: 'repository',
        ),
      ],
      generatedAt: DateTime.utc(2026, 6, 26),
    );
  }
}

class PaneConversationRepository extends RecordingGatewayRepository {
  @override
  Future<CcbAgentConversation> getAgentConversation({
    required String projectId,
    required String agent,
    required int namespaceEpoch,
    int limit = 50,
    String? cursor,
  }) async {
    conversationCalls.add((projectId, agent, namespaceEpoch));
    return CcbAgentConversation(
      projectId: projectId,
      agentName: agent,
      namespaceEpoch: namespaceEpoch,
      items: [
        CcbConversationItem(
          id: 'pane-conversation-$agent',
          agentName: agent,
          kind: CcbConversationItemKind.agentReply,
          title: 'Agent reply',
          body: 'Pane conversation visible',
          source: 'tmux output / tmux_scrollback / %2',
        ),
      ],
      generatedAt: DateTime.utc(2026, 6, 26),
    );
  }
}

class NativeConversationRepository extends RecordingGatewayRepository {
  @override
  Future<CcbAgentConversation> getAgentConversation({
    required String projectId,
    required String agent,
    required int namespaceEpoch,
    int limit = 50,
    String? cursor,
  }) async {
    conversationCalls.add((projectId, agent, namespaceEpoch));
    return CcbAgentConversation(
      projectId: projectId,
      agentName: agent,
      namespaceEpoch: namespaceEpoch,
      items: [
        CcbConversationItem(
          id: 'native-conversation-$agent',
          agentName: agent,
          kind: CcbConversationItemKind.agentReply,
          title: 'Agent reply',
          body: 'Native conversation visible',
          source: 'provider_native/codex',
        ),
      ],
      generatedAt: DateTime.utc(2026, 6, 26),
    );
  }
}

class BlockingPasteTerminalTransport implements TerminalTransport {
  BlockingPasteTerminalTransport({this.writeError});

  final Object? writeError;
  final _pasteGate = Completer<void>();
  final requests = <TerminalOpenRequest>[];
  final sessions = <BlockingPasteTerminalSession>[];

  @override
  Future<TerminalSession> open(TerminalOpenRequest request) async {
    requests.add(request);
    final session = BlockingPasteTerminalSession(
      request.attachCommand,
      pasteGate: _pasteGate.future,
      writeError: writeError,
    );
    sessions.add(session);
    return session;
  }

  void completePaste() {
    if (!_pasteGate.isCompleted) {
      _pasteGate.complete();
    }
  }
}

class BlockingPasteTerminalSession implements TerminalSession {
  BlockingPasteTerminalSession(
    this.launchedCommand, {
    required Future<void> pasteGate,
    this.writeError,
  }) : _pasteGate = pasteGate;

  final Future<void> _pasteGate;
  final Object? writeError;
  final _output = StreamController<Uint8List>.broadcast();

  @override
  final String launchedCommand;

  final pasted = <String>[];
  final written = <List<int>>[];

  @override
  Stream<Uint8List> get output => _output.stream;

  @override
  Future<void> close() async {
    await _output.close();
  }

  @override
  Future<void> paste(String text) async {
    pasted.add(text);
    await _pasteGate;
  }

  @override
  Future<void> reconnect() async {}

  @override
  Future<void> resize(TerminalGeometry geometry) async {}

  @override
  Future<void> writeBytes(List<int> bytes) async {
    final error = writeError;
    if (error != null) {
      throw error;
    }
    written.add(bytes);
  }
}
