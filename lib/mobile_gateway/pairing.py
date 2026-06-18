from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import secrets
import threading
from typing import Callable

_SCHEMA_VERSION = 1
_PAIRING_HASH_PREFIX = 'ccb-mobile-pairing-v1:'
_DEVICE_HASH_PREFIX = 'ccb-mobile-device-v1:'
_DEFAULT_PAIRING_EXPIRES_SECONDS = 10 * 60
_DEFAULT_DEVICE_SCOPES = ('view',)


class MobileGatewayPairingError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 400, reason: str = 'invalid') -> None:
        super().__init__(message)
        self.status_code = int(status_code)
        self.reason = str(reason or 'invalid')


@dataclass(frozen=True)
class AuthenticatedDevice:
    record: dict[str, object]

    @property
    def device_id(self) -> str:
        return str(self.record.get('device_id') or '')

    @property
    def scopes(self) -> set[str]:
        return _scope_set(self.record.get('scopes'))

    def public_payload(self) -> dict[str, object]:
        return _public_device(self.record)


class MobileGatewayPairingStore:
    def __init__(
        self,
        mobile_dir: Path,
        *,
        clock: Callable[[], datetime] | None = None,
        token_factory: Callable[[int], str] | None = None,
        id_factory: Callable[[str], str] | None = None,
    ) -> None:
        self._mobile_dir = Path(mobile_dir)
        self._clock = clock or _utc_now
        self._token_factory = token_factory or _token_urlsafe
        self._id_factory = id_factory or _random_id
        self._lock = threading.RLock()

    @property
    def gateway_path(self) -> Path:
        return self._mobile_dir / 'gateway.json'

    @property
    def devices_path(self) -> Path:
        return self._mobile_dir / 'devices.json'

    @property
    def pairing_tokens_path(self) -> Path:
        return self._mobile_dir / 'pairing-tokens.jsonl'

    @property
    def audit_path(self) -> Path:
        return self._mobile_dir / 'audit.jsonl'

    def write_gateway_state(
        self,
        *,
        project_id: str,
        gateway_url: str,
        route_provider: str,
        capabilities: Iterable[str],
    ) -> dict[str, object]:
        now = _iso(self._clock())
        payload = {
            'schema_version': _SCHEMA_VERSION,
            'project_id': str(project_id),
            'gateway_url': str(gateway_url),
            'route_provider': str(route_provider),
            'capabilities': sorted({str(item) for item in capabilities}),
            'updated_at': now,
        }
        with self._lock:
            self._ensure_dir()
            _write_json(self.gateway_path, payload)
        return payload

    def create_pairing_payload(
        self,
        *,
        project_id: str,
        gateway_url: str,
        route_provider: str = 'lan',
        scopes: Iterable[str] = _DEFAULT_DEVICE_SCOPES,
        expires_seconds: int = _DEFAULT_PAIRING_EXPIRES_SECONDS,
    ) -> dict[str, object]:
        now = self._clock()
        expires_at = now + timedelta(seconds=max(1, int(expires_seconds)))
        pairing_code = self._token_factory(18)
        pairing_id = self._id_factory('pair')
        scope_list = _scope_list(scopes)
        record = {
            'schema_version': _SCHEMA_VERSION,
            'pairing_id': pairing_id,
            'project_id': str(project_id),
            'token_hash': _token_hash(_PAIRING_HASH_PREFIX, pairing_code),
            'scopes': scope_list,
            'route_provider': str(route_provider),
            'gateway_url': str(gateway_url),
            'created_at': _iso(now),
            'expires_at': _iso(expires_at),
            'claimed_at': None,
            'claimed_by_device_id': None,
            'revoked_at': None,
        }
        with self._lock:
            self._ensure_dir()
            _append_jsonl(self.pairing_tokens_path, record)
            self._append_audit(
                event='pairing_token_created',
                result='ok',
                project_id=str(project_id),
                pairing_id=pairing_id,
                scopes=scope_list,
            )
        return {
            'schema_version': _SCHEMA_VERSION,
            'pairing_id': pairing_id,
            'pairing_code': pairing_code,
            'project_id': str(project_id),
            'route_provider': str(route_provider),
            'gateway_url': str(gateway_url),
            'claim_endpoint': f'{str(gateway_url).rstrip("/")}/v1/pairing/claim',
            'scopes': scope_list,
            'expires_at': _iso(expires_at),
        }

    def claim_pairing(
        self,
        *,
        pairing_code: str,
        device_name: str,
        requested_device_id: str | None = None,
    ) -> dict[str, object]:
        code = str(pairing_code or '').strip()
        if not code:
            raise MobileGatewayPairingError('pairing_code is required', status_code=400, reason='missing_code')
        name = str(device_name or '').strip() or 'Mobile device'
        now = self._clock()
        token_hash = _token_hash(_PAIRING_HASH_PREFIX, code)
        with self._lock:
            pairings = self._pairing_state_by_id()
            record = next(
                (item for item in pairings.values() if item.get('token_hash') == token_hash),
                None,
            )
            if not record:
                self._append_audit(event='pairing_claim_denied', result='denied', reason='invalid_code')
                raise MobileGatewayPairingError('invalid pairing_code', status_code=401, reason='invalid_code')
            pairing_id = str(record.get('pairing_id') or '')
            project_id = str(record.get('project_id') or '')
            if record.get('revoked_at'):
                self._append_audit(
                    event='pairing_claim_denied',
                    result='denied',
                    project_id=project_id,
                    pairing_id=pairing_id,
                    reason='revoked',
                )
                raise MobileGatewayPairingError('pairing_code revoked', status_code=410, reason='revoked')
            if record.get('claimed_at') or record.get('claimed_by_device_id'):
                self._append_audit(
                    event='pairing_claim_denied',
                    result='denied',
                    project_id=project_id,
                    pairing_id=pairing_id,
                    reason='already_claimed',
                )
                raise MobileGatewayPairingError('pairing_code already claimed', status_code=409, reason='already_claimed')
            expires_at = _parse_utc(record.get('expires_at'))
            if expires_at is not None and now > expires_at:
                self._append_audit(
                    event='pairing_claim_denied',
                    result='denied',
                    project_id=project_id,
                    pairing_id=pairing_id,
                    reason='expired',
                )
                raise MobileGatewayPairingError('pairing_code expired', status_code=410, reason='expired')

            device_token = self._token_factory(32)
            device_id = _clean_id(requested_device_id) or self._id_factory('dev')
            existing_device = next(
                (item for item in self._read_devices() if item.get('device_id') == device_id and not item.get('revoked_at')),
                None,
            )
            if existing_device:
                self._append_audit(
                    event='pairing_claim_denied',
                    result='denied',
                    project_id=project_id,
                    pairing_id=pairing_id,
                    device_id=device_id,
                    reason='device_id_exists',
                )
                raise MobileGatewayPairingError('device_id already exists', status_code=409, reason='device_id_exists')

            device_record = {
                'schema_version': _SCHEMA_VERSION,
                'device_id': device_id,
                'name': name,
                'project_id': project_id,
                'pairing_id': pairing_id,
                'token_hash': _token_hash(_DEVICE_HASH_PREFIX, device_token),
                'scopes': _scope_list(record.get('scopes')),
                'route_provider': str(record.get('route_provider') or 'lan'),
                'gateway_url': str(record.get('gateway_url') or ''),
                'created_at': _iso(now),
                'last_seen_at': None,
                'revoked_at': None,
            }
            devices = [item for item in self._read_devices() if item.get('device_id') != device_id]
            devices.append(device_record)
            _write_json(self.devices_path, {'schema_version': _SCHEMA_VERSION, 'devices': devices})

            updated_record = dict(record)
            updated_record['claimed_at'] = _iso(now)
            updated_record['claimed_by_device_id'] = device_id
            _append_jsonl(self.pairing_tokens_path, updated_record)
            self._append_audit(
                event='pairing_claimed',
                result='ok',
                project_id=project_id,
                pairing_id=pairing_id,
                device_id=device_id,
                scopes=device_record['scopes'],
            )

        return {
            'schema_version': _SCHEMA_VERSION,
            'status': 'ok',
            'device': _public_device(device_record),
            'device_token': device_token,
            'host_profile': {
                'host_id': project_id,
                'project_id': project_id,
                'device_id': device_id,
                'route_provider': device_record['route_provider'],
                'gateway_url': device_record['gateway_url'],
                'scopes': list(device_record['scopes']),
            },
        }

    def authenticate_device(
        self,
        device_token: str,
        *,
        required_scopes: Iterable[str] = (),
    ) -> AuthenticatedDevice:
        token = str(device_token or '').strip()
        if not token:
            raise MobileGatewayPairingError('device bearer token is required', status_code=401, reason='missing_token')
        token_hash = _token_hash(_DEVICE_HASH_PREFIX, token)
        required = _scope_set(required_scopes)
        with self._lock:
            devices = self._read_devices()
            for index, record in enumerate(devices):
                if record.get('token_hash') != token_hash:
                    continue
                device_id = str(record.get('device_id') or '')
                project_id = str(record.get('project_id') or '')
                if record.get('revoked_at'):
                    self._append_audit(
                        event='device_auth_denied',
                        result='denied',
                        project_id=project_id,
                        device_id=device_id,
                        reason='revoked',
                    )
                    raise MobileGatewayPairingError('device token revoked', status_code=401, reason='revoked')
                scopes = _scope_set(record.get('scopes'))
                missing = sorted(required - scopes)
                if missing:
                    self._append_audit(
                        event='device_auth_denied',
                        result='denied',
                        project_id=project_id,
                        device_id=device_id,
                        reason='missing_scope',
                        scopes=missing,
                    )
                    raise MobileGatewayPairingError('device scope denied', status_code=403, reason='missing_scope')
                updated = dict(record)
                updated['last_seen_at'] = _iso(self._clock())
                devices[index] = updated
                _write_json(self.devices_path, {'schema_version': _SCHEMA_VERSION, 'devices': devices})
                self._append_audit(
                    event='device_auth_ok',
                    result='ok',
                    project_id=project_id,
                    device_id=device_id,
                    scopes=sorted(required),
                )
                return AuthenticatedDevice(record=updated)
        self._append_audit(event='device_auth_denied', result='denied', reason='invalid_token')
        raise MobileGatewayPairingError('invalid device token', status_code=401, reason='invalid_token')

    def revoke_device(self, *, device_id: str, device_token: str) -> dict[str, object]:
        requested = _clean_id(device_id)
        if not requested:
            raise MobileGatewayPairingError('device_id is required', status_code=400, reason='missing_device_id')
        auth = self.authenticate_device(device_token)
        if auth.device_id != requested:
            self._append_audit(
                event='device_revoke_denied',
                result='denied',
                project_id=str(auth.record.get('project_id') or ''),
                device_id=auth.device_id,
                target_device_id=requested,
                reason='self_revoke_only',
            )
            raise MobileGatewayPairingError('device can only revoke itself in G2', status_code=403, reason='self_revoke_only')
        now = _iso(self._clock())
        with self._lock:
            devices = self._read_devices()
            for index, record in enumerate(devices):
                if record.get('device_id') != requested:
                    continue
                updated = dict(record)
                updated['revoked_at'] = now
                devices[index] = updated
                _write_json(self.devices_path, {'schema_version': _SCHEMA_VERSION, 'devices': devices})
                self._append_audit(
                    event='device_revoked',
                    result='ok',
                    project_id=str(record.get('project_id') or ''),
                    device_id=requested,
                )
                return {
                    'schema_version': _SCHEMA_VERSION,
                    'status': 'revoked',
                    'device': _public_device(updated),
                }
        raise MobileGatewayPairingError('device not found', status_code=404, reason='not_found')

    def _pairing_state_by_id(self) -> dict[str, dict[str, object]]:
        state: dict[str, dict[str, object]] = {}
        if not self.pairing_tokens_path.exists():
            return state
        for record in _read_jsonl(self.pairing_tokens_path):
            pairing_id = str(record.get('pairing_id') or '')
            if pairing_id:
                state[pairing_id] = record
        return state

    def _read_devices(self) -> list[dict[str, object]]:
        if not self.devices_path.exists():
            return []
        try:
            payload = json.loads(self.devices_path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            return []
        devices = payload.get('devices') if isinstance(payload, dict) else None
        if not isinstance(devices, list):
            return []
        return [dict(item) for item in devices if isinstance(item, dict)]

    def _append_audit(self, *, event: str, result: str, **fields: object) -> None:
        entry = {
            'schema_version': _SCHEMA_VERSION,
            'timestamp': _iso(self._clock()),
            'event': str(event),
            'result': str(result),
        }
        for key, value in fields.items():
            if value is not None and value != '':
                entry[key] = value
        _append_jsonl(self.audit_path, entry)

    def _ensure_dir(self) -> None:
        self._mobile_dir.mkdir(parents=True, exist_ok=True)


def _token_hash(prefix: str, value: str) -> str:
    digest = hashlib.sha256(f'{prefix}{value}'.encode('utf-8')).hexdigest()
    return f'sha256:{digest}'


def _scope_list(value: object) -> list[str]:
    return sorted(_scope_set(value) or set(_DEFAULT_DEVICE_SCOPES))


def _scope_set(value: object) -> set[str]:
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, Iterable):
        items = [str(item) for item in value]
    else:
        items = []
    return {item.strip() for item in items if item.strip()}


