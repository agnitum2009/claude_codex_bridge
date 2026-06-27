from __future__ import annotations

from ccbd.reload_additive_agents import window_agent_names, window_map

from .backend import find_window, kill_window, session_window_target
from .materialize_topology import sync_topology_sidebar_widths


def remove_agent_panes(
    controller,
    backend,
    *,
    old_topology,
    new_topology,
    existing_agent_panes: dict[str, str],
    current,
    result,
    timeout_s: float | None,
) -> None:
    old_windows = window_map(old_topology)
    new_windows = window_map(new_topology)
    removed_windows = set(old_windows) - set(new_windows)
    for window_name, old_window in old_windows.items():
        if window_name in removed_windows:
            if str(getattr(old_window, 'kind', '') or '') == 'tool':
                continue
            _remove_window_agents(
                backend,
                window_name=window_name,
                agents=window_agent_names(old_window),
                existing_agent_panes=existing_agent_panes,
                current=current,
                result=result,
                timeout_s=timeout_s,
            )
            _kill_window(backend, current=current, window_name=window_name, result=result, timeout_s=timeout_s)
            continue
        new_window = new_windows.get(window_name)
        if new_window is None:
            continue
        new_agents = set(window_agent_names(new_window))
        removed_agents = tuple(agent for agent in window_agent_names(old_window) if agent not in new_agents)
        _remove_window_agents(
            backend,
            window_name=window_name,
            agents=removed_agents,
            existing_agent_panes=existing_agent_panes,
            current=current,
            result=result,
            timeout_s=timeout_s,
        )
        if removed_agents:
            _reflow_window_after_remove(
                controller,
                backend,
                current=current,
                topology_plan=new_topology,
                window_name=window_name,
                result=result,
                timeout_s=timeout_s,
            )


def _remove_window_agents(
    backend,
    *,
    window_name: str,
    agents: tuple[str, ...],
    existing_agent_panes: dict[str, str],
    current,
    result,
    timeout_s: float | None,
) -> None:
    del current
    for agent_name in agents:
        pane_id = existing_agent_panes.get(agent_name)
        if not pane_id:
            raise RuntimeError(f'pane missing for removed agent {agent_name!r}')
        _kill_pane(backend, pane_id, timeout_s=timeout_s)
        _append_unique(result.removed_panes, pane_id)
        result.removed_agents[agent_name] = pane_id


def _kill_window(backend, *, current, window_name: str, result, timeout_s: float | None) -> None:
    kill_window(
        backend,
        target=session_window_target(current.tmux_session_name, window_name),
        timeout_s=timeout_s,
    )
    _append_unique(result.removed_windows, window_name)


def _reflow_window_after_remove(
    controller,
    backend,
    *,
    current,
    topology_plan,
    window_name: str,
    result,
    timeout_s: float | None,
) -> None:
    target = _reflow_target(backend, current=current, topology_plan=topology_plan, window_name=window_name, timeout_s=timeout_s)
    runner = getattr(backend, '_tmux_run', None)
    if not callable(runner):
        result.reflow_errors[window_name] = 'tmux backend does not support select-layout'
        return
    try:
        completed = runner(
            ['select-layout', '-E', '-t', target],
            check=False,
            capture=True,
            timeout=timeout_s,
        )
    except Exception as exc:
        result.reflow_errors[window_name] = str(exc)
        return
    if int(getattr(completed, 'returncode', 1) or 0) != 0:
        detail = str(getattr(completed, 'stderr', '') or getattr(completed, 'stdout', '') or '').strip()
        result.reflow_errors[window_name] = detail or 'select-layout failed'
        return
    _append_unique(result.reflowed_windows, window_name)
    try:
        sync_topology_sidebar_widths(
            controller,
            backend,
            session_name=current.tmux_session_name,
            topology_plan=topology_plan,
            timeout_s=timeout_s,
        )
    except Exception as exc:
        result.reflow_errors[window_name] = f'sidebar_width_sync_failed: {exc}'


def _reflow_target(backend, *, current, topology_plan, window_name: str, timeout_s: float | None) -> str:
    session_name = current.tmux_session_name
    if find_window(backend, session_name=session_name, window_name=window_name, timeout_s=timeout_s) is not None:
        return session_window_target(session_name, window_name)
    if _is_entry_window(topology_plan, window_name):
        workspace_ref = str(getattr(current, 'workspace_window_id', '') or '').strip()
        if not workspace_ref:
            workspace_ref = str(getattr(current, 'workspace_window_name', '') or '').strip()
        if workspace_ref:
            return session_window_target(session_name, workspace_ref)
    return session_window_target(session_name, window_name)


def _is_entry_window(topology_plan, window_name: str) -> bool:
    target = str(window_name or '').strip()
    if not target:
        return False
    entry = str(getattr(topology_plan, 'entry_window', '') or '').strip()
    if entry and target == entry:
        return True
    windows = tuple(getattr(topology_plan, 'windows', ()) or ())
    first = str(getattr(windows[0], 'name', '') or '').strip() if windows else ''
    return bool(first and target == first)


def _kill_pane(backend, pane_id: str, *, timeout_s: float | None) -> None:
    killer = getattr(backend, 'kill_pane', None)
    if callable(killer):
        try:
            killer(pane_id)
            return
        except TypeError:
            killer(pane_id, timeout_s=timeout_s)
            return
    runner = getattr(backend, '_tmux_run', None)
    if not callable(runner):
        raise RuntimeError('tmux backend does not support kill-pane')
    result = runner(['kill-pane', '-t', pane_id], check=False, capture=True, timeout=timeout_s)
    if int(getattr(result, 'returncode', 1) or 0) != 0:
        detail = str(getattr(result, 'stderr', '') or getattr(result, 'stdout', '') or '').strip()
        raise RuntimeError(f'failed to kill tmux pane {pane_id!r}: {detail}')


def _append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)


__all__ = ['remove_agent_panes']
