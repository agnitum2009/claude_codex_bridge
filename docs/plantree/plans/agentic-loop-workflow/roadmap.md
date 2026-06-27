# Agentic Loop Workflow Roadmap

Date: 2026-06-24

## Done

- Accepted the product direction that `frontdesk` should be reduced to user
  interaction, macro-task intake, confirmations, final reporting, and
  unrecoverable escalation.
- Accepted the Trellis-inspired principle that workflow state should live in
  external files and be advanced through scripts, not through one agent's
  conversation memory.
- Accepted the Team Builder-inspired principle that teams, roles, handoffs,
  termination conditions, and escalation rules should be declarative workflow
  objects.
- Accepted the simple-kernel/flexible-agent principle: workflow programs
  should stay small, stable, deterministic, and recoverable, while agents
  handle semantic planning, review, diagnosis, and complex documents. Scripts
  commit or reject agent artifacts through hard constraints rather than trying
  to encode all intelligence.
- Recorded the initial role split: `frontdesk`, planner group, plan steward, loop
  runner, orchestrator, execution nodes, inner monitor, recovery, and
  plan-tree synchronization.
- Accepted the non-goal that CCB should not copy Trellis' implicit subagent
  flow. CCB should use explicit, visible, inspectable agents and CCB-owned
  communication state.
- Accepted the context-purity principle: multi-agent workflow value comes from
  high-quality responsibility and granularity boundaries, not from agent count.
  Short-term, fast-changing execution detail should be assigned to short-lived
  workers or runtime artifacts and cleared after use; `frontdesk` and durable
  plan-tree documents should carry only macro intent, decisions, blockers, and
  evidence.
- Accepted the naming correction from `main` to `frontdesk`: the user-facing
  group is an intake/reporting boundary, not a primary authority or strongest
  agent. The name must discourage implementation, state mutation, and hidden
  orchestration behavior.
- Accepted the stage-batched clarification model: planner produces candidate
  questions for the current phase, a broker filters, merges, defaults, defers,
  or marks them obsolete, and `frontdesk` only presents curated user-facing
  question artifacts. The broker should not be a long-lived heavy-context role;
  persistent state is the question queue and runtime artifacts, while semantic
  broker work can be launched with fresh context per phase batch.
- Accepted the v1 execution-node model: default nodes are flat
  `worker + checker` units. Checker is an independent quality gate that designs
  node-level verification and rejects hidden fallback, degradation, scope
  shrinkage, or false success. Complex node-internal teams are deferred.
- Accepted partial branch semantics: non-converged nodes freeze only their
  dependent branch when safe, unrelated sibling work drains, and planner
  receives a partial package instead of allowing loop-local degradation.
- Accepted round-level verification: planner defines the verification contract,
  orchestrator summarizes actual node/dependency state, and round checker
  designs and executes the concrete whole-round verification plan.
- Accepted the plan/runtime state split: durable task packets live under
  `docs/plantree/plans/<plan-slug>/tasks/<task-id>/`, runtime loop lists live
  under `.ccb/runtime/loops/`, and scripts own all authoritative status,
  index, phase, owner, node, branch, ask, and round writes.
- Accepted the orchestrator boundary: it is an ask-activated semantic
  dispatcher that analyzes task complexity, chooses 1-4 nodes, slices work,
  constrains `ask` dispatch, requests runtime capacity, and aggregates results.
  It must not directly reload, unload, kill, or write runtime authority.
- Reviewed the `mother` role's orchestrator RolePack blueprint and accepted it
  as the V1 content plan for `agentroles.ccb_orchestrator`: single role,
  default local name `orchestrator`, six generic skills, seven templates,
  fixed-agent V1 operation, and explicit non-authority over reload, kill,
  provider sessions, runtime files, checker override, and partial-to-done
  conversion.
- Accepted the dynamic capacity direction: users declare allowed
  `loop.role_profiles` in config, including role, provider, model, thinking,
  workspace, max instances, and reuse policy; `orchestrator` uses a fixed
  `orchestrator-capacity` skill to call `ccb loop capacity
  ensure/status/release` by profile and count.
- Accepted the dynamic runtime layout direction: CCB should maintain logical
  tmux windows and panes for dynamic agents through a runtime layout manager.
  User-facing `frontend` and dialog experts live in `frontdesk-dialog`;
  planner/broker/orchestrator/round checker live in `plan-orchestrate`;
  each execution node receives its own `node-<loop-id>-<node-id>` window; and
  diagnostics live in `runtime`.
- Landed the first deterministic pane-growth slice in the current worktree:
  `ccb layout plan` reports 1->6 pane layouts and overflow windows, while
  `ccb layout smoke` creates placeholder panes in an isolated tmux session.
  Verified from `/home/bfly/yunwei/test_ccb2` with
  `/home/bfly/yunwei/ccb_source/ccb_test` for pane counts 1, 2, 3, 4, 5, 6,
  7, and 8; 7 panes produced `frontdesk-dialog` with six panes plus
  `frontdesk-dialog-2` with one pane, 8 panes produced a second window with two
  panes, and smoke cleanup succeeded each run.
- Accepted the dynamic release/shrink direction: dynamic agent exit should close
  only the released idle target pane, compact remaining panes through tmux
  move/resize operations, remove empty overflow windows, and retain busy agents
  without layout mutation. See
  [goals/dynamic-pane-shrink-release-goal.md](goals/dynamic-pane-shrink-release-goal.md).
- Accepted the dynamic lifecycle direction: long-lived interactive roles such
  as frontend, planner, and orchestrator default to `hide` or `park`, while
  short-lived worker/checker roles can unload only after evidence import and
  idle checks. See
  [topics/dynamic-agent-lifecycle-and-skills.md](topics/dynamic-agent-lifecycle-and-skills.md)
  and
  [decisions/012-long-lived-roles-park-before-unload.md](decisions/012-long-lived-roles-park-before-unload.md).
- Landed the first continuous dynamic layout smoke in the current worktree:
  `ccb layout dynamic-smoke` grows fake-agent panes in one isolated tmux session
  and then shrinks them. Verified from `/home/bfly/yunwei/test_ccb2` with
  source `ccb_test` for `1->6->1` and `1->8->1`; all retained panes stayed
  alive, `frontdesk-dialog-2` was added at overflow and removed when shrinking
  back to six, and cleanup succeeded.
- Landed a repeatable source-wrapper dynamic layout smoke script in the current
  worktree: `scripts/dynamic_layout_smoke.py` prepares isolated fake-provider
  projects, proves multi-node `worker + code_reviewer` windows can be loaded,
  reached by `ask`, drained, and released, and proves same-window middle-pane
  removal preserves surviving agent panes. Verified in
  `/home/bfly/yunwei/test_ccb2/dynamic-layout-smoke-1782565-*` with source
  `ccb_test`; both flows returned `dynamic_layout_smoke_status=ok` and cleanup
  reached `kill_status: ok`.
- Accepted the planner authority boundary: planner group owns semantic
  requirements, acceptance criteria, verification contract, risk notes, and
  readiness recommendations; `ccb plan` scripts own authoritative task status,
  indexes, imported artifact records, and current-loop bindings.
- Accepted the first plan-update landing direction: implement a narrow
  `ccb plan task-create/task-artifact/task-status/task-show/task-list/breadcrumb`
  slice before allowing autonomous planner-to-loop handoff.
- Landed the first `ccb plan` task-packet command surface in the current
  worktree. It creates durable task packets, imports planner artifacts with
  digest metadata, enforces review before `ready`, renders breadcrumb handoff
  text, and was externally smoke-tested through
  `/home/bfly/yunwei/ccb_source/ccb_test` in
  `/home/bfly/yunwei/test_ccb2/plan-task-smoke-v1`.
- Accepted the round-checker separation model: `round_checker` remains an
  independent post-round verifier, while planner rehydrates next-loop planning
  from task packet and round evidence instead of retained conversation memory.
- Extended the current `ccb loop run-once` slice to include a fixed
  `round_checker` ask after orchestrator aggregation.
- Ran an external fake-provider end-to-end smoke in
  `/home/bfly/yunwei/test_ccb2/agentic-loop-full-smoke-v1`: planner task packet
  reached `ready`, loop `loopfull2` completed worker/reviewer/orchestrator/
  round_checker asks, dynamic worker/reviewer nodes were released, round
  checker evidence was imported as `completion`, and the task reached `done`.
- Accepted the full workflow-loop model: planner is a workflow-loop phase but
  not part of the execution round; loop runner reads document/runtime state,
  activates planner or execution roles, and stops on terminal, paused, or
  limit states. See
  [topics/complete-workflow-design.md](topics/complete-workflow-design.md) and
  [decisions/009-loop-runner-activates-planner-and-stops.md](decisions/009-loop-runner-activates-planner-and-stops.md).
