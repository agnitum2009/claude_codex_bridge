# Execution Plan

Date: 2026-05-29

## Summary

Dynamic agent load/unload/replace must be delivered as a sequence of small
control-plane changes. The unsafe version is a single large `reload` handler
that reparses config, swaps objects, mutates tmux, and updates lifecycle in one
patch. The safe version first creates a measurable current-service boundary,
then a dry-run diff engine, then bounded mutation paths.

## Phase 0: Baseline And Instrumentation

Goal: know the current resource cost before reload work changes behavior.

Deliverables:

- Add metrics for heartbeat duration, project-view build duration, handler
  latency, reload duration, tmux command count, `capture-pane` count, and RSS.
- Expose the metrics through `ping` or diagnostics without adding a heavy read
  path.
- Add focused tests that metrics are updated without changing command behavior.
- Record a manual `test_ccb2` baseline with current release behavior.

Exit criteria:

- A no-op idle project has stable heartbeat and project-view timings.
- Metrics show whether CPU cost is dominated by heartbeat, project-view,
  tmux/capture-pane, dispatcher scans, or handler lock contention.

Rollback:

- Metrics must be removable or ignorable without changing runtime authority.

## Phase 1: Service Graph Boundary

Goal: make config-bound services replaceable as a bundle.

Deliverables:

- Introduce `CcbdServiceGraph` or equivalent bundle containing config,
  config identity, registry, runtime supervisor, runtime supervision,
  completion tracker, dispatcher, project view, project focus, and ping payload
  dependencies.
- Add one builder used by startup and future reload.
- Keep persistent stores, path layout, project namespace controller, mount
  manager, ownership guard, socket server, execution service, snapshot writer,
  and lifecycle generation outside the graph.
- Add graph version and created-at metadata for diagnostics.

Exit criteria:

- Startup behavior is identical when bootstrapped through the graph builder.
- Unit tests prove the graph can be built twice from the same config without
  writing runtime authority.

Rollback:

- Revert to direct `app.*` service fields because no reload mutation uses the
  graph yet.

## Phase 2: Non-Blocking Handler Routing

Goal: prevent stale handler captures after reload without adding request-path
lock contention.

Deliverables:

- Register stable handler wrappers once.
- Each wrapper resolves the current service graph at request time.
- The steady-state read path must not acquire a contended mutex.
- Mutating reload may acquire an exclusive publish lock, but ordinary submit,
  project-view, ping, queue, and focus requests should use the last fully
  published graph.

Exit criteria:

- Tests replace the graph and prove `submit`, `project_view`, `ping`, and
  focus handlers use the new graph.
- Startup registers stable wrappers once; wrappers read the current graph once
  per request without reparsing config or rebuilding the graph.
- `service_graph_retained_count` is explicitly scoped as published graph count
  until true old-graph in-flight retention is implemented in a later mutating
  reload phase.
- Handler latency does not regress beyond the gate in
  [performance-baseline-and-gates.md](performance-baseline-and-gates.md).

Rollback:

- Keep wrapper registration but point wrappers at the original graph.

## Phase 3: Dry-Run Reload

Goal: compute the reload plan without mutating daemon, tmux, runtime, or
lifecycle state.

Deliverables:

- Add `project_reload_config` dry-run service.
- Add CLI `ccb reload --dry-run`.
- Load and validate `.ccb/ccb.config`.
- Build old/new topology plans and classify the diff.
- Return planned operations, blocked operations, affected agents/windows, and
  estimated mutation class.

Exit criteria:

- Invalid config returns structured errors and leaves all state untouched.
- No-op reload reports no changes.
- Add, unload, replace, move, and view-only cases are classified.
- Phase 3 implementation status:
  - `project_reload_config` rejects non-dry-run requests before updating reload
    metrics.
  - `ccb reload --dry-run` calls the mounted daemon and does not bootstrap or
    write a missing `.ccb/ccb.config`.
  - returned payloads include old/new config signatures, `plan_class`,
    `safe_to_apply=false`, `future_safe_to_apply`, operations, reasons,
    warnings, and errors.
  - classification is conservative: existing agent spec changes are reported as
    `replace_agent`; presentation-only identity-preserving diffs are reported
    as `view_only_change`; Phase 3 does not split metadata-only agent fields
    from runtime-relevant replacement fields.
  - metrics `last_reload_duration_s`, `last_reload_plan_class`, and
    `last_reload_error` are updated only after a dry-run handler invocation.
  - dry-run does not publish a service graph, mutate tmux, write lifecycle,
    lease, namespace, start-policy, restore, or agent runtime authority, and
    does not install a config watcher.

Rollback:

- Disable CLI entrypoint; no daemon mutation exists yet.

## Phase 4: Bounded Draining And Retiring

Goal: make unload safe before exposing replacement.

Deliverables:

- Add runtime states or lifecycle markers for `draining`, `retiring`,
  `pending_unload`, and `retired`.
- Define the state/predicate boundary needed to stop accepting new jobs for
  draining agents once mutating unload is enabled.
