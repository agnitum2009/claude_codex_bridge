# Open Questions

Date: 2026-06-02

## Questions

1. Should the first release include a generated JSON schema, or only a
   human-readable metadata convention plus validation checklist?
   - A schema improves credibility.
   - A checklist avoids premature field lock-in.

2. How much Claude Code and Codex behavior should be described in v0.1 adapter
   docs?
   - Need enough to prove compatibility direction.
   - Avoid promising exact runtime behavior before implementation.

3. Should the v0.1 repository include a CLI skeleton?
   - A skeleton helps users see future direction.
   - It may distract from the spec-first release.

4. What is the right English wording for the Chinese "降临" concept?
   - `mount` is the stable technical verb.
   - "descend" can appear in marketing copy, but should not replace `mount` in
     specs or CLI naming.

## Resolved

- The first reference role should use `agentroles.archi` as its public role id;
  `ccb.archi` should not be the primary public identity.
