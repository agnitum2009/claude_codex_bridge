# Dynamic Window And Pane Agent Maintenance

Date: 2026-06-26

## Purpose

Define how CCB should maintain dynamic tmux windows and panes when the default
visible workspace starts with only one user-facing frontend, while dialog,
planning, orchestration, execution, monitoring, and recovery agents are loaded
and released on demand.

This document is a visual/runtime layout plan. It does not move authority from
scripts, task packets, runtime state, or loop runner into tmux panes. Windows
and panes are presentation and process containers, not workflow truth.

Agent lifecycle policy is specified separately in
[dynamic-agent-lifecycle-and-skills.md](dynamic-agent-lifecycle-and-skills.md).
This document describes where panes go; it does not decide whether an agent
should be hidden, parked, retained, or unloaded.

## Design Principle

CCB needs a runtime layout manager:

```text
semantic roles request capacity
runtime layout manager maps agents to windows and panes
ccbd/tmux owns process placement
workflow state remains in task/loop files
```

This follows the simple-kernel/flexible-agent principle:

- Agent roles decide semantic need: dialog, planning, orchestration, node work,
  review, recovery.
- Program code deterministically maintains windows, panes, ownership, limits,
  lifecycle, and cleanup.

## Window Classes

Prefer named windows over relying on tmux numeric indexes. Numeric ordering is
for usability only.

| Logical Order | Window Class | Default Name | Contents | Max Panes |
| :--- | :--- | :--- | :--- | :--- |
| 1 | user-facing dialog | `frontdesk-dialog` | `primary_frontend` plus user-visible dialog/expert agents | 6 |
| 2 | planning and orchestration | `plan-orchestrate` | planner group, broker, plan steward, orchestrator, round checker | 6 |
| 3+ | execution node | `node-<loop-id>-<node-id>` | one bounded execution node: worker/checker/status/artifacts | 4 |
| later | runtime diagnostics | `runtime` | loop runner, ccbd logs, capacity, ask/job queue, monitor, recovery | 6 |
| later | archived evidence | `archive-<loop-id>` | frozen panes or summaries retained for inspection | 6 |

When a class exceeds its pane limit:

- `frontdesk-dialog` creates `frontdesk-dialog-2`, then `-3`.
- `plan-orchestrate` creates `plan-orchestrate-2`, then `-3`.
- Execution nodes do not share overflow windows; each node receives its own
  `node-<loop-id>-<node-id>` window.

## Window 1: `frontdesk-dialog`

Purpose: visible user discussion space.

Default panes:

```text
primary_frontend
dialog:<expert-or-general>
dialog:<expert-or-general>
...
```

Rules:

- Exactly one `primary_frontend` is the default user entrypoint.
- Dialog agents may be user-visible and conversational.
- Dialog agents may be general assistants or domain experts.
- Dialog agents do not own task status, loop status, runtime lifecycle, or
  execution authority.
- Dialog agents should produce a summary artifact when they are released if
  their conversation affects the task.
- At most six panes per dialog window. More dialogs create a continuation
  dialog window.

Example:

```text
frontdesk-dialog
  primary_frontend
  dialog:architect
  dialog:docs
  dialog:debug
  dialog:general
```

## Window 2: `plan-orchestrate`

Purpose: planning, review, clarification, orchestration, and round-level
verification workspace.

Possible panes:

```text
planner_coordinator
plan_reviewer
clarification_broker
plan_steward
orchestrator
round_checker
```

Rules:

- Roles are loaded by workflow phase, not all at startup.
- Planner group can contain multiple agents, but `planner_coordinator` is the
  current owner for a unified task packet or clarification batch.
- Orchestrator lives here because it semantically decomposes work, but it does
  not directly create tmux windows or panes.
- Round checker lives here when it verifies the whole round result.
- Scripts and loop runner remain authority; these panes produce artifacts and
  recommendations.

Phase examples:

| Phase | Expected Panes |
| :--- | :--- |
| planning | `planner_coordinator`, `plan_reviewer` |
| clarification | `clarification_broker` |
| ready/execution start | `orchestrator` |
| round end | `round_checker`, optionally `plan_steward` |

## Window 3+: Execution Node Windows

Purpose: isolate bounded execution work so parallel nodes can be observed,
retried, blocked, or archived independently.

Default V1 node window:

```text
node-<loop-id>-<node-id>
  worker
  checker
```

Expanded node window:

```text
node-<loop-id>-<node-id>
  worker
  checker
  node-status
  artifacts-or-test-log
```

Rules:

- One execution node owns one window.
- Worker/checker pairs from different nodes should not share a window by
  default.
- Node windows are created by runtime layout manager after loop runner accepts
  a ready task and orchestrator requests node capacity.
- Node windows are released or archived when node and round evidence is
  imported.
- A blocked node can keep its window for inspection while unrelated sibling
  node windows continue or drain.

