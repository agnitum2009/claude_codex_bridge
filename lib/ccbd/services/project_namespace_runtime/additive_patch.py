from __future__ import annotations

from dataclasses import dataclass, field
import shlex
from types import SimpleNamespace
from typing import Any

from agents.models import parse_layout_spec
from terminal_runtime.placeholders import pane_placeholder_cmd
from terminal_runtime.tmux_identity import apply_ccb_pane_identity

from .backend import build_backend, create_window, session_alive, session_window_target, split_pane, window_root_pane
from .materialize_topology import existing_topology_agent_panes


@dataclass(frozen=True)
class NamespacePatchApplyResult:
    status: str
    created_windows: tuple[str, ...] = ()
    created_panes: tuple[str, ...] = ()
    agent_panes: dict[str, str] = field(default_factory=dict)
    sidebar_panes: dict[str, str] = field(default_factory=dict)
    preserved_before: dict[str, str] = field(default_factory=dict)
    preserved_after: dict[str, str] = field(default_factory=dict)
    partial: bool = False
    rollback_actions: tuple[str, ...] = ()
    diagnostics: dict[str, object] = field(default_factory=dict)

    def to_record(self) -> dict[str, object]:
        return {
            'status': self.status,
            'created_windows': list(self.created_windows),
            'created_panes': list(self.created_panes),
            'agent_panes': dict(self.agent_panes),
            'sidebar_panes': dict(self.sidebar_panes),
            'preserved_before': dict(self.preserved_before),
            'preserved_after': dict(self.preserved_after),
            'partial': bool(self.partial),
            'rollback_actions': list(self.rollback_actions),
            'diagnostics': dict(self.diagnostics),
        }


