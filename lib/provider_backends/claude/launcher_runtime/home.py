from __future__ import annotations

import getpass
import json
import os
import platform
from pathlib import Path
import shutil
import subprocess

from provider_core.memory_projection import (
    memory_projection_result,
    record_memory_projection_event,
    text_file_sha256,
)
from provider_core.projected_assets import route_projected_tree
from provider_core.source_home import current_provider_source_home
from provider_profiles import provider_api_env_keys
from rolepacks.projection import project_role_skills_to_home
from project_memory import (
    ensure_project_memory,
    load_memory_sources,
    read_memory_source,
    render_memory_bundle,
)
from project_memory.hashing import sha256_text
from storage.atomic import atomic_write_text

from ..home_layout import ClaudeHomeLayout, claude_layout_for_home, claude_layout_from_session_data
from .session_paths import read_session_payload, session_file_for_runtime_dir, state_dir_for_runtime_dir

_CLAUDE_RUNTIME_SETTINGS_KEYS = ('enabledPlugins', 'hooks', 'permissions')
_CLAUDE_CCB_PERMISSION_PREFIX = 'Bash(ccb '
_CLAUDE_AUTH_ENV_KEYS = ('ANTHROPIC_AUTH_TOKEN',)
_CLAUDE_API_AUTH_ENV_KEYS = ('ANTHROPIC_API_KEY',)
_CLAUDE_ROUTE_ENV_KEYS = ('ANTHROPIC_BASE_URL',)
_CLAUDE_HOME_HOOK_ASSET_DIRS = ('.codeisland',)
_CLAUDE_JSON_AUTH_METADATA_KEYS = ('oauthAccount',)
_CLAUDE_JSON_AUTH_SECRET_KEYS = ('primaryApiKey',)
_CLAUDE_JSON_AUTH_COMPANION_KEYS = (
    'hasCompletedOnboarding',
    'lastOnboardingVersion',
    'hasAvailableSubscription',
    'subscriptionNoticeCount',
)
_CLAUDE_JSON_MCP_ROOT_KEYS = ('mcpServers',)
_CLAUDE_JSON_MCP_PROJECT_KEYS = (
    'mcpServers',
    'enabledMcpjsonServers',
    'disabledMcpjsonServers',
    'disabledMcpServers',
    'mcpContextUris',
)
_MACOS_KEYCHAIN_CLAUDE_SERVICES = ('Claude Code-credentials', 'Claude Code-custom-oauth', 'Claude Code')
_CLAUDE_SKILLS_PROJECTION_LABEL = 'claude-inherited-skills'
_CLAUDE_COMMANDS_PROJECTION_LABEL = 'claude-inherited-commands'


def resolve_claude_home_layout(runtime_dir: Path, profile) -> ClaudeHomeLayout:
    explicit_runtime_home = _profile_runtime_home(profile)
    if explicit_runtime_home is not None:
        return claude_layout_for_home(explicit_runtime_home)

    managed_home = _managed_isolated_home(runtime_dir)
    existing = _existing_layout(runtime_dir, managed_home=managed_home)
    if existing is not None:
        return existing

    return claude_layout_for_home(managed_home)


