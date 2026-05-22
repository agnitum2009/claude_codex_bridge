from __future__ import annotations

from dataclasses import replace

from completion.models import CompletionDecision
from storage.text_artifacts import maybe_spill_text


def spill_terminal_reply_if_needed(
    dispatcher,
    current,
    decision: CompletionDecision,
    *,
    finished_at: str,
) -> CompletionDecision:
    diagnostics = dict(decision.diagnostics or {})
    if isinstance(diagnostics.get('reply_artifact'), dict):
        return decision
    reply, artifact = maybe_spill_text(
        dispatcher._layout,
        text=decision.reply,
        kind='completion-reply',
        owner_id=current.job_id,
        prefix=f'CCB completion reply for job {current.job_id} is larger than 4 KiB and was stored as an artifact.',
        now=finished_at,
    )
    if artifact is None:
        return decision
    diagnostics['reply_artifact'] = artifact
    return replace(decision, reply=reply, diagnostics=diagnostics)


__all__ = ['spill_terminal_reply_if_needed']