def apply_additive_patch(
    controller,
    *,
    patch_plan: dict[str, object],
    old_topology,
    new_topology,
    timeout_s: float | None = None,
) -> NamespacePatchApplyResult:
    current = controller._state_store.load()
    if current is None:
        return _blocked('namespace_missing', 'project namespace state is not available')
    if not bool(getattr(current, 'ui_attachable', True)):
        return _blocked('namespace_not_attachable', 'project namespace is not UI attachable')
    if str(getattr(current, 'project_id', '') or '').strip() != str(controller._project_id):
        return _blocked('project_id_mismatch', 'project namespace project_id does not match controller project_id')
    if getattr(current, 'namespace_epoch', None) is None:
        return _blocked('namespace_epoch_missing', 'project namespace epoch is missing')
    if str(getattr(current, 'tmux_socket_path', '') or '').strip() == '':
        return _blocked('tmux_socket_path_missing', 'project namespace tmux socket path is missing')
    if str(getattr(current, 'tmux_session_name', '') or '').strip() == '':
        return _blocked('tmux_session_name_missing', 'project namespace tmux session name is missing')

    unsupported = _unsupported_reason(patch_plan, old_topology, new_topology)
    if unsupported is not None:
        return _blocked(*unsupported)

    backend = build_backend(controller._backend_factory, socket_path=current.tmux_socket_path)
    if not session_alive(backend, current.tmux_session_name, timeout_s=timeout_s):
        return _blocked('session_unavailable', 'project namespace tmux session is not alive')

    context = SimpleNamespace(backend=backend)
    preserved_agents = tuple(str(item) for item in tuple((patch_plan or {}).get('preserved_agents') or ()))
    preserved_before = snapshot_preserved_agent_panes(
        controller,
        context,
        topology_plan=old_topology,
        agents=preserved_agents,
    )
    created_windows: list[str] = []
    created_panes: list[str] = []
    agent_panes: dict[str, str] = {}
    sidebar_panes: dict[str, str] = {}

    try:
        for window in _new_windows(old_topology, new_topology):
            window_name = str(window.name)
            record = create_window(
                backend,
                session_name=current.tmux_session_name,
                window_name=window_name,
                project_root=controller._layout.project_root,
                select=False,
                timeout_s=timeout_s,
            )
            created_windows.append(window_name)
            root_pane = window_root_pane(
                backend,
                target_window=session_window_target(current.tmux_session_name, record.window_id or window_name),
                timeout_s=timeout_s,
            )
            _append_unique(created_panes, root_pane)
            user_root = root_pane
            sidebar = getattr(window, 'sidebar', None)
            if sidebar is not None:
                user_root = split_pane(
                    backend,
                    target=root_pane,
                    direction='right',
                    percent=_user_pane_percent_for_sidebar(getattr(sidebar, 'width', '15%')),
                    project_root=controller._layout.project_root,
                    timeout_s=timeout_s,
                )
                _append_unique(created_panes, user_root)
                _respawn_sidebar(backend, root_pane, getattr(sidebar, 'launch_args', ()), cwd=str(controller._layout.project_root))
                apply_ccb_pane_identity(
                    backend,
                    root_pane,
                    title='sidebar',
                    agent_label='sidebar',
                    project_id=controller._project_id,
                    role='sidebar',
                    slot_key=f'sidebar:{window_name}',
                    window_name=window_name,
                    sidebar_instance=window_name,
                    namespace_epoch=current.namespace_epoch,
                    managed_by='ccbd',
                )
                sidebar_panes[window_name] = root_pane
            agent_panes.update(
                _materialize_new_window_agents(
                    controller,
                    backend,
                    window=window,
                    user_root=user_root,
                    namespace_epoch=current.namespace_epoch,
                    created_panes=created_panes,
                    timeout_s=timeout_s,
                )
            )
    except Exception as exc:
        preserved_after = snapshot_preserved_agent_panes(
            controller,
            context,
            topology_plan=old_topology,
            agents=preserved_agents,
        )
        return NamespacePatchApplyResult(
            status='failed',
            created_windows=tuple(created_windows),
            created_panes=tuple(created_panes),
            agent_panes=agent_panes,
            sidebar_panes=sidebar_panes,
            preserved_before=preserved_before,
            preserved_after=preserved_after,
            partial=bool(created_windows or created_panes),
            rollback_actions=tuple(f'created_pane:{pane}' for pane in created_panes),
            diagnostics={
                'reason': 'namespace_patch_failed',
                'error_type': type(exc).__name__,
                'error': str(exc),
                'graph_published': False,
                'runtime_authority_written': False,
                'lease_or_lifecycle_written': False,
            },
        )

    preserved_after = snapshot_preserved_agent_panes(
        controller,
        context,
        topology_plan=old_topology,
        agents=preserved_agents,
    )
    try:
        assert_preserved_agent_panes(
            preserved_before,
            preserved_after,
            expected_agents=preserved_agents,
        )
    except Exception as exc:
        return NamespacePatchApplyResult(
            status='failed',
            created_windows=tuple(created_windows),
            created_panes=tuple(created_panes),
            agent_panes=agent_panes,
            sidebar_panes=sidebar_panes,
            preserved_before=preserved_before,
            preserved_after=preserved_after,
            partial=bool(created_windows or created_panes),
            rollback_actions=tuple(f'created_pane:{pane}' for pane in created_panes),
            diagnostics={
                'reason': 'preserved_agent_pane_changed',
                'error_type': type(exc).__name__,
                'error': str(exc),
                'graph_published': False,
                'runtime_authority_written': False,
                'lease_or_lifecycle_written': False,
            },
        )
    return NamespacePatchApplyResult(
        status='applied',
        created_windows=tuple(created_windows),
        created_panes=tuple(created_panes),
        agent_panes=agent_panes,
        sidebar_panes=sidebar_panes,
        preserved_before=preserved_before,
        preserved_after=preserved_after,
        partial=False,
        diagnostics={
            'supported_operations': ['add_window'],
            'namespace_state_written': False,
            'graph_published': False,
            'runtime_authority_written': False,
            'lease_or_lifecycle_written': False,
        },
    )