def prepare_claude_home_overrides(
    runtime_dir: Path,
    profile,
    *,
    refresh_home: bool = True,
    auto_permission: bool = False,
    project_root: Path | None = None,
    agent_name: str | None = None,
    workspace_path: Path | None = None,
    memory_projection_event_path: Path | None = None,
    memory_projection_marker_path: Path | None = None,
) -> dict[str, str]:
    layout = resolve_claude_home_layout(runtime_dir, profile)
    if refresh_home:
        materialize_claude_home_config(
            layout.home_root,
            profile=profile,
            project_root=project_root,
            agent_name=agent_name,
            workspace_path=workspace_path,
            auto_permission=auto_permission,
            memory_projection_event_path=memory_projection_event_path,
            memory_projection_marker_path=memory_projection_marker_path,
        )
    overrides = {
        'HOME': str(layout.home_root),
        'CLAUDE_PROJECTS_ROOT': str(layout.projects_root),
        'CLAUDE_PROJECT_ROOT': str(layout.projects_root),
    }

    if "WSL_DISTRO_NAME" in os.environ:
        # We are running inside WSL. The target claude executable might be a Windows binary (via interop).
        # We must set USERPROFILE (which Windows Node.js uses as home) to the same isolated path.
        # WSLENV translates path variables with /p and forwards Claude API env names as raw values
        # when invoking a Windows executable. Linux executables will ignore WSLENV.
        overrides['USERPROFILE'] = str(layout.home_root)
        wslenv_additions = (
            "HOME/p:USERPROFILE/p:CLAUDE_PROJECTS_ROOT/p:CLAUDE_PROJECT_ROOT/p:"
            "ANTHROPIC_AUTH_TOKEN:ANTHROPIC_API_KEY:ANTHROPIC_BASE_URL"
        )
        existing_wslenv = os.environ.get("WSLENV", "")
        if existing_wslenv:
            overrides['WSLENV'] = f"{wslenv_additions}:{existing_wslenv}"
        else:
            overrides['WSLENV'] = wslenv_additions

    return overrides


def materialize_claude_home_config(
    target_home: Path,
    *,
    profile=None,
    source_home: Path | None = None,
    project_root: Path | None = None,
    agent_name: str | None = None,
    workspace_path: Path | None = None,
    auto_permission: bool = False,
    memory_projection_event_path: Path | None = None,
    memory_projection_marker_path: Path | None = None,
) -> ClaudeHomeLayout:
    layout = claude_layout_for_home(Path(target_home).expanduser())
    source_root = Path(source_home).expanduser() if source_home is not None else _system_home_root()
    memory_result = _prepare_managed_home(
        source_root,
        layout,
        profile=profile,
        project_root=project_root,
        agent_name=agent_name,
        workspace_path=workspace_path,
        auto_permission=auto_permission,
    )
    record_memory_projection_event(
        memory_result,
        provider='claude',
        event_path=memory_projection_event_path,
        marker_path=memory_projection_marker_path,
        agent_name=agent_name,
    )
    return layout


def _profile_runtime_home(profile) -> Path | None:
    del profile
    return None


def _existing_layout(runtime_dir: Path, *, managed_home: Path) -> ClaudeHomeLayout | None:
    session_file = session_file_for_runtime_dir(runtime_dir)
    if session_file is None or not session_file.is_file():
        return None
    data = read_session_payload(session_file)
    if not isinstance(data, dict):
        return None
    layout = claude_layout_from_session_data(data)
    if layout is None:
        return None
    return layout if _is_within_home_root(layout.home_root, managed_home) else None


def _managed_isolated_home(runtime_dir: Path) -> Path:
    state_dir = state_dir_for_runtime_dir(runtime_dir)
    if state_dir is not None:
        return state_dir / 'home'
    return Path(runtime_dir).expanduser() / 'claude-home'


def _is_within_home_root(candidate: Path, managed_home: Path) -> bool:
    normalized_candidate = _normalize_path(candidate)
    normalized_managed = _normalize_path(managed_home)
    if normalized_candidate is None or normalized_managed is None:
        return False
    try:
        normalized_candidate.relative_to(normalized_managed)
        return True
    except Exception:
        return False


def _normalize_path(value: object) -> Path | None:
    try:
        return Path(value).expanduser().resolve()
    except Exception:
        try:
            return Path(value).expanduser()
        except Exception:
            return None


def _prepare_managed_home(
    source_home: Path,
    target_layout: ClaudeHomeLayout,
    *,
    profile,
    project_root: Path | None,
    agent_name: str | None,
    workspace_path: Path | None,
    auto_permission: bool,
) -> dict[str, object]:
    target_layout.home_root.mkdir(parents=True, exist_ok=True)
    target_layout.claude_dir.mkdir(parents=True, exist_ok=True)
    target_layout.projects_root.mkdir(parents=True, exist_ok=True)
    target_layout.session_env_root.mkdir(parents=True, exist_ok=True)

    if target_layout.home_root == source_home.expanduser():
        _ensure_trust_file(target_layout.trust_path)
        return memory_projection_result(
            status='skipped',
            reason='source_home_is_target_home',
            path=target_layout.claude_dir / 'CLAUDE.md',
        )

    _materialize_settings(source_home, target_layout, profile=profile, auto_permission=auto_permission)
    _materialize_macos_keychain_preferences(source_home, target_layout, profile=profile)
    _materialize_auth(source_home, target_layout, profile=profile)
    _materialize_trust(
        source_home,
        target_layout,
        profile=profile,
        project_root=project_root,
        workspace_path=workspace_path,
    )
    return _materialize_inherited_assets(
        source_home,
        target_layout,
        profile=profile,
        project_root=project_root,
        agent_name=agent_name,
        workspace_path=workspace_path,
    )