- Completed a reviewer/coworker readiness review for the workflow-loop design.
  Accepted the required pre-implementation clarifications: round writeback must
  be idempotent and consistency-checked, `rework_node` must escalate to
  `partial` or `replan_required` when bounded repair no longer applies, and
  the next implementation should be a one-shot `loop runner --once` bridge
  instead of a daemon.
- Landed and verified
  [goals/loop-runner-bridge-goal.md](goals/loop-runner-bridge-goal.md) in the
  current worktree. The bridge now supports `task-bind-loop`,
  `task-import-round`, `loop run-once --task-id`, and
  `loop runner --once`; focused tests passed with `21 passed`, neighboring
  CLI/router/render tests passed with `102 passed`, touched CLI modules passed
  `py_compile`, and an external source-wrapper fake-provider smoke in
  `/home/bfly/yunwei/test_ccb2/loop-runner-bridge-smoke-1782493619` proved
  ready-task binding, one round execution, round result import, current-loop
  cleanup, and generated worker/reviewer release. The smoke intentionally
  imported `round_blocker` when fake `round_checker` output lacked an explicit
  machine result, preserving the rule that scripts must not infer semantic
  `pass`.
- Completed the first `mother` RolePack design pass for the workflow role
  catalog. Accepted P0 complete RolePack work for `ccb_planner`,
  `ccb_plan_reviewer`, `ccb_clarification_broker`, `ccb_orchestrator`, and
  `ccb_round_checker`; P1 simplified roles for `frontdesk`, `worker`, and
  `checker`; and P2 boundary-only roles for risk, monitor, recovery, plan
  steward, domain researcher, and spec checker. See
  [history/mother-rolepack-design-2026-06-27.md](history/mother-rolepack-design-2026-06-27.md).
- Landed the first workflow RolePack draft set in the current worktree:
  shared authority rule and artifact templates, P0 RolePacks for
  `agentroles.ccb_planner`, `agentroles.ccb_plan_reviewer`,
  `agentroles.ccb_clarification_broker`, tightened
  `agentroles.ccb_orchestrator`, `agentroles.ccb_round_checker`, and P1
  simplified RolePacks for `agentroles.ccb_frontdesk`,
  `agentroles.ccb_worker`, and `agentroles.ccb_checker`. Targeted verification
  passed with `PYTHONPATH=lib pytest -q test/test_orchestrator_rolepack.py`
  producing `7 passed`.
- Landed the first workflow runner state-router slice in the current
  worktree. `ccb plan` artifact imports now record actor/job provenance;
  `ccb loop runner --once` routes `ready` to the existing execution bridge,
  routes `draft`/`partial`/`replan_required` to one planner activation packet
  and ask, and stops without provider activation for
  `needs_clarification`/`blocked`/terminal states. Focused tests passed with
  `34 passed`; source-wrapper smokes in `/home/bfly/yunwei/test_ccb2` covered
  draft planner activation, paused clarification stop, and ready execution
  bridge behavior with fake providers. See
  [history/workflow-runner-state-router-2026-06-27.md](history/workflow-runner-state-router-2026-06-27.md).
- Landed startup layout identity diagnostics in the current worktree:
  non-interactive `ccb` start output now includes a compact layout summary
  generated from the same `layout status` source as dynamic runtime
  diagnostics, including window counts, observed pane counts, explicit-window
  state, and per-agent `ownership_class`, `dispatch_state`, `pane_id`,
  `pane_identity_source`, runtime state, and apply status. Focused tests passed
  with `68 passed`; the dynamic layout regression set passed with
  `118 passed`; and an external source-wrapper fake-provider
  `window-class` smoke in `/home/bfly/yunwei/test_ccb2` preserved hot-load,
  middle unload, `plan-orchestrate` reflow, survivor pane IDs, askability, and
  cleanup.
- Landed the first read-only cross-window move planner in the current
  worktree: `ccb layout move-plan <agent> ... --json` reports source window,
  resolved target window, created-window need, ownership class, source/target
  would-be agent order, and explicit no-mutation fields. It plans movement for
  dynamic session agents, returns `noop` for same-window requests, and blocks
  cross-window runtime moves for static configured agents. Focused tests passed
  with `37 passed`, touched modules passed `py_compile`, and an external
  source-wrapper smoke in `/home/bfly/yunwei/test_ccb2/move-plan-smoke` proved
  dynamic `helper1` can be planned from `plan-orchestrate` to a new `review`
  window while static `frontdesk` is blocked.
- Landed the first true existing-window cross-window move slice in the current
  worktree: `ccb agent move <agent> --window NAME --json` updates dynamic
  lifecycle placement, writes `placement_sequence` so moved agents append after
  existing target agents, applies a `move_agent` namespace patch with tmux
  `move-pane`, restamps `@ccb_window`, reflows source and target windows, and
  updates runtime authority without provider restart. Focused regression passed
  with `108 passed`; source-wrapper CLI smoke in
  `/home/bfly/yunwei/test_ccb2/source-move-smoke-20260628034710` proved
  unmounted add/add/move projection and valid config.
- Landed the first move-to-new-window transaction slice in the current
  worktree. A dynamic agent can now move from an existing window into a newly
  materialized target window without provider restart: the reload planner
  admits the guarded `add_window + move_agent` combination, the namespace patch
  creates the target window, moves the existing pane into it, removes the
  placeholder pane, restamps placement evidence, and reflows source/target
  windows. Focused tests passed with `110 passed`; source-wrapper CLI smoke in
  `/home/bfly/yunwei/test_ccb2/source-move-new-window-smoke-20260628035809`
  proved unmounted dynamic add, move to `review`, `placement_sequence=1`,
  deferred apply until start, and valid projected config.

## In Progress

- Shape the first architecture contract for a state-machine-driven agentic
  loop that separates user-facing interaction, planning, orchestration,
  execution, monitoring, recovery, and plan-tree maintenance.
- Drive the first implementation goal for
  [dynamic orchestrator capacity](goals/orchestrator-dynamic-capacity-goal.md):
  `loop.role_profiles`, `orchestrator-capacity`, dynamic
  `worker + code_reviewer` load/release, task dispatch, review, aggregation,
  and real `/home/bfly/yunwei/test_ccb2` validation.
- First config slice is implemented in the current worktree: project config can
  parse, validate, record, and render `loop.capacity` and
  `loop.role_profiles`; focused config-loader tests pass.
- First command/state slice is implemented in the current worktree:
  `ccb loop capacity ensure/status/release --json` writes and reads
  deterministic loop capacity state under `.ccb/runtime/loops` through the
  existing runtime-state path layout.
- Runtime overlay slice is implemented in the current worktree: active
  `capacity.json` records are merged into config loading, user
  `.ccb/ccb.config` is not rewritten, and ensure/release tries guarded reload
  when a daemon is mounted or defers materialization until next start when
  unmounted.
- Orchestrator RolePack slice is implemented in draft form:
  `drafts/agentroles.ccb_orchestrator` includes `orchestrator-capacity`, CCB
  adapter memory, and worker/checker templates; focused tests prove manifest
  translation and skill projection.
- Mounted fake-provider runtime smoke passed in
  `/home/bfly/yunwei/test_ccb2/orchestrator-capacity-runtime-smoke`: dynamic
  `worker + code_reviewer` ensure applied through guarded reload, generated
  targets accepted ask/watch jobs, release removed idle nodes, and busy release
  retained a running worker until terminal completion.
- Deterministic `ccb loop run-once` slice is implemented and tested: it ensures
  one worker/reviewer pair, dispatches worker/reviewer/orchestrator ask/watch
  jobs, dispatches a fixed `round_checker` ask, releases idle generated nodes,
  and writes `round.json`, `asks.jsonl`, `events.jsonl`, `breadcrumb.md`, and
  reply artifacts. Execution/release failures after live capacity are recorded
  in `round.json` and keep the command non-ok while still attempting idle
  release.
- External fake-provider run-once smoke passed in
  `/home/bfly/yunwei/test_ccb2/orchestrator-capacity-runtime-smoke` with
  isolated `HOME`, `CCB_SOURCE_HOME`, and `AGENT_ROLES_STORE`; post-run `ps`
  showed only `orchestrator`.
- A guarded real-provider semantic-smoke harness now exists at
  `scripts/orchestrator_capacity_semantic_smoke.py`. Codex prepare/preflight
  passed under
  `/home/bfly/yunwei/test_ccb2/orchestrator-capacity-real-provider-smoke`, and
  the generated project passed source `ccb_test config validate`. The harness
  refuses to start real providers unless `CCB_ORCH_SMOKE_RUN_REAL=1` is set.
