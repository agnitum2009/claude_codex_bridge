# Roadmap

Date: 2026-06-23

## Done

- Identified the idle pressure classes from live local diagnosis:
  daemon heartbeat writes, agent runtime/helper rewrite amplification, provider
  bridge/CLI residency, provider SQLite/session writes, and shared-cache disk
  footprint.
- Separated "space at rest" problems from "continuous write" problems so the
  first implementation slice can target SSD wear and idle churn.
- Identified that the `v7.6.14` Codex `logs_2.sqlite` mitigation was partial:
  the trigger-only policy did not move writes off durable storage and preserved
  some diagnostic rows, so it could still leave measurable write pressure.
- Implemented and corrected the Codex diagnostic SQLite policy in the working
  tree: managed `logs_2.sqlite` redirects to temp storage, existing DB/sidecars
  are backed up, CCB no longer pre-creates Codex-owned SQLite schema, trigger
  installation waits until Codex migration creates `logs`, diagnostics mode can
  restore the original DB, and symlink failure falls back to an in-place trigger.
- Added self-healing for temp DBs created by the bad intermediate policy:
  a symlink target with `logs` but no successful Codex migration record is moved
  aside so Codex can recreate it through its own migration path.
- Verified the corrected policy with `PYTHONPATH=lib pytest -q
  test/test_codex_diagnostic_log_filter.py
  test/test_codex_launcher_diagnostics_env.py test/test_v2_runtime_launch.py`
  plus `python -m compileall -q
  lib/provider_backends/codex/launcher_runtime/command_runtime/diagnostics.py
  lib/provider_backends/codex/launcher_runtime/command_runtime/home.py` and
  `git diff --check`.
- Source runtime smoke under
  `/home/bfly/yunwei/test_ccb2/codex-log-migration-smoke-20260623` passed:
  `/home/bfly/yunwei/ccb_source/ccb_test config validate`, `ccb_test -s`, and
  `ccb_test doctor` mounted one Codex agent without `table logs already exists`;
  `logs_2.sqlite` pointed to temp storage, Codex migration records existed, the
  CCB insert-block trigger was installed, and `ccb_test kill -f` stopped the
  smoke runtime.
- Confirmed `state_5.sqlite*` was not a release-blocking idle pressure path in
  local sampling; keep it under measurement rather than adding a speculative
  mitigation now.

## In Progress

- Shape worker-guided execution for the remaining idle resource phases.

## Next

1. Use [topics/worker-execution-goal.md](topics/worker-execution-goal.md) as
   the worker contract for phased landing, tests, source runtime validation, and
   plan-tree evidence updates.
2. Add an ask-stability gate for every idle optimization:
   plain ask submit, queued ask, callback continuation, reply delivery, cancel,
   resubmit, and first ask after idle or suspend.
3. Add measurement hooks for idle write bytes, runtime-store save count, helper
   manifest save count, provider process RSS, and provider idle age.
4. Add content-equality and debounce guards around JSON runtime writes:
   `runtime.json`, `helper.json`, lifecycle records, and lease heartbeat.
5. Introduce idle-mode heartbeat pacing:
   active interval, idle interval, deep-idle interval, and immediate wake on
   incoming socket requests.
6. Move rebuildable runtime residue toward tmpfs:
   provider-runtime, FIFOs, bridge scratch state, activity snapshots, and
   transient pid/socket markers.
7. Add provider idle suspend/resume for mounted-but-unused agents, starting with
   an opt-in Codex policy.
8. Add cleanup/compaction for provider-state:
   WAL checkpoint, session JSONL size policy, old cache pruning, and shared
   cache retention limits.

## Deferred

- Default provider suspend for every provider type before Codex behavior is
  proven.
- Rewriting provider session storage.
- Removing persistent sessions or auth material.
- Moving durable auth/session authority to tmpfs.

## Acceptance Criteria

- With 10 mounted idle Codex agents, idle daemon+provider write rate drops by at
  least 90% compared with the baseline sample.
- Idle provider RSS drops materially when suspend is enabled, without losing
  the ability to route a later ask.
- First ask after idle either starts immediately or reports a clear "waking"
  state, then proceeds without manual intervention.
- `ccb kill`, `ccb -n`, project restart, and callback continuation retain their
  current semantics.
- `ask` remains stable across idle policies:
  plain ask accepts quickly, queued ask remains ordered, callback continuation is
  delivered once, `--silence` does not require a reply, and reply delivery does
  not loop or disappear.
- Runtime files still provide enough evidence for diagnostics after a crash.