def _materialize_inherited_assets(
    source_home: Path,
    target_layout: ClaudeHomeLayout,
    *,
    profile,
    project_root: Path | None,
    agent_name: str | None,
    workspace_path: Path | None,
) -> dict[str, object]:
    _route_inherited_tree(
        source_home / '.claude' / 'commands',
        target_layout.claude_dir / 'commands',
        enabled=_inherits_commands(profile),
        label=_CLAUDE_COMMANDS_PROJECTION_LABEL,
    )
    _route_inherited_tree(
        source_home / '.claude' / 'skills',
        target_layout.claude_dir / 'skills',
        enabled=_inherits_skills(profile),
        label=_CLAUDE_SKILLS_PROJECTION_LABEL,
    )
    project_role_skills_to_home(
        project_root=project_root,
        agent_name=agent_name,
        provider='claude',
        target_skills_dir=target_layout.claude_dir / 'skills',
    )
    memory_result = _materialize_claude_memory(
        source_home,
        target_layout,
        profile=profile,
        project_root=project_root,
        agent_name=agent_name,
        workspace_path=workspace_path,
    )
    _materialize_home_hook_assets(source_home, target_layout, profile=profile)
    return memory_result


def _materialize_claude_memory(
    source_home: Path,
    target_layout: ClaudeHomeLayout,
    *,
    profile,
    project_root: Path | None,
    agent_name: str | None,
    workspace_path: Path | None,
) -> dict[str, object]:
    target = target_layout.claude_dir / 'CLAUDE.md'
    if not _inherits_memory(profile):
        _remove_file(target)
        return memory_projection_result(
            status='skipped',
            reason='inherit_memory_disabled',
            path=target,
        )
    if project_root is None or agent_name is None:
        return memory_projection_result(
            status='failed',
            reason='missing_project_context',
            path=target,
        )
    root = Path(project_root).expanduser()
    try:
        warnings: list[str] = []
        ensure_result = ensure_project_memory(root)
        if ensure_result.warning:
            warnings.append(ensure_result.warning)
        extra_sources = tuple(
            source
            for source in (
                read_memory_source(
                    kind='provider_user_memory',
                    title='Provider User Memory',
                    path=source_home / '.claude' / 'CLAUDE.md',
                    include_missing=False,
                ),
            )
            if source is not None
        )
        sources = load_memory_sources(
            root,
            agent_name=agent_name,
            provider='claude',
            extra_sources=extra_sources,
        )
        warnings.extend(source.warning for source in sources if source.warning)
        rendered = render_memory_bundle(
            project_root=root,
            agent_name=agent_name,
            provider='claude',
            sources=sources,
            workspace_path=workspace_path,
        )
        digest = sha256_text(rendered)
        if text_file_sha256(target) == digest:
            return memory_projection_result(
                status='skipped',
                reason='unchanged',
                path=target,
                sha256=digest,
                source_count=len(sources),
                warnings=warnings,
            )
        atomic_write_text(target, rendered)
        return memory_projection_result(
            status='ok',
            reason='written',
            path=target,
            sha256=digest,
            source_count=len(sources),
            warnings=warnings,
        )
    except Exception as exc:
        return memory_projection_result(
            status='failed',
            reason=type(exc).__name__,
            path=target,
            error_detail=str(exc),
        )