## Runtime Window

Purpose: diagnostics and operations, normally hidden or not focused.

Panes:

```text
loop_runner
ccbd logs
capacity status
ask/job queue
monitor
recovery
```

Open this window for:

- ask/callback stalls;
- provider auth or startup failures;
- stale leases;
- busy release;
- pane death;
- capacity mismatch;
- dispatcher or message-bureau diagnostics.

The runtime window can show program logs and state renderings, but it does not
replace structured runtime files.

## Agent Placement Rules

Placement should be deterministic:

```text
agent kind frontend/dialog
  -> first frontdesk-dialog window with fewer than 6 panes
  -> else create frontdesk-dialog-N

agent kind planner/broker/plan_steward/orchestrator/round_checker
  -> first plan-orchestrate window with fewer than 6 panes
  -> else create plan-orchestrate-N

agent kind worker/checker
  -> node-<loop-id>-<node-id>
  -> never share across nodes by default

agent kind monitor/recovery/system
  -> runtime
```

The pane limit is a readability constraint, not a workflow authority rule.

## Read-Only Placement Resolution

Workflow roles and skills should be able to ask CCB where a dynamic agent would
land before they request lifecycle changes. The command surface is read-only:

```bash
ccb layout resolve <agent> --window-class plan-orchestrate --json
ccb layout resolve <agent> --loop-id <loop-id> --node-id <node-id> --json
```

The resolver uses the same effective config and placement precedence as
dynamic agent overlays:

```text
--window
  -> exact window name

--loop-id/--node-id
  -> node-<loop-id>-<node-id>

--window-class
  -> first matching class window with fewer than six panes, else class-N

no explicit placement
  -> entry window for explicit [windows], else default layout surface
```

It must not write `.ccb/ccb.config`, create runtime lifecycle records, start a
provider, or mutate tmux. Its output is evidence for scripts and agents, not
workflow authority.

## Lifecycle Rules

These rules are layout effects of lifecycle decisions. The policy authority is
the lifecycle layer.

### Ensure

```text
request agent capacity
  -> runtime layout manager resolves window class or execution-node window
  -> ensure window
  -> ensure pane
  -> start provider session
  -> record placement
```

### Release

```text
release request
  -> check pending ask/job
  -> if busy: mark retained
  -> if idle: request summary artifact when needed
  -> record final placement state
  -> close pane
  -> compact window
  -> archive or remove empty node window
```

Release must never be a blind `tmux kill-pane`. It should go through CCB
runtime state so busy agents are retained and cleanup is auditable.

### Move

Moving panes is allowed for visual cleanup, but it must update placement state.
Moving a pane must not change role authority, task ownership, or loop state.

### Archive

Completed node windows can be removed after evidence import. For debugging,
they may be converted into an `archive-<loop-id>` window or summarized into
runtime artifacts.

## Runtime Layout State

CCB should maintain deterministic layout state. Candidate shape:

```json
{
  "windows": {
    "frontdesk-dialog": {
      "class": "dialog",
      "max_panes": 6,
      "agents": ["primary_frontend", "dialog_architect"]
    },
    "plan-orchestrate": {
      "class": "planning",
      "max_panes": 6,
      "agents": ["planner_coordinator", "orchestrator"]
    },
    "node:loop1:node1": {
      "class": "execution_node",
      "max_panes": 4,
      "loop_id": "loop1",
      "node_id": "node1",
      "agents": ["worker_1", "checker_1"]
    }
  }
}
```

The exact path can be decided during implementation. Likely options:

- project-level `.ccb/runtime/layout/windows.json`;
- loop-level `.ccb/runtime/loops/<loop-id>/layout.json`;
- both, with project layout indexing loop-local placements.

## True Hot-Load Design

True hot load means an operator, script, or orchestrator can add a dynamic
agent while CCB is already mounted, without restarting the project and without
interrupting preserved agents.

Acceptance criteria:

- `ccb agent add ...` writes a dynamic lifecycle record and immediately applies
  it when the project daemon is mounted;
- a new tmux pane or window is created by ccbd, not by the agent role;
- only the new agent runtime is started;
- preserved agents keep their pane ids, runtime authority, queues, and jobs;
- `ccb ps` shows the new agent after the transaction publishes;
- `ccb ask <new-agent> ...` is accepted after the command returns;
- failure rolls back or marks the dynamic record as failed without publishing a
  partial service graph.

The existing `ccb reload` path is the right transaction kernel. It already has:

- additive `add_agent` for appending a pane to an existing managed window;
- additive `add_window` for creating a new managed window and materializing its
  panes;
- runtime mount for only the newly materialized agent panes;
- graph/lease/lifecycle publish as a single transaction after namespace and
  runtime stages pass.

The missing layer is not another raw tmux command. The missing layer is a
dynamic placement overlay that can produce the same config/topology delta that
`ccb reload` already knows how to apply.

