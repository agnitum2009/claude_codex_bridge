# Implementation Status

Date: 2026-06-16

## Current Phase

Main-agent execution of the first interactive-latency slice. The first real
lifecycle profile is recorded; broad optimization still waits on narrower
attribution, but the current working-tree slice now targets click-to-focus
latency without expanding the Rust/helper scope.

Worker1 profiling harness returned and main review found/fixed two blockers:
default `ccb_test` invocation now uses project cwd instead of invalid
`--project ... start`, and process classification is project-scoped so other
running CCB daemons do not pollute the target project's CCB core buckets.

Worker2 startup slice returned with an artifact/worktree mismatch: the reported
tmux prepare cache and tests were not present. Main implemented the low-risk
cache directly: detached tmux server preparation is skipped only for the same
socket identity and same environment fingerprint, and failed prepare attempts
are not cached.

Worker3 interactive slice returned with an artifact/worktree mismatch and large
project_view/Rust-helper changes that are not accepted as part of this plan.
Main implemented only the narrow focus fast path in project_focus: after cache
invalidation, focus requests queue sidebar refresh through project_view when
available and fall back to the old synchronous sidebar refresh if the request
path is unavailable or fails.

Main review also found a blocker in the current worker3 project_view dirty
state: pending sidebar refresh called an undefined
`_record_project_view_sidebar_refresh`. Main fixed only that blocking path by
adding the metrics helper, declaring the metrics fields, removing duplicate
success recording, and covering `request_sidebar_refresh()` followed by
`build_response()`.

Interactive latency slice: `ccb __sidebar-click` now prefers a single
`project_sidebar_click` daemon RPC. The daemon resolves the current sidebar row
from the project_view payload and focuses the target in the same request,
preserving the previous `project_view` plus `project_focus_*` fallback for older
daemons that return `unknown op`. A focused dev probe,
`dev_tools/perf_sidebar_click_latency.py`, measures the single-RPC path against
an existing daemon socket when live UI timing evidence is needed.

## Active TODO

- Main: keep worker3's wider project_view/Rust-helper changes quarantined until
  they receive a separate review decision; do not bundle them with the accepted
  focus fast-path and pending-refresh fix unless explicitly selected.
- Main: measure the remaining click-to-focus delay after the single-RPC slice;
  if latency is still noticeable, inspect tmux select-pane/window cost and the
  foreground border/status hook path next.
- Main: design the high-load optimization around persistent or batched ask
  submission; current corrected profile shows one Python `ccb ask` process per
  submission is the largest high-load CPU owner.
- Main: design startup optimization around provider mount policy; current
  corrected profile shows provider launch dominates startup CPU.
- Next workload pass: run a mixed-provider matrix for Codex, Gemini, Claude,
  OpenCode mounted-idle, and active asks.

## Blockers

- Current high-load sample primarily targeted Codex; Claude/OpenCode/Gemini
  active-load shares still need a controlled mixed-provider matrix.
- The current worktree still contains unrelated and unaccepted dirty changes,
  including project_view/Rust-helper work from worker3; commit packaging must be
  path-scoped.

## Last Landed

- `af2818d Add runtime performance profiling and latency fast paths`: lifecycle
  profiling harness, detached tmux prepare cache, project_focus fast path,
  pending sidebar-refresh support, tests, and plan evidence.
- `4347082 Optimize project view recent job scans`: pure Python adaptive
  ProjectView recent-job scanning through `JobStore.list_project_view_recent_jobs`,
  preserving the old per-agent maximum scan limit while reducing common-case
  initial reads.

## Next Commit Target

Do not land the remaining Rust/helper and tmux parser slices in the next
performance commit. They stay quarantined until they show lifecycle-level
benefit over the Python paths and pass a fresh scoped review, staged-tree tests,
and source-runtime smoke.

Next optimization target is refined attribution of the `shell-system` bucket
into tmux server work, ask CLI process creation, shell wrappers, terminal
frontend, and unrelated system/UI work. First pass completed in
`history/shell-system-bucket-split-2026-06-16.md`; next implementation slice
should target high-load `ask-cli-subprocess` overhead before tmux CPU work.

Current working-tree interactive slice is path-scoped to sidebar click routing:
`dev_tools/perf_sidebar_click_latency.py`, `lib/sidebar_click_targets.py`,
`lib/cli/sidebar_click.py`, `lib/ccbd/handlers/project_focus.py`,
`lib/ccbd/app_runtime/handlers.py`, `lib/ccbd/socket_client_runtime/endpoints.py`,
and focused tests. It should not be bundled with Rust/helper residual work.
Per user decision, this slice may be committed locally on the current branch,
but it must not be merged to main or included in binary/release packaging until
live latency data justifies promotion and the user explicitly approves that
promotion.