def _materialize_home_hook_assets(source_home: Path, target_layout: ClaudeHomeLayout, *, profile) -> None:
    if not _inherits_config(profile):
        return
    source_settings = _read_json_object(source_home / '.claude' / 'settings.json')
    hooks_payload = source_settings.get('hooks')
    if not isinstance(hooks_payload, dict):
        return
    for dirname in _CLAUDE_HOME_HOOK_ASSET_DIRS:
        if _payload_mentions_home_asset(hooks_payload, dirname):
            _sync_tree(source_home / dirname, target_layout.home_root / dirname)


def _materialize_settings(
    source_home: Path,
    target_layout: ClaudeHomeLayout,
    *,
    profile,
    auto_permission: bool = False,
) -> None:
    payload = _projected_settings_payload(source_home / '.claude' / 'settings.json', profile=profile)
    existing = _read_json_object(target_layout.settings_path)
    merged = _merge_settings_payload(payload, existing=existing, profile=profile, auto_permission=auto_permission)
    if merged is None:
        return
    target_layout.settings_path.parent.mkdir(parents=True, exist_ok=True)
    target_layout.settings_path.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )


def _materialize_trust(
    source_home: Path,
    target_layout: ClaudeHomeLayout,
    *,
    profile,
    project_root: Path | None,
    workspace_path: Path | None,
) -> None:
    source_trust = source_home / '.claude.json'
    profile_servers = _profile_mcp_servers(profile)
    if source_trust.is_file() or target_layout.trust_path.exists() or profile_servers:
        merged = _projected_claude_json_payload(
            _read_json_object(source_trust) if source_trust.is_file() else {},
            existing=_read_json_object(target_layout.trust_path),
            profile=profile,
            project_root=project_root,
            workspace_path=workspace_path,
        )
        _write_json_object(target_layout.trust_path, merged)
    _ensure_trust_file(target_layout.trust_path)


def _materialize_auth(source_home: Path, target_layout: ClaudeHomeLayout, *, profile) -> None:
    if not _inherits_auth(profile):
        _remove_file(target_layout.auth_path)
        _remove_file(target_layout.credentials_path)
        return

    for source_auth, target_auth in _source_auth_paths(source_home, target_layout):
        if source_auth.is_file():
            _sync_file(source_auth, target_auth)
    _materialize_macos_keychain_auth(target_layout)


def _materialize_macos_keychain_preferences(source_home: Path, target_layout: ClaudeHomeLayout, *, profile) -> None:
    target = target_layout.home_root / 'Library' / 'Preferences' / 'com.apple.security.plist'
    target_keychains = target_layout.home_root / 'Library' / 'Keychains'
    if not _inherits_auth(profile):
        _remove_file(target)
        _remove_keychains_link(target_keychains)
        return
    if platform.system() != 'Darwin':
        return
    source = source_home / 'Library' / 'Preferences' / 'com.apple.security.plist'
    if source.is_file():
        _sync_file(source, target)
        return
    _remove_file(target)
    _materialize_macos_keychains_link(source_home / 'Library' / 'Keychains', target_keychains)


def _materialize_macos_keychains_link(source: Path, target: Path) -> None:
    if not source.is_dir():
        _remove_keychains_link(target)
        return
    try:
        if target.is_symlink():
            if target.resolve() == source.resolve():
                return
            target.unlink()
        elif target.exists():
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(source, target_is_directory=True)
    except Exception:
        pass


def _remove_keychains_link(path: Path) -> None:
    try:
        if path.is_symlink():
            path.unlink()
    except Exception:
        pass


def _projected_claude_json_payload(
    source_payload: dict[str, object],
    *,
    existing: dict[str, object],
    profile=None,
    project_root: Path | None = None,
    workspace_path: Path | None = None,
) -> dict[str, object]:
    merged = dict(existing or {})
    for key in _CLAUDE_JSON_AUTH_SECRET_KEYS:
        merged.pop(key, None)

    if _inherits_config(profile):
        _project_claude_mcp_config(
            source_payload,
            merged,
            project_root=project_root,
            workspace_path=workspace_path,
        )
    else:
        _strip_claude_mcp_config(
            merged,
            project_root=project_root,
            workspace_path=workspace_path,
        )

    _merge_profile_mcp_servers(merged, profile=profile)

    if not _inherits_auth(profile):
        for key in _CLAUDE_JSON_AUTH_METADATA_KEYS:
            merged.pop(key, None)
        return merged

    for key in (*_CLAUDE_JSON_AUTH_METADATA_KEYS, *_CLAUDE_JSON_AUTH_COMPANION_KEYS):
        if key in source_payload:
            merged[key] = _clone_jsonish(source_payload[key])
    return merged


