# Phase 6 Additive Apply Design

Date: 2026-05-29

## Scope

Phase 6a is design-only. It does not enable non-dry-run `ccb reload`, call
tmux, mount providers, write runtime authority, update lifecycle/lease state, or
publish a service graph.

Phase 6b may enable only these mutating classes:

- `view_only_change`;
- append-only `add_agent`;
- `add_window`.

`remove_agent`, `replace_agent`, `move_agent`, and arbitrary `layout_change`
remain rejected until later phases.

## Current API Findings

`project_reload_config` currently rejects non-dry-run before loading the new
config. Keep that guard until the additive transaction below exists.

`build_ccbd_service_graph()` is the right way to build a new config-bound
bundle. `publish_ccbd_service_graph()` is the only publish step and must be the
last in-memory graph mutation after namespace, runtime, lease, and lifecycle
state are consistent.

`ensure_project_namespace()` is not safe as the Phase 6b additive entrypoint.
For explicit window topology it calls `topology_recreate_reason()`, and missing
windows, missing agent panes, or missing sidebar panes become recreate reasons.
That is correct for cold start but too broad for hot reload.

The reusable tmux primitives are lower-level:

- `create_window()` for a new managed window in the current project session;
- `window_root_pane()` for the new window root pane;
- `split_pane()` for sidebar and agent leaves;
- `apply_ccb_pane_identity()` for `@ccb_project_id`, role, slot, window,
  namespace epoch, and `managed_by=ccbd` options;
- `existing_topology_agent_panes()` and a new preservation snapshot helper for
  pre/post pane evidence.

The reusable runtime path is `run_start_flow()` with
`namespace_agent_panes={new_agent: pane_id}` and
`cleanup_tmux_orphans=False`. It already passes assigned panes into
`start_agent_runtime()`, which launches or reuses provider runtime, relabels the
project namespace pane, and writes runtime authority through `RuntimeService`.
Phase 6b should call it only for newly-added agents, not for preserved agents.

`CcbdStartPolicyStore` should be read, not updated, by reload. Startup owns
persisting policy; reload should inherit `recovery_restore` and
`auto_permission` when present.

`MountManager.mark_mounted()` is the existing mounted lease write path, but
reload should not call it directly because it is a startup-style write unless
all current holder, generation, and `started_at` fields are replayed exactly.
Phase 6b needs a narrow wrapper that asserts the current lease holder matches
`app.pid` and `app.daemon_instance_id`, then rewrites only the
signature/heartbeat fields.

Lifecycle signature update can reuse the existing lifecycle model by loading the
current mounted lifecycle and saving `with_updates(config_signature=...,
namespace_epoch=...)`. Phase 6b should add a named helper so reload does not
call the startup-only `_mark_lifecycle_mounted()` path directly.

## Required Narrow APIs

Add these before opening non-dry-run reload:

- `ProjectNamespaceController.apply_additive_patch(plan, old_topology,
  new_topology, timeout_s=...) -> NamespacePatchApplyResult`.
- `NamespacePatchApplyResult` fields:
  `created_windows`, `created_panes`, `agent_panes`, `sidebar_panes`,
  `preserved_before`, `preserved_after`, `partial`, `rollback_actions`, and
  `diagnostics`.
- `snapshot_preserved_agent_panes(controller, context, agents) -> dict[str,
  str]`.
- `assert_preserved_agent_panes(before, after)` to fail before publish if any
  preserved agent has a changed or missing pane id.
- `update_current_lease_config_signature(app, new_signature)`.
- `update_mounted_lifecycle_config_signature(app, new_signature,
  namespace_epoch)`.
- `build_reload_service_graph(app, new_config, version=...)`, a reload wrapper
  around `build_ccbd_service_graph()` that reuses startup dependencies and does
  not publish.
