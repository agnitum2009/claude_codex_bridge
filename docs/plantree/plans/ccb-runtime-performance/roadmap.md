# Roadmap

Date: 2026-06-16

## Done

- Captured a real lifecycle CPU profile from an isolated source runtime under
  `/home/bfly/yunwei/test_ccb2` using `/home/bfly/yunwei/ccb_source/ccb_test`.
  Evidence:
  [history/real-lifecycle-cpu-profile-2026-06-16.md](history/real-lifecycle-cpu-profile-2026-06-16.md).
- Confirmed the currently landed Rust helpers improve local paths but do not
  explain the dominant lifecycle CPU share in the sampled workload.
- Established the current optimization priority: shell/tmux/subprocess
  orchestration first, then provider lifecycle policy, then CCB core only if it
  remains above the agreed threshold after those reductions.
- Added a repeatable lifecycle profiling harness and reviewed it for
  source-runtime-safe invocation and project-scoped process attribution.
- Added a low-risk detached tmux prepare cache keyed by socket identity and
  environment fingerprint.
- Added a narrow project_focus fast path that queues sidebar refresh through
  project_view when available, while preserving synchronous refresh fallback.
- Fixed the pending sidebar-refresh crash exposed by that fast path by adding
  the missing project_view refresh metrics helper and regression coverage.
- Split the previous `shell-system` bucket with corrected project-scoped
  profiling. Evidence:
  [history/shell-system-bucket-split-2026-06-16.md](history/shell-system-bucket-split-2026-06-16.md).
  High-load submission CPU is dominated by `ask-cli-subprocess`; startup CPU is
  dominated by provider launch/mount, not tmux server work.
- Added a working-tree interactive-latency slice for sidebar clicks:
  `ccb __sidebar-click` can now focus through one daemon RPC
  (`project_sidebar_click`) instead of a CLI-side `project_view` request
  followed by a second focus request, with old-daemon fallback preserved.
- Added `dev_tools/perf_sidebar_click_latency.py` as a focused single-RPC
  latency probe for live daemon socket measurements.

## In Progress

- Main-agent review of remaining interactive latency after the sidebar
  single-RPC slice. The slice is allowed as a local current-branch commit only;
  it must not be merged to main or included in binary/release packaging until
  live latency data justifies promotion and the user explicitly approves it.
- Main-agent review of the highest CPU paths identified by corrected profiling:
  persistent/batched ask submission for high-load operation and lazy or
  policy-controlled provider mounting for startup.

## Next

1. Design a low-risk persistent or batched ask submission path that avoids one
   Python process per `ccb ask` while preserving current CLI semantics.
2. Design startup provider-mount policy knobs so non-target providers can be
   deferred without breaking configured-agent supervision.
3. Add a repeatable startup profile gate with wall time, cumulative CPU, peak
   process count, and provider mount timing.
4. Add a high-load profile matrix by provider mix: Codex-only, Gemini-only,
   mixed mounted-idle, and mixed active.
5. Run the interactive latency probe on a live test daemon, then decide whether
   tmux focus commands or foreground border/status hooks are the next
   visible-latency owner.
6. Promote the highest-ROI implementation slice only after the refined profile
   shows a clear owner and acceptance threshold.

## Deferred

- Full CCB core rewrite or broad Rust migration.
- Provider CLI internal optimization.
- Default-enabling opt-in Rust storage summary without broader fixture evidence.