- Planner role design is documented in
  [topics/planner-role-design.md](topics/planner-role-design.md): V1 starts
  with `planner + plan_reviewer`, batches clarification through broker, and
  produces draft task artifacts plus readiness recommendation.
- Plan-update script landing is implemented and documented in
  [topics/plan-update-script-landing.md](topics/plan-update-script-landing.md)
  and tracked by
  [goals/planner-plan-script-goal.md](goals/planner-plan-script-goal.md).
- Complete workflow design is documented in
  [topics/complete-workflow-design.md](topics/complete-workflow-design.md):
  it defines nested workflow/execution loops, planner activation triggers,
  round result routing, stop conditions, authority ownership, and V1 command
  gaps.
- The active follow-through implementation goal is now fixed in
  [goals/clarification-planner-followthrough-goal.md](goals/clarification-planner-followthrough-goal.md):
  add the V1 `ccb question` artifact surface and the planner/broker/frontdesk/
  reviewer path that can move a routed `draft`, `partial`, or
  `replan_required` task toward script-owned `ready`.
- Dynamic agent lifecycle and skill design is documented in
  [topics/dynamic-agent-lifecycle-and-skills.md](topics/dynamic-agent-lifecycle-and-skills.md):
  it defines lifecycle states, runtime records, profile-based and inline
  role-based `ccb agent add ...` syntax, policy-based `remove`, loop capacity
  policy extensions, and a generic `dynamic-agent-lifecycle` skill boundary.
- Landed the first generic dynamic agent lifecycle CLI slice in the current
  worktree:
  `ccb agent status/show/add/remove --json`, runtime lifecycle records under
  `.ccb/runtime/agents`, dynamic-agent config overlay, profile-based add,
  inline `name:provider --role ...` add, policy-based remove, and kill safety
  validation. Focused tests passed, and external source-wrapper smoke in
  `/home/bfly/yunwei/test_ccb2/agent-lifecycle-real.o4yC4g` proved:
  add while unmounted, config overlay includes `helper`, startup mounts
  `main + helper`, `ask helper` completes through fake provider, `kill -f`
  unmounts, `remove --policy unload --idle-only` removes the overlay, and
  final `config validate` returns only `main`.
- Mounted reload analysis is now pinned: existing `ccb reload` already supports
  additive agent append from `ccb.config`, and the dynamic lifecycle overlay now
  has a matching reload-apply test proving it materializes a tmux pane before
  mounting runtime. External fake/fake-codex providers do not expose a preserved
  tmux pane anchor in `ps`, so they cannot prove online pane split; the CLI now
  reports the precise `namespace_patch_failed` anchor error instead of a generic
  reload failure.
- Landed the first true hot-load placement slice in the current worktree:
  `ccb agent add ... --window NAME` can append a new dynamic agent to an
  existing managed window or create a new managed window, `--window-class`
  chooses or creates a class window, and `--loop-id/--node-id` places execution
  agents in `node-<loop-id>-<node-id>`. Runtime lifecycle records now include
  placement intent and applied pane/window evidence. Focused tests prove
  parser, dry-run reload plans, existing-window `add_agent`, and new-window
  `add_window`; controlled mounted tmux smokes in
  `/home/bfly/yunwei/test_ccb2/agent-hot-pane-ident.otr4SM` and
  `/home/bfly/yunwei/test_ccb2/agent-hot-window-ident.Xj9dR6` proved the new
  agent mounts and accepts `ask` without changing preserved pane identity.
- Extended the true hot-load slice to cover safe dynamic unload:
  `remove --policy unload --idle-only` now records busy agents as
  `retained_busy`, applies the guarded `remove_agent` reload path after the
  target is idle, clears the active pane id while retaining `last_pane_id`,
  unloads runtime authority, removes the overlay from projected config, and
  removes empty dynamic windows. Focused tests passed, and controlled mounted
  tmux smokes in `/home/bfly/yunwei/test_ccb2/agent-hot-remove-pty.2FIiGo` and
  `/home/bfly/yunwei/test_ccb2/agent-hot-window-remove-pty.RqWVcE` proved
  existing-window and new-window release without breaking the preserved `main`
  pane.
- Landed the first safe `agent release` command surface and same-window dynamic
  cycle smoke. `ccb agent release <agent> --policy auto|hide|park|unload`
  avoids the destructive `kill` path; auto release unloads short-lived
  execution roles and parks unknown/long-lived roles. The mounted tmux cycle in
  `/home/bfly/yunwei/test_ccb2/agent-hot-cycle-pty.Tu9DCH` proved dynamic
  panes can grow from `1->6` and release back to `1` while preserving `%1:main`
  and returning `known_agents` to `['main']`.
- Landed the long-lived role park/resume slice. `ccb agent park <agent>` keeps
  the pane/runtime context but projects `dispatch_disabled=true`, publishes a
  config-only `view_only_change`, and causes direct `ask` dispatch to reject;
  `ccb agent resume <agent>` clears that dispatch gate without tmux mutation.
  Focused tests passed with `150 passed`, reload-focused tests passed with
  `70 passed`, and the mounted source-wrapper smoke in
  `/home/bfly/yunwei/test_ccb2/hotload-smoke-1782474327` proved
  add/ask/park-reject/resume-ask/new-window-add/release cleanup end to end.
- Landed the first clarification follow-through slice in the current worktree.
  `ccb question` now imports candidate questions, broker/user question batches,
  raw answers, normalized answers, and status refs with schema/path/provenance
  checks. `user-batch-import` pauses draft tasks at `needs_clarification`,
  `normalized-import` returns answered tasks to `draft`, runner paused
  responses include question refs, and planner activation packets include
  compact question/answer refs. The runner also activates `plan_reviewer` when
  planner artifacts are present but review is missing, and the existing
  `ccb plan` ready guard rejects `ready` until review is imported. Focused
  tests passed with
  `PYTHONPATH=lib pytest -q test/test_question_cli.py` producing `7 passed`;
  neighboring plan/loop/rolepack tests passed with `34 passed`, and the
  combined targeted regression set passed with `41 passed`; external
  source-wrapper smoke passed in
  `/home/bfly/yunwei/test_ccb2/question-followthrough-smoke-1782531830`,
  with review guard smoke in
  `/home/bfly/yunwei/test_ccb2/plan-review-guard-smoke-1782532093`.
- Completed the Clarification And Planner Follow-Through V1 goal in the
  current worktree. The full source-wrapper fake-provider smoke in
  `/home/bfly/yunwei/test_ccb2/question-followthrough-e2e-smoke-1782532792`
  covered draft planner activation, question import, clarification pause, raw
  and normalized answers, planner reactivation with answer refs, planner
  artifact imports, plan reviewer activation, review-backed `ready`, and ready
  execution bridge. The final task status was `blocked` with
  `round_result_source=missing_round_checker_result`, preserving the invariant
  that scripts do not infer `pass` from fake provider text.
- Completed Workflow RolePack External Spec Handoff V1. The workflow role
  drafts were promoted into `/home/bfly/yunwei/agent-roles-spec` as installable
  catalog Roles for `frontdesk`, `planner`, `clarification_broker`,
  `plan_reviewer`, `orchestrator`, `worker`, `ccb_checker`, and
  `round_checker`. External tests passed with `69 passed`; CCB targeted tests
  passed with `37 passed`; source-wrapper smoke in
  `/home/bfly/yunwei/test_ccb2/workflow-rolepack-handoff-smoke` installed all
  eight Roles, validated the five-role foreground config, planned dynamic
  worker/checker capacity, projected Codex `ask` plus role skills, and imported
  planner/broker/reviewer artifacts through `ccb plan` and `ccb question` until
  task `role-handoff-001` reached `ready`. The smoke also found and fixed the
  invalid `normalized-answers.jsonl` placeholder enum in both external Roles
  and local draft templates. CCB source now carries provider-local `ask` assets
  for the full workflow provider set, including Gemini, Qwen, and Z.ai.
- Completed the repeatable Workflow Closure Smoke goal in the current
  worktree. `scripts/workflow_closure_smoke.py` now prepares an isolated
  fake-provider source-wrapper project, installs the local workflow RolePacks,
  drives `ccb plan`, `ccb question`, and `ccb loop runner --once` through
  planner activation, clarification pause, normalized answers, planner
  reactivation, plan-reviewer gate, review-backed `ready`, execution bridge,
  round evidence import, and `release --policy auto` cleanup. Focused tests
  passed with `35 passed`; `git diff --check` and touched-file `py_compile`
  passed; external Agent Roles focused tests passed with `5 passed`; and the
  real smoke in
  `/home/bfly/yunwei/test_ccb2/workflow-closure-smoke-178255c` returned
  `workflow_smoke_status: ok`, `release_policy: auto`, `retained_count: 0`,
  and no dynamic worker/checker in `ps`. The fake-provider final task status
  remains intentionally `blocked` with
  `round_result_source=missing_round_checker_result`.
