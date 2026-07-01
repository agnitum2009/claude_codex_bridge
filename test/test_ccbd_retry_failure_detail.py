from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

from ccbd.services.dispatcher_runtime.finalization_retry_runtime.details import retry_failure_detail

_LIB = Path(__file__).resolve().parents[1] / 'lib'
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))


def _load_finish_hook_module():
    """Load bin/ccb-provider-finish-hook.py as a module (it has no package)."""
    hook_path = Path(__file__).resolve().parents[1] / 'bin' / 'ccb-provider-finish-hook.py'
    spec = importlib.util.spec_from_file_location('ccb_provider_finish_hook_test', hook_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_retry_failure_detail_collects_reason_and_diagnostics() -> None:
    decision = SimpleNamespace(
        reason="api_error",
        diagnostics={
            "error_type": "timeout",
            "error_code": "408",
            "error_message": "request timed out",
            "fault_rule_id": "rule-1",
        },
    )

    detail = retry_failure_detail(decision)

    assert detail == (
        "reason=api_error, error_type=timeout, error_code=408, "
        "error_message=request timed out, fault_rule_id=rule-1"
    )


def test_retry_failure_detail_falls_back_to_default_reason() -> None:
    decision = SimpleNamespace(reason="", diagnostics={})

    assert retry_failure_detail(decision) == "reason=api_error"


# --- provider content-error diagnostics on empty/error turns -------------


def test_codex_delivery_pane_signal_tags_usage_limit_with_pane_tail_and_retry_after() -> None:
    from provider_backends.codex.execution import _delivery_pane_signal

    banner = (
        "You've hit your usage limit. Visit https://chatgpt.com to purchase "
        "more credits or try again at Jul 2nd, 2026 10:21 AM."
    )

    class _Backend:
        def get_pane_content(self, pane_id, lines=120):
            return banner

    state = {'backend': _Backend(), 'pane_id': '%9'}
    signal = _delivery_pane_signal(state)

    assert signal is not None
    assert signal['error_kind'] == 'provider_usage_limit'
    assert signal['pane_signal_state'] == 'usage_limit'
    assert signal['retry_after'] == '2026-07-02T10:21:00'
    assert 'pane_tail' in signal
    assert 'usage limit' in signal['pane_tail'].lower()


def test_codex_delivery_pane_signal_returns_none_when_no_content_error() -> None:
    from provider_backends.codex.execution import _delivery_pane_signal

    class _Backend:
        def get_pane_content(self, pane_id, lines=120):
            return "openai codex\n› ready prompt"

    state = {'backend': _Backend(), 'pane_id': '%9'}
    assert _delivery_pane_signal(state) is None


def test_codex_delivery_pane_signal_returns_none_without_backend_seam() -> None:
    from provider_backends.codex.execution import _delivery_pane_signal

    # No get_pane_content on the backend -> nothing to tag.
    state = {'backend': SimpleNamespace(), 'pane_id': '%9'}
    assert _delivery_pane_signal(state) is None
    # No pane id at all.
    state2 = {'backend': object(), 'pane_id': ''}
    assert _delivery_pane_signal(state2) is None


def test_finish_hook_empty_reply_diagnostics_infers_usage_limit_error_kind() -> None:
    hook = _load_finish_hook_module()

    diagnostics = hook._empty_reply_diagnostics(
        reason='hook_after_agent_incomplete',
        context_text="You've hit your usage limit. try again at Jul 2nd, 2026 10:21 AM.",
    )

    assert diagnostics['empty_reply'] is True
    assert diagnostics['error_type'] == 'empty_provider_reply'
    assert diagnostics['error_kind'] == 'provider_usage_limit'


def test_finish_hook_empty_reply_diagnostics_has_no_error_kind_for_bare_empty_reply() -> None:
    hook = _load_finish_hook_module()

    diagnostics = hook._empty_reply_diagnostics(reason='hook_stop_empty_reply', context_text='')

    assert diagnostics['empty_reply'] is True
    assert 'error_kind' not in diagnostics


def test_finish_hook_empty_reply_diagnostics_maps_auth_and_api_markers() -> None:
    hook = _load_finish_hook_module()

    auth = hook._empty_reply_diagnostics(
        reason='hook_stop_empty_reply', context_text='Authentication failed: unauthorized'
    )
    assert auth['error_kind'] == 'provider_auth_failed'

    api = hook._empty_reply_diagnostics(
        reason='hook_stop_empty_reply', context_text='rate limit exceeded, too many requests'
    )
    assert api['error_kind'] == 'provider_api_error'