### Dynamic Add Transaction

```text
ccb agent add helper:codex --role agentroles.general --window-class plan-orchestrate
  -> validate role/provider/profile/lifecycle policy
  -> choose placement target
  -> write .ccb/runtime/agents/helper/lifecycle.json as pending/applied intent
  -> dynamic config overlay materializes target window/layout
  -> if unmounted: defer until startup
  -> if mounted: call reload transaction
       -> dry-run/plan class must be add_agent or add_window
       -> namespace patch creates pane/window and stamps @ccb identity
       -> runtime mount starts only helper
       -> publish graph/signatures
  -> update lifecycle record with pane/window evidence
  -> return apply details
```

The dynamic record should carry placement intent and evidence:

```json
{
  "agent": "helper",
  "provider": "codex",
  "role": "agentroles.general",
  "lifecycle_state": "hidden",
  "placement": {
    "mode": "auto",
    "window_class": "plan-orchestrate",
    "window_name": "plan-orchestrate",
    "layout_policy": "append-only",
    "loop_id": null,
    "node_id": null
  },
  "applied": {
    "status": "applied",
    "plan_class": "add_agent",
    "window_name": "plan-orchestrate",
    "pane_id": "%12",
    "published_graph_version": 4
  }
}
```

### Existing Window Pane Add

V1 should support append-only pane creation first.

Requirements:

- target window exists in current topology;
- target window has at least one preserved agent pane when appending;
- new agent is added at the end of that window's agent order;
- layout delta remains compatible with the current additive patch planner.

This maps cleanly to existing `add_agent`.

Startup compatibility requirement:

- compact legacy configs still normalize to the logical `main` window even
  when they are not written with explicit `[windows]`;
- startup panes must be stamped with `@ccb_window=main` so later dynamic
  overlays can use the same namespace patch proof as explicit-window configs;
- structured/fake providers that do not expose a provider session binding
  still need namespace pane evidence written into runtime authority, otherwise
  `ccb ps`, cleanup, and hot-load planning can disagree about the active pane.

### New Window Add

New-window hot load should be first-class, not a workaround.

When placement chooses a missing window, the dynamic overlay should add a
`WindowSpec` to the loaded config:

```text
plan-orchestrate
  helper

node-loop1-node1
  worker_1
  checker_1
```

This maps to existing `add_window`:

- namespace patch creates the tmux window;
- if sidebar policy applies, it creates a sidebar pane;
- it materializes all agent panes in the new window;
- runtime mount starts only those new agents;
- publish updates graph/signatures.

New-window add does not need a preserved pane anchor inside that new window,
but it still requires a live project tmux namespace and publishable reload
transaction.

### Placement Selection

V1 placement should be deterministic:

```text
explicit --window NAME
  -> use NAME; create it if allowed

explicit --window-class CLASS
  -> first existing CLASS window with room
  -> else create CLASS-N

worker/checker with --loop-id/--node-id
  -> node-<loop-id>-<node-id>
  -> create window if missing

no placement flags
  -> role-class default
  -> fallback to entry window append
```

Suggested command examples:

```bash
ccb agent add helper:codex --role agentroles.general --window main --hidden --json
ccb agent add planner2:codex --role agentroles.planner --window-class plan-orchestrate --hidden --json
ccb agent add docs:claude --role agentroles.docs --window-class frontdesk-dialog --visible --json
ccb agent add worker1:codex --profile worker --loop-id loop1 --node-id node1 --hidden --json
ccb agent add checker1:codex --profile code_reviewer --loop-id loop1 --node-id node1 --hidden --json
```

### Append-Only First, Reflow Later

The current safe reload planner supports appending and creating new windows. It
does not yet support arbitrary live reflow of existing panes.

Therefore:

- V1 true hot load should be append-only for existing windows and full
  materialization for new windows.
- V1 should not rearrange existing live panes into the 1->6 visual pattern.
- V2 can add a controlled reflow transaction after pane movement and placement
  evidence are modeled as first-class runtime state.

This keeps the first hot-load slice safe: adding an agent must not unexpectedly
move or resize active agents that are mid-conversation or mid-job.

### Current Landed Hot-Load Slice

Current worktree implementation now covers the first safe hot-load placement
slice:

- `ccb agent add ... --window NAME` appends to an existing managed window when
  `NAME` exists, or creates a new managed window when it does not.
- `ccb agent add ... --window-class CLASS` chooses the first class window with
  room, or creates a class window when none is available.
- `ccb agent add ... --loop-id LOOP --node-id NODE` maps to
  `node-<loop-id>-<node-id>` for execution-node placement.
- Dynamic overlays produce explicit `WindowSpec` data for placement and reuse
  the existing guarded reload transaction instead of issuing raw tmux commands.
