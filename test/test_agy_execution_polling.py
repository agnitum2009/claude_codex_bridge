from __future__ import annotations

import json
from pathlib import Path

from ccbd.api_models import DeliveryScope, JobRecord, JobStatus, MessageEnvelope
from completion.models import CompletionItemKind, CompletionSourceKind, CompletionStatus
from provider_backends.agy.comm import agy_pane_ready_for_input
from provider_backends.agy.execution_runtime import start as agy_start
from provider_backends.agy.execution_runtime.poll import poll_submission
from provider_backends.agy.native_log import observe_agy_transcript
from provider_execution.base import ProviderSubmission


class _Backend:
    def __init__(self, text: str = '') -> None:
        self.text = text
        self.sent: list[tuple[str, str]] = []

    def get_pane_content(self, pane_id: str, *, lines: int) -> str:
        del pane_id, lines
        return self.text

    def send_text_to_pane(self, pane_id: str, text: str) -> None:
        self.sent.append((pane_id, text))


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows),
        encoding='utf-8',
    )


def _submission(work_dir: Path, home: Path) -> ProviderSubmission:
    req_id = 'job_agynative123'
    return ProviderSubmission(
        job_id=req_id,
        agent_name='agy1',
        provider='agy',
        accepted_at='2026-06-13T00:00:00Z',
        ready_at='2026-06-13T00:00:00Z',
        source_kind=CompletionSourceKind.SESSION_EVENT_LOG,
        reply='',
        runtime_state={
            'mode': 'native_transcript_log',
            'backend': _Backend(),
            'pane_id': '%9',
            'req_id': req_id,
            'request_anchor': req_id,
            'work_dir': str(work_dir),
            'agy_home': str(home),
            'started_at': '2026-06-13T00:00:00Z',
            'last_poll_at': '2026-06-13T00:00:00Z',
            'prompt_sent': True,
            'next_seq': 1,
            'anchor_emitted': False,
            'reply_buffer': '',
            'last_reply_signature': '',
            'turn_boundary_ref': '',
            'session_path': '',
        },
    )


def _job(work_dir: Path) -> JobRecord:
    return JobRecord(
        job_id='job_agynative123',
        submission_id='sub_1',
        agent_name='agy1',
        provider='agy',
        request=MessageEnvelope(
            project_id='proj',
            to_agent='agy1',
            from_actor='main',
            body='hello',
            task_id=None,
            reply_to=None,
            message_type='ask',
            delivery_scope=DeliveryScope.SINGLE,
        ),
        status=JobStatus.RUNNING,
        terminal_decision=None,
        cancel_requested_at=None,
        created_at='2026-06-13T00:00:00Z',
        updated_at='2026-06-13T00:00:00Z',
        workspace_path=str(work_dir),
    )


def _ready_pane(req_id: str = 'job_agynative123', reply: str = 'native agy pane reply') -> str:
    return (
        f'> CCB_REQ_ID: {req_id}\n'
        '  hello\n'
        '\n'
        '▸ Thought for 3s, 400 tokens\n'
        f'  {reply}\n'
        '\n'
        '────────────────────────────────────────────────────────────\n'
        '>\n'
        '────────────────────────────────────────────────────────────\n'
        '? for shortcuts                                                   Gemini 3.1 Pro (High)\n'
    )


def test_agy_poll_completes_from_native_transcript(tmp_path: Path) -> None:
    home = tmp_path / 'home'
    work_dir = tmp_path / 'project'
    work_dir.mkdir()
    transcript = (
        home
        / '.gemini'
        / 'antigravity-cli'
        / 'brain'
        / 'conv-1'
        / '.system_generated'
        / 'logs'
        / 'transcript.jsonl'
    )
    _write_jsonl(
        transcript,
        [
            {
                'step_index': 1,
                'source': 'USER_EXPLICIT',
                'type': 'USER_INPUT',
                'status': 'DONE',
                'created_at': '2026-06-13T00:00:01Z',
                'content': 'CCB_REQ_ID: job_agynative123\nhello',
            },
            {
                'step_index': 2,
                'source': 'MODEL',
                'type': 'PLANNER_RESPONSE',
                'status': 'DONE',
                'created_at': '2026-06-13T00:00:03Z',
                'content': 'native agy reply',
            },
        ],
    )

    result = poll_submission(_submission(work_dir, home), now='2026-06-13T00:00:05Z')

    assert result is not None
    assert result.decision is None
    assert result.submission.reply == 'native agy reply'
    assert [item.kind for item in result.items] == [
        CompletionItemKind.SESSION_ROTATE,
        CompletionItemKind.ANCHOR_SEEN,
        CompletionItemKind.ASSISTANT_FINAL,
        CompletionItemKind.TURN_BOUNDARY,
    ]
    assert result.items[-1].payload['reason'] == 'agy_transcript_response_done'


def test_agy_start_defers_prompt_until_pane_ready(monkeypatch, tmp_path: Path) -> None:
    work_dir = tmp_path / 'project'
    home = tmp_path / 'home'
    runtime_dir = tmp_path / 'runtime'
    work_dir.mkdir()
    backend = _Backend('▸ Thought for 30s, 1.1k tokens\n  still working\n')
    session = type(
        'Session',
        (),
        {
            'pane_id': '%9',
            'runtime_dir': runtime_dir,
            'start_cmd': f"export HOME='{home}'; agy",
            'backend': lambda self: backend,
        },
    )()
    monkeypatch.setattr(agy_start, 'load_project_session', lambda *_args, **_kwargs: session)

    submission = agy_start.start_submission(
        _job(work_dir),
        context=None,
        now='2026-06-13T00:00:00Z',
        provider='agy',
    )

    assert submission.runtime_state['prompt_sent'] is False
    assert submission.runtime_state['prompt_deferred_until_ready'] is True
    assert backend.sent == []

    backend.text = _ready_pane()
    result = poll_submission(submission, now='2026-06-13T00:00:05Z')

    assert result is not None
    assert result.decision is None
    assert result.submission.runtime_state['prompt_sent'] is True
    assert result.submission.runtime_state['started_at'] == '2026-06-13T00:00:05Z'
    assert len(backend.sent) == 1
    assert 'CCB_REQ_ID: job_agynative123' in backend.sent[0][1]


