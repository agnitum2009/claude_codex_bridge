# CCB Mobile App

This is the Flutter source for the CCB Mobile controller.

Current status:

- Android Alpha app published with CCB v8.0.3;
- server-wide real-project discovery through the CCB mobile gateway;
- pane-native text input and native transcript rendering for selected agents;
- terminal view, route diagnostics, notifications, and lifecycle actions;
- image/document upload and download through authenticated gateway routes.

The Android and iOS platform folders were generated with `flutter create` after
the local Flutter/Android toolchain became available.

Useful first commands once Flutter is installed:

```bash
cd app
flutter create .
flutter test
flutter run -d <android-emulator-id>
```

Current workspace toolchain snapshot:

- Flutter 3.44.2 / Dart 3.12.2:
  `/home/bfly/.local/share/flutter-sdks/3.44.2/flutter/bin/flutter`
- JDK 17: `/home/bfly/.local/share/jdks/temurin-17.0.19+10`
- Android SDK: `/home/bfly/.local/share/android-sdk`

The generated Android/iOS platform folders are now present. The current
validated commands are:

```bash
cd app
/home/bfly/.local/share/flutter-sdks/3.44.2/flutter/bin/flutter analyze
/home/bfly/.local/share/flutter-sdks/3.44.2/flutter/bin/flutter test
/home/bfly/.local/share/flutter-sdks/3.44.2/flutter/bin/flutter build apk --release
```

Release APK output:

```text
build/app/outputs/flutter-apk/app-release.apk
```

The Android app icon source is kept at
[`assets/brand/ccb-mobile-icon-1024.png`](assets/brand/ccb-mobile-icon-1024.png).