- Landed the first read-only runtime layout status surface. `ccb layout status`
  and `ccb layout status --json` now report effective `[windows]` topology
  after dynamic overlays, configured vs dynamic agents, lifecycle state,
  runtime state, pane ids, namespace state, and best-effort tmux observations.
  Focused tests passed with `39 passed`, touched-file `py_compile` passed, and
  the source-wrapper smoke in
  `/home/bfly/yunwei/test_ccb2/layout-status-real-1782553123` proved mounted
  explicit-window startup, same-window hot add/release, new-window
  add/release with empty-window removal, ask reachability for the dynamic fake
  agent, and unmounted stale-namespace status skipping tmux observation.
- Landed stable dynamic placement order for explicit `[windows]` hot load.
  Dynamic lifecycle records now carry `created_sequence`, semantic placement
  requests are resolved back into `resolved_window_name`, and config overlays
  order dynamic agents by creation instead of agent name. This fixed the real
  same execution-node failure where adding `checker1` after `worker1` was
  misclassified as `layout_change`; it now remains an append-only `add_agent`.
  Focused tests passed with `185 passed`, and the source-wrapper smoke in
  `/home/bfly/yunwei/test_ccb2/layout-placement-real-1782555` proved class
  overflow to `plan-orchestrate-2`, execution node creation
  `node-round1-node1`, same-node `worker1, checker1` ordering, ask submission
  to `checker1`, reverse unload, empty dynamic-window removal, and final return
  to the two configured windows.
- Connected `ccb loop capacity` to the runtime layout placement model.
  Capacity-generated worker/checker agents now carry `loop_id`, `node_id`,
  `created_sequence`, and execution-node placement; explicit `[windows]`
  overlays materialize them in `node-<loop-id>-<node-id>` windows instead of
  appending them to the entry window. `layout status` now distinguishes
  `source=loop` agents and reports `loop_agent_count`, loop id, node id,
  profile, pane, and runtime state. Focused tests passed with `187 passed`,
  and the source-wrapper smoke in
  `/home/bfly/yunwei/test_ccb2/loop-capacity-layout-real-1782557` proved
  mounted `loop capacity ensure` creates `node-round1-node1`, status reports
  two loop agents there, and `loop capacity release --idle-only` removes the
  node window and returns to `loop_agent_count=0`.
- Aligned orchestrator-facing RolePack and capacity documentation with the
  runtime layout model. `orchestrator-capacity` now states that
  `ccb loop capacity ensure/status/release` is the only dynamic execution
  capacity path, returned `node_id`/window/placement fields are CCB-owned
  evidence only, `ccb layout status --json` is read-only diagnostics for
  `source=loop`, and raw `ccb agent add --window`, `--window-class`, tmux,
  reload, and kill remain forbidden. Focused RolePack tests passed with
  `8 passed`; related orchestrator/loop/layout/lifecycle tests passed with
  `49 passed`; and a source-wrapper prepare/config/capacity smoke in
  `/home/bfly/yunwei/test_ccb2/orchestrator-capacity-rolepack-projection-1782560`
  proved config validity, planned node placement, layout status
  `loop_agent_count=2`, and release cleanup back to `loop_agent_count=0`.
- Extended loop-capacity explicit `[windows]` coverage from one execution node
  to multiple node windows. Focused tests now prove `worker=2` and
  `code_reviewer=2` become `node-round2-node1` and `node-round2-node2`, that
  each node keeps its worker/checker order, that release removes both node
  windows from the effective layout, and that `layout status` returns to
  `loop_agent_count=0`. Related targeted tests passed with `50 passed`; the
  mounted fake-provider source-wrapper smoke in
  `/home/bfly/yunwei/test_ccb2/multi-node-layout-smoke-1782561` proved live
  `add_window` materialization to 8 tmux panes, ask submission to two generated
  loop agents, `remove_agent` release of all four loop agents, and return to
  the original `main` window with only sidebar plus `orchestrator`.
- Extended same-window dynamic release coverage for middle-pane deletion.
  Dynamic lifecycle tests now prove `main + helper1 + helper2 + helper3`
  can unload middle `helper2` while preserving effective order
  `main + helper1 + helper3` and staying in safe `remove_agent` instead of
  degrading to `layout_change`. The mounted fake-provider smoke in
  `/home/bfly/yunwei/test_ccb2/same-window-middle-release-1782562` proved
  live append-only hot load to panes `%2/%3/%4`, middle release removing only
  `%3`, preserved helper panes `%2` and `%4` staying alive, and accepted asks
  to both surviving dynamic agents after release.
- Landed the first real remove-path reflow slice. `remove_agent` now records
  `reflowed_windows` / `reflow_errors`, runs best-effort `select-layout -E`
  after successful same-window pane removal, and reapplies topology sidebar
  widths so visual compaction does not permanently flatten CCB sidebars.
  Focused tests prove pane-only removal, reflow diagnostics, and sidebar width
  restoration; the repeatable source-wrapper smoke in
  `/home/bfly/yunwei/test_ccb2/dynamic-layout-reflow-1782570-same-window`
  proved middle `helper2` removal reports `namespace_reflowed_windows=["main"]`
  while preserving `helper1` and `helper3` and keeping survivor asks reachable.
- Hardened the orchestrator autonomous smoke harness so a round is only
  accepted after capacity release and layout cleanup both pass. The harness now
  captures `ccb layout status --json` after the parent callback chain and
  requires `layout_status=ok` with `loop_agent_count=0`, preventing a false
  pass when generated loop agents are released from capacity state but still
  visible in runtime layout. Source-wrapper prepare/config validation passed in
  `/home/bfly/yunwei/test_ccb2/orchestrator-capacity-layout-prepare-1782571`,
  and the fake workflow closure smoke in
  `/home/bfly/yunwei/test_ccb2/workflow-closure-layout-1782571` proved
  dynamic generated agents release with no `ps` residue.
- Extended the repeatable dynamic layout smoke to explicit workflow windows.
  The new `window_class_middle_release` flow creates `main` plus
  `plan-orchestrate`, hot-loads `planner_helper1/2/3` with
  `--window-class plan-orchestrate`, removes the middle helper, and proves
  `namespace_reflowed_windows=["plan-orchestrate"]` while preserving surviving
  pane ids and ask reachability. The source-wrapper run in
  `/home/bfly/yunwei/test_ccb2/dynamic-layout-window-class-1782560319-window-class`
  passed with all three dynamic layout flows green.
- Parameterized the dynamic layout smoke harness for the next real-provider
  slice. It now supports `--provider`, repeatable `--flow`,
  `--provider-home-mode`, and `--prepare-only`, while requiring
  `CCB_DYNAMIC_LAYOUT_SMOKE_RUN_REAL=1` before any non-fake provider is
  started. Default fake-provider regression still passed all three flows, a
  selected `--flow window-class` source-wrapper run passed, and Codex
  `--prepare-only --provider-home-mode real-home` proved executable/auth
  preflight without launching provider panes.
- Integrated the dynamic layout line with remote `origin/main`/`v7.7.0`
  runtime-accelerator and theme changes. Conflict-surface tests passed with
  `105 passed`, dynamic layout regression passed with `101 passed`, runtime
  accelerator focused checks passed, and the merged source-wrapper smoke in
  `/home/bfly/yunwei/test_ccb2/dynamic-layout-merged-1782561461-*` kept all
  three fake-provider layout flows green.
- Ran the first guarded real-provider explicit-window smoke:
  `CCB_DYNAMIC_LAYOUT_SMOKE_RUN_REAL=1 ... --provider codex --flow
  window-class --provider-home-mode real-home --command-timeout 240`.
  `/home/bfly/yunwei/test_ccb2/dynamic-layout-codex-window-1782561840-window-class`
  passed: `frontdesk` and `planner` Codex panes started, three Codex helper
  agents hot-loaded into `plan-orchestrate`, middle `planner_helper2` unloaded
  with `namespace_reflowed_windows=["plan-orchestrate"]`, surviving helper pane
  ids were preserved, and asks to both surviving helpers were accepted.
