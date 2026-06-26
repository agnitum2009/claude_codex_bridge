from __future__ import annotations

import json

from terminal_runtime.ui_theme import (
    load_theme_preference,
    resolve_theme_request,
    save_theme_preference,
    theme_config_path,
)


def test_theme_preference_normalizes_aliases_and_persists(tmp_path) -> None:
    env = {'XDG_CONFIG_HOME': str(tmp_path / 'config')}
    preference = resolve_theme_request('catppuccin-latte', environ=env)

    assert preference is not None
    assert preference.theme == 'light'
    assert preference.palette == 'latte'
    assert preference.tmux_profile == 'light'

    path = save_theme_preference(preference, environ=env)
    assert path == theme_config_path(env)
    payload = json.loads(path.read_text(encoding='utf-8'))
    assert payload['theme'] == 'light'
    assert payload['palette'] == 'latte'
    assert payload['tmux_profile'] == 'light'
    assert load_theme_preference(env) == preference


def test_theme_preference_cycles_from_saved_theme(tmp_path) -> None:
    env = {'XDG_CONFIG_HOME': str(tmp_path / 'config')}
    light = resolve_theme_request('light', environ=env)
    assert light is not None
    save_theme_preference(light, environ=env)

    assert resolve_theme_request('+', environ=env).theme == 'solarized'
    assert resolve_theme_request('-', environ=env).theme == 'dark'


def test_theme_preference_returns_none_for_unknown_theme(tmp_path) -> None:
    assert resolve_theme_request('unknown-theme', environ={'XDG_CONFIG_HOME': str(tmp_path / 'config')}) is None
