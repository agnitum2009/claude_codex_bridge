# Incident Analysis

Role: context
Status: active
Read when: diagnosing callback loops, mixed Claude/Codex chains, or bad second callback edges
Related: [../roadmap.md](../roadmap.md), [runtime guard contract](runtime-guard-and-prompt-contract.md)

Date: 2026-06-22

## Failure Shape

The failure requires at least one callback continuation:

```text
A asks B with callback
B asks C with callback
C finishes
CCB sends callback_continuation to B
B should finish current turn so CCB can return to A
B instead asks A with callback
```

The last step is the bug. It creates a new callback edge where the intended
operation is finalization of the existing edge.

## Observed Provider Difference

Codex-only chains are less likely to misroute because the Codex backend starts
active submissions as `PROTOCOL_EVENT_STREAM` and sends the wrapped prompt
directly into a bound protocol turn:

- [codex start runtime](../../../../../lib/provider_backends/codex/execution_runtime/start.py)

Claude-involved chains are more fragile because the Claude backend runs through
an interactive Claude Code session event log. It stores prompt text and dispatches
later when the pane is ready:

- [claude start runtime](../../../../../lib/provider_backends/claude/execution_runtime/start.py)
- [claude deferred prompt dispatch](../../../../../lib/provider_backends/claude/execution_runtime/polling.py)

That interaction model means Claude sees the continuation as ordinary task text
inside a tool-capable session. If the text says "reply to original caller",
Claude can satisfy that by running `ask --callback` instead of producing the
current turn's final answer.

## Runtime Acceptance Gap

The current callback validation path accepts callback requests when:

- the route is callback mode;
- there is message bureau support;
- delivery is single target;
- the sender has an active parent job;
- the parent message resolves;
- the parent has no existing outstanding callback;
- the callback chain depth/cycle check passes.

The missing check is specific to continuation jobs: a
`callback_continuation` parent should not open a new callback to the upstream
caller as a way to deliver the final result.

Relevant source:

- [callback validation and continuation generation](../../../../../lib/ccbd/services/dispatcher_runtime/callbacks.py)
  (`validate_callback_request`, `_continuation_request`, and
  `_continuation_body`).
- [callback edge record storage](../../../../../lib/message_bureau/callback_edges.py)
  (`CallbackEdgeRecord.original_caller`).

## Prompt Ambiguity

The continuation body currently includes original task context, child task,
child result, and the final instruction to continue the original task and reply
to the original caller.

That is correct at the product level but ambiguous at the agent-command level.
For tool-capable providers, "reply to original caller" must be rephrased as:

```text
Finish this current turn with the final result. Do not call ask, --callback, or
--silence to the original caller; CCB will deliver this continuation result.
```

## Working Conclusion

This is not an `archi` auto-reply bug. The child reply is the expected trigger
for the continuation. The safety issue is that the continuation receiver can
turn finalization into a new upstream callback, and the runtime currently
permits that edge.