- Lifecycle records are updated with placement intent and apply evidence:
  `window_name`, `pane_id`, `plan_class`, `runtime_mount_status`, and published
  graph version.
- Existing windows use append-only layout, preserving current panes. New
  windows use the deterministic pane-growth layout for their initial contents.
- `remove --policy unload --idle-only` applies the guarded `remove_agent`
  reload path after idle checks, closes only the released dynamic pane, unloads
  runtime authority, records `last_pane_id`, and removes empty dynamic windows.
- `agent release --policy unload --idle-only` exposes the same safe non-kill
  release path for workflow roles and scripts.
- Busy dynamic agents are retained instead of being killed or removed.
- `ccb layout status` and `ccb layout status --json` expose the effective
  runtime layout view for explicit `[windows]`: configured/static vs dynamic
  agents, lifecycle state, dispatch state, runtime state, pane ids, namespace
  state, and best-effort tmux pane observations. Unmounted projects with stale
  namespace state skip tmux observation instead of reporting a false failure.
- Dynamic lifecycle records now store `created_sequence` and
  `resolved_window_name`. The config overlay uses creation order for active
  dynamic agents, so a second agent in the same execution node appends after
  the existing worker instead of being alphabetically reordered into a
  non-additive `layout_change`.
- Loop capacity records now use the same placement model. Generated capacity
  agents carry `loop_id`, `node_id`, `created_sequence`, and
  `placement.window_name`, and explicit `[windows]` overlays place worker /
  checker capacity in `node-<loop-id>-<node-id>` windows. `layout status`
  reports these records as `source=loop`, separate from configured and generic
  dynamic agents.

Evidence:

- Parser and dry-run plan tests cover explicit window, window class, and
  loop/node placement in `test/test_agent_lifecycle_cli.py`.
- Reload apply tests cover both `add_agent` and `add_window` dynamic overlays:
  `test_additive_reload_apply_dynamic_agent_overlay_materializes_tmux_pane_before_mount`
  and
  `test_additive_reload_apply_dynamic_agent_overlay_materializes_new_window_before_mount`.
- Controlled mounted tmux smoke passed for existing-window append in
  `/home/bfly/yunwei/test_ccb2/agent-hot-pane-ident.otr4SM`; the new `helper`
  pane was mounted and reachable by `ask`.
- Controlled mounted tmux smoke passed for new-window creation in
  `/home/bfly/yunwei/test_ccb2/agent-hot-window-ident.Xj9dR6`; the `review`
  window was created, `helper` was mounted, and `ask helper` completed.
- Controlled mounted tmux smoke passed for existing-window add plus release in
  `/home/bfly/yunwei/test_ccb2/agent-hot-remove-pty.2FIiGo`; an unload request
  while `helper` was busy returned `retained_busy`, and the retry after `ask`
  completion closed only the `helper` pane and removed it from `ps`.
- Controlled mounted tmux smoke passed for new-window add plus release in
  `/home/bfly/yunwei/test_ccb2/agent-hot-window-remove-pty.RqWVcE`; the
  `review` window was created for `helper`, then removed after idle unload.
- Controlled mounted tmux cycle smoke passed in
  `/home/bfly/yunwei/test_ccb2/agent-hot-cycle-pty.Tu9DCH`; panes grew from
  `%1:main` to `%1:main,%2:dyn1,%3:dyn2,%4:dyn3,%5:dyn4,%6:dyn5`, then
  released back to `%1:main` with `known_agents: ['main']`.
- Source-wrapper smoke in
  `/home/bfly/yunwei/test_ccb2/hotload-real-1782476922` proved compact startup
  now stamps `@ccb_window=main`, existing-window `add_agent` creates `%2`,
  new-window `add_window` creates `review/%4`, and `ask` submission is accepted
  for both dynamic agents without manual tmux option seeding.
- Source-wrapper smoke in
  `/home/bfly/yunwei/test_ccb2/hotload-unload-1782477435` proved explicit
  `remove --policy unload --force` removes the dynamic reviewer pane `%4`,
  removes the empty `review` window, removes the helper pane `%2`, stops
  dynamic runtime authority, and leaves only `main/%1`.
- Source-wrapper cycle smoke in
  `/home/bfly/yunwei/test_ccb2/hotload-cycle-auto-1782482877` proved single
  window continuous growth and shrink without manual pane seeding:
  `main/%1 -> dyn1/%2 -> dyn2/%3 -> dyn3/%4 -> dyn4/%5 -> dyn5/%6`, followed
  by forced unload in reverse order back to only `main/%1`.
- Source-wrapper status smoke in
  `/home/bfly/yunwei/test_ccb2/layout-status-real-1782553123` proved
  `layout status --json` on an explicit-window project before mount, after
  mount, after same-window hot add/release, after new-window add/release with
  empty-window removal, and after forced kill with stale namespace state.