def test_agy_ready_detector_ignores_old_prompt_before_active_thought() -> None:
    pane_text = (
        '────────────────────────────────────────────────────────────\n'
        '>\n'
        '────────────────────────────────────────────────────────────\n'
        '▸ Thought for 30s, 1.1k tokens\n'
        '  still working\n'
        '? for shortcuts                                                   Gemini 3.1 Pro (High)\n'
    )

    assert agy_pane_ready_for_input(pane_text) is False


def test_agy_poll_does_not_anchor_timeout_while_pane_busy(tmp_path: Path) -> None:
    home = tmp_path / 'home'
    work_dir = tmp_path / 'project'
    work_dir.mkdir()
    submission = _submission(work_dir, home)
    submission.runtime_state['backend'] = _Backend('▸ Thought for 301s, 2.0k tokens\n  still working\n')

    result = poll_submission(submission, now='2026-06-13T00:05:01Z')

    assert result is not None
    assert result.decision is None


def test_agy_poll_accepts_transcript_after_ambiguous_send_error(tmp_path: Path) -> None:
    home = tmp_path / 'home'
    work_dir = tmp_path / 'project'
    work_dir.mkdir()
    transcript = (
        home
        / '.gemini'
        / 'antigravity-cli'
        / 'brain'
        / 'conv-1'
        / '.system_generated'
        / 'logs'
        / 'transcript.jsonl'
    )
    _write_jsonl(
        transcript,
        [
            {
                'step_index': 1,
                'source': 'USER_EXPLICIT',
                'type': 'USER_INPUT',
                'status': 'DONE',
                'created_at': '2026-06-13T00:00:01Z',
                'content': 'CCB_REQ_ID: job_agynative123\nhello',
            },
            {
                'step_index': 2,
                'source': 'MODEL',
                'type': 'PLANNER_RESPONSE',
                'status': 'DONE',
                'created_at': '2026-06-13T00:00:03Z',
                'content': 'reply despite tmux send warning',
            },
        ],
    )
    submission = _submission(work_dir, home)
    submission.runtime_state['prompt_sent'] = False
    submission.runtime_state['send_error'] = "send_text_failed:CalledProcessError(1, ['tmux', 'send-keys'])"

    result = poll_submission(submission, now='2026-06-13T00:00:05Z')

    assert result is not None
    assert result.decision is None
    assert result.submission.reply == 'reply despite tmux send warning'
    assert result.items[-1].payload['reason'] == 'agy_transcript_response_done'
    assert result.submission.runtime_state['delivery_ambiguous_send_error']


def test_agy_poll_completes_from_stable_pane_fallback_when_transcript_lags(tmp_path: Path) -> None:
    home = tmp_path / 'home'
    work_dir = tmp_path / 'project'
    work_dir.mkdir()
    submission = _submission(work_dir, home)
    submission.runtime_state['backend'] = _Backend(_ready_pane())

    first = poll_submission(submission, now='2026-06-13T00:00:05Z')

    assert first is not None
    assert first.decision is None
    assert first.submission.reply == 'native agy pane reply'
    assert [item.kind for item in first.items] == [
        CompletionItemKind.SESSION_ROTATE,
        CompletionItemKind.ANCHOR_SEEN,
        CompletionItemKind.ASSISTANT_FINAL,
    ]

    stable = poll_submission(first.submission, now='2026-06-13T00:00:16Z')

    assert stable is not None
    assert stable.decision is None
    assert stable.submission.reply == 'native agy pane reply'
    assert [item.kind for item in stable.items] == [CompletionItemKind.TURN_BOUNDARY]


def test_agy_coalesced_user_input_marks_non_latest_request_incomplete(tmp_path: Path) -> None:
    home = tmp_path / 'home'
    work_dir = tmp_path / 'project'
    work_dir.mkdir()
    transcript = (
        home
        / '.gemini'
        / 'antigravity-cli'
        / 'brain'
        / 'conv-1'
        / '.system_generated'
        / 'logs'
        / 'transcript.jsonl'
    )
    _write_jsonl(
        transcript,
        [
            {
                'step_index': 1,
                'source': 'USER_EXPLICIT',
                'type': 'USER_INPUT',
                'status': 'DONE',
                'created_at': '2026-06-13T00:00:01Z',
                'content': 'CCB_REQ_ID: job_agynative123\nold\n\nCCB_REQ_ID: job_next456\nnew',
            },
            {
                'step_index': 2,
                'source': 'MODEL',
                'type': 'PLANNER_RESPONSE',
                'status': 'DONE',
                'created_at': '2026-06-13T00:00:03Z',
                'content': 'reply for latest',
            },
        ],
    )

    observed = observe_agy_transcript(work_dir, 'job_agynative123', home_candidates=[home])

    assert observed is not None
    assert observed.completed is False
    assert observed.coalesced_request_ids == ('job_agynative123', 'job_next456')
    assert observed.request_is_latest is False

    result = poll_submission(_submission(work_dir, home), now='2026-06-13T00:00:05Z')

    assert result is not None
    assert result.decision is not None
    assert result.decision.status is CompletionStatus.INCOMPLETE
    assert result.decision.reason == 'agy_request_coalesced'
    assert result.decision.diagnostics['request_coalesced'] is True