def _public_device(record: dict[str, object]) -> dict[str, object]:
    return {
        'device_id': record.get('device_id'),
        'name': record.get('name'),
        'project_id': record.get('project_id'),
        'pairing_id': record.get('pairing_id'),
        'scopes': _scope_list(record.get('scopes')),
        'route_provider': record.get('route_provider'),
        'gateway_url': record.get('gateway_url'),
        'created_at': record.get('created_at'),
        'last_seen_at': record.get('last_seen_at'),
        'revoked': bool(record.get('revoked_at')),
        'revoked_at': record.get('revoked_at'),
    }


def _clean_id(value: str | None) -> str:
    text = str(value or '').strip()
    return ''.join(ch for ch in text if ch.isalnum() or ch in {'_', '-'})


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    try:
        lines = path.read_text(encoding='utf-8').splitlines()
    except OSError:
        return records
    for line in lines:
        text = line.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            records.append(dict(payload))
    return records


def _append_jsonl(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        handle.write('\n')


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f'.{path.name}.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    tmp.replace(path)


def _parse_utc(value: object) -> datetime | None:
    text = str(value or '').strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace('Z', '+00:00'))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _token_urlsafe(size: int) -> str:
    return secrets.token_urlsafe(size)


def _random_id(prefix: str) -> str:
    return f'{prefix}_{secrets.token_hex(8)}'


__all__ = [
    'AuthenticatedDevice',
    'MobileGatewayPairingError',
    'MobileGatewayPairingStore',
]
