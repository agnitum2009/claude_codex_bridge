from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

from ccbd.api_models import JobRecord
from ccbd.system import parse_utc_timestamp
from completion.models import (
    CompletionCursor,
    CompletionItem,
    CompletionItemKind,
    CompletionSourceKind,
)

from .base import ProviderPollResult, ProviderSubmission
from .fake_runtime import (
    DEFAULT_LATENCY_SECONDS,
    FakeDirective,
    FakeScriptEvent,
    TERMINAL_KINDS,
    build_terminal_decision,
    default_script,
    first_text,
    materialize_payload,
    normalize_script_event,
    parse_directive,
)


class FakeProviderAdapter:
    def __init__(
        self,
        *,
        provider: str = 'fake',
        source_kind: CompletionSourceKind = CompletionSourceKind.STRUCTURED_RESULT_STREAM,
        script_mode: str = 'structured_result',
        latency_seconds: float = DEFAULT_LATENCY_SECONDS,
    ) -> None:
        self.provider = provider
        self._source_kind = source_kind
        self._script_mode = script_mode
        self._latency_seconds = latency_seconds

    def start(self, job: JobRecord, *, context, now: str) -> ProviderSubmission:
        del context
        directive = parse_directive(job.request.task_id, default_latency_seconds=self._latency_seconds)
        events = tuple(normalize_script_event(raw) for raw in (directive.script or default_script(directive, mode=self._script_mode)))
        max_delay_ms = max((event.at_ms for event in events), default=0)
        ready_at = parse_utc_timestamp(now) + timedelta(milliseconds=max_delay_ms)
        reply, attachments = _reply_for_body(job)
        return ProviderSubmission(
            job_id=job.job_id,
            agent_name=job.agent_name,
            provider=self.provider,
            accepted_at=now,
            ready_at=ready_at.isoformat().replace('+00:00', 'Z'),
            source_kind=self._source_kind,
            reply=reply,
            status=directive.status,
            reason=directive.reason,
            confidence=directive.confidence,
            diagnostics={'provider': self.provider, 'task_id': job.request.task_id},
            runtime_state={
                'events': [
                    {
                        'at_ms': event.at_ms,
                        'kind': event.kind.value if event.kind is not None else None,
                        'payload': dict(event.payload),
                    }
                    for event in events
                ],
                'next_index': 0,
                'next_seq': 1,
                'reply_buffer': '',
                'attachments': attachments,
            },
        )

    def poll(self, submission: ProviderSubmission, *, now: str) -> ProviderPollResult | None:
        state = dict(submission.runtime_state)
        events = list(state.get('events', []))
        next_index = int(state.get('next_index', 0))
        next_seq = int(state.get('next_seq', 1))
        reply_buffer = str(state.get('reply_buffer', ''))
        elapsed_ms = max(
            0,
            int((parse_utc_timestamp(now) - parse_utc_timestamp(submission.accepted_at)).total_seconds() * 1000),
        )

        emitted: list[CompletionItem] = []
        decision: CompletionDecision | None = None
        accepted_at = parse_utc_timestamp(submission.accepted_at)

        while next_index < len(events):
            raw_event = events[next_index]
            at_ms = int(raw_event['at_ms'])
            if at_ms > elapsed_ms:
                break

            kind_name = raw_event.get('kind')
            payload = dict(raw_event.get('payload') or {})
            next_index += 1
            if kind_name is None:
                continue

            kind = CompletionItemKind(str(kind_name))
            timestamp = (accepted_at + timedelta(milliseconds=at_ms)).isoformat().replace('+00:00', 'Z')
            payload, reply_buffer = materialize_payload(
                kind,
                payload,
                reply_buffer=reply_buffer,
                default_reply=submission.reply,
                turn_ref=submission.job_id,
                terminal_reason=submission.reason,
            )
            cursor = CompletionCursor(
                source_kind=submission.source_kind,
                event_seq=next_seq,
                updated_at=timestamp,
            )
            item = CompletionItem(
                kind=kind,
                timestamp=timestamp,
                cursor=cursor,
                provider=submission.provider,
                agent_name=submission.agent_name,
                req_id=submission.job_id,
                payload=payload,
            )
            emitted.append(item)
            next_seq += 1

            if kind in TERMINAL_KINDS:
                decision = build_terminal_decision(
                    submission,
                    payload=payload,
                    cursor=cursor,
                    finished_at=timestamp,
                    reply=reply_buffer or submission.reply,
                )
                break

        if not emitted and decision is None:
            return None

        updated = replace(
            submission,
            runtime_state={
                **state,
                'next_index': next_index,
                'next_seq': next_seq,
                'reply_buffer': reply_buffer,
            },
        )
        return ProviderPollResult(submission=updated, items=tuple(emitted), decision=decision)

    def export_runtime_state(self, submission: ProviderSubmission) -> dict[str, object]:
        return dict(submission.runtime_state)

    def resume(self, job: JobRecord, submission: ProviderSubmission, *, context, persisted_state, now: str) -> ProviderSubmission | None:
        del context, persisted_state, now
        if submission.job_id != job.job_id or submission.provider != job.provider:
            return None
        return submission


