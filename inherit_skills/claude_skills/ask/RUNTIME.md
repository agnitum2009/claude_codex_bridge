# Async Ask

Use this only to submit a CCB ask request, then stop.

Choose the mode before running a command:

- Normal user turn or any context that is not a CCB-delivered active parent job:
  use plain `ask`.
- Do not probe `--callback`. If unsure, use plain `ask`.
- Use `--callback` only when this exact turn is an active CCB task and the child
  result is required before finishing that parent task.
- If CCB says `ask --callback requires an active parent job`, the mode choice was
  wrong. For a user-requested delegation, submit once with plain `ask` and stop.
- Use `--artifact-request` when the task body is large or must be passed by file.
- Use `--artifact-reply` when the caller or callback continuation should receive
  the target result as a text artifact path, even if the target replies inline.
- Use `--artifact-io` when both the request and reply should be artifact-backed.
- `--artifact-*` modes are CCB/daemon managed; they do not require the target
  agent to manually write a reply file.

Always send `MESSAGE` through the `<<'EOF' ... EOF` heredoc below. No other form
is allowed.

```bash
command ask "$TARGET" <<'EOF'
$MESSAGE
EOF
```

- Sender is inferred from the current CCB workspace.
- `TARGET=all` broadcasts.
- Use `--compact` for actively distilled replies.
- Use `--silence` for silent-on-success delivery.
- Use `--callback` only from inside an active parent task when the target result
  should return as a continuation task.
- For callback work with a large child result, combine `--callback` with
  `--artifact-reply`.
- Plain nested `ask` from an active CCB task is rejected; choose `--callback` for
  needed dependency results or `--silence` for independent no-result-needed work.
- `ask get`, `pend`, `watch`, and `ping` are diagnostics-only commands for explicit debugging requests, not normal ask workflow tools.
- After the command returns, immediately end the turn. Do not wait for a reply, do not run `ask get` / `pend` / `ping` / `watch`, do not poll.
- For `--callback`, report only that delegation was submitted; the final result
  belongs in the later continuation task.