def _project_claude_mcp_config(
    source_payload: dict[str, object],
    merged: dict[str, object],
    *,
    project_root: Path | None,
    workspace_path: Path | None,
) -> None:
    for key in _CLAUDE_JSON_MCP_ROOT_KEYS:
        value = source_payload.get(key)
        if isinstance(value, dict):
            merged[key] = _clone_jsonish(value)
        else:
            merged.pop(key, None)

    target_key = _claude_project_target_key(project_root=project_root, workspace_path=workspace_path)
    if not target_key:
        return

    selected = _selected_source_project_mcp_config(
        source_payload,
        project_root=project_root,
        workspace_path=workspace_path,
    )
    _refresh_project_mcp_record(merged, target_key=target_key, selected=selected)


def _merge_profile_mcp_servers(merged: dict[str, object], *, profile) -> None:
    profile_servers = _profile_mcp_servers(profile)
    if not profile_servers:
        return

    existing = merged.get('mcpServers')
    servers = dict(existing) if isinstance(existing, dict) else {}
    for raw_name, raw_config in profile_servers.items():
        name = str(raw_name or '').strip()
        if not name:
            continue
        if _mcp_server_disabled(raw_config):
            servers.pop(name, None)
            continue
        payload = _clone_jsonish(raw_config)
        if not isinstance(payload, dict):
            continue
        payload.pop('enabled', None)
        servers[name] = payload

    if servers:
        merged['mcpServers'] = servers
    else:
        merged.pop('mcpServers', None)


def _profile_mcp_servers(profile) -> dict[str, object]:
    if profile is None:
        return {}
    raw = getattr(profile, 'mcp_servers', None)
    return dict(raw) if isinstance(raw, dict) else {}


def _mcp_server_disabled(value: object) -> bool:
    return isinstance(value, dict) and value.get('enabled') is False


def _strip_claude_mcp_config(
    merged: dict[str, object],
    *,
    project_root: Path | None,
    workspace_path: Path | None,
) -> None:
    for key in _CLAUDE_JSON_MCP_ROOT_KEYS:
        merged.pop(key, None)
    target_key = _claude_project_target_key(project_root=project_root, workspace_path=workspace_path)
    if target_key:
        _refresh_project_mcp_record(merged, target_key=target_key, selected={})


def _selected_source_project_mcp_config(
    source_payload: dict[str, object],
    *,
    project_root: Path | None,
    workspace_path: Path | None,
) -> dict[str, object]:
    for key in _claude_project_source_keys(project_root=project_root, workspace_path=workspace_path):
        selected: dict[str, object] = {}
        for record in _source_project_records(source_payload, key):
            for mcp_key in _CLAUDE_JSON_MCP_PROJECT_KEYS:
                if mcp_key in record:
                    selected[mcp_key] = _clone_jsonish(record[mcp_key])
        if selected:
            return selected
    return {}


def _refresh_project_mcp_record(
    merged: dict[str, object],
    *,
    target_key: str,
    selected: dict[str, object],
) -> None:
    projects = merged.get('projects')
    if not isinstance(projects, dict):
        projects = {}
    else:
        projects = dict(projects)

    project_record = _project_record_copy(projects.get(target_key))
    top_record = _project_record_copy(merged.get(target_key))
    _strip_project_mcp_keys(project_record)
    _strip_project_mcp_keys(top_record)

    for key, value in selected.items():
        project_record[key] = _clone_jsonish(value)
        top_record[key] = _clone_jsonish(value)

    if project_record:
        projects[target_key] = project_record
    else:
        projects.pop(target_key, None)

    if projects:
        merged['projects'] = projects
    else:
        merged.pop('projects', None)

    if top_record:
        merged[target_key] = top_record
    else:
        merged.pop(target_key, None)


