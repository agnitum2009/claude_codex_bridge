import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart' show ScrollDirection;

import '../../app/app_factories.dart';
import '../../app/app_theme.dart';
import '../../app/runtime_mode.dart';
import '../../debug/debug_profile_seed.dart';
import '../../l10n/ccb_mobile_localizations.dart';
import '../../models/ccb_agent.dart';
import '../../models/ccb_notification.dart';
import '../../models/ccb_project.dart';
import '../../models/ccb_project_lifecycle.dart';
import '../../models/ccb_project_view.dart';
import '../../notifications/task_completion_notifications.dart';
import '../../pairing/gateway_pairing.dart';
import '../../repository/mobile_ccb_repository.dart';
import '../../transport/gateway_route_diagnostics.dart';
import '../../transport/route_provider.dart';
import '../../transport/terminal_transport.dart';
import 'project_home_connection_details_panel_host.dart';
import 'project_home_focus_coordinator.dart';
import 'project_home_lifecycle_coordinator.dart';
import 'project_home_notification_target.dart';
import 'project_home_onboarding.dart';
import 'project_home_pairing_flow.dart';
import 'project_home_pairing_form_controller.dart';
import 'project_home_profile_bootstrapper.dart';
import 'project_home_profile_loading.dart';
import 'project_home_route_actions.dart';
import 'project_home_route_diagnostics.dart';
import 'project_home_runtime_activation.dart';
import 'project_home_scaffold_host.dart';
import 'project_home_shell_state.dart';
import 'project_home_task_completion_notifications.dart';
import 'project_home_terminal_navigation.dart';
import 'project_home_view_refresh.dart';
import 'project_shell_widgets.dart';

class ProjectHomeScreen extends StatelessWidget {
  const ProjectHomeScreen({
    required this.repository,
    this.profileStore,
    this.pairingClaimAndStore = defaultPairingClaimAndStore,
    this.pairingScanner = defaultPairingScanner,
    this.gatewayRepositoryFactory = defaultGatewayRepositoryFactory,
    this.gatewayTerminalTransportFactory =
        defaultGatewayTerminalTransportFactory,
    this.gatewayRouteDiagnostics = defaultGatewayRouteDiagnostics,
    this.showOnboardingWhenUnpaired = false,
    this.autoActivateStoredProfile = false,
    this.themePreference = CcbThemePreference.system,
    this.onThemePreferenceChanged,
    this.taskNotificationStreamClient,
    this.taskCompletionLocalNotifications,
    this.taskCompletionSeenStore,
    super.key,
  });

  final MobileCcbRepository repository;
  final GatewayHostProfileStore? profileStore;
  final GatewayPairingClaimAndStore pairingClaimAndStore;
  final GatewayPairingScanner pairingScanner;
  final GatewayRepositoryFactory gatewayRepositoryFactory;
  final GatewayTerminalTransportFactory gatewayTerminalTransportFactory;
  final GatewayRouteDiagnosticsFactory gatewayRouteDiagnostics;
  final bool showOnboardingWhenUnpaired;
  final bool autoActivateStoredProfile;
  final CcbThemePreference themePreference;
  final ValueChanged<CcbThemePreference>? onThemePreferenceChanged;
  final GatewayTaskCompletionNotificationStreamClient?
  taskNotificationStreamClient;
  final TaskCompletionLocalNotifications? taskCompletionLocalNotifications;
  final TaskCompletionSeenDedupeStore? taskCompletionSeenStore;

  @override
  Widget build(BuildContext context) {
    return _ProjectHomeView(
      repository: repository,
      profileStore: profileStore ?? GatewayHostProfileStore(),
      pairingClaimAndStore: pairingClaimAndStore,
      pairingScanner: pairingScanner,
      gatewayRepositoryFactory: gatewayRepositoryFactory,
      gatewayTerminalTransportFactory: gatewayTerminalTransportFactory,
      gatewayRouteDiagnostics: gatewayRouteDiagnostics,
      showOnboardingWhenUnpaired: showOnboardingWhenUnpaired,
      autoActivateStoredProfile: autoActivateStoredProfile,
      themePreference: themePreference,
      onThemePreferenceChanged: onThemePreferenceChanged,
      taskNotificationStreamClient: taskNotificationStreamClient,
      taskCompletionLocalNotifications: taskCompletionLocalNotifications,
      taskCompletionSeenStore: taskCompletionSeenStore,
    );
  }
}

class _ProjectHomeView extends StatefulWidget {
  const _ProjectHomeView({
    required this.repository,
    required this.profileStore,
    required this.pairingClaimAndStore,
    required this.pairingScanner,
    required this.gatewayRepositoryFactory,
    required this.gatewayTerminalTransportFactory,
    required this.gatewayRouteDiagnostics,
    required this.showOnboardingWhenUnpaired,
    required this.autoActivateStoredProfile,
    required this.themePreference,
    required this.onThemePreferenceChanged,
    required this.taskNotificationStreamClient,
    required this.taskCompletionLocalNotifications,
    required this.taskCompletionSeenStore,
  });