- Source-wrapper placement smoke in
  `/home/bfly/yunwei/test_ccb2/layout-placement-real-1782555` proved
  `--window-class plan-orchestrate` overflows from a full 6-pane
  `plan-orchestrate` window into `plan-orchestrate-2`, the loop/node placement
  flags create `node-round1-node1`, a second same-node agent appends as
  `worker1; checker1` with reload `plan_class=add_agent`, `ask checker1` is
  accepted, and reverse unload removes the checker pane, removes the empty node
  window after worker unload, removes the empty overflow window, and returns
  layout status to the two configured windows with `dynamic_agent_count=0`.
- Focused regression after the placement-order fix passed with `185 passed`
  across agent lifecycle, layout status, pane growth, layout runtime, reload
  patch/runtime mount, config loader, and loop capacity tests.
- Source-wrapper loop-capacity layout smoke in
  `/home/bfly/yunwei/test_ccb2/loop-capacity-layout-real-1782557` proved
  mounted loop capacity ensure for `worker=1` and `code_reviewer=1` creates
  `node-round1-node1`, status reports `loop_agent_count=2` with both agents as
  `source=loop`, the node panes are alive, and idle loop-capacity release
  removes the node window and returns to `loop_agent_count=0`.
- Repeatable dynamic layout smoke script
  `scripts/dynamic_layout_smoke.py` now covers the two high-risk mounted
  source-wrapper flows. In
  `/home/bfly/yunwei/test_ccb2/dynamic-layout-smoke-1782565-multi-node`,
  `loop capacity ensure --profile worker=2 --profile code_reviewer=2`
  created `node-round2-node1` and `node-round2-node2`, accepted asks to worker
  and reviewer targets, waited for terminal fake jobs, released four loop
  agents, and returned to only the `main` window with `orchestrator`. In
  `/home/bfly/yunwei/test_ccb2/dynamic-layout-smoke-1782565-same-window`,
  `agent add` grew `main` to `main, helper1, helper2, helper3`, removing the
  middle `helper2` used `plan_class=remove_agent`, preserved `helper1` and
  `helper3` pane ids, accepted asks to both survivors, and cleaned up with
  `kill_status: ok`.
- Real `remove_agent` namespace patch apply now performs best-effort visual
  reflow after same-window pane removal and then reapplies configured sidebar
  widths. `NamespacePatchApplyResult` records `reflowed_windows` and
  `reflow_errors`, and `agent remove --json` exposes them as
  `namespace_reflowed_windows` / `namespace_reflow_errors`. Focused tests cover
  reflow after pane-only removal and sidebar width restoration. The
  source-wrapper smoke in
  `/home/bfly/yunwei/test_ccb2/dynamic-layout-reflow-1782570-same-window`
  proved `main, helper1, helper2, helper3 -> main, helper1, helper3` reports
  `namespace_reflowed_windows=["main"]`, preserves survivor panes, accepts
  asks to both survivors, and cleans up with `kill_status: ok`.
- The orchestrator autonomous smoke harness now treats layout residue as a
  failure even when capacity release succeeds. After each autonomous parent
  callback chain it runs `layout status --json` and requires
  `loop_agent_count=0`; script tests cover both clean release and residual
  loop-agent failure. The source-wrapper fake workflow closure smoke in
  `/home/bfly/yunwei/test_ccb2/workflow-closure-layout-1782571` also proved
  generated loop agents release from layout and `ps` state with
  `dynamic_agents_absent_from_ps=true`.
- `scripts/dynamic_layout_smoke.py` now includes an explicit workflow-window
  flow for `--window-class plan-orchestrate`. The source-wrapper smoke in
  `/home/bfly/yunwei/test_ccb2/dynamic-layout-window-class-1782560319-window-class`
  proved `main=[frontdesk]` and
  `plan-orchestrate=[planner, planner_helper1, planner_helper2,
  planner_helper3]`, removed middle `planner_helper2` with
  `plan_class=remove_agent`, reported
  `namespace_reflowed_windows=["plan-orchestrate"]`, preserved
  `planner_helper1` and `planner_helper3` pane ids, kept `main` unchanged, and
  accepted asks to both surviving helpers.
- The same smoke harness is now ready for guarded real-provider probes:
  `--provider` rewrites the generated config and dynamic `agent add` provider,
  `--flow` can isolate one scenario such as `window-class`,
  `--provider-home-mode` separates isolated source-home from real user auth,
  and non-fake runs require `CCB_DYNAMIC_LAYOUT_SMOKE_RUN_REAL=1`.
  Verification covered the unchanged default fake run, a selected
  `--flow window-class` fake run, and Codex `--prepare-only` preflight with
  real-home auth discovery under `/home/bfly`.
