from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import os
from typing import Mapping


SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ThemePreference:
    theme: str
    palette: str
    tmux_profile: str


_THEMES: dict[str, ThemePreference] = {
    'dark': ThemePreference(theme='dark', palette='dark', tmux_profile='default'),
    'light': ThemePreference(theme='light', palette='latte', tmux_profile='light'),
    'solarized': ThemePreference(theme='solarized', palette='solarized_light', tmux_profile='light'),
    'tokyo': ThemePreference(theme='tokyo', palette='tokyo_night_light', tmux_profile='light'),
    'gruvbox': ThemePreference(theme='gruvbox', palette='gruvbox_light', tmux_profile='light'),
    'rose-pine': ThemePreference(theme='rose-pine', palette='rose_pine_dawn', tmux_profile='light'),
}

THEME_CYCLE: tuple[str, ...] = ('dark', 'light', 'solarized', 'tokyo', 'gruvbox', 'rose-pine')

_ALIASES = {
    '': 'dark',
    'default': 'dark',
    'nord': 'dark',
    'contrast': 'dark',
    'dark': 'dark',
    'light': 'light',
    'latte': 'light',
    'catppuccin-latte': 'light',
    'catppuccin_latte': 'light',
    'solarized': 'solarized',
    'solarized-light': 'solarized',
    'solarized_light': 'solarized',
    'tokyo': 'tokyo',
    'tokyo-light': 'tokyo',
    'tokyo_light': 'tokyo',
    'tokyo-night-light': 'tokyo',
    'tokyo_night_light': 'tokyo',
    'tokyo-night-day': 'tokyo',
    'gruvbox': 'gruvbox',
    'gruvbox-light': 'gruvbox',
    'gruvbox_light': 'gruvbox',
    'rose-pine': 'rose-pine',
    'rose-pine-dawn': 'rose-pine',
    'rose_pine_dawn': 'rose-pine',
}


def theme_config_path(environ: Mapping[str, str] | None = None) -> Path:
    env = environ if environ is not None else os.environ
    config_home = str(env.get('XDG_CONFIG_HOME') or '').strip()
    home = Path(str(env.get('HOME') or Path.home())).expanduser()
    root = Path(config_home).expanduser() if config_home else home / '.config'
    return root / 'ccb' / 'theme.json'


def normalize_theme_name(value: str | None) -> str | None:
    key = str(value or '').strip().lower().replace('_', '-').replace(' ', '-')
    if key in _ALIASES:
        return _ALIASES[key]
    return None


def preference_for_theme(theme: str | None) -> ThemePreference | None:
    name = normalize_theme_name(theme)
    if name is None:
        return None
    return _THEMES[name]


def default_theme_preference() -> ThemePreference:
    return _THEMES['dark']


def available_themes() -> tuple[str, ...]:
    return THEME_CYCLE


def load_theme_preference(environ: Mapping[str, str] | None = None) -> ThemePreference | None:
    path = theme_config_path(environ)
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    for key in ('theme', 'palette'):
        preference = preference_for_theme(str(payload.get(key) or ''))
        if preference is not None:
            return preference
    tmux_profile = str(payload.get('tmux_profile') or '').strip().lower()
    if tmux_profile == 'light':
        return _THEMES['light']
    if tmux_profile in {'default', 'contrast'}:
        return _THEMES['dark']
    return None


def load_or_default_theme_preference(environ: Mapping[str, str] | None = None) -> ThemePreference:
    return load_theme_preference(environ) or default_theme_preference()


def resolve_theme_request(request: str | None, *, environ: Mapping[str, str] | None = None) -> ThemePreference | None:
    token = str(request or '').strip()
    current = load_or_default_theme_preference(environ)
    if token == '+':
        return _cycle_from(current, step=1)
    if token == '-':
        return _cycle_from(current, step=-1)
    return preference_for_theme(token)


def save_theme_preference(preference: ThemePreference, environ: Mapping[str, str] | None = None) -> Path:
    path = theme_config_path(environ)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'schema_version': SCHEMA_VERSION,
        'theme': preference.theme,
        'palette': preference.palette,
        'tmux_profile': preference.tmux_profile,
    }
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    temporary.replace(path)
    return path


def _cycle_from(current: ThemePreference, *, step: int) -> ThemePreference:
    try:
        index = THEME_CYCLE.index(current.theme)
    except ValueError:
        index = 0
    return _THEMES[THEME_CYCLE[(index + step) % len(THEME_CYCLE)]]


__all__ = [
    'ThemePreference',
    'available_themes',
    'default_theme_preference',
    'load_or_default_theme_preference',
    'load_theme_preference',
    'normalize_theme_name',
    'preference_for_theme',
    'resolve_theme_request',
    'save_theme_preference',
    'theme_config_path',
]