  final MobileCcbRepository repository;
  final GatewayHostProfileStore profileStore;
  final GatewayPairingClaimAndStore pairingClaimAndStore;
  final GatewayPairingScanner pairingScanner;
  final GatewayRepositoryFactory gatewayRepositoryFactory;
  final GatewayTerminalTransportFactory gatewayTerminalTransportFactory;
  final GatewayRouteDiagnosticsFactory gatewayRouteDiagnostics;
  final bool showOnboardingWhenUnpaired;
  final bool autoActivateStoredProfile;
  final CcbThemePreference themePreference;
  final ValueChanged<CcbThemePreference>? onThemePreferenceChanged;
  final GatewayTaskCompletionNotificationStreamClient?
  taskNotificationStreamClient;
  final TaskCompletionLocalNotifications? taskCompletionLocalNotifications;
  final TaskCompletionSeenDedupeStore? taskCompletionSeenStore;

  @override
  State<_ProjectHomeView> createState() => _ProjectHomeViewState();
}

class _ProjectHomeViewState extends State<_ProjectHomeView> {
  static const _defaultProjectId = 'proj-demo';

  final _pairingForm = ProjectHomePairingFormController();

  late MobileCcbRepository _activeRepository;
  late Future<CcbProjectView> _viewFuture;
  Future<List<CcbProject>>? _serverProjectsFuture;
  AppRuntimeMode _mode = AppRuntimeMode.fake;
  List<GatewayPairedHost> _profiles = const [];
  GatewayPairedHost? _selectedProfile;
  GatewayRouteDiagnosticReport? _routeDiagnostics;
  final _lifecycleResultNotifier = ValueNotifier<CcbProjectLifecycleResult?>(
    null,
  );
  String _activeProjectId = _defaultProjectId;
  String? _openedProjectId;
  String? _selectedAgentName;
  TerminalTransport? _terminalTransport;
  bool _loadingProfiles = false;
  bool _claimingPairing = false;
  bool _checkingRoute = false;
  bool _profilesInitialized = false;
  CcbLifecycleAction? _runningLifecycleAction;
  final _runningLifecycleActionNotifier = ValueNotifier<CcbLifecycleAction?>(
    null,
  );
  bool _showPairingSetup = false;
  WideSidebarState _wideSidebarState = WideSidebarState.expanded;
  WideSidebarState _wideSidebarDragStartState = WideSidebarState.expanded;
  double _wideSidebarDragDelta = 0;
  bool _mobileAgentsCollapsed = false;

  late final ProjectHomeProfileBootstrapper _profileBootstrapper =
      ProjectHomeProfileBootstrapper(store: widget.profileStore);
  late final ProjectHomeProfileLoadingCoordinator _profileLoadingCoordinator =
      ProjectHomeProfileLoadingCoordinator(bootstrapper: _profileBootstrapper);
  final _lifecycleCoordinator = const ProjectHomeLifecycleCoordinator();
  final _pairingFlowCoordinator = const ProjectHomePairingFlowCoordinator();
  final _routeDiagnosticsCoordinator =
      const ProjectHomeRouteDiagnosticsCoordinator();
  final _focusCoordinator = const ProjectHomeFocusCoordinator();
  final _runtimeSessionCoordinator =
      const ProjectHomeRuntimeSessionCoordinator();
  final _viewRefreshCoordinator = const ProjectHomeViewRefreshCoordinator();
  late final TaskCompletionNotificationController _taskNotifications;

  @override
  void initState() {
    super.initState();
    _taskNotifications = TaskCompletionNotificationController(
      streamClient:
          widget.taskNotificationStreamClient ??
          HttpGatewayTaskCompletionNotificationStreamClient(),
      localNotifications:
          widget.taskCompletionLocalNotifications ??
          MethodChannelTaskCompletionLocalNotifications(),
      seenStore:
          widget.taskCompletionSeenStore ?? TaskCompletionSeenDedupeStore(),
      onTap: _handleTaskCompletionNotificationTap,
    );
    _activeRepository = widget.repository;
    _viewFuture = _loadActiveProjectView();
    _bootstrapProfiles();
  }

