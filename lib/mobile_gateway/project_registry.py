from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Callable

from ccbd.socket_client import CcbdClient
from storage.atomic import atomic_write_json


@dataclass(frozen=True)
class MobileGatewayProject:
    project_id: str
    project_root: Path
    ccbd_client_factory: Callable[[], object]
    display_name: str | None = None

    def __post_init__(self) -> None:
        project_id = str(self.project_id or '').strip()
        if not project_id:
            raise ValueError('project_id cannot be empty')
        object.__setattr__(self, 'project_id', project_id)
        object.__setattr__(self, 'project_root', Path(self.project_root))
        display_name = str(self.display_name or '').strip() or None
        object.__setattr__(self, 'display_name', display_name)

    def client(self):
        return self.ccbd_client_factory()

    @property
    def public_display_name(self) -> str:
        return self.display_name or self.project_root.name or self.project_id


class MobileGatewayProjectRegistry:
    def __init__(self, projects: list[MobileGatewayProject] | tuple[MobileGatewayProject, ...]) -> None:
        ordered: list[MobileGatewayProject] = []
        by_id: dict[str, MobileGatewayProject] = {}
        for project in projects:
            if project.project_id in by_id:
                raise ValueError(f'duplicate mobile gateway project: {project.project_id}')
            ordered.append(project)
            by_id[project.project_id] = project
        if not ordered:
            raise ValueError('mobile gateway project registry cannot be empty')
        self._ordered = tuple(ordered)
        self._by_id = dict(by_id)

    @classmethod
    def current_project(
        cls,
        *,
        project_id: str,
        project_root: Path,
        ccbd_client_factory: Callable[[], object],
    ) -> MobileGatewayProjectRegistry:
        return cls(
            [
                MobileGatewayProject(
                    project_id=project_id,
                    project_root=project_root,
                    ccbd_client_factory=ccbd_client_factory,
                )
            ]
        )

    @property
    def default_project(self) -> MobileGatewayProject:
        return self._ordered[0]

    def projects(self) -> tuple[MobileGatewayProject, ...]:
        return self._ordered

    def get(self, project_id: str) -> MobileGatewayProject | None:
        return self._by_id.get(str(project_id or '').strip())


HOST_PROJECT_REGISTRY_RECORD_TYPE = 'ccb_mobile_host_project_registry'
HOST_PROJECT_REGISTRY_FILENAME = 'projects.json'


def mobile_host_state_dir() -> Path:
    explicit = str(os.environ.get('CCB_MOBILE_HOST_STATE_HOME') or '').strip()
    if explicit:
        return Path(explicit).expanduser()
    xdg_state_home = str(os.environ.get('XDG_STATE_HOME') or '').strip()
    if xdg_state_home:
        return Path(xdg_state_home).expanduser() / 'ccb' / 'mobile'
    return Path.home().expanduser() / '.local' / 'state' / 'ccb' / 'mobile'


def mobile_host_project_registry_path(*, state_dir: Path | None = None) -> Path:
    return Path(state_dir or mobile_host_state_dir()).expanduser() / HOST_PROJECT_REGISTRY_FILENAME


def publish_mobile_gateway_project(
    *,
    project_id: str,
    project_root: Path,
    ccbd_socket_path: Path,
    display_name: str | None = None,
    registry_path: Path | None = None,
    updated_at: str | None = None,
) -> None:
    path = Path(registry_path or mobile_host_project_registry_path()).expanduser()
    payload = _read_registry_payload(path)
    projects = _registry_projects(payload)
    normalized = MobileGatewayProject(
        project_id=project_id,
        project_root=project_root,
        ccbd_client_factory=lambda: None,
        display_name=display_name,
    )
    projects[normalized.project_id] = {
        'project_id': normalized.project_id,
        'display_name': normalized.public_display_name,
        'project_root': str(normalized.project_root),
        'ccbd_socket_path': str(Path(ccbd_socket_path).expanduser()),
        **({'updated_at': str(updated_at)} if updated_at else {}),
    }
    atomic_write_json(
        path,
        {
            'schema_version': 1,
            'record_type': HOST_PROJECT_REGISTRY_RECORD_TYPE,
            'projects': [projects[key] for key in sorted(projects)],
        },
    )


def load_mobile_gateway_project_registry(
    *,
    registry_path: Path | None = None,
) -> MobileGatewayProjectRegistry:
    path = Path(registry_path or mobile_host_project_registry_path()).expanduser()
    payload = _read_registry_payload(path)
    projects: list[MobileGatewayProject] = []
    for record in _registry_projects(payload).values():
        project = _project_from_record(record)
        if project is not None:
            projects.append(project)
    return MobileGatewayProjectRegistry(projects)


def _read_registry_payload(path: Path) -> dict[str, object]:
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {}
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    if str(data.get('record_type') or '').strip() != HOST_PROJECT_REGISTRY_RECORD_TYPE:
        return {}
    return data


def _registry_projects(payload: dict[str, object]) -> dict[str, dict[str, object]]:
    raw = payload.get('projects')
    records = raw if isinstance(raw, list) else []
    projects: dict[str, dict[str, object]] = {}
    for item in records:
        if not isinstance(item, dict):
            continue
        project_id = str(item.get('project_id') or '').strip()
        if not project_id:
            continue
        projects[project_id] = dict(item)
    return projects


def _project_from_record(record: dict[str, object]) -> MobileGatewayProject | None:
    project_id = str(record.get('project_id') or '').strip()
    root_text = str(record.get('project_root') or '').strip()
    socket_text = str(record.get('ccbd_socket_path') or '').strip()
    if not project_id or not root_text or not socket_text:
        return None
    project_root = Path(root_text).expanduser()
    socket_path = Path(socket_text).expanduser()
    if not project_root.is_absolute() or not socket_path.is_absolute():
        return None
    display_name = str(record.get('display_name') or '').strip() or None
    return MobileGatewayProject(
        project_id=project_id,
        project_root=project_root,
        display_name=display_name,
        ccbd_client_factory=lambda socket_path=socket_path: CcbdClient(socket_path),
    )


__all__ = [
    'HOST_PROJECT_REGISTRY_FILENAME',
    'HOST_PROJECT_REGISTRY_RECORD_TYPE',
    'MobileGatewayProject',
    'MobileGatewayProjectRegistry',
    'load_mobile_gateway_project_registry',
    'mobile_host_project_registry_path',
    'mobile_host_state_dir',
    'publish_mobile_gateway_project',
]
