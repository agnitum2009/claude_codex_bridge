# CCBD Agent Hot Reload Roadmap

Date: 2026-05-29

## Done

- Confirmed current daemon initialization loads `.ccb/ccb.config` once and
  injects the resulting object into registry, supervisor, supervision,
  completion tracking, dispatcher, project view, and project focus services.
- Confirmed current keeper behavior treats config signature drift as a daemon
  restart trigger.
- Confirmed current namespace topology check escalates missing windows,
  changed agent pane membership, and missing sidebar panes into namespace
  recreation.
- Confirmed `[ui.sidebar.view]` is already a view-only hot-load precedent
  through `project_view`, but it does not cover agent/runtime topology.
- Recorded additive-first hot reload as the first supported target.
- Discussed the full dynamic load/unload/replace direction and recorded the
  main safety risks: handler lock contention, stale handler service captures,
  unbounded draining, unbounded pending replacement, and namespace patch drift.
- Established Phase 0 baseline diagnostics for control-plane handler latency,
  heartbeat steps, project-view work, process metrics, and reload placeholders.
- Introduced the Phase 1 config-bound service graph boundary used by startup,
  with graph version and created-at diagnostics.
- Added Phase 2 stable handler routing wrappers so request handlers resolve the
  current service graph at request time without a steady-state publish/read
  mutex.
- Added Phase 3 dry-run reload planning: `project_reload_config` accepts only
  `dry_run=true`, `ccb reload --dry-run` renders the no-mutation plan, and the
  classifier reports no-op, view-only, add, remove, replace, move/layout, and
  invalid-config cases without publishing a graph or touching tmux/runtime
  authority.
- Added Phase 4 bounded drain/retire state machinery: a pure drain queue model
  with timeout, pending-count, and age bounds, an explicit `reload-drain.json`
  store, injectable busy predicate transitions, retired terminal state, and
  dry-run drain intent suggestions for unload/replace plans. Phase 4 still does
  not publish a graph, patch namespace, mutate runtime authority, or execute
  tmux operations.
- Added Phase 5 namespace patch planning foundation: dry-run payloads now
  include a deferred namespace patch plan for view-only and additive
  add-agent/add-window classes, with required project/session/slot proofs,
  preserved-agent reporting, and explicit blocks for remove/replace/move/layout.
  Mutating apply, tmux writes, runtime authority writes, agent mounting, and
  service-graph publish remain deferred.
- Added Phase 6a additive apply design: documented the transaction order,
  rollback/diagnostic behavior, pane preservation proof, reusable existing APIs,
  and required narrow APIs before non-dry-run reload can be enabled.
- Added the Phase 6b first implementation step: a fake-backend-tested
  `add_window` namespace additive patch API that creates only new
  window/sidebar/agent pane evidence and remains disconnected from
  non-dry-run `ccb reload`.

## In Progress

- Phase 6b additive mutating reload remains in progress. Next work is
  append-only `add_agent` patching, then new-agent runtime mounts,
  lease/lifecycle signature updates, and final graph publish.

## Next

1. Implement append-only `add_agent` namespace patch apply without opening
   `ccb reload`.
2. Wire new-agent runtime mounts behind transaction tests.
3. Add lease/lifecycle signature update and graph publish handoff tests.
4. Expose additive mutating reload: view-only, add agent, and add window.
5. Expose dynamic unload for idle and bounded-draining agents.
6. Expose replacement only after unload semantics are safe; busy replacement
   remains pending with explicit bounds.
7. Run the automatic and manual matrix in
    [topics/test-matrix.md](topics/test-matrix.md).

## Deferred

- Pane-preserving arbitrary layout reshuffle.
- Background file watching of `.ccb/ccb.config`.
- General `ccbd` control-plane performance optimization.
- Automatic replace of indefinitely busy agents without user policy.
- Cross-window movement of busy panes.
