from __future__ import annotations

from dataclasses import replace

from agents.config_loader import load_project_config
from ccbd.lifecycle_report_store import CcbdStartupReportStore

from .daemon import ensure_daemon_started
from .daemon_runtime.policy import STARTUP_TRANSACTION_TIMEOUT_S
from .layout_status import layout_status
from .maintenance import startup_ensure_maintenance_heartbeat
from .start_runtime import StartSummary, start_agents as _start_agents_impl
from .tmux_project_cleanup import ProjectTmuxCleanupSummary
from workspace.reconcile import format_workspace_blockers, reconcile_start_workspaces


def start_agents(
    context,
    command,
    *,
    terminal_size: tuple[int, int] | None = None,
) -> StartSummary:
    summary = _start_agents_impl(
        context,
        command,
        terminal_size=terminal_size,
        ensure_daemon_started_fn=ensure_daemon_started,
        startup_report_store_cls=CcbdStartupReportStore,
        cleanup_summary_cls=ProjectTmuxCleanupSummary,
        before_client_start_fn=_reconcile_start_workspaces,
        enrich_summary_fn=_merge_workspace_guard_summary,
        start_rpc_timeout_s=STARTUP_TRANSACTION_TIMEOUT_S,
    )
    summary = _attach_start_layout_summary(context, summary)
    heartbeat_summary = startup_ensure_maintenance_heartbeat(context)
    if heartbeat_summary is None:
        return summary
    return replace(summary, maintenance_heartbeat=heartbeat_summary)


def _reconcile_start_workspaces(context):
    summary = reconcile_start_workspaces(
        context.project.project_root,
        load_project_config(context.project.project_root).config,
    )
    if summary.blockers:
        raise RuntimeError(format_workspace_blockers('ccb start', summary.blockers))
    return summary


def _merge_workspace_guard_summary(context, summary: StartSummary, guard_summary) -> StartSummary:
    del context
    if guard_summary is None:
        return summary
    return replace(
        summary,
        worktree_warnings=tuple(getattr(guard_summary, 'warnings', ()) or ()),
        worktree_retired=tuple(getattr(guard_summary, 'retired', ()) or ()),
    )


def _attach_start_layout_summary(context, summary: StartSummary) -> StartSummary:
    try:
        payload = layout_status(context)
    except Exception as exc:
        payload = {
            'layout_summary_status': 'unavailable',
            'layout_status': 'unavailable',
            'error_type': type(exc).__name__,
            'error': str(exc),
        }
    else:
        payload = _compact_start_layout_summary(payload)
    return replace(summary, layout_summary=payload)


def _compact_start_layout_summary(payload: dict[str, object]) -> dict[str, object]:
    observed = payload.get('observed') if isinstance(payload.get('observed'), dict) else {}
    windows = [
        _compact_start_window(window)
        for window in tuple(payload.get('windows') or ())
        if isinstance(window, dict)
    ]
    return {
        'layout_summary_status': str(payload.get('layout_status') or 'unknown'),
        'layout_status': payload.get('layout_status'),
        'ccbd_state': payload.get('ccbd_state'),
        'windows_explicit': bool(payload.get('windows_explicit')),
        'entry_window': payload.get('entry_window'),
        'window_count': payload.get('window_count'),
        'pane_count': payload.get('pane_count'),
        'dynamic_agent_count': payload.get('dynamic_agent_count'),
        'loop_agent_count': payload.get('loop_agent_count'),
        'runtime_agent_count': payload.get('runtime_agent_count'),
        'observe_status': observed.get('observe_status'),
        'observe_reason': observed.get('reason'),
        'observed_pane_count': observed.get('observed_pane_count'),
        'windows': windows,
    }


def _compact_start_window(window: dict[str, object]) -> dict[str, object]:
    agents = [
        _compact_start_agent(agent)
        for agent in tuple(window.get('agents') or ())
        if isinstance(agent, dict)
    ]
    return {
        'name': window.get('name'),
        'index': window.get('index'),
        'pane_count': window.get('pane_count'),
        'runtime_pane_count': window.get('runtime_pane_count'),
        'agent_names': list(window.get('agent_names') or ()),
        'agents': agents,
    }


def _compact_start_agent(agent: dict[str, object]) -> dict[str, object]:
    return {
        'agent': agent.get('agent'),
        'source': agent.get('source'),
        'agent_kind': agent.get('agent_kind'),
        'ownership_class': agent.get('ownership_class'),
        'dispatch_state': agent.get('dispatch_state'),
        'window_name': agent.get('window_name'),
        'pane_id': agent.get('pane_id'),
        'pane_identity_source': agent.get('pane_identity_source'),
        'runtime_state': agent.get('runtime_state'),
        'apply_status': agent.get('apply_status'),
        'failed_apply': agent.get('failed_apply'),
    }


__all__ = ['StartSummary', 'start_agents']