def _project_record_copy(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def _strip_project_mcp_keys(record: dict[str, object]) -> None:
    for key in _CLAUDE_JSON_MCP_PROJECT_KEYS:
        record.pop(key, None)


def _source_project_records(source_payload: dict[str, object], key: str) -> tuple[dict[str, object], ...]:
    records: list[dict[str, object]] = []
    top_record = source_payload.get(key)
    if isinstance(top_record, dict):
        records.append(top_record)
    projects = source_payload.get('projects')
    if isinstance(projects, dict):
        project_record = projects.get(key)
        if isinstance(project_record, dict):
            records.append(project_record)
    return tuple(records)


def _claude_project_target_key(
    *,
    project_root: Path | None,
    workspace_path: Path | None,
) -> str | None:
    for candidate in (workspace_path, project_root):
        key = _claude_path_key(candidate)
        if key:
            return key
    return None


def _claude_project_source_keys(
    *,
    project_root: Path | None,
    workspace_path: Path | None,
) -> tuple[str, ...]:
    keys: list[str] = []
    for candidate in (workspace_path, project_root):
        for key in _claude_path_key_candidates(candidate):
            if key and key not in keys:
                keys.append(key)
    return tuple(keys)


def _claude_path_key_candidates(value: Path | None) -> tuple[str, ...]:
    if value is None:
        return ()
    keys: list[str] = []
    path = Path(value).expanduser()
    for candidate in (path, _normalize_path(path)):
        if candidate is None:
            continue
        key = str(candidate)
        if key and key not in keys:
            keys.append(key)
    return tuple(keys)


def _claude_path_key(value: Path | None) -> str | None:
    candidates = _claude_path_key_candidates(value)
    return candidates[-1] if candidates else None


def _clone_jsonish(value: object) -> object:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False))
    except Exception:
        return value


def _materialize_macos_keychain_auth(target_layout: ClaudeHomeLayout) -> None:
    payload = _read_macos_keychain_claude_credentials()
    if not payload:
        return
    _write_json_object(target_layout.credentials_path, payload, mode=0o600)


