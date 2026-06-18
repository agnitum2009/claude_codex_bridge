# Integration Design

Date: 2026-06-13

## Provider Keys And Commands

| Provider key | Default command | Override env |
| :--- | :--- | :--- |
| `kimi` | `kimi` | `KIMI_START_CMD` |
| `deepseek` | `deepcode` | `DEEPSEEK_START_CMD` |
| `mimo` | `mimo` | `MIMO_START_CMD` |
| `qwen` | `qwen` | `QWEN_START_CMD` |
| `copilot` | `copilot` | `COPILOT_START_CMD` |
| `cursor` | `agent` | `CURSOR_START_CMD` |
| `kiro` | `kiro-cli` | `KIRO_START_CMD` |
| `crush` | `crush` | `CRUSH_START_CMD` |
| `pi` | `pi` | `PI_START_CMD` |

The `deepseek` provider key follows user intent and model family language; the
actual CLI command remains `deepcode` because that is the DeepSeek documented
terminal integration.

The `cursor` provider key follows product naming; the default executable is
`agent` because that is what the official Cursor Agent installer exposes.

## Runtime Model

These providers enter CCB as optional built-in managed providers:

- `kimi` and `deepseek` use `ProviderManifest` `SESSION_BOUNDARY`.
- `kimi` uses `CompletionSourceKind.SESSION_EVENT_LOG`.
- `deepseek` uses `CompletionSourceKind.SESSION_SNAPSHOT`.
- `mimo` uses `CompletionFamily.STRUCTURED_RESULT` and
  `CompletionSourceKind.STRUCTURED_RESULT_STREAM` for ask execution because
  terminalization comes from `mimo run --format json` result events.
- `ProviderRuntimeLauncher` uses `simple_tmux`.
- `ProviderSessionBinding` uses `.kimi-session`, `.deepseek-session`, and
  `.mimo-session`.
- Startup command supports `spec.startup_args`, `spec.env`, caller context env,
  and `provider_command_template`.
- Provider start-command override env vars such as `QWEN_START_CMD` and
  `KIRO_START_CMD` are control-plane inputs. They must be passed from the CLI
  process into ccbd so background startup and source-runtime smoke can use the
  same command authority as foreground launchers. Provider home/session authority
  remains isolated and must not be broadly passed through by prefix.

Next-wave runtime should split visible pane startup from ask execution:

- `qwen`, `copilot`, `cursor`, and `pi` use per-job subprocess execution with
  JSONL/stream-json parsing.
- `crush` and `kiro` use per-job subprocess execution with process exit plus
  stdout as the completion signal.
- Visible panes still use simple tmux launchers for user observation and
  runtime maintenance.
- Shared native CLI launchers may derive visible-pane arguments from prepared
  provider-state. Crush uses this to start visible panes with
  `--data-dir <provider-state>/data`, matching the state isolation used by
  `crush run`.
- Shared native CLI launchers may also derive visible-pane env vars from
  prepared provider-state. Pi uses this to set `PI_CODING_AGENT_DIR`,
  `PI_CODING_AGENT_SESSION_DIR`, `PI_SKIP_VERSION_CHECK`, and `PI_TELEMETRY`.
- Existing partial backend directories for `qwen` and `copilot` have been
  upgraded to modern backend shape before registration:
  `manifest.py`, `launcher.py`, `execution.py`, and tests.

## Completion Strategy

The current strategy uses provider-native session/event stores or structured
result streams:

1. Send a wrapped prompt to the managed provider pane.
2. The prompt contains `CCB_REQ_ID: <job_id>`.
3. Do not ask Kimi, DeepSeek/DeepCode, or AGY to print `CCB_DONE`.
4. Kimi polls `wire.jsonl`, binds the turn by `CCB_REQ_ID`, emits
   `ASSISTANT_FINAL` from `ContentPart`, and emits `TURN_BOUNDARY` on
   native `TurnEnd`.
5. DeepSeek polls DeepCode `sessions-index.json` and session jsonl, binds the
   user message by `CCB_REQ_ID`, emits `ASSISTANT_FINAL` from assistant
   messages, and emits `TURN_BOUNDARY` on native `status=completed`.
