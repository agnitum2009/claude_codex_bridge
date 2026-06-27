# CCB Mobile

Native Android/iOS/iPadOS remote controller for server-side CCB tmux projects.

This is the mobile app source inside the CCB monorepo. CCB and provider CLIs
run on the server; the mobile app is a controller for project discovery, agent
switching, terminal access, Markdown reading, notifications, local/Tailnet
gateway access, and file transfer.

## Android Alpha Release

CCB Mobile v8.0.0 is published as an Android APK:

- [Download ccb-mobile-v8.0.0.apk](https://github.com/SeemSeam/claude_codex_bridge/releases/download/v8.0.0/ccb-mobile-v8.0.0.apk)
- Server setup entrypoint: `ccb update mobile`
- App source: [`app/`](app/)

The app is designed for real server-side CCB projects, not a demo-only flow.
It connects to the server-wide mobile gateway, lists mounted CCB projects,
renders agent transcripts, sends pane-native text input, opens terminal views,
and supports image/document upload and download through the authenticated
gateway.

## Plan Tree

- [Mobile tmux control plan](docs/plantree/plans/mobile-tmux-control/README.md)
- [Remote access roadmap](docs/plantree/plans/mobile-tmux-control/topics/remote-access-roadmap.md)
- [Native Flutter blueprint](docs/plantree/plans/mobile-tmux-control/topics/native-flutter-ccb-blueprint.md)

## Project Layout

```text
app/                 Flutter mobile app
docs/plantree/       Planning tree and design decisions
tools/               Emulator, gateway, and acceptance helpers
```

iOS/iPadOS remain source-supported targets, but v8.0.0 release validation is
Android-focused.
