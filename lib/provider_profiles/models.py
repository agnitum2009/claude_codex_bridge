from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


_VALID_PROFILE_MODES = {"inherit", "overlay", "isolated"}


@dataclass(frozen=True)
class ProviderProfileSpec:
    mode: str = "inherit"
    home: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    mcp_servers: dict[str, dict[str, Any]] = field(default_factory=dict)
    inherit_api: bool = True
    inherit_auth: bool = True
    inherit_config: bool = True
    inherit_skills: bool = True
    inherit_commands: bool = True
    inherit_memory: bool = True

    def __post_init__(self) -> None:
        mode = str(self.mode or "inherit").strip().lower() or "inherit"
        if mode not in _VALID_PROFILE_MODES:
            raise ValueError(f"provider_profile.mode must be one of: {', '.join(sorted(_VALID_PROFILE_MODES))}")
        object.__setattr__(self, 'mode', mode)
        home = str(self.home).strip() if self.home is not None else None
        object.__setattr__(self, 'home', home or None)
        object.__setattr__(self, 'env', {str(key): str(value) for key, value in dict(self.env).items()})
        object.__setattr__(self, 'mcp_servers', _normalize_mcp_servers(self.mcp_servers))

    def to_record(self) -> dict[str, Any]:
        payload = {
            'mode': self.mode,
            'home': self.home,
            'env': dict(self.env),
            'inherit_api': bool(self.inherit_api),
            'inherit_auth': bool(self.inherit_auth),
            'inherit_config': bool(self.inherit_config),
            'inherit_skills': bool(self.inherit_skills),
            'inherit_commands': bool(self.inherit_commands),
            'inherit_memory': bool(self.inherit_memory),
        }
        if self.mcp_servers:
            payload['mcp_servers'] = _clone_jsonish_mapping(self.mcp_servers)
        return payload


@dataclass(frozen=True)
class ResolvedProviderProfile:
    provider: str
    agent_name: str
    mode: str = "inherit"
    profile_root: str | None = None
    runtime_home: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    mcp_servers: dict[str, dict[str, Any]] = field(default_factory=dict)
    inherit_api: bool = True
    inherit_auth: bool = True
    inherit_config: bool = True
    inherit_skills: bool = True
    inherit_commands: bool = True
    inherit_memory: bool = True

    def __post_init__(self) -> None:
        provider = str(self.provider or '').strip().lower()
        if not provider:
            raise ValueError('provider cannot be empty')
        agent_name = str(self.agent_name or '').strip().lower()
        if not agent_name:
            raise ValueError('agent_name cannot be empty')
        mode = str(self.mode or 'inherit').strip().lower() or 'inherit'
        if mode not in _VALID_PROFILE_MODES:
            raise ValueError(f"mode must be one of: {', '.join(sorted(_VALID_PROFILE_MODES))}")
        object.__setattr__(self, 'provider', provider)
        object.__setattr__(self, 'agent_name', agent_name)
        object.__setattr__(self, 'mode', mode)
        object.__setattr__(self, 'profile_root', _normalize_path_text(self.profile_root))
        object.__setattr__(self, 'runtime_home', _normalize_path_text(self.runtime_home))
        object.__setattr__(self, 'env', {str(key): str(value) for key, value in dict(self.env).items()})
        object.__setattr__(self, 'mcp_servers', _normalize_mcp_servers(self.mcp_servers))

    @property
    def profile_root_path(self) -> Path | None:
        if not self.profile_root:
            return None
        return Path(self.profile_root)

    @property
    def runtime_home_path(self) -> Path | None:
        if not self.runtime_home:
            return None
        return Path(self.runtime_home)

    def to_record(self) -> dict[str, Any]:
        payload = {
            'provider': self.provider,
            'agent_name': self.agent_name,
            'mode': self.mode,
            'profile_root': self.profile_root,
            'runtime_home': self.runtime_home,
            'env': dict(self.env),
            'inherit_api': bool(self.inherit_api),
            'inherit_auth': bool(self.inherit_auth),
            'inherit_config': bool(self.inherit_config),
            'inherit_skills': bool(self.inherit_skills),
            'inherit_commands': bool(self.inherit_commands),
            'inherit_memory': bool(self.inherit_memory),
        }
        if self.mcp_servers:
            payload['mcp_servers'] = _clone_jsonish_mapping(self.mcp_servers)
        return payload

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "ResolvedProviderProfile":
        return cls(
            provider=str(record.get('provider') or ''),
            agent_name=str(record.get('agent_name') or ''),
            mode=str(record.get('mode') or 'inherit'),
            profile_root=record.get('profile_root'),
            runtime_home=record.get('runtime_home'),
            env=dict(record.get('env') or {}),
            mcp_servers=dict(record.get('mcp_servers') or {}),
            inherit_api=bool(record.get('inherit_api', True)),
            inherit_auth=bool(record.get('inherit_auth', True)),
            inherit_config=bool(record.get('inherit_config', True)),
            inherit_skills=bool(record.get('inherit_skills', True)),
            inherit_commands=bool(record.get('inherit_commands', True)),
            inherit_memory=bool(record.get('inherit_memory', True)),
        )


def _normalize_path_text(value: object) -> str | None:
    raw = str(value or '').strip()
    if not raw:
        return None
    try:
        path = Path(raw).expanduser()
        try:
            path = path.resolve()
        except Exception:
            path = path.absolute()
        return str(path)
    except Exception:
        return raw


def _normalize_mcp_servers(value: object) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, dict[str, Any]] = {}
    for raw_name, raw_payload in value.items():
        name = str(raw_name or '').strip()
        if not name or not isinstance(raw_payload, dict):
            continue
        normalized[name] = _clone_jsonish_mapping(raw_payload)
    return normalized


def _clone_jsonish_mapping(payload: dict[object, object]) -> dict[str, Any]:
    return {str(key): _clone_jsonish(value) for key, value in payload.items()}


def _clone_jsonish(value: object) -> Any:
    if isinstance(value, dict):
        return _clone_jsonish_mapping(value)
    if isinstance(value, (list, tuple)):
        return [_clone_jsonish(item) for item in value]
    return value


__all__ = ['ProviderProfileSpec', 'ResolvedProviderProfile']