- Keep running work visible until completion, cancellation, timeout, or force.
- Add queue length and age limits for pending unload/replace records.
- Add clear terminal errors when a reload is rejected because a previous drain
  is still active.

Exit criteria:

- Idle drain reaches `idle_ready` / `retiring` without mutating runtime or tmux.
- Busy drain waits, then either reaches `idle_ready` within the configured
  bound or returns a stable timeout/rejected state.
- Pending unload/replace queues cannot grow unbounded.
- Actual new-job rejection, runtime retirement writes, and managed-pane removal
  remain deferred until mutating unload phases wire this state to dispatcher and
  namespace operations.

Phase 4 implementation status:

- Added `ccbd.reload_drain` as pure state machinery with `DrainIntent`,
  `DrainRecord`, `DrainBounds`, `DrainQueue`, `DrainQueueStore`,
  `plan_drain_transition()`, and `retire_record()`.
- Bounds are explicit: `max_pending` caps non-terminal unload/replace records
  across the queue, `timeout_s` caps active draining time, and `max_age_s` caps
  stale intent age before or during drain.
- Busy/idle is an injected predicate over the current `DrainRecord`; the module
  does not import dispatcher, comms, provider execution, tmux, namespace, or
  service-graph publish code.
- `DrainQueueStore` persists only explicit state-machine calls to
  `.ccb/ccbd/reload-drain.json`; heartbeat and request steady state do not scan
  it.
- Phase 3 dry-run plans now include `drain_intents` suggestions for
  `remove_agent` and `replace_agent`, but `safe_to_apply=false` and
  `mutation_enabled=false` remain unchanged.
- Non-dry-run `project_reload_config` / `ccb reload` is still rejected. Phase 4
  performs no tmux delete/create, graph publish, namespace patch, runtime
  authority write, config watch, mount, unmount, provider start, or provider
  stop.

Rollback:

- Treat deletion as `unsafe_requires_restart` until drain machinery is enabled.

## Phase 5: Namespace Patch Operations

Goal: introduce namespace patch/additive mutation behind dry-run-proven plans,
without full namespace recreation or unrelated pane churn.

Deliverables:

- Add namespace patch operations for add window, add sidebar, add agent pane,
  remove retired agent pane, and refresh sidebar width/UI.
- Every operation must prove project id, socket, session, window, role,
  `slot_key`, and `managed_by=ccbd` before mutation.
- Do not use full namespace recreation for accepted additive/unload operations.
- Keep CCB-owned tmux settings project/session-scoped.

Exit criteria:

- Additive reload preserves old pane ids.
- Retired unload removes only the target agent pane.
- Failed patch does not publish the new graph.

Rollback:

- Reject mutating reload and keep dry-run available.

## Phase 6: Additive Mutating Reload

Goal: expose the first safe mutation.

Deliverables:

- Enable view-only, add-agent, and add-window reload.
- Publish new service graph only after namespace patch and new runtime mount
  succeed.
- Update lifecycle/lease/ping config signature so keeper does not restart the
  hot-loaded daemon.
- Invalidate project view and refresh sidebars.

Exit criteria:

- Busy unrelated agents continue through add-agent/add-window reload.
- Keeper sees the new config as current.
- Manual `test_ccb2` screenshots show unchanged old panes and new mounted
  agents.

Rollback:

- Disable mutating classes and keep dry-run.

## Phase 7: Dynamic Unload

Goal: expose safe unload after bounded drain is proven.

Deliverables:

- Enable deletion from `[windows]` to plan and execute unload.
- Retire runtime authority through explicit authority writes.
- Remove managed pane only after runtime is idle, completed, cancelled, timed
  out, or force-approved.
- Preserve `.ccb/agents/<agent>` history as residue/audit data, not configured
  authority.

Exit criteria:

- Removing an idle agent unloads it without affecting other panes.
- Removing a busy agent follows the configured draining behavior.
- Project view no longer treats retired agents as configured agents.

Rollback:

- Return deletion to `unsafe_requires_restart`.

## Phase 8: Dynamic Replace

Goal: replace an existing agent route without breaking unrelated panes.

Deliverables:

- Treat provider/workspace/model/key/url changes as replace plans.
- Idle replacement can retire the old runtime and mount the new runtime in the
  same logical slot.
- Busy replacement becomes bounded `pending_replace`.
- Replacement must never rewrite provider session authority as if it were the
  same conversation unless provider-specific resume authority proves it.

Exit criteria:

- Idle replace preserves slot identity but advances runtime authority epoch.
- Busy replace cannot grow unbounded and cannot block future reload forever.
- Codex/Claude session continuity is preserved or explicitly restarted.

Rollback:

- Return replace classes to `unsafe_requires_restart`.

## Phase 9: Optional Movement And Watchers

Goal: handle layout reshaping only after core dynamic lifecycle is stable.

Deliverables:

- Consider idle pane movement within the same project namespace.
- Consider file watching only after explicit reload is reliable.
- Keep busy pane cross-window movement deferred unless there is a proven
  session-preserving tmux operation and rollback path.

Exit criteria:

- Movement has separate tests and does not share first-release reload gates.