- After merging remote `v7.7.0` runtime-accelerator/theme work, the dynamic
  layout smoke still passed all fake-provider flows in
  `/home/bfly/yunwei/test_ccb2/dynamic-layout-merged-1782561461-*`. A guarded
  Codex real-provider `window-class` run then passed in
  `/home/bfly/yunwei/test_ccb2/dynamic-layout-codex-window-1782561840-window-class`:
  three Codex helpers hot-loaded into `plan-orchestrate`, middle
  `planner_helper2` unloaded with `plan_class=remove_agent`, reflow reported
  `namespace_reflowed_windows=["plan-orchestrate"]`, surviving panes stayed in
  place, and asks to `planner_helper1` and `planner_helper3` were accepted.
- The matching guarded Claude real-provider `window-class` run passed in
  `/home/bfly/yunwei/test_ccb2/dynamic-layout-claude-window-1782563057-window-class`:
  `frontdesk` and `planner` started as explicit Claude panes, three Claude
  helpers hot-loaded into `plan-orchestrate`, middle `planner_helper2` removed
  with `plan_class=remove_agent`, reflow reported
  `namespace_reflowed_windows=["plan-orchestrate"]`, surviving helper pane ids
  were preserved, asks to `planner_helper1` and `planner_helper3` were
  accepted, and cleanup returned `state: unmounted`.
- `layout status --json` now includes script-facing ownership and apply
  diagnostics on each agent record: `agent_kind`, `ownership_class`,
  `dispatch_state`, `pane_identity_source`, `apply_status`,
  `apply_plan_class`, `apply_stage`, `failed_apply`, and `retained_busy`.
  Focused tests cover static configured agents, dynamic session helpers, loop
  capacity agents, parked dispatch-disabled helpers, and failed apply records;
  the fake explicit-window smoke remained green after adding the fields.
- `agent status --json` and `agent show --json` now mirror the same
  ownership/apply vocabulary for configured and dynamic lifecycle records, so
  orchestrator scripts can query either the layout view or the lifecycle view
  without switching field names. Focused tests cover static configured agents,
  active dynamic agents, parked dispatch-disabled agents, deferred apply
  records, and failed-apply detection.
- Non-interactive `ccb` start output now carries a compact layout identity
  summary generated from the same `layout status` source. The startup view
  reports explicit-window state, window/pane counts, observed pane count, and
  per-agent `ownership_class`, `dispatch_state`, `pane_id`,
  `pane_identity_source`, runtime state, and apply status. If that diagnostic
  probe fails, start still reports success but surfaces
  `layout_summary_status: unavailable` with the error type and message.
- The orchestrator draft RolePack now includes `dynamic-agent-lifecycle` for
  non-loop dynamic agents while `orchestrator-capacity` remains loop-only. The
  skill documents allowed `ccb agent ... --json` and read-only
  `ccb layout status --json` commands, forbidden raw state/tmux/reload/kill
  actions, ownership/apply fields, safe park/resume/release behavior, and
  failure reporting.
- `scripts/dynamic_layout_smoke.py` now supports repeated `--provider` values
  for a guarded provider matrix. The real Codex+Claude matrix passed in
  `/home/bfly/yunwei/test_ccb2/dynamic-layout-matrix-real-1782567263-*` for
  `--flow window-class`, with both providers proving hot add, middle unload,
  explicit-window reflow, survivor pane preservation, ask reachability, and
  cleanup.
- `scripts/guarded_dynamic_layout_provider_smoke.py` now provides a fixed
  guarded entrypoint for future release/CI wiring. It defaults to prepare-only
  Codex+Claude `window-class`, requires `--run` plus
  `CCB_DYNAMIC_LAYOUT_SMOKE_RUN_REAL=1` for live provider execution, and passed
  both prepare-only and real guarded source-wrapper runs in
  `/home/bfly/yunwei/test_ccb2/guarded-dynamic-layout-prepare-1782568181-*`
  and `/home/bfly/yunwei/test_ccb2/guarded-dynamic-layout-real-1782568215-*`.
- The default `Tests` workflow now runs that wrapper as a prepare-only Ubuntu
  py3.11 gate, without `--run`, and asserts that the Codex+Claude
  `window-class` provider matrix reaches `prepared`. This keeps real provider
  execution behind explicit local/release opt-in while making wrapper drift a
  normal CI failure.
- Dynamic reload apply reports now carry pane identity diagnostics. The shared
  `pane_identity_report` appears under mounted `ccb agent add/remove --json`
  and `ccb loop capacity ensure/release --json` apply payloads, summarizing
  added and removed agent panes, preserved before/after panes, created/removed
  panes, removed windows, reflowed windows, reflow errors, mounted agents, and
  unloaded agents from the same namespace patch/runtime mount transaction.
- Focused regression after connecting loop capacity to layout placement passed
  with `187 passed` across loop capacity, agent lifecycle, layout status, pane
  growth, layout runtime, reload patch/runtime mount, and config loader tests.