6. AGY polls Antigravity transcript logs, binds `USER_INPUT` by `CCB_REQ_ID`,
   emits `ASSISTANT_FINAL` from model response events, and emits
   `TURN_BOUNDARY` when a completed response is observed. AGY prompt delivery
   is ready-gated: CCB defers the prompt while the Antigravity pane is busy,
   sends only after an empty input prompt is observed, diagnoses native
   coalesced `CCB_REQ_ID` rows, and uses stable pane fallback only when
   transcript persistence lags.
7. MiMo asks run as native subprocesses using
   `mimo run --format json --dir <workdir>`. CCB emits `ASSISTANT_FINAL` from
   nested `part.text` events and emits `TURN_BOUNDARY` / terminal completed on
   `step_finish` with `part.reason=stop`.
8. Qwen asks parse `stream-json` or JSON output and terminalize from
   result/final assistant envelopes.
9. Cursor asks parse `agent --print --output-format stream-json` envelopes and
   terminalize from final result/completion events.
10. Copilot asks parse `--output-format json` JSONL in prompt mode and
   terminalize from the final prompt-mode result event.
11. Crush asks collect stdout from `crush run --quiet` and trust process exit;
   source evidence shows `crush run` itself exits only after a matching
   `RunComplete`.
12. Kiro asks initially collect stdout from `kiro-cli chat --no-interactive
   --wrap never` and treat process exit as completion until a stable structured
   chat event source is found.
13. Pi asks parse `pi --mode json` JSONL and terminalize from native
   `turn_end` events carrying assistant message content.
14. Completed-native-empty replies are `incomplete` with
   `empty_provider_reply` diagnostics, not `completed`.
15. Long-running native CLI subprocesses terminalize with explicit
   provider-specific timeout reasons such as `qwen_run_timeout` and terminate
   the child process group instead of waiting only for the outer reliability
   fallback.

## Skill And Instruction Injection

Provider onboarding must include a capability-projection check in addition to
native completion detection:

- If the provider exposes native skills, use that native surface.
- If the provider exposes only instruction files/config, inject CCB ask guidance
  through that instruction surface.
- Do not ask the model to rediscover `ask` usage from memory alone when a
  provider-native or provider-supported projection path exists.

Current behavior:

- Kimi gets inherited CCB ask skill content from
  `inherit_skills/kimi_skills/ask/SKILL.md`. Startup materializes a managed
  skills root under `.ccb/agents/<agent>/provider-state/kimi/inherited-skills`
  and passes it to Kimi with `--skills-dir`. Because Kimi treats any
  `--skills-dir` as replacement for default discovery, CCB first passes
  existing default Kimi project/user skill directories, then appends managed
  inherited and role skill roots.
- OpenCode does not expose a stable `--skills-dir` equivalent in the observed
  CLI help. CCB writes `.ccb/runtime/skills/<agent>/opencode/ask.md` and appends
  that path to generated `opencode.json.instructions` alongside the memory
  bridge.
- MiMo writes `.ccb/runtime/skills/<agent>/mimo/ask.md` and appends that path
  to generated `mimocode.json.instructions` alongside the memory bridge.
- Qwen should prefer native settings/instruction surfaces when confirmed;
  until then, inherited ask guidance can be injected through prompt wrapping
  while preserving `QWEN_HOME` isolation.
- Pi should prefer native skills/resources if CCB later projects richer ask
  guidance; first landing keeps prompt wrapping and isolates Pi global/session
  state with `PI_CODING_AGENT_DIR` and `PI_CODING_AGENT_SESSION_DIR`.
- Copilot should project inherited ask guidance through `--plugin-dir`, using
  plugin metadata compatible with Copilot's local plugin discovery.
- Cursor should project inherited ask guidance through repeatable
  `--plugin-dir` if the installed bundle accepts the same local plugin shape;
  otherwise use prompt wrapping in the first slice.
- Crush should use prompt wrapping first unless source validation confirms a
  stable skills/config path. `--data-dir` keeps any managed instructions inside
  provider state.
- Kiro should use prompt wrapping first because no stable skill/instruction
  projection surface has been confirmed for chat mode.