def _read_macos_keychain_claude_credentials() -> dict[str, object] | None:
    if platform.system() != 'Darwin':
        return None
    security = shutil.which('security') or '/usr/bin/security'
    account = _macos_keychain_account()
    if not account:
        return None

    for service in _macos_keychain_services():
        try:
            result = subprocess.run(
                [security, 'find-generic-password', '-a', account, '-s', service, '-w'],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except Exception:
            continue
        if result.returncode != 0:
            continue
        payload = _json_object_from_text(result.stdout)
        if isinstance(payload.get('claudeAiOauth'), dict):
            return payload
    return None


def _macos_keychain_account() -> str:
    account = str(os.environ.get('USER') or '').strip()
    if account:
        return account
    try:
        return str(getpass.getuser() or '').strip()
    except Exception:
        return ''


def _macos_keychain_services() -> tuple[str, ...]:
    services = list(_MACOS_KEYCHAIN_CLAUDE_SERVICES)
    custom_service = 'Claude Code-custom-oauth'
    if os.environ.get('CLAUDE_CODE_CUSTOM_OAUTH_URL') and custom_service in services:
        services.remove(custom_service)
        services.insert(1, custom_service)
    # Allow callers to bind a CCB stack to a specific keychain entry,
    # e.g. when isolating multiple Claude accounts on one machine.
    override = os.environ.get('CCB_KEYCHAIN_SERVICE_OVERRIDE')
    if override:
        services.insert(0, override)
    return tuple(services)


def _projected_settings_payload(source_settings_path: Path, *, profile) -> dict[str, object] | None:
    source_payload = _read_json_object(source_settings_path)
    if not source_payload:
        return {} if _needs_settings_stub(profile) else None

    env_payload = dict(source_payload.get('env') or {}) if isinstance(source_payload.get('env'), dict) else {}
    if not _inherits_api(profile):
        for key in provider_api_env_keys('claude'):
            env_payload.pop(key, None)
    elif not _inherits_auth(profile):
        env_payload.pop('ANTHROPIC_AUTH_TOKEN', None)
        env_payload.pop('ANTHROPIC_API_KEY', None)

    include_config = _inherits_config(profile)
    payload: dict[str, object] = {}
    if include_config:
        payload.update(source_payload)
    if env_payload:
        payload['env'] = env_payload
    else:
        payload.pop('env', None)
    if payload:
        return payload
    return {} if _needs_settings_stub(profile) else None


def _merge_settings_payload(
    projected: dict[str, object] | None,
    *,
    existing: dict[str, object],
    profile=None,
    auto_permission: bool = False,
) -> dict[str, object] | None:
    existing_payload = dict(existing or {})
    projected_payload = dict(projected or {})
    merged = dict(projected_payload)
    _carry_forward_managed_auth_env(merged, existing_payload, profile=profile)

    for key in _CLAUDE_RUNTIME_SETTINGS_KEYS:
        value = existing_payload.get(key)
        if value is not None:
            if key == 'enabledPlugins':
                enabled_plugins = _merge_enabled_plugins_payload(projected_payload.get('enabledPlugins'), value)
                if enabled_plugins:
                    merged[key] = enabled_plugins
                else:
                    merged.pop(key, None)
                continue
            if key == 'hooks':
                hooks = _merge_hooks_payload(projected_payload.get('hooks'), value)
                if hooks:
                    merged[key] = hooks
                else:
                    merged.pop(key, None)
                continue
            if key == 'permissions' and auto_permission and _is_ccb_only_permission_payload(value):
                continue
            merged[key] = value

    if merged:
        return merged
    if projected is not None:
        return {}
    return None


def _merge_enabled_plugins_payload(projected: object, existing: object) -> dict[str, object]:
    existing_plugins = _settings_mapping_copy(existing)
    projected_plugins = _settings_mapping_copy(projected)
    if not existing_plugins:
        return projected_plugins
    if not projected_plugins:
        return existing_plugins
    merged = dict(existing_plugins)
    merged.update(projected_plugins)
    return merged


def _merge_hooks_payload(projected: object, existing: object) -> dict[str, object]:
    projected_hooks = _settings_mapping_copy(projected)
    existing_hooks = _settings_mapping_copy(existing)
    if not projected_hooks:
        return existing_hooks
    if not existing_hooks:
        return projected_hooks

    merged = dict(projected_hooks)
    for event_name, existing_groups in existing_hooks.items():
        projected_groups = merged.get(event_name)
        if not isinstance(existing_groups, list):
            if event_name not in merged:
                merged[event_name] = _clone_jsonish(existing_groups)
            continue
        if not isinstance(projected_groups, list):
            if event_name in merged:
                continue
            merged[event_name] = [_clone_jsonish(group) for group in existing_groups]
            continue
        fingerprints = {_json_fingerprint(group) for group in projected_groups}
        groups = list(projected_groups)
        for group in existing_groups:
            fingerprint = _json_fingerprint(group)
            if fingerprint in fingerprints:
                continue
            groups.append(_clone_jsonish(group))
            fingerprints.add(fingerprint)
        merged[event_name] = groups
    return merged


def _settings_mapping_copy(value: object) -> dict[str, object]:
    return dict(_clone_jsonish(value)) if isinstance(value, dict) else {}


def _json_fingerprint(value: object) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    except Exception:
        return repr(value)


def _is_ccb_only_permission_payload(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    allow = value.get('allow')
    if not isinstance(allow, list):
        return False
    normalized = tuple(str(item or '').strip() for item in allow if str(item or '').strip())
    if not normalized:
        return False
    if any(not item.startswith(_CLAUDE_CCB_PERMISSION_PREFIX) for item in normalized):
        return False
    deny = value.get('deny')
    return deny in (None, [])


def _carry_forward_managed_auth_env(
    merged_payload: dict[str, object],
    existing_payload: dict[str, object],
    *,
    profile=None,
) -> None:
    if not _inherits_auth(profile):
        return
    existing_env = _read_env_payload(existing_payload)
    if not existing_env:
        return
    merged_env = _read_env_payload(merged_payload)
    if _has_projected_auth_authority(merged_env):
        return

    preserved_any = False
    for key in _CLAUDE_AUTH_ENV_KEYS:
        value = existing_env.get(key)
        if _env_value_present(value):
            merged_env[key] = value
            preserved_any = True
    if _inherits_api(profile):
        for key in _CLAUDE_API_AUTH_ENV_KEYS:
            value = existing_env.get(key)
            if _env_value_present(value):
                merged_env[key] = value
                preserved_any = True
        if preserved_any:
            for key in _CLAUDE_ROUTE_ENV_KEYS:
                if _env_value_present(merged_env.get(key)):
                    continue
                value = existing_env.get(key)
                if _env_value_present(value):
                    merged_env[key] = value

    if merged_env:
        merged_payload['env'] = merged_env
    else:
        merged_payload.pop('env', None)


def _read_env_payload(payload: dict[str, object]) -> dict[str, object]:
    env_payload = payload.get('env')
    return dict(env_payload) if isinstance(env_payload, dict) else {}


def _has_projected_auth_authority(env_payload: dict[str, object]) -> bool:
    return any(_env_value_present(env_payload.get(key)) for key in (*_CLAUDE_AUTH_ENV_KEYS, *_CLAUDE_API_AUTH_ENV_KEYS))


def _env_value_present(value: object) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    return value is not None


def _needs_settings_stub(profile) -> bool:
    return bool(_inherits_api(profile) or _inherits_auth(profile) or _inherits_config(profile))


def _inherits_api(profile) -> bool:
    return True if profile is None else bool(getattr(profile, 'inherit_api', True))


def _inherits_auth(profile) -> bool:
    return True if profile is None else bool(getattr(profile, 'inherit_auth', True))


def _inherits_config(profile) -> bool:
    return True if profile is None else bool(getattr(profile, 'inherit_config', True))


def _inherits_skills(profile) -> bool:
    return True if profile is None else bool(getattr(profile, 'inherit_skills', True))


def _inherits_commands(profile) -> bool:
    return True if profile is None else bool(getattr(profile, 'inherit_commands', True))


def _inherits_memory(profile) -> bool:
    return True if profile is None else bool(getattr(profile, 'inherit_memory', True))


def _read_json_object(path: Path) -> dict[str, object]:
    try:
        data = _json_object_from_text(path.read_text(encoding='utf-8'))
    except Exception:
        return {}
    return data


def _json_object_from_text(value: str) -> dict[str, object]:
    try:
        data = json.loads(str(value or '').strip())
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _write_json_object(path: Path, payload: dict[str, object], *, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )
    if mode is not None:
        try:
            path.chmod(mode)
        except Exception:
            pass


def _payload_mentions_home_asset(value: object, dirname: str) -> bool:
    if isinstance(value, str):
        return any(
            marker in value
            for marker in (
                f'$HOME/{dirname}/',
                f'${{HOME}}/{dirname}/',
                f'~/{dirname}/',
            )
        )
    if isinstance(value, dict):
        return any(_payload_mentions_home_asset(child, dirname) for child in value.values())
    if isinstance(value, list):
        return any(_payload_mentions_home_asset(child, dirname) for child in value)
    return False


def _ensure_trust_file(path: Path) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{}\n', encoding='utf-8')


def _copy_if_missing(source: Path, target: Path) -> None:
    if target.exists() or not source.is_file():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(source, target)
    except Exception:
        pass


def _sync_file(source: Path, target: Path) -> None:
    if not source.is_file():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(source, target)
    except Exception:
        pass


def _remove_file(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except Exception:
        pass


def _source_auth_paths(source_home: Path, target_layout: ClaudeHomeLayout) -> tuple[tuple[Path, Path], ...]:
    return (
        (source_home / '.claude' / '.credentials.json', target_layout.credentials_path),
        (source_home / '.config' / 'claude-code' / 'auth.json', target_layout.auth_path),
    )


def _sync_tree(source: Path, target: Path) -> None:
    if not source.is_dir():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copytree(source, target, dirs_exist_ok=True)
    except Exception:
        pass


def _route_inherited_tree(source: Path, target: Path, *, enabled: bool, label: str) -> None:
    route_projected_tree(source, target, enabled=enabled, label=label, allow_unmarked_replace=True)


def _system_home_root() -> Path:
    return current_provider_source_home()


__all__ = ['materialize_claude_home_config', 'prepare_claude_home_overrides', 'resolve_claude_home_layout']