- Focused regression passed with `222 passed` across dynamic lifecycle,
  config-loader, dispatcher, start-runtime, start-flow, reload-apply,
  reload-runtime-mount, and tmux-start-layout tests.

## Command Surface Direction

User-facing commands should stay small:

```bash
ccb view
ccb view frontdesk
ccb view dialogs
ccb view plan
ccb view loop <loop-id>
ccb view node <node-id>
ccb view runtime
```

Internal or advanced commands can be added later:

```bash
ccb layout status --json
ccb layout ensure-window --class <class> --name <name>
ccb layout assign-agent --agent <agent> --window <window>
ccb layout release-agent --agent <agent> --idle-only
ccb layout compact --window <window>
ccb layout archive --window <window>
```

Avoid making users manually manage tmux panes for normal workflow operations.

## Relationship To Orchestrator

Orchestrator does semantic execution planning. It may request:

```text
need 3 execution nodes:
  node1: worker + checker
  node2: worker + checker
  node3: worker + checker
```

Runtime layout manager decides:

```text
create node-<loop-id>-node1 window
create node-<loop-id>-node2 window
create node-<loop-id>-node3 window
place worker/checker panes
record placement state
```

Therefore:

- orchestrator does not call raw tmux commands;
- orchestrator does not decide visual layout details;
- runtime layout manager does not decide semantic task decomposition;
- loop runner and scripts remain state authority.

## Configuration Direction

Candidate config:

```toml
[ui.windows.frontdesk_dialog]
class = "dialog"
max_panes = 6
agents = ["frontend", "dialog"]

[ui.windows.plan_orchestrate]
class = "planning"
max_panes = 6
agents = ["planner", "plan_reviewer", "broker", "orchestrator", "round_checker", "plan_steward"]

[ui.windows.execution_node]
class = "execution_node"
mode = "one_window_per_node"
max_panes = 4

[ui.windows.runtime]
class = "runtime"
hidden_by_default = true
max_panes = 6
```

The initial implementation can hard-code these classes before exposing config.

## V1 Slice

V1 should implement enough to support the agentic loop without making tmux
layout a second workflow system:

1. Track logical window class and pane placement for dynamic agents.
2. Keep `primary_frontend` in `frontdesk-dialog`.
3. Place user-visible dialog agents in `frontdesk-dialog`, with six-pane
   overflow.
4. Place planner/orchestrator/round_checker in `plan-orchestrate`.
5. Create one `node-<loop-id>-<node-id>` window for each worker/checker pair.
6. Retain busy agents and release idle agents through runtime state, not raw
   tmux kills.
7. Provide a read-only `ccb layout status --json` or equivalent diagnostic.

## Fixed Pane Growth Order

The first implementation slice should not attempt arbitrary placement. Within
one logical page, panes grow in a deterministic 1->6 pattern:

| Count | Intent | Layout spec |
| --- | --- | --- |
| 1 | full pane | `p1` |
| 2 | left/right | `p1; p2` |
| 3 | left stacked, right full | `(p1, p3); p2` |
| 4 | two columns, two rows | `(p1, p3); (p2, p4)` |
| 5 | left three rows, right two rows | `(p1, p3, p5); (p2, p4)` |
| 6 | two columns, three rows | `(p1, p3, p5); (p2, p4, p6)` |

This keeps early panes visually stable as new panes are appended:

- pane 1 remains the top-left anchor;
- pane 2 remains the top-right anchor after the second pane appears;
- odd-numbered additions extend the left column;
- even-numbered additions extend the right column.

Overflow creates another tmux window with the same local 1->6 rule. The layout
manager should treat the window name as a page, not as semantic workflow
authority.

Initial landing target:

- add a scriptable planning surface for 1->6 plus overflow;
- add an isolated tmux smoke surface for placeholder panes;
- add a dynamic smoke surface that continuously grows and shrinks fake-agent
  panes in one isolated tmux session;
- defer live agent movement and drag/drop editing until the deterministic
  growth model is verified.

## Fixed Pane Shrink Order

Dynamic release is the inverse operation of growth, but it is more sensitive
because some panes contain still-running providers. CCB must not rebuild the
whole window to compact after deletion.

Release flow:

```text
release dynamic agent
  -> resolve target pane by @ccb_project_id + @ccb_slot
  -> check ask/job/queue state
  -> if busy: retain and report
  -> if idle: unload target provider and close only that pane
  -> recompute growth-1-6 layout for remaining ordered agents
  -> compact remaining panes without respawning them
  -> remove empty overflow window if needed
  -> update layout state
```

The target layout is computed from the remaining logical order:

| Shrink | Remaining order | Target layout |
| --- | --- | --- |
| 6->5 | `p1 p2 p3 p4 p5` | `p1, p3, p5; p2, p4` |
| 5->4 | `p1 p2 p3 p4` | `p1, p3; p2, p4` |
| 4->3 | `p1 p2 p3` | `p1, p3; p2` |
| 3->2 | `p1 p2` | `p1; p2` |
| 2->1 | `p1` | `p1` |