_build_terminal_decision = build_terminal_decision
_default_script = default_script
_first_text = first_text
_materialize_payload = materialize_payload
_normalize_script_event = normalize_script_event
_parse_directive = parse_directive


def _reply_for_body(job: JobRecord) -> tuple[str, list[dict[str, object]]]:
    agent_name = job.agent_name
    body = job.request.body
    marker = body.strip()
    prefix = 'ccb-local-md:'
    if marker.startswith(prefix):
        ident = marker[len(prefix) :].strip() or 'sample'
        return (
            f'# CCB Local Markdown {ident}\n\n'
            f'- reply marker: `ccb-local-reply:{ident}`\n'
            '- rendered list item from the real local backend\n\n'
            '```text\n'
            f'agent={agent_name}\n'
            'route=local-loopback\n'
            '```\n\n'
            f'[blocked local link](https://example.invalid/ccb-local-md/{ident})',
            []
        )
    
    artifact_prefix = 'ccb-local-artifact:'
    if marker.startswith(artifact_prefix):
        ident = marker[len(artifact_prefix) :].strip() or 'sample'
        
        import uuid
        import json
        import hashlib
        from pathlib import Path
        from datetime import datetime, timezone
        
        project_id = job.request.project_id
        route_options = dict(getattr(job.request, 'route_options', None) or {})
        mobile_files_dir_text = str(route_options.get('mobile_files_dir') or '').strip()
        if mobile_files_dir_text:
            mobile_files_dir = Path(mobile_files_dir_text)
        else:
            workspace_path = job.workspace_path
            if not workspace_path:
                return (f"FAKE_ERROR: no mobile file store to generate artifact for {ident}", [])
            project_root = Path(workspace_path).parents[4]
            mobile_files_dir = project_root / '.ccb' / 'ccbd' / 'mobile' / 'files'
        
        attachments = []
        
        txt_file_id = f'mobile-file-{uuid.uuid4().hex[:16]}'
        txt_body = f'Generated text artifact for {ident}'.encode('utf-8')
        txt_digest = hashlib.sha256(txt_body).hexdigest()
        txt_dir = mobile_files_dir / project_id / agent_name / txt_file_id
        txt_dir.mkdir(parents=True, exist_ok=True)
        (txt_dir / 'content.bin').write_bytes(txt_body)
        txt_meta = {
            'schema_version': 1,
            'file_id': txt_file_id,
            'project_id': project_id,
            'agent': agent_name,
            'device_id': 'backend-agent',
            'file_name': f'artifact-{ident}.txt',
            'mime_type': 'text/plain',
            'size_bytes': len(txt_body),
            'sha256': txt_digest,
            'created_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        }
        (txt_dir / 'metadata.json').write_text(json.dumps(txt_meta, ensure_ascii=False, sort_keys=True), encoding='utf-8')
        attachments.append({
            'file_id': txt_file_id,
            'file_name': f'artifact-{ident}.txt',
            'mime_type': 'text/plain',
            'size_bytes': len(txt_body),
            'kind': 'document',
        })
        
        png_file_id = f'mobile-file-{uuid.uuid4().hex[:16]}'
        png_body = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xfc\xcf\xc0\x00\x00\x03\x01\x01\x00\x18\xdd\x8d\xb0\x00\x00\x00\x00IEND\xaeB`\x82'
        png_digest = hashlib.sha256(png_body).hexdigest()
        png_dir = mobile_files_dir / project_id / agent_name / png_file_id
        png_dir.mkdir(parents=True, exist_ok=True)
        (png_dir / 'content.bin').write_bytes(png_body)
        png_meta = {
            'schema_version': 1,
            'file_id': png_file_id,
            'project_id': project_id,
            'agent': agent_name,
            'device_id': 'backend-agent',
            'file_name': f'image-{ident}.png',
            'mime_type': 'image/png',
            'size_bytes': len(png_body),
            'sha256': png_digest,
            'created_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        }
        (png_dir / 'metadata.json').write_text(json.dumps(png_meta, ensure_ascii=False, sort_keys=True), encoding='utf-8')
        attachments.append({
            'file_id': png_file_id,
            'file_name': f'image-{ident}.png',
            'mime_type': 'image/png',
            'size_bytes': len(png_body),
            'kind': 'image',
        })
        
        return (
            f'# CCB Local Artifacts {ident}\n\n'
            f'- generated artifact: [{txt_meta["file_name"]}](ccb-artifact://{txt_file_id})\n'
            f'- generated image: [{png_meta["file_name"]}](ccb-artifact://{png_file_id})\n',
            attachments
        )

    return (f'FAKE[{agent_name}] {body}', [])


__all__ = [
    'FakeDirective',
    'FakeProviderAdapter',
    'FakeScriptEvent',
]