- `run_additive_agent_mounts(app, graph, namespace, agent_panes, agent_names)`,
  which calls `run_start_flow()` or a small supervisor wrapper only for new
  agents, with `cleanup_tmux_orphans=False`,
  `interactive_tmux_layout=True`, and explicit `namespace_agent_panes`.

## Add Agent Append

The Phase 5 planner only accepts append-only changes where the old window agent
list is a prefix of the new list. Phase 6b should implement this by:

1. Loading the current namespace and verifying project id, tmux socket path,
   session name, namespace epoch, window, role, slot key, and
   `managed_by=ccbd`.
2. Taking `preserved_before` for `namespace_patch_plan.preserved_agents`.
   This list is only the input set for the preservation gate, not a promise
   that panes were already reused.
3. Finding the anchor pane from the previous managed agent in the same window.
4. Splitting exactly one new pane per appended agent from the anchor/previous
   new pane, then applying CCB pane identity to the new pane.
5. Returning `agent_panes` only for new agents and `preserved_after` for the
   preservation gate.

Missing narrow API: a supported append splitter that computes the split
direction/percent for the appended leaf without parsing the whole new layout
into a full-window materialization that would touch old panes. Until that API
exists, Phase 6b should accept only a constrained append placement such as
"split after anchor with default horizontal/right or bottom policy" and record
the limitation.

## Add Window

`add_window` should not call `ensure_project_namespace(topology_plan=new_plan)`,
because that path can recreate the whole namespace.

The narrow patcher should:

1. Verify the current session identity from namespace state.
2. Call `create_window()` with `session_name=current.tmux_session_name`,
   the new window name, and project root. This is project/session scoped.
3. Resolve the new window root pane with `window_root_pane()`.
4. If sidebar is enabled, split the root pane, respawn the sidebar command, and
   apply sidebar CCB identity for the new window only.
5. Materialize only the new window's agent layout under the new window user
   root, applying CCB identity to each new agent pane.
6. Refresh project tmux UI/sidebar width for the project session only.
7. Persist namespace state with the new topology signature and the same
   namespace epoch unless a later decision explicitly advances epoch for
   additive patches. The chosen rule must be consistent with focus requests that
   validate namespace epoch.

This path creates no windows or panes for existing windows and must not call
`kill_server`, `kill_window`, `reflow_workspace`, `force_recreate_namespace`, or
`topology_recreate_reason()` as an apply gate.

## Transaction Order

For accepted non-dry-run reload, Phase 6b should execute in this order:

1. Acquire a reload/app maintenance lock so heartbeat does not concurrently
   mount/reconcile through the old desired set while the transaction is active.
2. Read current graph, load new config once, build the dry-run plan, and reject
   unless the plan class is `view_only_change`, append-only `add_agent`, or
   `add_window` with an unblocked namespace patch plan.
3. Build the new service graph but do not publish it.
4. Snapshot preserved agent pane ids and existing runtime authority for
   `preserved_agents`.
5. Apply the additive namespace patch and collect new pane ids. For
   `view_only_change`, skip tmux namespace mutation.
6. Mount/start only new agents through the new graph runtime service and the
   current start policy, using the new pane ids from the patcher.
7. Verify every new configured agent has runtime authority and every preserved
   agent has unchanged pane id/runtime authority evidence.
8. Update lease config signature for the current daemon holder.
9. Update mounted lifecycle config signature and namespace epoch.
10. Publish the new service graph.
11. Invalidate project view cache and refresh managed sidebar panes in the
    project session.
12. Return a structured apply summary.

The graph publish step is intentionally after all durable state required by
keeper and handlers is consistent. If any earlier step fails, handlers continue
reading the old graph.

The final signature handoff needs a dedicated Phase 6b race test. The keeper
process checks the mounted daemon by calling `ping('ccbd')` and comparing the
daemon-reported config signature with the on-disk config. A reload implementation
must therefore prevent a keeper-visible window where disk config is new,
`ping('ccbd')` still reports the old graph signature, and the keeper requests
shutdown. If the lease/lifecycle writes cannot be proven adjacent enough to
graph publish, Phase 6b must add an explicit reload-in-progress keeper grace or
another tested handoff mechanism before enabling non-dry-run reload.