For middle deletion, the same rule applies after removing the target from the
ordered list. Example:

```text
[p1, p2, p3, p4, p5, p6] - p3
=> [p1, p2, p4, p5, p6]
=> p1, p4, p6; p2, p5
```

Multi-window shrink:

- 8->7 keeps `frontdesk-dialog-2` with one remaining pane.
- 7->6 removes `frontdesk-dialog-2` after its last pane is released.
- Empty execution-node windows are removed or archived after node evidence is
  imported.

Compaction can use tmux resize/swap/move operations on surviving panes, but it
must never kill or respawn surviving agent panes to make the visual layout
prettier.

Current evidence:

- isolated fake-agent dynamic smoke passed for `1->6->1`;
- isolated fake-agent dynamic smoke passed for `1->8->1`, including page add
  at 7 and page removal at 6;
- `ccb layout status --json` now provides a read-only effective topology and
  runtime pane diagnostic for explicit `[windows]`, including dynamic overlays
  and best-effort tmux observations;
- dynamic same-node placement now preserves creation order, so worker/checker
  execution-node windows remain append-only and eligible for live guarded
  reload;
- loop-capacity worker/checker allocation now uses execution-node windows and
  is visible in `layout status` as `source=loop`;
- multi-node loop-capacity allocation is proven for explicit `[windows]`:
  `worker=2` plus `code_reviewer=2` creates separate
  `node-round2-node1` and `node-round2-node2` windows, each with ordered
  worker/checker panes, and release removes both node windows;
- existing-window and new-window dynamic hot add are proven through guarded
  reload tests and controlled mounted tmux smoke;
- existing-window and new-window dynamic hot unload are proven through
  controlled mounted tmux smoke, including busy retain and empty-window removal;
- same-window middle dynamic release is proven: removing the middle helper pane
  deletes only the target pane, preserves the remaining dynamic pane ids, keeps
  their ask targets reachable, and avoids `layout_change`;
- same-window dynamic agent cycle smoke passed for `1->6->1` without changing
  the preserved `main` pane id;
- mounted source-wrapper smoke in
  `/home/bfly/yunwei/test_ccb2/hotload-smoke-1782474327` proved a full
  runtime sequence across existing-window add, `park` config-only dispatch
  disable, `resume`, new-window `add_window`, ask reachability, idle release,
  empty-window removal, and return to one `main` pane;
- mounted source-wrapper smoke in
  `/home/bfly/yunwei/test_ccb2/resolve-preflight-smoke-1782573894-resolve-preflight`
  proved the role-facing preflight chain on explicit `[windows]`: `layout
  resolve` predicted `plan-orchestrate-2`, `agent add` materialized it as
  `add_window`, `agent show` and `layout status` confirmed placement,
  `agent release --idle-only` unloaded the short-lived reviewer and removed the
  empty overflow window, then `layout resolve --loop-id/--node-id` predicted
  `node-round3-node1` before `ccb loop capacity` created and released the
  worker/checker execution-node window;
- guarded provider prepare-only now covers both `window-class` and
  `resolve-preflight` for Codex+Claude, so CI validates the new project/config
  surface without requiring real provider auth;
- guarded `resolve-preflight` provider preparation can now keep static
  overflow filler panes on `fake` while reserving Codex/Claude for the dynamic
  reviewer and loop worker/checker profiles, reducing the future real-provider
  run from a large static pane startup to the actual dynamic add/release and
  loop-capacity surfaces that need real-provider proof;
- the first opt-in Codex real-provider run of this lighter
  `resolve-preflight` variant passed in `/home/bfly/yunwei/test_ccb2`, proving
  real dynamic reviewer add/release and real loop worker/checker
  create/release while static overflow panes remained `fake`;
- the matching opt-in Claude real-provider run of the lighter
  `resolve-preflight` variant also passed in `/home/bfly/yunwei/test_ccb2`,
  proving the same real dynamic reviewer and loop worker/checker lifecycle
  path for Claude;
- compact workspace release reflow now resolves entry-window reflow through
  namespace workspace id/name when logical `main` is not an actual tmux window
  name; the workflow closure source-wrapper smoke proved loop worker/checker
  release with `namespace_reflowed_windows=["main"]` and empty reflow errors;
- the fake-provider workflow closure layout-cleanup smoke is now part of the
  Ubuntu py3.11 CI gate, asserting workflow closure, auto release, zero
  retained loop agents, and empty namespace/pane reflow errors;
- live provider release remains gated on busy/idle checks.

Deferred:

- interactive drag/drop layout management;
- visual rich panel for window topology;
- automatic screenshot/archive of completed node windows;
- cross-session restoration of exact pane geometry;
- user-defined arbitrary window classes.