def snapshot_preserved_agent_panes(
    controller,
    context,
    *,
    topology_plan,
    agents: tuple[str, ...] | list[str],
) -> dict[str, str]:
    expected = {str(agent) for agent in tuple(agents or ())}
    if not expected:
        return {}
    panes = existing_topology_agent_panes(controller, context, topology_plan=topology_plan)
    return {agent: pane_id for agent, pane_id in panes.items() if agent in expected}


def assert_preserved_agent_panes(
    before: dict[str, str],
    after: dict[str, str],
    *,
    expected_agents: tuple[str, ...] | list[str] = (),
) -> None:
    expected = {str(agent) for agent in tuple(expected_agents or ())}
    missing_before = sorted(expected - set(before))
    missing_after = sorted((expected or set(before)) - set(after))
    missing = sorted(set(before) - set(after))
    changed = sorted(agent for agent in set(before) & set(after) if before[agent] != after[agent])
    if missing_before or missing_after or missing or changed:
        details = []
        if missing_before:
            details.append(f'missing_before={",".join(missing_before)}')
        if missing_after:
            details.append(f'missing_after={",".join(missing_after)}')
        if missing:
            details.append(f'missing={",".join(missing)}')
        if changed:
            details.append(f'changed={",".join(changed)}')
        raise RuntimeError(f'preserved agent pane ids changed: {" ".join(details)}')


def _unsupported_reason(patch_plan: dict[str, object], old_topology, new_topology) -> tuple[str, str] | None:
    if str((patch_plan or {}).get('status') or '') != 'planned':
        return ('patch_plan_not_planned', 'namespace patch plan is not planned')
    if tuple((patch_plan or {}).get('blocked_operations') or ()):
        return ('patch_plan_blocked', 'namespace patch plan has blocked operations')
    old_windows = set(_window_map(old_topology))
    new_windows = set(_window_map(new_topology))
    added_windows = new_windows - old_windows
    steps = tuple((patch_plan or {}).get('steps') or ())
    planned_windows = {
        str(step.get('window') or '')
        for step in steps
        if isinstance(step, dict) and step.get('action') == 'create_window'
    }
    if not planned_windows:
        return ('add_agent_not_implemented', 'Phase 6b first step only applies add_window patches')
    if planned_windows != added_windows:
        return ('patch_plan_mismatch', 'namespace patch plan windows do not match new topology windows')
    for step in steps:
        if not isinstance(step, dict):
            return ('invalid_patch_step', 'namespace patch plan step must be an object')
        action = str(step.get('action') or '')
        window = str(step.get('window') or '')
        if action == 'refresh_project_view':
            continue
        if action not in {'create_window', 'create_sidebar_pane', 'create_agent_pane'}:
            return ('unsupported_patch_step', f'unsupported namespace patch step: {action}')
        if window not in added_windows:
            return ('add_agent_not_implemented', 'Phase 6b first step only applies panes in newly-added windows')
        if str(step.get('managed_by') or '') != 'ccbd':
            return ('scope_proof_missing', 'namespace patch step is missing managed_by=ccbd proof')
        if action in {'create_sidebar_pane', 'create_agent_pane'}:
            role = str(step.get('role') or '')
            slot_key = str(step.get('slot_key') or '')
            if not role or not slot_key:
                return ('scope_proof_missing', 'namespace patch pane step is missing role or slot_key proof')
            expected_role = 'sidebar' if action == 'create_sidebar_pane' else 'agent'
            if role != expected_role:
                return ('scope_proof_mismatch', f'namespace patch pane step role must be {expected_role}')
    return None


def _new_windows(old_topology, new_topology) -> tuple[object, ...]:
    old_windows = set(_window_map(old_topology))
    return tuple(window for window in tuple(getattr(new_topology, 'windows', ()) or ()) if str(window.name) not in old_windows)


def _window_map(topology) -> dict[str, object]:
    return {str(window.name): window for window in tuple(getattr(topology, 'windows', ()) or ())}