- Ran the matching guarded Claude real-provider explicit-window smoke:
  `CCB_DYNAMIC_LAYOUT_SMOKE_RUN_REAL=1 ... --provider claude --flow
  window-class --provider-home-mode real-home --command-timeout 300`.
  `/home/bfly/yunwei/test_ccb2/dynamic-layout-claude-window-1782563057-window-class`
  passed with `frontdesk` and `planner` Claude panes, three Claude helper panes
  hot-loaded into `plan-orchestrate`, middle `planner_helper2` unloaded with
  `namespace_reflowed_windows=["plan-orchestrate"]`, surviving pane ids
  preserved, asks accepted to `planner_helper1` and `planner_helper3`, and
  final `kill -f` returning `state: unmounted`.
- Strengthened `ccb layout status --json` as a script-facing diagnostic for
  dynamic orchestration. Each agent record now exposes `agent_kind`,
  `ownership_class`, `dispatch_state`, `pane_identity_source`, `apply_status`,
  `apply_plan_class`, `apply_stage`, `failed_apply`, and `retained_busy`, so
  orchestrator scripts can distinguish static configured panes, dynamic
  helpers, loop capacity agents, parked/dispatch-disabled nodes, and failed
  apply attempts without reading raw lifecycle files. Focused regression passed
  with `104 passed`, and a fake `--flow window-class` source-wrapper smoke in
  `/home/bfly/yunwei/test_ccb2/dynamic-layout-status-diag-1782564247-window-class`
  stayed green.
- Mirrored the same ownership/apply vocabulary into `ccb agent status --json`
  and `ccb agent show --json`, keeping command-level lifecycle diagnostics
  aligned with `layout status --json`. Focused lifecycle/layout tests passed
  with `25 passed`; the broader dynamic lifecycle regression stayed at
  `104 passed`, and another fake explicit-window smoke in
  `/home/bfly/yunwei/test_ccb2/dynamic-layout-status-helper-1782565815-window-class`
  stayed green.
- Packaged the verified command vocabulary into the orchestrator draft
  RolePack as `dynamic-agent-lifecycle` and kept `orchestrator-capacity` as the
  loop-only worker/checker capacity boundary. The orchestrator CCB adapter now
  projects both skills, and `orchestrator-capacity` explicitly points non-loop
  helpers, brokers, planner/frontdesk companions, and diagnostics to
  `dynamic-agent-lifecycle`.
- Added a standard provider-matrix entrypoint to
  `scripts/dynamic_layout_smoke.py`: repeat `--provider` to run the same
  selected flow across providers with one command while preserving the old
  single-provider output shape. The guarded real matrix command passed for
  `--provider codex --provider claude --flow window-class` in
  `/home/bfly/yunwei/test_ccb2/dynamic-layout-matrix-real-1782567263-*`.
  Both providers hot-loaded three helpers into `plan-orchestrate`, unloaded
  middle `planner_helper2`, reflowed only `plan-orchestrate`, preserved
  surviving panes, accepted asks to surviving helpers, and cleaned up to
  `state: unmounted`.
- Added the fixed guarded release/local entrypoint
  `scripts/guarded_dynamic_layout_provider_smoke.py`. It defaults to
  prepare-only Codex+Claude `window-class`, requires both `--run` and
  `CCB_DYNAMIC_LAYOUT_SMOKE_RUN_REAL=1` for real provider execution, and wraps
  the provider matrix with a stable command for future release gates. The
  wrapper passed prepare-only in
  `/home/bfly/yunwei/test_ccb2/guarded-dynamic-layout-prepare-1782568181-*`
  and a real guarded run in
  `/home/bfly/yunwei/test_ccb2/guarded-dynamic-layout-real-1782568215-*`.
- Wired the guarded provider matrix into the default `Tests` workflow as a
  prepare-only Ubuntu py3.11 gate. The CI step runs
  `scripts/guarded_dynamic_layout_provider_smoke.py` without `--run`, asserts
  `dynamic_layout_smoke_status=prepared`, `providers=["codex","claude"]`, and
  `flows=["window-class"]`, and therefore checks the release wrapper contract
  without requiring real provider auth on GitHub runners. Local verification
  passed with `44 passed`, the broader dynamic layout regression set passed
  with `162 passed`, and the source-wrapper prepare-only command returned
  `prepared` from `/home/bfly/yunwei/test_ccb2`.
- Added shared reload apply pane-identity diagnostics for dynamic
  add/remove reports. Mounted `ccb agent add/remove --json` and
  `ccb loop capacity ensure/release --json` now include a
  `pane_identity_report` built from reload `namespace_patch` and
  `runtime_mount` facts: added agents, removed agents, preserved before/after
  panes, created/removed panes, removed windows, reflowed windows, reflow
  errors, mounted agents, and unloaded agents. Focused lifecycle/capacity tests
  passed with `40 passed`, the broader dynamic layout regression set passed
  with `163 passed`, and an external source-wrapper fake-provider
  `window-class` smoke in `/home/bfly/yunwei/test_ccb2` remained green.
- Landed the first read-only dynamic placement resolver. `ccb layout resolve
  <agent> --json` reports the effective target surface before lifecycle
  mutation, using the same placement precedence as dynamic overlays:
  `--window`, then execution node `--loop-id/--node-id`, then `--window-class`,
  then entry/default layout. Focused layout tests passed with `11 passed`;
  lifecycle/capacity/RolePack regression passed with `49 passed`; touched
  files passed `py_compile`; and the external source-wrapper smoke in
  `/home/bfly/yunwei/test_ccb2/layout-resolve-smoke-1782572776` proved
  `plan-orchestrate` overflow resolves to `plan-orchestrate-2`, execution-node
  placement resolves to `node-round1-node1`, and no dynamic lifecycle state is
  created.
- Packaged the resolver into the orchestrator draft RolePack's
  `dynamic-agent-lifecycle` skill. Non-loop dynamic agent adds now document the
  required script chain `layout resolve -> agent add -> agent show/status ->
  layout status`, with resolver evidence for `addable`, `placement_mode`,
  `resolved_window_name`, and `will_create_window`. Focused RolePack tests
  passed with `9 passed`, including Codex home skill projection.
- Landed repeatable guarded smoke coverage for the resolver-driven chain.
  `scripts/dynamic_layout_smoke.py --flow resolve-preflight` now starts an
  explicit `[windows]` fake-provider project, proves `layout resolve` overflows
  a full `plan-orchestrate` class to `plan-orchestrate-2`, hot-adds a dynamic
  short-lived reviewer there with `add_window`, verifies `agent show` and
  `layout status`, releases the agent and removes the empty overflow window,
  then resolves `node-round3-node1` and uses `ccb loop capacity` to create and
  release worker/checker panes without exposing raw `agent add` for loop
  capacity. The external source-wrapper run in
  `/home/bfly/yunwei/test_ccb2/resolve-preflight-smoke-1782573894-resolve-preflight`
  returned `dynamic_layout_smoke_status=ok`; the guarded provider wrapper now
  prepares both `window-class` and `resolve-preflight` for Codex+Claude in CI;
  script/guarded tests passed with `19 passed`; layout tests passed with
  `30 passed`; lifecycle/capacity/RolePack regression passed with `49 passed`;
  touched script tests passed `py_compile`; and `git diff --check` passed.
- Reconciled the dynamic layout line with remote `origin/main` / `v8.0.0`
  release workflow fixes. Post-merge focused verification passed for dynamic
  layout smoke/resolver/status tests (`30 passed`), lifecycle/capacity/
  RolePack tests (`49 passed`), and the merged mobile/sidebar release-fix
  tests (`54 passed`); `git diff --check` passed.
- Landed the lighter guarded real-provider `resolve-preflight` variant. The
  smoke harness can now keep static overflow filler panes on `fake` while
  reserving the selected real provider for the dynamic reviewer and loop
  worker/checker profiles. Guarded Codex/Claude prepare-only from
  `/home/bfly/yunwei/test_ccb2` generated `frontdesk + p1..p6` as `fake` and
  loop profiles as `codex` / `claude`; fake source-wrapper
  `resolve-preflight` still passed the full add/release/capacity chain with
  `dynamic_layout_smoke_status=ok`. Focused script tests passed with
  `21 passed`; related layout/lifecycle/capacity/RolePack tests passed with
  `81 passed`; `py_compile` and `git diff --check` passed.
- Ran the first opt-in Codex real-provider `resolve-preflight` proof for the
  lighter variant in
  `/home/bfly/yunwei/test_ccb2/guarded-light-codex-real-1782574-codex-resolve-preflight`.
  With `CCB_DYNAMIC_LAYOUT_SMOKE_RUN_REAL=1`, the flow passed
  `dynamic_layout_smoke_status=ok`: `layout resolve` predicted
  `plan-orchestrate-2`, dynamic Codex reviewer add used `add_window`, release
  removed the overflow window, execution-node resolve predicted
  `node-round3-node1`, loop capacity created and released Codex worker/checker
  panes, and final `kill -f` returned `state: unmounted`.
