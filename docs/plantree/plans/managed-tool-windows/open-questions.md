# Managed Tool Windows Open Questions

Date: 2026-05-30

## Questions

- Should the first command contract be a single shell command string only, or
  should it also support an argv array before the feature ships?
- When a tool command exits, should CCB leave the pane open, restart it, or show
  an exited marker until explicit reload/restart?
- Should command changes be blocked until a future explicit `tool restart`
  policy exists, or should they be treated as remove-and-add when the old tool
  pane is idle/exited?
- Which clipboard lane should be the standard fallback inside tmux when the OS
  clipboard helper is missing: Neovim OSC52, tmux `set-clipboard`, or explicit
  platform helper installation?
- Should browser-based Markdown preview be installed by default, or should the
  default stay with in-buffer Markdown rendering and make browser preview an
  optional capability-gated overlay?
- Should inline image rendering attempt automatically when terminal support is
  detected, or should it require an explicit command/keymap even when
  `snacks.image` reports support?
- Should CCB pin the managed Neovim profile plugin set with a CCB-owned lockfile
  to reduce LazyVim/plugin drift, or follow upstream LazyVim/lazy.nvim stable
  behavior and rely on doctor/repair when drift breaks the profile?
- On WSL, should external file/URL opening prefer `wslview`, Windows interop
  tools such as `explorer.exe`, or Linux desktop tools when more than one is
  present?
