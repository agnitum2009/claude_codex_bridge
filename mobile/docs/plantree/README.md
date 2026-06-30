# CCB Mobile Plan Tree

Date: 2026-06-27

## Purpose

This is the planning entrypoint for the standalone CCB mobile project.

## Authority Order

1. Active decisions under `docs/plantree/plans/mobile-tmux-control/decisions/`.
2. The mobile roadmap and execution plan under
   `docs/plantree/plans/mobile-tmux-control/`.
3. Baseline notes under `docs/plantree/baseline/`.
4. External CCB source contracts in `/home/bfly/yunwei/ccb_source/docs/` when
   server-side CCB behavior is relevant.

## Baseline

- [baseline/README.md](baseline/README.md)

## Active Plans

| Plan | Status | Current Phase | Last Landed | Next Target |
| :--- | :--- | :--- | :--- | :--- |
| [mobile-tmux-control](plans/mobile-tmux-control/README.md) | In Progress | Phase 4F Pane Live-Output Smoothness | 2026-06-29 real server-wide `test_ccb2` AVD evidence proves active-send `Working` p50 `138 ms`, `/status` marker visibility in `562 ms`, scroll-away explicit-refresh `New messages`, 180-second idle request count `0`, adb-reverse recovery timing, and a 40-line long-output shape smoke. | Continue [low-latency conversation goal](plans/mobile-tmux-control/goal-low-latency-conversation.md): extend strict real Android Emulator evidence to long-duration/high-volume output, live-turn reconciliation, and broader device health metrics. |

## How To Read

Start with the active plan root, then read roadmap, decisions, and the
specific topic file for the current task.