- Ran the matching opt-in Claude real-provider `resolve-preflight` proof for
  the lighter variant in
  `/home/bfly/yunwei/test_ccb2/guarded-light-claude-real-1782574-claude-resolve-preflight`.
  The flow passed `dynamic_layout_smoke_status=ok` with the same critical
  checks: dynamic Claude reviewer add/release used `add_window` then
  `remove_agent`, execution-node capacity created and released Claude
  worker/checker panes in `node-round3-node1`, layout status returned to
  `dynamic_agent_count=0` and `loop_agent_count=0`, and final `kill -f`
  returned `state: unmounted`.
- Fixed compact workspace release reflow for loop-capacity cleanup. The
  workflow closure smoke exposed a `remove_agent` reflow error when logical
  window `main` mapped to the namespace workspace window `ccb` / `@1`.
  Namespace patch release now targets the stable namespace workspace id/name
  for entry-window reflow when the logical window name is not present in tmux.
  Focused namespace/reload/capacity/workflow tests passed with `78 passed`,
  and a source-wrapper workflow closure run in
  `/home/bfly/yunwei/test_ccb2/workflow-closure-ci-gate-1782575` passed with
  `workflow_smoke_status=ok`, `released_count=2`,
  `namespace_reflowed_windows=["main"]`, and empty reflow errors.
- Wired the fake-provider workflow closure layout-cleanup smoke into the
  Ubuntu py3.11 `Tests` workflow. The gate runs
  `scripts/workflow_closure_smoke.py --run --json` and asserts workflow
  closure, auto release, zero retained loop agents, and empty namespace/pane
  reflow errors.
- Wired the orchestrator autonomous cleanup contract into the Ubuntu py3.11
  `Tests` workflow without requiring real provider credentials. The
  `orchestrator_capacity_semantic_smoke.py --provider fake --prepare-only`
  gate now prepares an isolated role store/source home, asserts the autonomous
  success contract rejects retained capacity or layout loop-agent residue, and
  validates the prepared `.ccb/ccb.config` through the source `ccb_test`
  wrapper. Focused tests passed with `20 passed`; source-wrapper prepare and
  config validation passed in
  `/home/bfly/yunwei/test_ccb2/orchestrator-autonomous-cleanup-contract-smoke`.
- Landed a richer live reflow/remove-window boundary for explicit `[windows]`.
  `remove_agent` namespace apply now tolerates the case where killing the last
  agent pane closes a no-sidebar agent window before an explicit `kill-window`,
  records `namespace_removed_windows`, and keeps removed agent/pane
  diagnostics. The dynamic layout smoke now includes a `single-agent-window`
  fake-provider flow; source-wrapper validation in
  `/home/bfly/yunwei/test_ccb2/single-agent-window-release-smoke-single-agent-window`
  passed with `add_window`, `remove_agent`, `namespace_removed_windows=["review"]`,
  final `dynamic_agent_count=0`, and `ask main` accepted. Focused tests passed
  with `60 passed`.
- Added a continuous same-window live dynamic layout regression. The
  `same-window-continuous` fake-provider flow grows the entry window from
  `main` to `main + helper1..helper5`, waits for a helper ask to complete,
  unloads helpers in reverse order back to a single `main` pane, and verifies
  `remove_agent`, `namespace_reflowed_windows=["main"]`, preserved `main`
  pane identity, final `dynamic_agent_count=0`, and `ask main` reachability.
  The source-wrapper run in
  `/home/bfly/yunwei/test_ccb2/same-window-continuous-smoke-same-window-continuous`
  passed with `dynamic_layout_smoke_status=ok`, and the same flow is now a
  Ubuntu py3.11 `Tests` workflow gate. Focused dynamic layout regression
  passed with `67 passed`.
- Added a multi-window continuous add/remove smoke for explicit `[windows]`
  page growth and collapse. The `multi-window-continuous` fake-provider flow
  dynamically creates `review1..review3`, verifies the project has four
  windows, waits for `helper2` ask completion, unloads helper windows in
  reverse order, and proves each removal reports `namespace_removed_windows`,
  preserves the `main` pane, returns to a single `main` window, and leaves
  `dynamic_agent_count=0`. Source-wrapper validation passed in
  `/home/bfly/yunwei/test_ccb2/multi-window-continuous-smoke-multi-window-continuous`
  with `dynamic_layout_smoke_status=ok`; focused dynamic layout regression
  passed with `69 passed`.
- Strengthened runtime layout verification with pane geometry diagnostics.
  `ccb layout status --json` now captures best-effort tmux `pane_index`,
  `pane_width`, and `pane_height` for observed panes, while dynamic smoke
  checks count only effective agent panes so sidebar panes remain visible
  diagnostics without polluting agent layout assertions. The same-window
  continuous CI gate now asserts observed growth to six agent panes, contiguous
  pane indexes, geometry presence, and shrink back to one agent pane. Focused
  tests passed with `32 passed`, the broader dynamic layout regression passed
  with `78 passed`, and the source-wrapper fake-provider smoke in
  `/home/bfly/yunwei/test_ccb2/observed-geometry-smoke.json` passed both
  `same-window-continuous` and `multi-window-continuous` flows with all
  observed geometry checks green.
- Added append-path live reflow for dynamic hot load. Append-only
  `add_agent` now uses the same `select-layout -E` plus sidebar width sync
  helper as `remove_agent`, and records the result in existing
  `namespace_reflowed_windows` / `namespace_reflow_errors` diagnostics. The
  same-window continuous smoke now rejects collapsed hot-load geometry with
  `observed_grow_min_width`; source-wrapper validation in
  `/home/bfly/yunwei/test_ccb2/add-reflow-smoke.json` proved six agent panes
  grew to observable widths `20,22,22,22,22,22` instead of the previous
  repeated-split shape `66,33,16,8,3,4`. Combined source-wrapper validation in
  `/home/bfly/yunwei/test_ccb2/add-reflow-combined-smoke.json` passed both
  same-window and multi-window flows, and focused regression passed with
  `78 passed`.
- Landed fixed live reflow for fully managed agent windows with one to six
  effective agent panes. Add/remove reflow now first applies a generated tmux
  layout matching the runtime planner visual order (`p1,p3,p5` left and
  `p2,p4,p6` right), then uses `swap-pane` to preserve existing pane IDs and
  provider sessions; unsafe or unsupported windows fall back to tmux even
  compaction. `layout status --json` now exposes `pane_left` and `pane_top` in
  addition to existing pane geometry, and the same-window continuous smoke
  rejects horizontal-only compaction via `observed_grow_fixed_columns`. Focused
  tests passed with `34 passed` and `46 passed`; source-wrapper fake-provider
  smoke in `/home/bfly/yunwei/test_ccb2/fixed-reflow-smoke.json` proved
  `main/helper2/helper4` in the left column and
  `helper1/helper3/helper5` in the right column after `1->6`, and
  `/home/bfly/yunwei/test_ccb2/fixed-reflow-combined-smoke.json` passed both
  same-window `1->6->1` and multi-window add/remove flows.
- Added a continuous window-class overflow regression for dynamic layout.
  `scripts/dynamic_layout_smoke.py --flow window-class-continuous` now grows
  `plan-orchestrate` from `planner` to a full six-agent first page, creates
  `plan-orchestrate-2` for the seventh/eighth logical panes, verifies fixed
  observed columns on both pages, asks the overflow helper, then unloads in
  reverse order and requires the empty overflow page to disappear. The Ubuntu
  py3.11 fake-provider CI gate now runs this flow alongside
  `same-window-continuous`. Focused tests passed with `24 passed` and
  `81 passed`; source-wrapper fake-provider evidence in
  `/home/bfly/yunwei/test_ccb2/window-class-continuous-smoke.json` proved
  page1=`planner, planner_helper1..5`, page2=`planner_helper6, planner_helper7`,
  ask reachability, and cleanup to only `main` plus `plan-orchestrate`.
  `/home/bfly/yunwei/test_ccb2/ci-combined-layout-smoke.json` passed the
  CI-equivalent combined same-window plus window-class continuous run.