def _materialize_new_window_agents(
    controller,
    backend,
    *,
    window,
    user_root: str,
    namespace_epoch: int,
    created_panes: list[str],
    timeout_s: float | None,
) -> dict[str, str]:
    layout = parse_layout_spec(window.user_layout)
    agent_names = tuple(str(name) for name in getattr(window, 'agent_names', ()) or ())
    style_index_by_agent = {name: index for index, name in enumerate(agent_names)}
    agent_panes: dict[str, str] = {}

    def assign_leaf(item: str, pane_id: str) -> None:
        if item == 'cmd':
            return
        _append_unique(created_panes, pane_id)
        agent_panes[item] = pane_id
        apply_ccb_pane_identity(
            backend,
            pane_id,
            title=item,
            agent_label=item,
            project_id=controller._project_id,
            order_index=style_index_by_agent.get(item),
            role='agent',
            slot_key=item,
            window_name=str(window.name),
            namespace_epoch=namespace_epoch,
            managed_by='ccbd',
        )

    _materialize_layout(
        controller,
        backend,
        parent_pane_id=user_root,
        node=layout,
        assign_leaf=assign_leaf,
        created_panes=created_panes,
        timeout_s=timeout_s,
    )
    return agent_panes


def _materialize_layout(
    controller,
    backend,
    *,
    parent_pane_id: str,
    node: Any,
    assign_leaf,
    created_panes: list[str],
    timeout_s: float | None,
) -> None:
    if node.kind == 'leaf':
        assert node.leaf is not None
        assign_leaf(node.leaf.name, parent_pane_id)
        return
    assert node.left is not None
    assert node.right is not None
    total = max(1, node.leaf_count)
    right_count = max(1, node.right.leaf_count)
    percent = max(1, min(99, round((right_count * 100) / total)))
    direction = 'right' if node.kind == 'horizontal' else 'bottom'
    new_pane_id = split_pane(
        backend,
        target=parent_pane_id,
        direction=direction,
        percent=percent,
        project_root=controller._layout.project_root,
        timeout_s=timeout_s,
    )
    _append_unique(created_panes, new_pane_id)
    _materialize_layout(
        controller,
        backend,
        parent_pane_id=parent_pane_id,
        node=node.left,
        assign_leaf=assign_leaf,
        created_panes=created_panes,
        timeout_s=timeout_s,
    )
    _materialize_layout(
        controller,
        backend,
        parent_pane_id=new_pane_id,
        node=node.right,
        assign_leaf=assign_leaf,
        created_panes=created_panes,
        timeout_s=timeout_s,
    )


def _user_pane_percent_for_sidebar(width: object) -> int:
    text = str(width or '').strip()
    if text.endswith('%'):
        try:
            sidebar_percent = int(text[:-1])
        except Exception:
            sidebar_percent = 15
        return max(10, min(99, 100 - sidebar_percent))
    return 85


def _respawn_sidebar(backend, pane_id: str, launch_args: tuple[str, ...], *, cwd: str) -> None:
    args = tuple(launch_args or ())
    command = ' '.join(shlex.quote(str(part)) for part in args) if args else pane_placeholder_cmd()
    respawn = getattr(backend, 'respawn_pane', None)
    if callable(respawn):
        respawn(pane_id, cmd=command, cwd=cwd, remain_on_exit=True)
        return
    runner = getattr(backend, '_tmux_run', None)
    if callable(runner):
        runner(['respawn-pane', '-k', '-t', pane_id, 'sh', '-lc', command], check=False)


def _blocked(reason: str, message: str) -> NamespacePatchApplyResult:
    return NamespacePatchApplyResult(
        status='blocked',
        diagnostics={
            'reason': reason,
            'message': message,
            'graph_published': False,
            'runtime_authority_written': False,
            'lease_or_lifecycle_written': False,
        },
    )


def _append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)


__all__ = [
    'NamespacePatchApplyResult',
    'apply_additive_patch',
    'assert_preserved_agent_panes',
    'snapshot_preserved_agent_panes',
]
