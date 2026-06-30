import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../../app/runtime_mode.dart';
import '../../models/ccb_project_lifecycle.dart';
import '../../models/ccb_project_view.dart';
import '../../pairing/gateway_pairing.dart';
import '../../transport/gateway_route_diagnostics.dart';
import 'connection_details.dart';
import 'project_home_update_panel.dart';

class ProjectHomeConnectionDetailsPanelHost extends StatelessWidget {
  const ProjectHomeConnectionDetailsPanelHost({
    required this.view,
    required this.mode,
    required this.profiles,
    required this.selectedProfile,
    required this.routeDiagnostics,
    required this.lifecycleResultListenable,
    required this.loadingProfiles,
    required this.checkingRoute,
    required this.runningLifecycleActionListenable,
    required this.onModeChanged,
    required this.onProfileSelected,
    required this.onCheckRoute,
    required this.onLifecycleAction,
    super.key,
  });

  final CcbProjectView view;
  final AppRuntimeMode mode;
  final List<GatewayPairedHost> profiles;
  final GatewayPairedHost? selectedProfile;
  final GatewayRouteDiagnosticReport? routeDiagnostics;
  final ValueListenable<CcbProjectLifecycleResult?> lifecycleResultListenable;
  final bool loadingProfiles;
  final bool checkingRoute;
  final ValueListenable<CcbLifecycleAction?> runningLifecycleActionListenable;
  final ValueChanged<AppRuntimeMode> onModeChanged;
  final ValueChanged<GatewayPairedHost> onProfileSelected;
  final VoidCallback onCheckRoute;
  final ValueChanged<CcbLifecycleAction> onLifecycleAction;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        ConnectionDetailsPanel(
          view: view,
          mode: mode,
          profiles: profiles,
          selectedProfile: selectedProfile,
          routeDiagnostics: routeDiagnostics,
          lifecycleResultListenable: lifecycleResultListenable,
          loadingProfiles: loadingProfiles,
          checkingRoute: checkingRoute,
          runningLifecycleActionListenable: runningLifecycleActionListenable,
          initiallyExpanded: true,
          onModeChanged: onModeChanged,
          onProfileSelected: onProfileSelected,
          onCheckRoute: onCheckRoute,
          onLifecycleAction: onLifecycleAction,
        ),
        const SizedBox(height: 12),
        const ProjectHomeUpdatePanel(),
      ],
    );
  }
}