- Landed a repeatable dynamic agent lifecycle policy smoke in the current
  worktree. `scripts/dynamic_agent_lifecycle_smoke.py` starts an explicit
  `[windows]` fake-provider project, hot-loads a long-lived
  `planner_helper` into `plan-orchestrate`, proves `release --policy auto`
  resolves to `park`, dispatch is disabled, parked `ask` is rejected, and
  `resume --hidden` preserves the pane and restores ask reachability. The same
  smoke hot-loads a short-lived `reviewer_helper`, proves `release --policy
  auto` resolves to `unload`, removes the reviewer pane through
  `remove_agent`, and cleans up the planner helper back to only static
  `frontdesk` plus `planner`. Focused tests passed with `5 passed`, adjacent
  lifecycle/layout script regression passed with `49 passed`, and
  `/home/bfly/yunwei/test_ccb2/lifecycle-policy-smoke.json` returned
  `dynamic_agent_lifecycle_smoke_status=ok` with all lifecycle checks true.
- Landed the first manual runtime rearrangement command in the current
  worktree. `ccb layout arrange --window NAME --json` is mounted-only,
  topology-preserving, and reuses the same safe fixed/even reflow helper used
  by dynamic add/remove; it does not add/remove agents, rewrite
  `.ccb/ccb.config`, or restart providers. Focused layout tests passed with
  `16 passed`, neighboring layout/dynamic script regression passed with
  `40 passed`, and the source-wrapper smoke in
  `/home/bfly/yunwei/test_ccb2/layout-arrange-smoke.json` proved
  `plan-orchestrate` can be hot-loaded to five panes, manually disturbed into
  a horizontal tmux layout, restored by `layout arrange` into the managed
  two-column layout, and kept the agent order
  `planner, helper1, helper2, helper3, helper4`.
- Added direct JSON artifact output to the dynamic layout smoke harness and
  reran the current source-wrapper fake-provider closure for explicit-window
  dynamic maintenance. `scripts/dynamic_layout_smoke.py --output <path>` now
  writes the same compact/full JSON that it prints, making local and CI smoke
  evidence directly reusable. The run at
  `/home/bfly/yunwei/test_ccb2/dynamic-layout-output-latest.json` passed
  `same-window-continuous`, `multi-window-continuous`, and
  `window-class-continuous`: same-window panes grew `1->6->1` with fixed
  columns and preserved `main`, separate review windows were created and
  removed back to one `main` window, and `plan-orchestrate-2` overflow was
  created, used, then removed after reverse unload.
- Promoted manual rearrangement into the repeatable dynamic layout smoke
  harness. `scripts/dynamic_layout_smoke.py --flow arrange-window` now starts
  an explicit `[windows]` fake-provider project, hot-loads four helpers into
  `plan-orchestrate`, intentionally disturbs the tmux window into a horizontal
  layout, calls `ccb layout arrange --window plan-orchestrate --json`, verifies
  managed fixed columns, preserved pane ids, preserved agent order, post-arrange
  ask reachability, and reverse unload cleanup. Source-wrapper evidence in
  `/home/bfly/yunwei/test_ccb2/dynamic-layout-arrange-latest.json` passed with
  `arrange_window_disturb_restore=true`; focused dynamic layout regression
  passed with `44 passed`. The Ubuntu py3.11 fake-provider CI gate now runs
  `arrange-window` with the existing `same-window-continuous` and
  `window-class-continuous` flows; source-wrapper CI-equivalent evidence in
  `/home/bfly/yunwei/test_ccb2/dynamic-layout-ci-arrange-latest.json` passed
  all three flow checks.
- Ran opt-in real-provider `arrange-window` smokes for both Codex and Claude.
  Codex evidence in
  `/home/bfly/yunwei/test_ccb2/dynamic-layout-arrange-codex-real-latest.json`
  and Claude evidence in
  `/home/bfly/yunwei/test_ccb2/dynamic-layout-arrange-claude-real-latest.json`
  both returned `dynamic_layout_smoke_status=ok` with
  `arrange_window_disturb_restore=true`: hot add used `add_agent`, disturbance
  made the layout non-fixed, `layout arrange` restored fixed columns, pane ids
  and agent order were preserved, post-arrange ask reached the helper, and
  reverse unload returned to static `frontdesk` plus `planner`.
- Promoted dynamic agent movement into the repeatable mounted smoke harness.
  `scripts/dynamic_layout_smoke.py --flow move-agent` now hot-loads `helper`
  into `main`, proves ask reachability, moves the preserved pane to a newly
  materialized `review` window, proves ask reachability again, and unloads the
  helper while removing the empty `review` window. The first real run exposed a
  transaction gate bug where runtime `status=moved` was rejected before
  publish; the gate now treats `moved` as publish-ready alongside
  `mounted/noop/unloaded`. Focused tests passed with `41 passed`; source-wrapper
  evidence in `/home/bfly/yunwei/test_ccb2/dynamic-layout-move-agent-latest.json`
  passed with `move_agent_to_new_window=true`; the CI-equivalent fake flow
  bundle in `/home/bfly/yunwei/test_ccb2/dynamic-layout-ci-move-latest.json`
  passed `same-window-continuous`, `move-agent`,
  `window-class-continuous`, and `arrange-window`.
- Extended dynamic movement from one-way movement to a full bounded move
  cycle. `move-agent` now proves `main -> review -> main -> unload`: the
  helper keeps the same pane id across both moves, remains ask-reachable before
  movement, after movement, and after return, the return transaction removes
  the now-empty `review` window, and final unload returns the project to one
  static `main` window. Focused regression passed with `135 passed`; external
  source-wrapper evidence in
  `/home/bfly/yunwei/test_ccb2/dynamic-layout-move-cycle-latest.json` passed
  the cycle checks; the CI-equivalent fake flow bundle in
  `/home/bfly/yunwei/test_ccb2/dynamic-layout-ci-cycle-latest.json` passed
  `same-window-continuous`, `move-agent`, `window-class-continuous`, and
  `arrange-window`.
- Promoted the bounded move cycle into the guarded provider matrix. The wrapper
  now prepares Codex+Claude `window-class`, `move-agent`, and
  `resolve-preflight` projects by default, and the Ubuntu py3.11 CI assertion
  checks that exact flow set. The smoke harness now observes submitted jobs
  through `ccb pend --watch` with an explicit `CCB_WATCH_TIMEOUT_S` matching
  the smoke command timeout, avoiding false non-terminal failures from the old
  10-second weak watch default. Focused script tests passed with `35 passed`;
  source-wrapper prepare-only evidence in
  `/home/bfly/yunwei/test_ccb2/guarded-dynamic-layout-move-prepare-latest.json`
  reached `prepared` for Codex+Claude; opt-in Codex real-provider evidence in
  `/home/bfly/yunwei/test_ccb2/guarded-dynamic-layout-codex-move-real-latest.json`
  and opt-in Claude real-provider evidence in
  `/home/bfly/yunwei/test_ccb2/guarded-dynamic-layout-claude-move-real-latest.json`
  both returned `dynamic_layout_smoke_status=ok` with all move-cycle ask
  terminal, pane-preservation, empty-window removal, and cleanup checks true;
  the source-wrapper fake CI-equivalent regression in
  `/home/bfly/yunwei/test_ccb2/dynamic-layout-watch-regression-latest.json`
  passed `same-window-continuous`, `move-agent`,
  `window-class-continuous`, and `arrange-window`.
- Extended movement coverage to a shared dynamic source window. The new
  `move-shared-source` smoke hot-loads `helper1` and `helper2` into `review`,
  moves only `helper1` to `main`, proves `helper2` stays in `review` with the
  same pane id and ask reachability, moves `helper1` back into `review`, then
  unloads both helpers so the empty `review` window is removed only after the
  last dynamic agent exits. Focused tests passed with `83 passed`; external
  source-wrapper evidence in
  `/home/bfly/yunwei/test_ccb2/dynamic-layout-shared-source-latest.json`
  returned `move_agent_shared_source=true`; the CI-equivalent fake bundle in
  `/home/bfly/yunwei/test_ccb2/dynamic-layout-shared-source-ci-latest.json`
  passed `same-window-continuous`, `move-agent`, `move-shared-source`,
  `window-class-continuous`, and `arrange-window`.
- Landed guarded low-level support for same-transaction movement of multiple
  agents out of one source window while the source window remains alive. The
  reload planner now validates source-window order after removing all moved
  source agents as a set, not one agent at a time, and namespace apply moves
  both existing panes into the target window without restart or source-window
  removal. Focused tests passed with `68 passed` across reload planning,
  namespace patch apply, and agent lifecycle CLI coverage. This is a
  transaction-kernel proof; a user-facing batch `ccb agent move` command is
  still not exposed.
- Extended the same transaction kernel to full source-window evacuation. A
  reload patch can now move every agent out of a source window and remove that
  emptied source window in the same guarded transaction, while ordering moved
  panes by the new target topology instead of agent-name sort order. Focused
  regression passed with `70 passed` across reload planning, namespace patch
  apply, and lifecycle CLI tests. This still remains below the user-facing
  command layer.