## Last Verified

- Source runtime profile artifact:
  `/tmp/perf_realtarget/real_provider_cpu_profile_accurate3.json`
- Worker1 harness review:
  `python -m pytest -q test/test_perf_runtime_lifecycle_profile.py`
  passed with `11 passed`.
- Worker1 smoke checks from `/home/bfly/yunwei/test_ccb2`:
  `/tmp/ccb_runtime_profile_startup_diagnose_scoped.json` and
  `/tmp/ccb_runtime_profile_load_sleep_scoped.json`.
- Worker2/main tmux prepare cache review:
  `PYTHONPATH=lib python -m pytest -q
  test/test_cli_runtime_launch_tmux_panes.py test/test_v2_runtime_launch.py -q`
  passed.
- Main focus fast-path review:
  `PYTHONPATH=lib python -m pytest -q
  test/test_ccbd_project_focus.py test/test_sidebar_click.py` passed with
  `15 passed`.
- Combined targeted regression:
  `PYTHONPATH=lib python -m pytest -q
  test/test_perf_runtime_lifecycle_profile.py
  test/test_cli_runtime_launch_tmux_panes.py test/test_v2_runtime_launch.py
  test/test_ccbd_project_focus.py test/test_sidebar_click.py` passed with
  `117 passed`.
- Project_view dirty-state regression:
  `PYTHONPATH=lib python -m pytest -q
  test/test_ccbd_project_view.py test/test_ccbd_service_graph.py` passed with
  `65 passed`; this verifies current consistency but does not accept worker3's
  mismatched project_view/Rust-helper slice.
- Project_view pending-refresh blocker fix:
  `PYTHONPATH=lib python -m pytest -q
  test/test_ccbd_project_focus.py test/test_sidebar_click.py
  test/test_ccbd_project_view.py test/test_ccbd_service_graph.py` passed with
  `81 passed`.
- Final targeted regression:
  `PYTHONPATH=lib python -m pytest -q
  test/test_perf_runtime_lifecycle_profile.py
  test/test_cli_runtime_launch_tmux_panes.py test/test_v2_runtime_launch.py
  test/test_ccbd_project_focus.py test/test_sidebar_click.py
  test/test_ccbd_project_view.py test/test_ccbd_service_graph.py` passed with
  `183 passed`.
- Sidebar single-RPC working-tree slice:
  `PYTHONPATH=lib python -m pytest -q test/test_sidebar_click.py
  test/test_ccbd_socket_client.py test/test_ccbd_service_graph.py` passed with
  `27 passed`; `python -m py_compile
  dev_tools/perf_sidebar_click_latency.py` passed; `git diff --check` passed
  for the touched sidebar/RPC/test/plan paths.
- Source wrapper smoke after runtime helper change:
  `/home/bfly/yunwei/ccb_source/ccb_test --diagnose` and
  `ccb_test config validate` passed from `/home/bfly/yunwei/test_ccb2`.
- Shell/system bucket split:
  `PYTHONPATH=lib python -m pytest -q test/test_perf_runtime_lifecycle_profile.py`
  passed with `12 passed`; `python -m py_compile
  dev_tools/perf_runtime_lifecycle_profile.py
  test/test_perf_runtime_lifecycle_profile.py` passed.
  High-load artifact: `/tmp/ccb_runtime_shellsplit_profile_v2.json`.
  Startup artifact: `/tmp/ccb_runtime_shellsplit_startup_profile.json`.
- Worker report artifact:
  `.ccb/ccbd/artifacts/text/completion-reply/job_21a7c0c0b62a-art_19c8d2c809734472.txt`
- Rust helper benchmark evidence remains in
  `dev_tools/perf_results/python_rust_phase3_native_output_helper.json`,
  `python_rust_phase4_storage_scan_helper.json`, and
  `python_rust_phase12_storage_summary_helper.json`.

## Dispatch Notes

- Workers must not commit, push, reset, checkout, or delete unrelated dirty
  worktree changes.
- Reviewer agents are not part of this task; `reviewer1` dispatch
  `job_1d22628e6e26` was cancelled at the user's request.
- Source runtime validation must run from `/home/bfly/yunwei/test_ccb2` with
  `/home/bfly/yunwei/ccb_source/ccb_test` and isolated `HOME` /
  `CCB_SOURCE_HOME`.
- Each worker reply must include changed files, commands/tests run, measured
  before/after values when available, residual risk, and rollback notes.
