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

## In Progress

- Phase 5 namespace patch/additive mutation design is the next implementation
  target. It must stay behind dry-run-proven plans and must preserve
  project/session-scoped CCB-owned tmux behavior.

## Next

1. Add namespace additive/remove patch operations behind dry-run-proven plans.
2. Expose additive mutating reload: view-only, add agent, and add window.
3. Expose dynamic unload for idle and bounded-draining agents.
4. Expose replacement only after unload semantics are safe; busy replacement
   remains pending with explicit bounds.
5. Run the automatic and manual matrix in
    [topics/test-matrix.md](topics/test-matrix.md).

## Deferred

- Pane-preserving arbitrary layout reshuffle.
- Background file watching of `.ccb/ccb.config`.
- General `ccbd` control-plane performance optimization.
- Automatic replace of indefinitely busy agents without user policy.
- Cross-window movement of busy panes.
