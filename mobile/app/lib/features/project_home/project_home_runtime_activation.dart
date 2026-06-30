import '../../models/ccb_project.dart';
import '../../models/ccb_project_view.dart';
import '../../pairing/gateway_pairing.dart';
import '../../repository/mobile_ccb_repository.dart';
import '../../transport/terminal_transport.dart';
import '../../transport/route_provider.dart';

const projectHomeRuntimeNoProfileSnack = 'Pair a gateway profile first';
const projectHomeRuntimeViewLoadTimeout = Duration(seconds: 10);

typedef ProjectHomeGatewayRepositoryFactory =
    MobileCcbRepository Function(GatewayPairedHost profile);

typedef ProjectHomeGatewayTerminalTransportFactory =
    TerminalTransport Function(GatewayPairedHost profile);

ProjectHomePairedRuntimeSelection selectProjectHomePairedRuntimeProfile({
  required List<GatewayPairedHost> profiles,
  required GatewayPairedHost? selectedProfile,
}) {
  final profile = selectedProfile ?? (profiles.isEmpty ? null : profiles.first);
  if (profile == null) {
    return const ProjectHomePairedRuntimeSelection.noProfile(
      snackMessage: projectHomeRuntimeNoProfileSnack,
    );
  }
  return ProjectHomePairedRuntimeSelection.activate(
    ProjectHomeGatewayActivationData.fromProfile(profile),
  );
}

ProjectHomeGatewayActivationData activateProjectHomeGatewayProfile(
  GatewayPairedHost profile,
) {
  return ProjectHomeGatewayActivationData.fromProfile(profile);
}

ProjectHomeFakeRuntimeResetData resetProjectHomeFakeRuntime({
  required String defaultProjectId,
}) {
  return ProjectHomeFakeRuntimeResetData(defaultProjectId: defaultProjectId);
}

class ProjectHomeRuntimeSessionCoordinator {
  const ProjectHomeRuntimeSessionCoordinator();

  ProjectHomeFakeRuntimeSession activateFake({
    required MobileCcbRepository repository,
    required String defaultProjectId,
    Duration viewLoadTimeout = projectHomeRuntimeViewLoadTimeout,
  }) {
    return ProjectHomeFakeRuntimeSession(
      repository: repository,
      activeProjectId: defaultProjectId,
      terminalTransport: null,
      viewFuture: repository
          .getProjectView(defaultProjectId)
          .timeout(viewLoadTimeout),
    );
  }

  ProjectHomeGatewayRuntimeSession activateGateway({
    required ProjectHomeGatewayActivationData activation,
    required ProjectHomeGatewayRepositoryFactory repositoryFactory,
    required ProjectHomeGatewayTerminalTransportFactory
    terminalTransportFactory,
    Duration projectListTimeout = projectHomeRuntimeViewLoadTimeout,
  }) {
    final profile = activation.profile;
    final repository = repositoryFactory(profile);
    return ProjectHomeGatewayRuntimeSession(
      activation: activation,
      repository: repository,
      preferredProjectId: activation.activeProjectId,
      terminalTransport: terminalTransportFactory(profile),
      projectsFuture: Future<List<CcbProject>>(
        () => repository.listProjects(),
      ).timeout(projectListTimeout),
    );
  }
}

enum ProjectHomePairedRuntimeSelectionKind { noProfile, activate }

class ProjectHomePairedRuntimeSelection {
  const ProjectHomePairedRuntimeSelection.noProfile({
    required String snackMessage,
  }) : this._(
         kind: ProjectHomePairedRuntimeSelectionKind.noProfile,
         snackMessage: snackMessage,
       );

  const ProjectHomePairedRuntimeSelection.activate(
    ProjectHomeGatewayActivationData activation,
  ) : this._(
        kind: ProjectHomePairedRuntimeSelectionKind.activate,
        activation: activation,
      );

  const ProjectHomePairedRuntimeSelection._({
    required this.kind,
    this.activation,
    this.snackMessage,
  });

  final ProjectHomePairedRuntimeSelectionKind kind;
  final ProjectHomeGatewayActivationData? activation;
  final String? snackMessage;
}

class ProjectHomeGatewayActivationData {
  const ProjectHomeGatewayActivationData({
    required this.profile,
    required this.gatewayUrlText,
    required this.routeKind,
    required this.activeProjectId,
  });

  factory ProjectHomeGatewayActivationData.fromProfile(
    GatewayPairedHost profile,
  ) {
    return ProjectHomeGatewayActivationData(
      profile: profile,
      gatewayUrlText: profile.profile.routeProvider.gatewayUrl.toString(),
      routeKind: profile.profile.routeProvider.kind,
      activeProjectId: profile.projectId ?? profile.profile.hostId,
    );
  }

  final GatewayPairedHost profile;
  final String gatewayUrlText;
  final RouteProviderKind routeKind;
  final String activeProjectId;
}

class ProjectHomeFakeRuntimeResetData {
  const ProjectHomeFakeRuntimeResetData({required this.defaultProjectId});

  final String defaultProjectId;
}

class ProjectHomeFakeRuntimeSession {
  const ProjectHomeFakeRuntimeSession({
    required this.repository,
    required this.activeProjectId,
    required this.terminalTransport,
    required this.viewFuture,
  });

  final MobileCcbRepository repository;
  final String activeProjectId;
  final TerminalTransport? terminalTransport;
  final Future<CcbProjectView> viewFuture;
}

class ProjectHomeGatewayRuntimeSession {
  const ProjectHomeGatewayRuntimeSession({
    required this.activation,
    required this.repository,
    required this.preferredProjectId,
    required this.terminalTransport,
    required this.projectsFuture,
  });

  final ProjectHomeGatewayActivationData activation;
  final MobileCcbRepository repository;
  final String preferredProjectId;
  final TerminalTransport terminalTransport;
  final Future<List<CcbProject>> projectsFuture;
}
