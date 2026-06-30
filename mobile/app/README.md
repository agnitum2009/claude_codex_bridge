# CCB Mobile App

This is the Flutter source baseline for the CCB Mobile controller.

Current status:

- permissive/minimal baseline while AGPL app-source reuse is undecided;
- fake CCB repository and `project_view` fixtures first;
- socket-aware tmux command builder before live terminal networking;
- no ServerBox or Paseo source copied into this tree.

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
/home/bfly/.local/share/flutter-sdks/3.44.2/flutter/bin/flutter build apk --debug
```