- Exposed the first user-facing batch move command:
  `ccb agent move --agents a,b --window NAME --json`. The command writes all
  selected dynamic lifecycle records first, applies one guarded reload
  transaction, and restores all touched records if reload fails. The same
  slice also allows multiple moved panes to enter a newly materialized target
  window. Focused regression passed with `106 passed`, and source-wrapper
  fake-provider evidence in `/home/bfly/yunwei/test_ccb2/batch-move-*-latest.json`
  proved mounted `review=[zeta,alpha] -> archive=[zeta,alpha]`, preserved pane
  ids `%3/%4`, removed the empty `review` window, and kept both moved ask
  targets accepted.
- Exposed the first user-facing batch release/unload command:
  `ccb agent remove --agents a,b --policy unload --idle-only --json` and
  `ccb agent release --agents a,b --idle-only --json`. The command validates
  every selected dynamic agent first, treats the idle gate as all-or-nothing,
  writes one lifecycle batch, applies one guarded reload transaction, and
  restores all touched records if reload fails. Focused regression passed with
  `110 passed`; source-wrapper evidence in
  `/home/bfly/yunwei/test_ccb2/batch-remove-smoke-evidence/summary.json`
  proved mounted `main=[main,helper1,helper2,helper3]` batch-unloads
  `helper2,helper3`, reports `plan_class=remove_agent`,
  `namespace_reflowed_windows=["main"]`, keeps `main,helper1`, accepts ask to
  remaining `helper1`, and cleans up with `kill_status: ok`.
- Promoted batch release into the repeatable dynamic layout smoke harness.
  `scripts/dynamic_layout_smoke.py --flow batch-release` now hot-loads one
  survivor in `main` plus two single-agent review windows, batch-unloads the
  two review agents with one `remove --agents` command, proves both review
  windows are removed, verifies survivor pane preservation, and checks ask
  reachability for both `helper1` and `main`. Script tests passed with
  `39 passed`; source-wrapper evidence in
  `/home/bfly/yunwei/test_ccb2/dynamic-layout-batch-release-latest.json`
  returned `dynamic_layout_smoke_status=ok`.
- Added `batch-release` to the default Ubuntu Python 3.11 fake-provider
  dynamic layout CI bundle, beside same-window growth/shrink, move-agent,
  shared-source move, window-class continuous paging, and arrange-window. The
  workflow now asserts the batch flow status plus removed-window, removed-pane,
  survivor-pane, and ask-reachability invariants instead of relying only on
  the standalone smoke evidence.
- Extended user-facing batch `ccb agent move --agents a,b` beyond explicit
  `--window NAME` placement to the same dynamic target grammar as single-agent
  move. `--window-class CLASS` now resolves each moved agent through the
  effective `[windows]` topology and capacity rules before applying one reload
  transaction; the response includes `target_window_names` when a batch splits
  across multiple resolved windows. Focused regression passed with `67
  passed`; source-wrapper fake-provider evidence in
  `/home/bfly/yunwei/test_ccb2/dynamic-layout-batch-move-window-class-latest.json`
  proved `review=[zeta,alpha]` batch-moves into
  `plan-orchestrate=[p1..p5,zeta]` plus `plan-orchestrate-2=[alpha]`,
  preserves both moved pane ids, removes the empty `review` window, and keeps
  both moved ask targets accepted.
- Proved the same batch move surface for execution-node placement.
  `scripts/dynamic_layout_smoke.py --flow batch-move-execution-node` now
  hot-loads `worker,checker` into a `review` window, runs one
  `ccb agent move --agents worker,checker --loop-id round1 --node-id node1`,
  and verifies both existing panes move into `node-round1-node1` without
  respawn, the empty `review` window is removed, and both moved ask targets
  remain accepted. Focused regression passed with `70 passed`; source-wrapper
  fake-provider evidence is preserved in
  `/home/bfly/yunwei/test_ccb2/dynamic-layout-batch-move-execution-node-latest.json`.
- Exposed the first user-facing batch park/resume command:
  `ccb agent park --agents a,b --json` and
  `ccb agent resume --agents a,b --hidden|--visible --json`. The command
  validates every selected dynamic agent first, writes one lifecycle batch,
  applies one config-only reload transaction, and restores all touched records
  if reload fails. Focused regression passed with `64 passed`; source-wrapper
  evidence in
  `/home/bfly/yunwei/test_ccb2/batch-park-resume-smoke-evidence/summary.json`
  proved mounted batch park sets dispatch disabled for both helpers, rejects
  ask while parked, batch resume re-enables dispatch without changing pane ids,
  accepts ask after resume, and cleans up with `kill_status: ok`.

## Next

1. Continue richer live reflow beyond the proven same-window continuous,
   single-agent-window, multi-window add/remove, and explicit-window-class
   middle-removal cases, especially cases that require manual move planning or
   dynamic visibility changes rather than pure reflow.
2. Extend `ccb agent move` beyond the bounded single-agent cycle: Codex and
   Claude opt-in real-provider movement are proven, and shared-source
   single-agent movement is proven with fake providers; the low-level kernel
   and user-facing command now move multiple source-window agents in one
   transaction, including newly materialized target windows and emptied source
   window removal. Batch `--window-class` placement is now proven for
   capacity-based split targets, and batch execution-node placement is proven
   for `--loop-id/--node-id`; next evaluate transactions that mix moved panes
   with newly created agents in one target.
3. Extend the shrink/release proof from single-agent and batch fake-provider
   source-wrapper/CI smokes to opt-in real-provider tolerance where useful.
4. Define the minimum `ccb loop`, `ccb plan`, and `ccb question` command
   surface for creating tasks, transitioning phases, recording artifacts,
   blocking, finishing, and syncing to plan-tree.
5. Continue the V1 `ccb loop capacity` path selected in
   [goals/orchestrator-dynamic-capacity-goal.md](goals/orchestrator-dynamic-capacity-goal.md):
   run the guarded real-provider semantic smoke for
   `agentroles.ccb_orchestrator` when real provider usage is intentionally
   allowed; daemon-side transient capacity ownership remains deferred.
6. Define the v1 team spec format for planner group, orchestrator, execution
   node, recovery node, and monitor behavior.
7. Define context-purity budgets for each role, including what may enter
   `frontdesk`, planner group, orchestrator, execution nodes, monitor, runtime
   artifacts, and long-term plan-tree.
8. Define the v1 clarification command surface and artifact schema for
   candidate questions, broker review, user display, raw answers, normalized
   answers, deferred questions, and planner wakeup.
9. Define the v1 execution-node and round-verification artifact schemas,
   including node check plans, non-convergence reports, branch freeze records,
   partial loop reports, verification contracts, and round verification plans.
10. Map the design to existing CCB communication primitives: `ask`,
   `--callback`, `--silence`, message bureau records, dispatcher jobs,
   completion state, and queue/trace diagnostics.
11. Identify the first implementation slice that can run with one planner, one
   orchestrator, one execution node, and deterministic monitoring before
   enabling dynamic multi-node fanout.

## V1 Readiness Blockers

1. The authoritative state writer must be scripted before multiple agents are
   allowed to chain transitions.
2. Ready task to execution round binding must have per-task lock/lease
   protection and idempotent round-result import.
3. The full loop runner must have bounded termination and escalation
   conditions before multi-round dynamic execution nodes are enabled.
4. The inner monitor must be split into deterministic health checks and
   optional semantic assessment before it can be trusted to escalate reliably.
5. The plan-tree synchronization policy must prevent high-frequency loop noise
   from entering committed Markdown.
6. The ask/callback handoff contract must define how a child result advances
   loop state without being mistaken for new upstream work.
7. The execution state model must distinguish node status, branch status, and
   round status before parallel node execution is enabled.
8. Dynamic window/pane placement must be tracked in runtime state before CCB
   can safely load many visible dialog, planning, and execution agents without
   cluttering or losing panes.

## Deferred

- Fully dynamic multi-node execution fanout.
- Full multi-round loop-runner-mediated dynamic agent load/unload beyond the
  bounded `run-once` smoke.
- Long-running loop runner daemon.
- Automatic planner activation and clarification routing before the one-shot
  runner bridge is proven.
- User-defined arbitrary window classes and interactive drag/drop layout.
- Exact tmux geometry restoration across restarts.
- Multi-orchestrator arbitration.
- Autonomous release publication.
- Automatic destructive cleanup or broad repair.
- UI-rich Team Builder editor for authoring workflow specs.
- Cross-project reusable workflow marketplace.