- `inherit_skills = false` disables inherited skill projection. For OpenCode,
  `inherit_memory = false` disables only the memory bridge; inherited ask
  instructions continue unless `inherit_skills = false` is also set.

## Config Boundary

Supported native-provider config:

```toml
[windows]
main = "kimi_agent:kimi, deep_agent:deepseek, mimo_agent:mimo"

[agents.kimi_agent]
provider = "kimi"

[agents.deep_agent]
provider = "deepseek"

[agents.mimo_agent]
provider = "mimo"
```

Next-wave provider config:

```toml
[windows]
main = "qwen1:qwen, cursor1:cursor, copilot1:copilot, crush1:crush, kiro1:kiro, pi1:pi"

[agents.qwen1]
provider = "qwen"

[agents.cursor1]
provider = "cursor"

[agents.copilot1]
provider = "copilot"

[agents.crush1]
provider = "crush"

[agents.kiro1]
provider = "kiro"

[agents.pi1]
provider = "pi"
```

Not supported in first slice:

- `key` / `url` shortcuts for Kimi or DeepSeek.
- `key` / `url` shortcuts for MiMo.
- `key` / `url` shortcuts for Qwen, Cursor, Copilot, Crush, or Kiro.
- Automatic writing of `~/.deepcode/settings.json`.
- Automatic Kimi login.
- Automatic credential acquisition for Qwen, Cursor, Copilot, Crush, or Kiro.

## Tests

Focused unit tests should cover:

- Optional provider registry includes `kimi`, `deepseek`, and `mimo`.
- Runtime specs include `.kimi-session`, `.deepseek-session`, and
  `.mimo-session`.
- Start command env overrides and default executables.
- Kimi startup includes existing default skill directories and materialized CCB
  skill directories as repeatable `--skills-dir` arguments, while skipping
  missing directories.
- OpenCode generated config preserves user instructions and appends memory and
  ask-skill instruction entries without duplication.
- MiMo generated config preserves user instructions and appends memory and
  ask-skill instruction entries without duplication.
- Session binding maps and runtime launcher maps include the native providers.
- Native readers parse Kimi `wire.jsonl`, DeepCode sessions, and AGY
  transcripts.
- MiMo execution parses `mimo run --format json` nested `part.text` and
  `part.reason=stop`.
- Provider adapters emit `SESSION_ROTATE`, `ANCHOR_SEEN`, `ASSISTANT_FINAL`,
  and `TURN_BOUNDARY` from native evidence.
- Provider adapters diagnose completed-native-empty replies and fail on missing
  runtime state.
- Config loader accepts agents using `provider = "kimi"` and
  `provider = "deepseek"` and `provider = "mimo"`.
- Optional provider registry includes `qwen`, `cursor`, `copilot`, `crush`,
  `kiro`, and `pi`.
- Existing partial `qwen` and `copilot` backend packages are migrated to
  modern manifest/launcher/execution contracts while old protocol helpers
  remain only for compatibility tests.
- Qwen parser handles `stream-json` assistant and result envelopes.
- Cursor parser handles `agent --print --output-format stream-json` envelopes.
- Copilot parser handles prompt-mode JSONL output.
- Crush execution treats nonzero exit as failure and zero exit/stdout as
  completion, with empty stdout producing an empty-reply diagnostic.
- Kiro execution treats nonzero exit as failure and zero exit/stdout as
  completion until a better native event source is confirmed.
- All six next-wave adapters report provider-specific run timeouts and
  terminate the subprocess when `CCB_<PROVIDER>_RUN_TIMEOUT_S` is exceeded.
- Crush visible pane launch includes `--data-dir <provider-state>/data`.
- Native CLI provider-state classification covers session/cache/projected skill
  evidence for Qwen, Cursor, Copilot, Crush, Kiro, and Pi.

Source-runtime validation should run from `/home/bfly/yunwei/test_ccb2` using
`/home/bfly/yunwei/ccb_source/ccb_test` and isolated source home. Real CLI
help/version checks validate installability; CCB ask completion can use
provider command templates that point to deterministic stub TUIs when API
credentials are unavailable.
