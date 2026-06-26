from __future__ import annotations

from typing import TextIO
import os
import shutil
import subprocess

from cli.services.tmux_ui_runtime.helpers import script_path
from terminal_runtime.ui_theme import (
    ThemePreference,
    available_themes,
    load_or_default_theme_preference,
    resolve_theme_request,
    save_theme_preference,
    theme_config_path,
)


def cmd_theme(argv: list[str], *, stdout: TextIO, stderr: TextIO) -> int:
    tokens = list(argv or [])
    if tokens and tokens[0] in {'-h', '--help', 'help'}:
        print_theme_usage(stdout)
        return 0
    if len(tokens) > 1:
        print('ERROR: theme accepts at most one value', file=stderr)
        print_theme_usage(stderr)
        return 2
    if not tokens:
        preference = load_or_default_theme_preference()
        _print_theme_status(
            stdout,
            preference=preference,
            action='status',
            tmux_refresh='skipped',
            tmux_refresh_reason='status_only',
        )
        return 0

    preference = resolve_theme_request(tokens[0])
    if preference is None:
        print(f'ERROR: unsupported theme: {tokens[0]}', file=stderr)
        print(f'Available themes: {", ".join(available_themes())}', file=stderr)
        return 2
    save_theme_preference(preference)
    tmux_refresh, tmux_refresh_reason = _refresh_current_tmux(preference)
    _print_theme_status(
        stdout,
        preference=preference,
        action='set',
        tmux_refresh=tmux_refresh,
        tmux_refresh_reason=tmux_refresh_reason,
    )
    return 0


def print_theme_usage(stdout: TextIO) -> None:
    print('usage: ccb theme [dark|light|+|-|solarized|tokyo|gruvbox|rose-pine]', file=stdout)
    print('       ccb theme +', file=stdout)
    print('       ccb theme light', file=stdout)
    print('       ccb theme dark', file=stdout)


def _refresh_current_tmux(preference: ThemePreference) -> tuple[str, str]:
    if not ((os.environ.get('TMUX') or os.environ.get('TMUX_PANE') or '').strip()):
        return ('skipped', 'not_inside_tmux')
    tmux = shutil.which('tmux')
    if not tmux:
        return ('skipped', 'tmux_not_found')
    env = dict(os.environ)
    env['CCB_TMUX_THEME_PROFILE'] = preference.tmux_profile
    env['CCB_SIDEBAR_THEME_PROFILE'] = preference.tmux_profile
    for key, value in (
        ('CCB_TMUX_THEME_PROFILE', preference.tmux_profile),
        ('CCB_SIDEBAR_THEME_PROFILE', preference.tmux_profile),
    ):
        try:
            subprocess.run([tmux, 'set-environment', '-g', key, value], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
        except Exception:
            pass
    on_script = script_path('ccb-tmux-on.sh')
    if not on_script:
        return ('partial', 'ccb_tmux_on_not_found')
    try:
        result = subprocess.run([on_script], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    except Exception:
        return ('failed', 'ccb_tmux_on_failed')
    if result.returncode != 0:
        return ('failed', 'ccb_tmux_on_failed')
    return ('applied', 'ok')


def _rich_context_status() -> str:
    if str(os.environ.get('CCB_WORKBENCH_PROFILE') or '').strip().lower() != 'rich':
        return 'not_rich'
    if (os.environ.get('WEZTERM_PANE') or os.environ.get('WEZTERM_UNIX_SOCKET') or os.environ.get('WEZTERM_EXECUTABLE')):
        return 'rich_wezterm'
    return 'rich'


def _print_theme_status(
    stdout: TextIO,
    *,
    preference: ThemePreference,
    action: str,
    tmux_refresh: str,
    tmux_refresh_reason: str,
) -> None:
    rich_context = _rich_context_status()
    if rich_context == 'rich_wezterm':
        wezterm_refresh = 'watched_config_reload'
    elif rich_context == 'rich':
        wezterm_refresh = 'rich_context_without_wezterm'
    else:
        wezterm_refresh = 'next_rich_start'
    print('theme_status: ok', file=stdout)
    print(f'theme_action: {action}', file=stdout)
    print(f'theme: {preference.theme}', file=stdout)
    print(f'palette: {preference.palette}', file=stdout)
    print(f'tmux_profile: {preference.tmux_profile}', file=stdout)
    print(f'config_path: {theme_config_path()}', file=stdout)
    print(f'tmux_refresh: {tmux_refresh}', file=stdout)
    print(f'tmux_refresh_reason: {tmux_refresh_reason}', file=stdout)
    print(f'rich_context: {rich_context}', file=stdout)
    print(f'wezterm_refresh: {wezterm_refresh}', file=stdout)


__all__ = ['cmd_theme', 'print_theme_usage']
