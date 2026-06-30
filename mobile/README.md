# CCB Mobile

Native Android/iOS/iPadOS remote controller for server-side CCB tmux projects.

This project is intentionally separate from `ccb_source`. CCB and provider
CLIs run on the server; the mobile app is a controller for project discovery,
agent switching, terminal access, Markdown reading, notifications, and
Cloudflare Tunnel based remote access.

## Current Plan

- [Mobile tmux control plan](docs/plantree/plans/mobile-tmux-control/README.md)
- [Remote access roadmap](docs/plantree/plans/mobile-tmux-control/topics/remote-access-roadmap.md)
- [Native Flutter blueprint](docs/plantree/plans/mobile-tmux-control/topics/native-flutter-ccb-blueprint.md)

## Project Layout

Planned shape:

```text
app/                 Flutter mobile app, once created or forked
docs/plantree/       Planning tree and design decisions
.ccb/                CCB project config/runtime anchor
```

The first development target is an Android emulator vertical slice. iOS/iPadOS
will require macOS/Xcode or real-device validation later.
