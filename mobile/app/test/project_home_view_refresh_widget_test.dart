import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:ccb_mobile/ccb_mobile.dart';

import 'support/project_home_test_driver.dart';
import 'support/project_home_test_fakes.dart';

void main() {
  testWidgets('stale namespace chat send refreshes and retries', (
    tester,
  ) async {
    final repository = _RefreshWidgetRepository(
      refreshedView: CcbProjectView.fromProjectViewPayload(
        demoPayloadWithEpoch(5),
      ),
    );
    await tester.pumpWidget(
      MaterialApp(home: ProjectHomeScreen(repository: repository)),
    );
    await tester.pumpAndSettle();
    await openCurrentProject(tester);

    await _sendMessage(tester, 'retry after stale epoch');

    _expectOnlyProjectViewCalls(repository, minCalls: 2);
    expect(
      [for (final item in repository.submittedMessages) item.namespaceEpoch],
      [4, 5],
    );
    expect(find.text('retry after stale epoch'), findsOneWidget);
    expect(find.text('Failed'), findsNothing);
  });

  testWidgets('refreshed view missing selected agent clears selection', (
    tester,
  ) async {
    final repository = _RefreshWidgetRepository(
      refreshedView: _viewWithoutAgent('lead'),
    );
    await tester.pumpWidget(
      MaterialApp(home: ProjectHomeScreen(repository: repository)),
    );
    await tester.pumpAndSettle();
    await openCurrentProject(tester);
    await tester.tap(find.byKey(const ValueKey('agent-lead')));
    await tester.pumpAndSettle();
    expectAgentSelected(tester, 'lead');

    await _sendMessage(tester, 'lead goes stale');

    _expectOnlyProjectViewCalls(repository, minCalls: 2);
    expect(find.byKey(const ValueKey('agent-lead')), findsNothing);
    expectAgentSelected(tester, 'mobile');
  });

  testWidgets('refresh failure shows snack and preserves current view', (
    tester,
  ) async {
    final repository = _RefreshWidgetRepository(
      refreshError: StateError('refresh failed'),
    );
    await tester.pumpWidget(
      MaterialApp(home: ProjectHomeScreen(repository: repository)),
    );
    await tester.pumpAndSettle();
    await openCurrentProject(tester);
    await tester.tap(find.byKey(const ValueKey('agent-lead')));
    await tester.pumpAndSettle();
    expectAgentSelected(tester, 'lead');

    await _sendMessage(tester, 'refresh fails');

    _expectOnlyProjectViewCalls(repository, minCalls: 2);
    expectAgentSelected(tester, 'lead');
    expect(find.byKey(const ValueKey('agent-mobile')), findsOneWidget);
    expect(find.text('Bad state: refresh failed'), findsOneWidget);
    expect(find.text('Failed'), findsOneWidget);
  });
}

void _expectOnlyProjectViewCalls(
  _RefreshWidgetRepository repository, {
  required int minCalls,
}) {
  expect(repository.getProjectViewCalls.length, greaterThanOrEqualTo(minCalls));
  expect(repository.getProjectViewCalls.toSet(), {'proj-demo'});
}

Future<void> _sendMessage(WidgetTester tester, String body) async {
  await tester.enterText(
    find.byKey(const ValueKey('agent-message-composer')),
    body,
  );
  await tester.pump();
  final sendButton = tester.widget<IconButton>(
    find.byKey(const ValueKey('agent-message-send-button')),
  );
  sendButton.onPressed!();
  await tester.pumpAndSettle();
}

class _RefreshWidgetRepository extends RecordingGatewayRepository {
  _RefreshWidgetRepository({this.refreshedView, this.refreshError})
    : _initialView = CcbProjectView.fromProjectViewPayload(
        demoPayloadWithEpoch(4),
      );

  final CcbProjectView _initialView;
  final CcbProjectView? refreshedView;
  final Object? refreshError;
  final getProjectViewCalls = <String>[];

  @override
  Future<CcbProjectView> getProjectView(String projectId) async {
    getProjectViewCalls.add(projectId);
    if (getProjectViewCalls.length == 1) {
      return _initialView;
    }
    final error = refreshError;
    if (error != null) {
      throw error;
    }
    return refreshedView ??
        CcbProjectView.fromProjectViewPayload(demoPayloadWithEpoch(5));
  }

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
      items: const [],
      generatedAt: DateTime.utc(2026, 6, 23),
    );
  }

  @override
  Future<CcbAgentMessageSubmitResult> submitAgentMessage(
    CcbAgentMessageSubmitRequest request,
  ) async {
    submittedMessages.add(request);
    if (request.namespaceEpoch == _initialView.namespaceEpoch) {
      throw GatewayHttpException(
        Uri.parse('http://gateway.local/messages'),
        409,
        '{"error":"stale namespace epoch"}',
      );
    }
    final message = CcbConversationItem.userMessage(
      id: request.idempotencyKey,
      agentName: request.agentName,
      body: request.body,
      state: CcbConversationDeliveryState.sent,
    );
    return CcbAgentMessageSubmitResult(
      accepted: true,
      idempotencyKey: request.idempotencyKey,
      messageId: request.idempotencyKey,
      state: CcbConversationDeliveryState.sent,
      message: message,
    );
  }
}

CcbProjectView _viewWithoutAgent(String agentName) {
  final payload = demoPayloadWithEpoch(5);
  final view = payload['view']! as Map<String, Object?>;
  final agents = view['agents']! as List<Object?>;
  agents.removeWhere((item) {
    final agent = item! as Map<String, Object?>;
    return agent['name'] == agentName;
  });
  return CcbProjectView.fromProjectViewPayload(payload);
}