  @override
  void dispose() {
    _pairingForm.dispose();
    unawaited(_taskNotifications.dispose());
    _lifecycleResultNotifier.dispose();
    _runningLifecycleActionNotifier.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_showPairingSetup) {
      return _buildOnboardingScaffold();
    }
    if (_shouldShowUnpairedLoading) {
      return const ProjectHomeOnboardingLoadingScaffold();
    }
    if (_shouldShowUnpairedOnboarding) {
      return _buildOnboardingScaffold();
    }
    final serverProjectsFuture = _serverProjectsFuture;
    if (_mode == AppRuntimeMode.pairedGateway &&
        _activeProjectId.isEmpty &&
        serverProjectsFuture != null) {
      return _buildServerProjectList(serverProjectsFuture);
    }
    return FutureBuilder<CcbProjectView>(
      future: _viewFuture,
      builder: (context, snapshot) {
        final error = snapshot.error;
        if (error != null) {
          return _buildProjectLoadError(error);
        }
        final view = snapshot.data;
        final selectedAgent = view == null ? null : _selectedAgentFor(view);
        if (view == null) {
          return const Scaffold(
            body: SafeArea(child: Center(child: CircularProgressIndicator())),
          );
        }
        if (MediaQuery.sizeOf(context).width >=
            projectHomeWideLayoutBreakpoint) {
          return _buildWideProjectScaffold(view, selectedAgent);
        }
        if (_openedProjectId != view.project.id) {
          return _buildProjectListScaffold(view, selectedAgent);
        }
        return ProjectHomeMobileChatScaffoldHost(
          view: view,
          selectedAgent: selectedAgent,
          repository: _activeRepository,
          terminalTransport: _terminalTransport,
          usePaneInputForMessages: _mode == AppRuntimeMode.pairedGateway,
          mobileAgentsCollapsed: _mobileAgentsCollapsed,
          onBack: _closeProject,
          onOpenTerminal: (agentName) {
            _openAgentTerminal(view, agentName);
          },
          onOpenConnectionDetails: () {
            _openConnectionDetails(view);
          },
          onCollapseAgents: _collapseMobileAgents,
          onExpandAgents: _expandMobileAgents,
          onWindowSelected: (windowName) {
            _selectWindow(view, windowName);
          },
          onAgentSelected: _selectAgent,
          onRefreshView: _refreshActiveView,
          onTimelineScrollDirectionChanged:
              _handleMobileTimelineScrollDirection,
        );
      },
    );
  }

  Future<CcbProjectView> _loadActiveProjectView() {
    return _deferredBuilderFuture(
      () => _activeRepository
          .getProjectView(_activeProjectId)
          .timeout(projectHomeRuntimeViewLoadTimeout),
    );
  }

  Future<List<CcbProject>> _loadServerProjects() {
    return _deferredBuilderFuture(
      () => _activeRepository.listProjects().timeout(
        projectHomeRuntimeViewLoadTimeout,
      ),
    );
  }

  Future<T> _deferredBuilderFuture<T>(Future<T> Function() load) {
    final completer = Completer<T>();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      try {
        completer.complete(await load());
      } catch (error, stackTrace) {
        completer.completeError(error, stackTrace);
      }
    });
    return completer.future;
  }

  bool get _shouldShowUnpairedLoading =>
      widget.showOnboardingWhenUnpaired &&
      _mode == AppRuntimeMode.fake &&
      !_profilesInitialized;

  bool get _shouldShowUnpairedOnboarding =>
      widget.showOnboardingWhenUnpaired &&
      _mode == AppRuntimeMode.fake &&
      _profilesInitialized &&
      _profiles.isEmpty;

  Widget _buildOnboardingScaffold() {
    return ProjectHomeOnboardingScaffold(
      gatewayUrlController: _pairingForm.gatewayUrlController,
      pairingCodeController: _pairingForm.pairingCodeController,
      deviceNameController: _pairingForm.deviceNameController,
      routeKindListenable: _pairingForm.routeKindListenable,
      claiming: _claimingPairing,
      loadingProfiles: _loadingProfiles,
      themePreference: widget.themePreference,
      onThemePreferenceChanged: widget.onThemePreferenceChanged,
      onRouteKindChanged: (value) {
        setState(() {
          _setPairingRouteKind(value);
        });
      },
      onScan: _scanGatewayProfile,
      onClaim: _claimGatewayProfile,
      onClose: _canClosePairingSetup ? _closePairingSetup : null,
    );
  }

  bool get _canClosePairingSetup =>
      _mode == AppRuntimeMode.pairedGateway && _profiles.isNotEmpty;

  void _closePairingSetup() {
    setState(() {
      _showPairingSetup = false;
    });
  }

  Widget _buildProjectLoadError(Object error) {
    final strings = CcbMobileLocalizations.of(context);
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Icon(Icons.cloud_off_outlined, size: 48),
                  const SizedBox(height: 16),
                  Text(
                    strings.couldNotLoadProject,
                    key: const ValueKey('project-view-load-error'),
                    style: Theme.of(context).textTheme.titleLarge,
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 8),
                  Text(
                    error.toString(),
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: Theme.of(context).colorScheme.onSurfaceVariant,
                    ),
                  ),
                  const SizedBox(height: 20),
                  FilledButton.icon(
                    key: const ValueKey('project-view-retry-button'),
                    onPressed: _retryActiveProjectView,
                    icon: const Icon(Icons.refresh),
                    label: Text(strings.retry),
                  ),
                  const SizedBox(height: 8),
                  if (_mode == AppRuntimeMode.pairedGateway)
                    TextButton.icon(
                      key: const ValueKey('project-view-back-to-list-button'),
                      onPressed: _returnToServerProjectList,
                      icon: const Icon(Icons.list_alt_outlined),
                      label: Text(strings.backToProjects),
                    )
                  else
                    TextButton(
                      key: const ValueKey('project-view-use-fake-button'),
                      onPressed: () {
                        _setRuntimeMode(AppRuntimeMode.fake);
                      },
                      child: Text(strings.useFakeDemo),
                    ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  void _retryActiveProjectView() {
    setState(() {
      _viewFuture = _loadActiveProjectView();
    });
  }

  void _retryServerProjects() {
    setState(() {
      _serverProjectsFuture = _loadServerProjects();
    });
  }

  void _returnToServerProjectList() {
    setState(() {
      _activeProjectId = '';
      _openedProjectId = null;
      _selectedAgentName = null;
      _serverProjectsFuture = _loadServerProjects();
    });
  }

  Widget _buildServerProjectList(Future<List<CcbProject>> projectsFuture) {
    return FutureBuilder<List<CcbProject>>(
      future: projectsFuture,
      builder: (context, snapshot) {
        final error = snapshot.error;
        if (error != null) {
          return _buildProjectCatalogError(error);
        }
        final projects = snapshot.data;
        if (projects == null) {
          return const Scaffold(
            body: SafeArea(child: Center(child: CircularProgressIndicator())),
          );
        }
        return ProjectHomeServerProjectListHost(
          projects: projects,
          onRefreshProjects: _retryServerProjects,
          onOpenSettings: _openPairingSettings,
          onOpenProject: _openServerProject,
        );
      },
    );
  }

  Widget _buildProjectCatalogError(Object error) {
    final strings = CcbMobileLocalizations.of(context);
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Icon(Icons.cloud_off_outlined, size: 48),
                  const SizedBox(height: 16),
                  Text(
                    strings.couldNotLoadProjects,
                    key: const ValueKey('project-list-load-error'),
                    style: Theme.of(context).textTheme.titleLarge,
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 8),
                  Text(
                    error.toString(),
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: Theme.of(context).colorScheme.onSurfaceVariant,
                    ),
                  ),
                  const SizedBox(height: 20),
                  FilledButton.icon(
                    key: const ValueKey('project-list-retry-button'),
                    onPressed: _retryServerProjects,
                    icon: const Icon(Icons.refresh),
                    label: Text(strings.retry),
                  ),
                  const SizedBox(height: 8),
                  OutlinedButton.icon(
                    key: const ValueKey('project-list-back-to-setup-button'),
                    onPressed: _returnToPairingSetup,
                    icon: const Icon(Icons.settings_outlined),
                    label: Text(strings.backToSetup),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildWideProjectScaffold(CcbProjectView view, CcbAgent? agent) {
    return ProjectHomeWideScaffoldHost(
      view: view,
      selectedAgent: agent,
      repository: _activeRepository,
      terminalTransport: _terminalTransport,
      usePaneInputForMessages: _mode == AppRuntimeMode.pairedGateway,
      sidebarState: _wideSidebarState,
      onOpenProject: () {
        _openProject(view);
      },
      onOpenNotifications: () {
        _openNotificationCenter(view);
      },
      onOpenConnectionDetails: () {
        _openConnectionDetails(view);
      },
      onShowProjects: _expandWideSidebarLevel,
      onAgentSelected: (agent) {
        _selectAgent(agent.name);
      },
      onOpenTerminal: (agentName) {
        _openAgentTerminal(view, agentName);
      },
      onToggleSidebar: _toggleWideSidebarLevel,
      onHorizontalDragStart: _startWideSidebarDrag,
      onHorizontalDragUpdate: _updateWideSidebarDrag,
      onHorizontalDragEnd: _endWideSidebarDrag,
      onRefreshView: _refreshActiveView,
    );
  }

  void _expandWideSidebarLevel() {
    final next = expandWideSidebarLevel(_wideSidebarState);
    if (next == _wideSidebarState) {
      return;
    }
    setState(() {
      _wideSidebarState = next;
      _wideSidebarDragDelta = 0;
    });
  }

  void _toggleWideSidebarLevel() {
    final next = toggleWideSidebarLevel(_wideSidebarState);
    setState(() {
      _wideSidebarState = next;
      _wideSidebarDragDelta = 0;
    });
  }

  void _startWideSidebarDrag(DragStartDetails details) {
    _wideSidebarDragStartState = _wideSidebarState;
    _wideSidebarDragDelta = 0;
  }

  void _updateWideSidebarDrag(DragUpdateDetails details) {
    _wideSidebarDragDelta += details.delta.dx;
    final target = wideSidebarTargetForDrag(
      _wideSidebarDragStartState,
      _wideSidebarDragDelta,
    );
    if (target != _wideSidebarState) {
      setState(() {
        _wideSidebarState = target;
      });
    }
  }

  void _endWideSidebarDrag(DragEndDetails details) {
    final reset = endWideSidebarDrag(_wideSidebarState);
    _wideSidebarDragDelta = reset.dragDelta;
    _wideSidebarDragStartState = reset.dragStartState;
  }

  void _collapseMobileAgents() {
    final outcome = collapseProjectHomeMobileAgents(_mobileAgentsCollapsed);
    if (!outcome.shouldUpdate) {
      return;
    }
    setState(() {
      _mobileAgentsCollapsed = outcome.collapsed;
    });
  }

  void _expandMobileAgents() {
    final outcome = expandProjectHomeMobileAgents(_mobileAgentsCollapsed);
    if (!outcome.shouldUpdate) {
      return;
    }
    setState(() {
      _mobileAgentsCollapsed = outcome.collapsed;
    });
  }

  Widget _buildProjectListScaffold(CcbProjectView view, CcbAgent? agent) {
    return ProjectHomeProjectListHost(
      view: view,
      selectedAgent: agent,
      onOpenProject: () {
        _openProject(view);
      },
      onOpenNotifications: () {
        _openNotificationCenter(view);
      },
      onOpenConnectionDetails: () {
        _openConnectionDetails(view);
      },
    );
  }

  CcbAgent? _selectedAgentFor(CcbProjectView view) {
    return selectedProjectHomeAgent(view, _selectedAgentName);
  }

  void _selectAgent(String agentName) {
    final outcome = selectProjectHomeAgent(agentName);
    setState(() {
      _selectedAgentName = outcome.selectedAgentName;
    });
  }

  void _handleMobileTimelineScrollDirection(ScrollDirection direction) {
    if (direction == ScrollDirection.reverse) {
      _collapseMobileAgents();
    }
  }

  void _selectWindow(CcbProjectView view, String windowName) {
    if (_mode == AppRuntimeMode.pairedGateway) {
      _focusWindow(view, windowName);
      return;
    }
    final outcome = selectProjectHomeLocalWindow(view, windowName);
    if (!outcome.shouldUpdate) {
      return;
    }
    setState(() {
      _selectedAgentName = outcome.selectedAgentName;
    });
  }

  void _openProject(CcbProjectView view) {
    final outcome = openProjectHomeProject(view);
    setState(() {
      _openedProjectId = outcome.openedProjectId;
    });
  }

  void _openServerProject(CcbProject project) {
    setState(() {
      _activeProjectId = project.id;
      _openedProjectId = project.id;
      _selectedAgentName = null;
      _viewFuture = _loadActiveProjectView();
    });
  }

  void _closeProject() {
    if (_mode == AppRuntimeMode.pairedGateway) {
      _returnToServerProjectList();
      return;
    }
    final outcome = closeProjectHomeProject();
    setState(() {
      _openedProjectId = outcome.openedProjectId;
    });
  }

  Future<void> _bootstrapProfiles() async {
    final debugProfile = debugPairedHostFromEnvironment();
    if (debugProfile != null) {
      setState(() {
        _loadingProfiles = true;
      });
    }
    final outcome = await _profileLoadingCoordinator.bootstrap(
      selectedProfile: _selectedProfile,
      debugProfile: debugProfile,
      autoActivateDebugProfile: debugAutoActivatePairedHost,
    );
    if (!mounted) {
      return;
    }
    switch (outcome.kind) {
      case ProjectHomeProfileBootstrapLoadKind.loadRequired:
        await _loadProfiles();
      case ProjectHomeProfileBootstrapLoadKind.success:
        final result = outcome.result!;
        setState(() {
          _profiles = result.profiles;
          _selectedProfile = result.selectedProfile;
          _loadingProfiles = false;
          _profilesInitialized = true;
        });
        final activateProfile =
            result.activateProfile ??
            (widget.autoActivateStoredProfile ? result.selectedProfile : null);
        if (activateProfile != null) {
          _activateGatewayProfile(activateProfile);
        }
      case ProjectHomeProfileBootstrapLoadKind.fallbackToLoad:
        setState(() {
          _loadingProfiles = false;
        });
        await _loadProfiles();
    }
  }

  Future<void> _loadProfiles() async {
    setState(() {
      _loadingProfiles = true;
    });
    final outcome = await _profileLoadingCoordinator.load(
      selectedProfile: _selectedProfile,
    );
    if (!mounted) {
      return;
    }
    switch (outcome.kind) {
      case ProjectHomeProfileLoadKind.success:
        final result = outcome.result!;
        setState(() {
          _profiles = result.profiles;
          _selectedProfile = result.selectedProfile;
          _loadingProfiles = false;
          _profilesInitialized = true;
        });
        final activateProfile =
            widget.autoActivateStoredProfile ? result.selectedProfile : null;
        if (activateProfile != null) {
          _activateGatewayProfile(activateProfile);
        }
      case ProjectHomeProfileLoadKind.failure:
        setState(() {
          _loadingProfiles = false;
          _profilesInitialized = true;
        });
    }
  }

  void _setRuntimeMode(AppRuntimeMode mode) {
    switch (mode) {
      case AppRuntimeMode.fake:
        final reset = resetProjectHomeFakeRuntime(
          defaultProjectId: _defaultProjectId,
        );
        final session = _runtimeSessionCoordinator.activateFake(
          repository: widget.repository,
          defaultProjectId: reset.defaultProjectId,
        );
        setState(() {
          _mode = mode;
          _showPairingSetup = false;
          _activeRepository = session.repository;
          _activeProjectId = session.activeProjectId;
          _serverProjectsFuture = null;
          _openedProjectId = null;
          _selectedAgentName = null;
          _terminalTransport = session.terminalTransport;
          _viewFuture = session.viewFuture;
        });
        unawaited(_taskNotifications.stop());
        _lifecycleResultNotifier.value = null;
      case AppRuntimeMode.pairedGateway:
        final selection = selectProjectHomePairedRuntimeProfile(
          profiles: _profiles,
          selectedProfile: _selectedProfile,
        );
        if (selection.kind == ProjectHomePairedRuntimeSelectionKind.noProfile) {
          _showSnack(selection.snackMessage!);
          return;
        }
        _activateGateway(selection.activation!);
    }
  }

  void _selectGatewayProfile(GatewayPairedHost profile) {
    _activateGatewayProfile(profile);
  }

  void _activateGatewayProfile(GatewayPairedHost profile) {
    _activateGateway(activateProjectHomeGatewayProfile(profile));
  }

  void _activateGateway(ProjectHomeGatewayActivationData activation) {
    _pairingForm.applyGatewayActivation(
      gatewayUrlText: activation.gatewayUrlText,
      routeKind: activation.routeKind,
    );
    final session = _runtimeSessionCoordinator.activateGateway(
      activation: activation,
      repositoryFactory: widget.gatewayRepositoryFactory,
      terminalTransportFactory: widget.gatewayTerminalTransportFactory,
    );
    // FutureBuilder attaches on the next build; register an error listener now
    // so immediate DNS/socket failures render in the error page.
    unawaited(
      session.projectsFuture.catchError((Object _) => const <CcbProject>[]),
    );
    final profile = session.activation.profile;
    setState(() {
      _mode = AppRuntimeMode.pairedGateway;
      _showPairingSetup = false;
      _selectedProfile = profile;
      _routeDiagnostics = null;
      _activeRepository = session.repository;
      _activeProjectId = '';
      _serverProjectsFuture = session.projectsFuture;
      _openedProjectId = null;
      _selectedAgentName = null;
      _terminalTransport = session.terminalTransport;
    });
    _lifecycleResultNotifier.value = null;
    _startTaskCompletionNotifications(profile);
  }

  void _returnToPairingSetup() {
    unawaited(_taskNotifications.stop());
    setState(() {
      _mode = AppRuntimeMode.fake;
      _showPairingSetup = true;
      _activeRepository = widget.repository;
      _activeProjectId = _defaultProjectId;
      _serverProjectsFuture = null;
      _openedProjectId = null;
      _selectedAgentName = null;
      _terminalTransport = null;
      _routeDiagnostics = null;
      _viewFuture = _loadActiveProjectView();
    });
    _lifecycleResultNotifier.value = null;
  }

  void _openPairingSettings() {
    setState(() {
      _showPairingSetup = true;
    });
  }

  Future<void> _scanGatewayProfile() async {
    final outcome = await _pairingFlowCoordinator.scan(
      isClaimingPairing: _claimingPairing,
      scanner: () => widget.pairingScanner(context),
    );
    if (!mounted) {
      return;
    }
    switch (outcome.kind) {
      case ProjectHomePairingFlowScanOutcomeKind.busy:
      case ProjectHomePairingFlowScanOutcomeKind.canceled:
        return;
      case ProjectHomePairingFlowScanOutcomeKind.success:
        final pairing = outcome.pairingToApply!;
        setState(() {
          _pairingForm.applyScannedPairing(pairing);
        });
        await _claimGatewayProfile(pairingOverride: outcome.pairingToClaim);
      case ProjectHomePairingFlowScanOutcomeKind.failure:
        _showSnack(outcome.snackMessage!);
    }
  }

  Future<void> _claimGatewayProfile({
    GatewayPairingPayload? pairingOverride,
  }) async {
    final requestOutcome = _pairingFlowCoordinator.buildRequest(
      builder: _pairingForm.buildRequest,
      pairingOverride: pairingOverride,
    );
    if (requestOutcome.kind == ProjectHomePairingRequestOutcomeKind.invalid) {
      _showSnack(requestOutcome.snackMessage!);
      return;
    }
    setState(() {
      _claimingPairing = true;
    });
    final outcome = await _pairingFlowCoordinator.claim(
      request: requestOutcome.request!,
      claimAndStore: widget.pairingClaimAndStore,
      store: widget.profileStore,
      mergeProfiles: _profileBootstrapper.mergeStoredWith,
    );
    if (!mounted) {
      return;
    }
    switch (outcome.kind) {
      case ProjectHomePairingFlowClaimOutcomeKind.success:
        setState(() {
          _profiles = outcome.profiles!;
          _pairingForm.clearPairingCode();
          _claimingPairing = false;
        });
        _activateGatewayProfile(outcome.paired!);
        _showSnack(outcome.snackMessage!);
      case ProjectHomePairingFlowClaimOutcomeKind.failure:
        setState(() {
          _claimingPairing = false;
        });
        _showSnack(outcome.snackMessage!);
    }
  }

  void _setPairingRouteKind(RouteProviderKind value) {
    _pairingForm.setRouteKind(value);
  }

  Future<void> _checkGatewayRoute() async {
    final profile = _selectedProfile;
    final beginOutcome = _routeDiagnosticsCoordinator.begin(
      selectedProfile: _selectedProfile,
      checking: _checkingRoute,
    );
    if (beginOutcome.kind == ProjectHomeRouteDiagnosticsOutcomeKind.noProfile) {
      _showSnack(beginOutcome.snackMessage!);
      return;
    }
    if (beginOutcome.kind == ProjectHomeRouteDiagnosticsOutcomeKind.busy) {
      return;
    }
    if (beginOutcome.kind != ProjectHomeRouteDiagnosticsOutcomeKind.ready) {
      return;
    }
    setState(() {
      _checkingRoute = true;
    });
    final outcome = await _routeDiagnosticsCoordinator.complete(
      profile: profile!,
      diagnostics: widget.gatewayRouteDiagnostics,
    );
    if (!mounted) {
      return;
    }
    if (outcome.kind == ProjectHomeRouteDiagnosticsOutcomeKind.success) {
      final report = outcome.report!;
      setState(() {
        _routeDiagnostics = report;
        _checkingRoute = false;
      });
      _showSnack(outcome.snackMessage!);
      return;
    }
    if (outcome.kind == ProjectHomeRouteDiagnosticsOutcomeKind.failure) {
      setState(() {
        _checkingRoute = false;
      });
      _showSnack(outcome.snackMessage!);
    }
  }

  Future<void> _requestLifecycle(
    CcbProjectView view,
    CcbLifecycleAction action,
  ) async {
    final beginOutcome = _lifecycleCoordinator.begin(
      runningAction: _runningLifecycleAction,
      action: action,
    );
    if (beginOutcome.kind == ProjectHomeLifecycleOutcomeKind.busy) {
      return;
    }
    if (beginOutcome.kind ==
        ProjectHomeLifecycleOutcomeKind.needsStopConfirmation) {
      final confirmed = await _confirmStopProject(view);
      if (confirmed != true || !mounted) {
        return;
      }
    }
    setState(() {
      _runningLifecycleAction = action;
    });
    _runningLifecycleActionNotifier.value = action;
    final outcome = await _lifecycleCoordinator.complete(
      repository: _activeRepository,
      projectId: view.project.id,
      action: action,
    );
    if (!mounted) {
      return;
    }
    setState(() {
      _runningLifecycleAction = null;
      final refreshed = outcome.refreshedView;
      if (refreshed != null) {
        _viewFuture = Future<CcbProjectView>.value(refreshed);
      }
    });
    final result = outcome.result;
    if (result != null) {
      _lifecycleResultNotifier.value = result;
    }
    _runningLifecycleActionNotifier.value = null;
    _showSnack(outcome.snackMessage!);
  }

  Future<bool?> _confirmStopProject(CcbProjectView view) {
    return confirmProjectHomeStop(context, view: view);
  }

  Future<CcbProjectView?> _refreshActiveView() async {
    final outcome = await _viewRefreshCoordinator.refresh(
      repository: _activeRepository,
      projectId: _activeProjectId,
      selectedAgentName: _selectedAgentName,
    );
    if (outcome.kind == ProjectHomeViewRefreshOutcomeKind.success) {
      if (!mounted) {
        return null;
      }
      final refreshed = outcome.refreshedView!;
      setState(() {
        _viewFuture = Future<CcbProjectView>.value(refreshed);
        _selectedAgentName = outcome.selectedAgentName;
      });
      return refreshed;
    }
    if (mounted) {
      _showSnack(outcome.snackMessage!);
    }
    return null;
  }

  Future<CcbProjectView?> _focusAgent(
    CcbProjectView view,
    String agentName,
  ) async {
    final outcome = await _focusCoordinator.focusAgent(
      repository: _activeRepository,
      view: view,
      agentName: agentName,
    );
    if (outcome.kind == ProjectHomeFocusOutcomeKind.stale) {
      if (!mounted) {
        return null;
      }
      _showSnack(outcome.snackMessage!);
      return null;
    }
    if (outcome.kind == ProjectHomeFocusOutcomeKind.success) {
      if (!mounted) {
        return null;
      }
      final focusedView = outcome.focusedView!;
      setState(() {
        _selectedAgentName = outcome.selectedAgentName;
        _viewFuture = Future<CcbProjectView>.value(focusedView);
      });
      return focusedView;
    }
    if (!mounted) {
      return null;
    }
    setState(() {
      _viewFuture = Future<CcbProjectView>.value(outcome.originalView!);
    });
    _showSnack(outcome.snackMessage!);
    return null;
  }

  Future<CcbProjectView?> _focusWindow(
    CcbProjectView view,
    String windowName,
  ) async {
    final outcome = await _focusCoordinator.focusWindow(
      repository: _activeRepository,
      view: view,
      windowName: windowName,
      previousSelectedAgentName: _selectedAgentName,
    );
    if (outcome.kind == ProjectHomeFocusOutcomeKind.stale) {
      if (!mounted) {
        return null;
      }
      _showSnack(outcome.snackMessage!);
      return null;
    }
    if (outcome.kind == ProjectHomeFocusOutcomeKind.success) {
      if (!mounted) {
        return null;
      }
      final focusedView = outcome.focusedView!;
      setState(() {
        _selectedAgentName = outcome.selectedAgentName;
        _viewFuture = Future<CcbProjectView>.value(focusedView);
      });
      return focusedView;
    }
    if (!mounted) {
      return null;
    }
    setState(() {
      _viewFuture = Future<CcbProjectView>.value(outcome.originalView!);
    });
    _showSnack(outcome.snackMessage!);
    return null;
  }

  Future<void> _openAgentTerminal(CcbProjectView view, String agentName) async {
    if (_mode == AppRuntimeMode.pairedGateway) {
      final focusedView = await _focusAgent(view, agentName);
      if (focusedView == null || !mounted) {
        return;
      }
      final transport = _terminalTransport;
      final outcome = projectHomeGatewayTerminalNavigation(
        focusedView: focusedView,
        agentName: agentName,
        hasTerminalTransport: transport != null,
      );
      if (outcome.kind == ProjectHomeTerminalNavigationKind.noTransport) {
        _showSnack(outcome.snackMessage!);
        return;
      }
      if (outcome.kind != ProjectHomeTerminalNavigationKind.open) {
        return;
      }
      final spec = outcome.spec!;
      await pushProjectHomeTerminalRoute(
        context,
        repository: _activeRepository,
        projectId: spec.projectId,
        agentName: spec.agentName,
        terminalTransport: transport,
        gatewayTerminal: spec.gatewayTerminal,
      );
      return;
    }
    final outcome = projectHomeFakeTerminalNavigation(
      view: view,
      agentName: agentName,
    );
    final spec = outcome.spec!;
    pushProjectHomeTerminalRoute(
      context,
      repository: _activeRepository,
      projectId: spec.projectId,
      agentName: spec.agentName,
      terminalTransport: null,
      gatewayTerminal: spec.gatewayTerminal,
    );
  }

  void _openConnectionDetails(CcbProjectView view) {
    pushProjectHomeConnectionDetailsRoute(
      context,
      panel: ProjectHomeConnectionDetailsPanelHost(
        view: view,
        mode: _mode,
        profiles: _profiles,
        selectedProfile: _selectedProfile,
        routeDiagnostics: _routeDiagnostics,
        lifecycleResultListenable: _lifecycleResultNotifier,
        loadingProfiles: _loadingProfiles,
        checkingRoute: _checkingRoute,
        runningLifecycleActionListenable: _runningLifecycleActionNotifier,
        onModeChanged: _setRuntimeMode,
        onProfileSelected: _selectGatewayProfile,
        onCheckRoute: _checkGatewayRoute,
        onLifecycleAction: (action) {
          _requestLifecycle(view, action);
        },
      ),
    );
  }

  void _openNotificationCenter(CcbProjectView view) {
    showProjectHomeNotificationCenter(
      context,
      notifications: view.notifications,
      onOpen: (notification) {
        _openNotificationTarget(view, notification);
      },
    );
  }

  void _openNotificationTarget(
    CcbProjectView view,
    CcbNotification notification,
  ) {
    final outcome = resolveProjectHomeNotificationOpenOutcome(
      view,
      notification,
    );
    if (outcome.openedProjectId != null && outcome.selectedAgentName != null) {
      setState(() {
        _openedProjectId = outcome.openedProjectId;
        _selectedAgentName = outcome.selectedAgentName;
      });
    }
    _showSnack(outcome.snackMessage);
  }

  void _startTaskCompletionNotifications(GatewayPairedHost profile) {
    unawaited(
      _taskNotifications.start(profile).then((status) {
        if (!mounted) {
          return;
        }
        if (status ==
            TaskCompletionNotificationSubscriptionStatus.missingNotifyScope) {
          _showSnack(taskCompletionMissingNotifyScopeMessage);
        }
      }),
    );
  }

  void _handleTaskCompletionNotificationTap(TaskCompletionNotificationTap tap) {
    unawaited(_openTaskCompletionNotificationTap(tap));
  }

  Future<void> _openTaskCompletionNotificationTap(
    TaskCompletionNotificationTap tap,
  ) async {
    if (_mode != AppRuntimeMode.pairedGateway) {
      return;
    }
    CcbProjectView? targetView;
    try {
      targetView = await _activeRepository
          .getProjectView(tap.projectId)
          .timeout(projectHomeRuntimeViewLoadTimeout);
    } catch (_) {
      targetView = null;
    }
    if (!mounted) {
      return;
    }
    final route = resolveProjectHomeTaskCompletionNotificationTap(
      tap: tap,
      targetView: targetView,
    );
    switch (route.kind) {
      case ProjectHomeTaskCompletionNotificationRouteKind.openProjectAgent:
        setState(() {
          _activeProjectId = route.projectId!;
          _openedProjectId = route.projectId;
          _selectedAgentName = route.agentName;
          _serverProjectsFuture = null;
          _viewFuture = Future<CcbProjectView>.value(route.view!);
        });
      case ProjectHomeTaskCompletionNotificationRouteKind.projectList:
        setState(() {
          _activeProjectId = '';
          _openedProjectId = null;
          _selectedAgentName = null;
          _serverProjectsFuture = _loadServerProjects();
        });
    }
  }

  void _showSnack(String message) {
    final messenger = ScaffoldMessenger.of(context);
    messenger.clearSnackBars();
    messenger.showSnackBar(SnackBar(content: Text(message)));
  }
}