## Failure And Diagnostics

Failure before namespace patch:

- return `reload_status=blocked` or `failed`;
- do not publish a graph;
- do not write lease/lifecycle signature;
- no rollback is required because no mutation happened.

Failure during namespace patch:

- do not publish a graph;
- do not write lease/lifecycle signature;
- return created panes/windows and `partial=true`;
- best-effort rollback may kill only panes/windows created by this patch and
  only if their identity options prove `project_id`, session, namespace epoch,
  role, slot, and `managed_by=ccbd`;
- if rollback is not proven, leave created panes as managed residue and report a
  recoverable diagnostic for a later repair path.

Failure during new runtime mount:

- do not publish a graph;
- do not write lease/lifecycle signature;
- preserve any runtime failure records written by the normal mount path for the
  new agent only;
- leave existing agents untouched;
- return the new pane/runtime diagnostic so the user can retry after fixing the
  provider problem.

Failure during lease/lifecycle signature update:

- do not publish a graph;
- return failure with old graph active;
- new panes/runtime records may exist as residue or partially mounted new
  agents, but they are not part of the published desired graph until retry
  succeeds;
- diagnostics must include whether lease or lifecycle write failed.

Failure after graph publish:

- only project-view/sidebar refresh should remain. A refresh failure should be
  reported as degraded UI refresh, not as reload rollback, because config,
  namespace, runtime, lease, lifecycle, and graph are already consistent.

## Preservation Proof

`namespace_patch_plan.preserved_agents` is the set of agents common to old and
new topology. It is not a claim that panes have already been reused.

Phase 6b must prove preservation by recording:

- `preserved_before`: agent -> pane id from current CCB tmux identity options
  before patch;
- `preserved_after`: agent -> pane id after patch;
- unchanged runtime authority fields for preserved agents, especially pane id,
  runtime refs, provider/session refs, and daemon generation.

Reload must fail before graph publish if a preserved agent is missing in either
snapshot or has a changed pane id.

## Scope Diagnostics

Dry-run and apply diagnostics should distinguish:

- namespace state load failed;
- namespace state missing;
- project id mismatch;
- tmux socket path missing;
- session name missing;
- namespace epoch missing;
- UI not attachable.

The current Phase 5 `_current_namespace(app)` returns `None` for both missing
state and load failure, and `reload_patch` reports a broad scope failure. Phase
6b should return a small diagnostic object instead, while preserving the
existing dry-run payload shape for compatibility.

## Phase 6b First Step

The smallest implementation step is not enabling `ccb reload`. First add a fake
backend unit-tested namespace patch apply API for `add_window` only:

- input: Phase 5 `namespace_patch_plan`, old/new topology, and current
  namespace;
- output: `NamespacePatchApplyResult`;
- tests: no calls to `kill_server`, `kill_window`, `reflow_workspace`, or
  `ensure_project_namespace`; only project/session-scoped `create_window`,
  `split_pane`, and identity writes for the new window.

After that passes, add append-only `add_agent`, then wire runtime mounts, then
open non-dry-run reload behind the transaction order above.

Implementation status:

- `ProjectNamespaceController.apply_additive_patch(...)` now exists and returns
  `NamespacePatchApplyResult`.
- The first implementation supports `add_window` only and blocks append-only
  `add_agent`.
- The fake-backend tests cover new window/sidebar/agent pane creation,
  `managed_by=ccbd` identity evidence, preservation snapshots, failure
  diagnostics, and continued non-dry-run reload rejection.
- The API is not wired into `project_reload_config`; it does not mount
  providers, write runtime authority, update lease/lifecycle, publish a graph,
  or add config watching.
