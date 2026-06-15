from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
from typing import TextIO

from . import neovim as neovim_tools


SCHEMA_VERSION = 1
DEFAULT_PROFILE = 'rich'
GENERATED_MARKER = '# CCB managed workbench file'
DETACHED_TMUX_ENV_KEYS = (
    'TMUX',
    'TMUX_PANE',
    'CCB_TMUX_SOCKET',
    'CCB_TMUX_SOCKET_PATH',
)


def cmd_tools(
    argv: list[str],
    *,
    script_root: Path | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    del script_root
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    if not argv or argv[0] in {'-h', '--help', 'help'}:
        _print_help(stdout)
        return 0
    if len(argv) < 2:
        _print_help(stdout)
        return 2
    action, tool = argv[0], argv[1]
    if tool != 'workbench':
        print(f'ERROR: unsupported tool: {tool}', file=stderr)
        return 2
    options = _parse_options(argv[2:])
    if options.get('error'):
        print(f"ERROR: {options['error']}", file=stderr)
        return 2
    profile = str(options.get('profile') or DEFAULT_PROFILE)
    if action == 'doctor':
        status = workbench_status(profile=profile)
        _print_status(status, stdout)
        return 0 if status.get('status') in {'ok', 'degraded', 'missing'} else 1
    if action in {'install', 'update'}:
        result = provision_workbench(profile=profile)
        _print_status(result, stdout)
        return 0 if result.get('status') in {'ok', 'degraded'} else 1
    if action == 'enable':
        result = enable_workbench(profile=profile)
        _print_status(result, stdout)
        return 0 if result.get('status') in {'ok', 'degraded'} else 1
    if action in {'disable', 'close'}:
        result = disable_workbench(profile=profile, close=True)
        _print_status(result, stdout)
        return 0 if result.get('status') in {'ok', 'degraded', 'missing'} else 1
    if action == 'launch':
        result = launch_workbench(profile=profile, dry_run=bool(options.get('dry_run')))
        _print_status(result, stdout)
        return 0 if result.get('status') in {'ok', 'degraded'} else 1
    if action == 'uninstall':
        result = uninstall_workbench(profile=profile, remove_cache=bool(options.get('remove_cache')))
        _print_status(result, stdout)
        return 0 if result.get('status') in {'ok', 'missing'} else 1
    print(f'ERROR: unsupported tools action: {action}', file=stderr)
    return 2


def cmd_rich(
    *,
    script_root: Path,
    cwd: Path,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    result = launch_rich_ccb(script_root=script_root, cwd=cwd)
    _print_status(result, stdout)
    if result.get('status') not in {'ok', 'degraded'}:
        if result.get('reason'):
            print(f"ERROR: {result['reason']}", file=stderr)
        return 1
    return 0 if result.get('launch_status') == 'started' else 1


def update_rich_workbench() -> dict[str, object]:
    result = provision_workbench(profile='rich')
    if result.get('status') not in {'ok', 'degraded'}:
        result['rich_update_status'] = result.get('status')
        return result
    enabled = enable_workbench(profile='rich')
    enabled['rich_update_status'] = result.get('status')
    return enabled


def print_workbench_status(status: dict[str, object], stdout: TextIO | None = None) -> None:
    _print_status(status, stdout or sys.stdout)


def provision_workbench(*, profile: str = DEFAULT_PROFILE) -> dict[str, object]:
    paths = _paths()
    _ensure_dirs(paths)
    _write_preview_helpers(paths)
    _write_piper_plugin(paths['yazi_safe_profile'] / 'plugins' / 'piper.yazi')
    _write_piper_plugin(paths['yazi_rich_profile'] / 'plugins' / 'piper.yazi')
    _write_yazi_config(paths, rich=False)
    _write_yazi_config(paths, rich=True)
    _write_wezterm_config(paths)
    _write_wrappers(paths)
    _write_bin_links(paths)
    neovim_result = neovim_tools.provision_neovim(required=False)
    status = _build_status(paths, profile=profile, neovim_result=neovim_result, installed=True)
    _write_manifest(paths, status)
    return status


def workbench_status(*, profile: str = DEFAULT_PROFILE) -> dict[str, object]:
    paths = _paths()
    manifest = _read_manifest(paths)
    if not paths['manifest'].is_file() or not paths['wrapper'].is_file():
        return {
            'status': 'missing',
            'reason': 'ccb workbench bundle is not installed',
            'profile': profile,
            **_status_paths(paths),
            **_component_statuses(paths, profile=profile, manifest=manifest),
        }
    neovim_result = neovim_tools.neovim_status()
    enabled = bool(manifest.get('enabled', False))
    status = _build_status(paths, profile=profile, neovim_result=neovim_result, installed=True, enabled=enabled)
    status['installed_at'] = manifest.get('installed_at')
    status['enabled_at'] = manifest.get('enabled_at')
    status['disabled_at'] = manifest.get('disabled_at')
    return status


def enable_workbench(*, profile: str = DEFAULT_PROFILE) -> dict[str, object]:
    paths = _paths()
    manifest = _read_manifest(paths)
    if not paths['manifest'].is_file():
        manifest = provision_workbench(profile=profile)
    else:
        manifest = workbench_status(profile=profile)
    manifest['enabled'] = True
    manifest['enabled_at'] = _now()
    manifest.pop('disabled_at', None)
    _write_manifest(paths, manifest)
    return manifest


def disable_workbench(*, profile: str = DEFAULT_PROFILE, close: bool = True) -> dict[str, object]:
    paths = _paths()
    if not paths['manifest'].is_file():
        return {
            'status': 'missing',
            'reason': 'ccb workbench bundle is not installed',
            'profile': profile,
            **_status_paths(paths),
        }
    manifest = workbench_status(profile=profile)
    close_result = _close_recorded_processes(paths) if close else {'closed_processes': 0}
    manifest['enabled'] = False
    manifest['disabled_at'] = _now()
    manifest['close_status'] = close_result.get('status', 'ok')
    manifest['closed_processes'] = close_result.get('closed_processes', 0)
    if close_result.get('reason'):
        manifest['close_reason'] = close_result.get('reason')
    _write_manifest(paths, manifest)
    return manifest


def launch_workbench(*, profile: str = DEFAULT_PROFILE, dry_run: bool = False) -> dict[str, object]:
    paths = _paths()
    status = workbench_status(profile=profile)
    if status.get('status') == 'missing':
        status['reason'] = 'install the workbench bundle before launching it'
        return status
    commands = _launch_commands(paths)
    status['launch_commands'] = commands
    if dry_run:
        status['launch_status'] = 'dry_run'
        return status
    if not status.get('enabled'):
        status['status'] = 'failed'
        status['reason'] = 'workbench bundle is disabled; run `ccb tools enable workbench --profile rich` first'
        status['launch_status'] = 'disabled'
        return status
    completed = subprocess.Popen([str(paths['wrapper']), 'terminal'], env=_detached_terminal_env())
    _record_launch(paths, pid=completed.pid, command=[str(paths['wrapper']), 'terminal'])
    status['launch_status'] = 'started'
    status['launch_pid'] = completed.pid
    return status


def launch_rich_ccb(*, script_root: Path, cwd: Path) -> dict[str, object]:
    status = workbench_status(profile='rich')
    if status.get('status') == 'missing':
        status['status'] = 'failed'
        status['reason'] = 'rich bundle is not installed; run `ccb update rich` first'
        status['launch_status'] = 'missing_rich_bundle'
        return status
    if not status.get('enabled'):
        status['status'] = 'failed'
        status['reason'] = 'rich bundle is disabled; run `ccb update rich` first'
        status['launch_status'] = 'disabled'
        return status
    if status.get('wezterm_status') != 'ok':
        status['status'] = 'failed'
        status['reason'] = 'rich startup requires WezTerm; install WezTerm or use normal `ccb`'
        status['launch_status'] = 'missing_wezterm'
        return status
    paths = _paths()
    entrypoint = _ccb_entrypoint(script_root)
    command = [
        str(paths['wrapper']),
        'terminal',
        '/bin/sh',
        '-lc',
        f'{_shell_quote(str(entrypoint))}; exec "${{SHELL:-/bin/sh}}" -l',
    ]
    process = subprocess.Popen(command, cwd=str(cwd), env=_detached_terminal_env())
    _record_launch(paths, pid=process.pid, command=command)
    status['launch_status'] = 'started'
    status['launch_pid'] = process.pid
    status['launch_command'] = ' '.join(_shell_quote(item) for item in command)
    return status


def uninstall_workbench(*, profile: str = DEFAULT_PROFILE, remove_cache: bool = False) -> dict[str, object]:
    paths = _paths()
    if not paths['root'].exists() and not paths['manifest'].exists():
        return {
            'status': 'missing',
            'reason': 'ccb workbench bundle is not installed',
            'profile': profile,
            **_status_paths(paths),
        }
    disable_workbench(profile=profile, close=True)
    _remove_bin_links(paths)
    shutil.rmtree(paths['root'], ignore_errors=True)
    shutil.rmtree(paths['state_root'], ignore_errors=True)
    if remove_cache:
        shutil.rmtree(paths['cache_root'], ignore_errors=True)
    return {
        'status': 'ok',
        'profile': profile,
        'uninstalled': True,
        'cache_removed': remove_cache,
        **_status_paths(paths),
    }


def _paths() -> dict[str, Path]:
    data_home = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local' / 'share')
    state_home = Path(os.environ.get('XDG_STATE_HOME') or Path.home() / '.local' / 'state')
    cache_home = Path(os.environ.get('XDG_CACHE_HOME') or Path.home() / '.cache')
    root = data_home / 'ccb' / 'tools' / 'workbench'
    bin_dir = root / 'bin'
    profiles = root / 'profiles'
    bin_link_dir = Path(os.environ.get('CODEX_BIN_DIR') or Path.home() / '.local' / 'bin')
    return {
        'root': root,
        'bin_dir': bin_dir,
        'bin_link_dir': bin_link_dir,
        'wrapper': bin_dir / 'ccb-workbench',
        'yazi_wrapper': bin_dir / 'ccb-yazi',
        'yazi_rich_wrapper': bin_dir / 'ccb-yazi-rich',
        'md_preview': bin_dir / 'ccb-md-preview',
        'image_preview': bin_dir / 'ccb-image-preview',
        'pdf_preview': bin_dir / 'ccb-pdf-preview',
        'video_preview': bin_dir / 'ccb-video-preview',
        'wrapper_link': bin_link_dir / 'ccb-workbench',
        'yazi_link': bin_link_dir / 'ccb-yazi',
        'yazi_rich_link': bin_link_dir / 'ccb-yazi-rich',
        'md_preview_link': bin_link_dir / 'ccb-md-preview',
        'image_preview_link': bin_link_dir / 'ccb-image-preview',
        'pdf_preview_link': bin_link_dir / 'ccb-pdf-preview',
        'video_preview_link': bin_link_dir / 'ccb-video-preview',
        'profiles': profiles,
        'yazi_safe_profile': profiles / 'yazi-safe',
        'yazi_rich_profile': profiles / 'yazi-rich',
        'wezterm_profile': profiles / 'wezterm',
        'wezterm_config': profiles / 'wezterm' / 'wezterm.lua',
        'manifest': root / 'manifest.json',
        'state_root': state_home / 'ccb' / 'tools' / 'workbench',
        'launches': state_home / 'ccb' / 'tools' / 'workbench' / 'launches.json',
        'cache_root': cache_home / 'ccb' / 'tools' / 'workbench',
    }


def _detached_terminal_env(environ: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(environ if environ is not None else os.environ)
    for key in DETACHED_TMUX_ENV_KEYS:
        env.pop(key, None)
    return env


def _ensure_dirs(paths: dict[str, Path]) -> None:
    for key in ('bin_dir', 'bin_link_dir', 'yazi_safe_profile', 'yazi_rich_profile', 'wezterm_profile', 'state_root', 'cache_root'):
        paths[key].mkdir(parents=True, exist_ok=True)


def _write_preview_helpers(paths: dict[str, Path]) -> None:
    _write_executable(
        paths['md_preview'],
        f'''#!/usr/bin/env sh
{GENERATED_MARKER}
set -eu
file="${{1:-}}"
width="${{w:-100}}"
if [ -z "$file" ]; then
  exit 2
fi
if command -v glow >/dev/null 2>&1; then
  exec glow -w "$width" -s dark "$file"
fi
if command -v mdcat >/dev/null 2>&1; then
  exec mdcat "$file"
fi
exec python3 - "$file" "$width" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
try:
    width = max(40, int(float(sys.argv[2])))
except Exception:
    width = 100
try:
    text = path.read_text(encoding="utf-8", errors="replace")
except Exception as exc:
    sys.stderr.write(f"markdown preview failed: {{exc}}\\n")
    raise SystemExit(1)
try:
    from rich.console import Console
    from rich.markdown import Markdown
    console = Console(force_terminal=True, color_system="256", width=width)
    console.print(Markdown(text))
except Exception:
    sys.stdout.write(text)
PY
''',
    )
    _write_executable(
        paths['image_preview'],
        f'''#!/usr/bin/env sh
{GENERATED_MARKER}
set -eu
file="${{1:-}}"
width="${{w:-80}}"
height="${{h:-24}}"
if [ -z "$file" ]; then
  exit 2
fi
echo "Image preview: $file"
echo
if command -v identify >/dev/null 2>&1; then
  identify "$file" 2>/dev/null || true
elif command -v file >/dev/null 2>&1; then
  file "$file" 2>/dev/null || true
else
  echo "No image preview helper found."
fi
echo
echo "Inline image preview requires the rich Yazi profile in a terminal with image protocol support."
''',
    )
    _write_executable(
        paths['pdf_preview'],
        f'''#!/usr/bin/env sh
{GENERATED_MARKER}
set -eu
file="${{1:-}}"
if [ -z "$file" ]; then
  exit 2
fi
echo "PDF preview: $file"
echo
if command -v pdfinfo >/dev/null 2>&1; then
  pdfinfo "$file" 2>/dev/null | sed -n '1,24p' || true
else
  echo "pdfinfo: missing"
fi
echo
echo "--- text, first 3 pages ---"
if command -v pdftotext >/dev/null 2>&1; then
  pdftotext -layout -f 1 -l 3 "$file" - 2>/dev/null | sed -n '1,120p' || true
else
  echo "pdftotext: missing"
fi
''',
    )
    _write_executable(
        paths['video_preview'],
        f'''#!/usr/bin/env sh
{GENERATED_MARKER}
set -eu
file="${{1:-}}"
if [ -z "$file" ]; then
  exit 2
fi
echo "Video preview: $file"
echo
if command -v ffprobe >/dev/null 2>&1; then
  ffprobe -hide_banner -v error -show_format -show_streams "$file" 2>/dev/null | sed -n '1,140p' || true
else
  echo "ffprobe: missing"
fi
''',
    )


def _write_yazi_config(paths: dict[str, Path], *, rich: bool) -> None:
    profile = paths['yazi_rich_profile'] if rich else paths['yazi_safe_profile']
    md = _shell_double_quote(str(paths['md_preview']))
    image = _shell_double_quote(str(paths['image_preview']))
    pdf = _shell_double_quote(str(paths['pdf_preview']))
    video = _shell_double_quote(str(paths['video_preview']))
    previewers_key = 'prepend_previewers' if rich else 'previewers'
    lines = [
        '# CCB managed Yazi profile. Do not edit; regenerate with `ccb tools install workbench`.',
        '',
        '[preview]',
        'wrap = "yes"',
        'tab_size = 2',
        'max_width = 1200',
        'max_height = 1600',
        'image_delay = 20',
        'image_filter = "triangle"',
        'image_quality = 75',
        '',
        '[plugin]',
        f'{previewers_key} = [',
        f'  {{ url = "*.md", run = \'piper -- {md} "$1"\' }},',
        f'  {{ url = "*.markdown", run = \'piper -- {md} "$1"\' }},',
    ]
    if rich:
        lines.extend(
            [
                '  { mime = "image/*", run = "image" },',
                '  { mime = "application/pdf", run = "pdf" },',
                '  { url = "*.pdf", run = "pdf" },',
                '  { mime = "video/*", run = "video" },',
            ]
        )
    if not rich:
        lines.extend(
            [
                f'  {{ url = "*.png", run = \'piper -- {image} "$1"\' }},',
                f'  {{ url = "*.jpg", run = \'piper -- {image} "$1"\' }},',
                f'  {{ url = "*.jpeg", run = \'piper -- {image} "$1"\' }},',
                f'  {{ url = "*.gif", run = \'piper -- {image} "$1"\' }},',
                f'  {{ url = "*.webp", run = \'piper -- {image} "$1"\' }},',
                f'  {{ url = "*.bmp", run = \'piper -- {image} "$1"\' }},',
                f'  {{ url = "*.tif", run = \'piper -- {image} "$1"\' }},',
                f'  {{ url = "*.tiff", run = \'piper -- {image} "$1"\' }},',
                f'  {{ url = "*.pdf", run = \'piper -- {pdf} "$1"\' }},',
                f'  {{ url = "*.mp4", run = \'piper -- {video} "$1"\' }},',
                f'  {{ url = "*.mkv", run = \'piper -- {video} "$1"\' }},',
                f'  {{ url = "*.mov", run = \'piper -- {video} "$1"\' }},',
                f'  {{ url = "*.webm", run = \'piper -- {video} "$1"\' }},',
                f'  {{ url = "*.avi", run = \'piper -- {video} "$1"\' }},',
                '  { url = "*/", run = "folder" },',
                '  { mime = "text/*", run = "code" },',
                '  { mime = "application/{mbox,javascript,wine-extension-ini}", run = "code" },',
                '  { mime = "application/{json,ndjson}", run = "json" },',
                '  { mime = "application/{zip,rar,7z*,tar,gzip,xz,zstd,bzip*,lzma,compress,archive,cpio,arj,xar,ms-cab*}", run = "archive" },',
                '  { mime = "application/{debian*-package,redhat-package-manager,rpm,android.package-archive}", run = "archive" },',
                '  { url = "*.{AppImage,appimage}", run = "archive" },',
                '  { mime = "application/{iso9660-image,qemu-disk,ms-wim,apple-diskimage}", run = "archive" },',
                '  { mime = "application/virtualbox-{vhd,vhdx}", run = "archive" },',
                '  { url = "*.{img,fat,ext,ext2,ext3,ext4,squashfs,ntfs,hfs,hfsx}", run = "archive" },',
                '  { mime = "font/*", run = "font" },',
                '  { mime = "application/ms-opentype", run = "font" },',
                '  { mime = "inode/empty", run = "empty" },',
                '  { mime = "vfs/*", run = "vfs" },',
                '  { mime = "null/*", run = "null" },',
                '  { url = "*", run = "file" },',
            ]
        )
    lines.extend([']'])
    if not rich:
        lines.extend(
            [
                '',
                'preloaders = []',
            ]
        )
    lines.append('')
    (profile / 'yazi.toml').write_text('\n'.join(lines), encoding='utf-8')


def _write_piper_plugin(target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    (target / 'main.lua').write_text(
        '''-- CCB managed minimal piper-compatible previewer.
-- The interface follows yazi-rs/plugins:piper so generated profiles remain
-- independent from the user's personal Yazi plugin directory.
local M = {}

local function fail(job, text)
  ya.preview_widget(job, ui.Text.parse(text):area(job.area):wrap(ui.Wrap.YES))
end

function M:peek(job)
  local child, err = Command("sh")
    :arg({ "-c", job.args[1], "sh", tostring(job.file.path) })
    :env("w", job.area.w)
    :env("h", job.area.h)
    :stdout(Command.PIPED)
    :stderr(Command.PIPED)
    :spawn()
  if not child then
    return fail(job, "sh: " .. err)
  end
  local limit = job.area.h
  local i, outs, errs = 0, {}, {}
  repeat
    local next, event = child:read_line()
    if event == 1 then
      errs[#errs + 1] = next
    elseif event ~= 0 then
      break
    end
    i = i + 1
    if i > job.skip then
      outs[#outs + 1] = next
    end
  until i >= job.skip + limit
  child:start_kill()
  if #errs > 0 then
    fail(job, table.concat(errs, ""))
  else
    local text = table.concat(outs, ""):gsub("\\t", string.rep(" ", rt.preview.tab_size))
    ya.preview_widget(job, ui.Text.parse(text):area(job.area))
  end
end

function M:seek(job)
  require("code"):seek(job)
end

return M
''',
        encoding='utf-8',
    )


def _write_wezterm_config(paths: dict[str, Path]) -> None:
    paths['wezterm_config'].write_text(
        f'''-- {GENERATED_MARKER}
local wezterm = require("wezterm")
local config = wezterm.config_builder and wezterm.config_builder() or {{}}

config.automatically_reload_config = false
config.check_for_updates = false
config.window_close_confirmation = "NeverPrompt"
config.warn_about_missing_glyphs = false
config.font = wezterm.font_with_fallback({{
  "JetBrains Mono",
  "Fira Code",
  "Noto Sans Mono",
  "Noto Sans Mono CJK SC",
  "Noto Sans Symbols2",
  "Symbols Nerd Font Mono",
  "Symbols Nerd Font",
  "Unifont CSUR",
  "Apple Color Emoji",
  "Segoe UI Emoji",
  "Noto Color Emoji",
  "monospace",
}})
config.harfbuzz_features = {{ "calt=0", "clig=0", "liga=0" }}
config.font_size = 10.5
config.line_height = 1.05
config.cell_width = 1.0
config.initial_cols = 132
config.initial_rows = 38
config.enable_scroll_bar = false
config.use_fancy_tab_bar = false
config.hide_tab_bar_if_only_one_tab = true
config.window_padding = {{
  left = 4,
  right = 4,
  top = 2,
  bottom = 2,
}}
config.window_frame = {{
  font = wezterm.font("JetBrains Mono"),
  font_size = 9.5,
}}
config.colors = {{
  foreground = "#d8dee9",
  background = "#1f2328",
  cursor_bg = "#88c0d0",
  cursor_fg = "#1f2328",
  cursor_border = "#88c0d0",
  selection_fg = "#eceff4",
  selection_bg = "#3b4252",
  split = "#4c566a",
  tab_bar = {{
    background = "#1f2328",
    active_tab = {{
      bg_color = "#2e3440",
      fg_color = "#eceff4",
    }},
    inactive_tab = {{
      bg_color = "#242933",
      fg_color = "#a7b0be",
    }},
    inactive_tab_hover = {{
      bg_color = "#303846",
      fg_color = "#eceff4",
    }},
    new_tab = {{
      bg_color = "#1f2328",
      fg_color = "#a7b0be",
    }},
  }},
}}
config.set_environment_variables = {{
  CCB_WORKBENCH_PROFILE = "rich",
  CCB_WORKBENCH_ROOT = "{_lua_string(str(paths['root']))}",
  CCB_WORKBENCH_TERMINAL_PROGRAM = "WezTerm",
  CCB_WORKBENCH_TERMINAL_PROGRAM_VERSION = wezterm.version,
  CCB_WORKBENCH_YAZI_SAFE_CONFIG = "{_lua_string(str(paths['yazi_safe_profile']))}",
  CCB_WORKBENCH_YAZI_RICH_CONFIG = "{_lua_string(str(paths['yazi_rich_profile']))}",
}}

return config
''',
        encoding='utf-8',
    )


def _write_wrappers(paths: dict[str, Path]) -> None:
    path_prefix = _shell_quote(str(paths['bin_dir']))
    _write_executable(
        paths['yazi_wrapper'],
        f'''#!/usr/bin/env sh
{GENERATED_MARKER}
set -eu
export CCB_WORKBENCH_ROOT={_shell_quote(str(paths['root']))}
export YAZI_CONFIG_HOME={_shell_quote(str(paths['yazi_safe_profile']))}
export PATH={path_prefix}${{PATH:+":$PATH"}}
exec yazi "$@"
''',
    )
    _write_executable(
        paths['yazi_rich_wrapper'],
        f'''#!/usr/bin/env sh
{GENERATED_MARKER}
set -eu
export CCB_WORKBENCH_ROOT={_shell_quote(str(paths['root']))}
export PATH={path_prefix}${{PATH:+":$PATH"}}
case "${{CCB_WORKBENCH_FORCE_RICH:-}}" in
  1|true|yes) rich=1 ;;
  *) rich=0 ;;
esac
term_program="$(printf '%s' "${{TERM_PROGRAM:-}}" | tr '[:upper:]' '[:lower:]')"
if [ "$rich" = 0 ] && [ -z "${{TMUX:-}}" ]; then
  case "$term_program" in
    *wezterm*|*kitty*|*ghostty*) rich=1 ;;
  esac
fi
if [ "$rich" = 0 ] && [ -n "${{KITTY_WINDOW_ID:-}}" ] && [ -z "${{TMUX:-}}" ]; then
  rich=1
fi
if [ "$rich" = 1 ]; then
  case "${{TERM_PROGRAM:-}}" in
    ""|tmux)
      if [ -n "${{CCB_WORKBENCH_TERMINAL_PROGRAM:-}}" ]; then
        export TERM_PROGRAM="${{CCB_WORKBENCH_TERMINAL_PROGRAM}}"
      fi
      if [ -n "${{CCB_WORKBENCH_TERMINAL_PROGRAM_VERSION:-}}" ]; then
        export TERM_PROGRAM_VERSION="${{CCB_WORKBENCH_TERMINAL_PROGRAM_VERSION}}"
      fi
      ;;
  esac
  export YAZI_CONFIG_HOME={_shell_quote(str(paths['yazi_rich_profile']))}
else
  export YAZI_CONFIG_HOME={_shell_quote(str(paths['yazi_safe_profile']))}
fi
exec yazi "$@"
''',
    )
    _write_executable(
        paths['wrapper'],
        f'''#!/usr/bin/env sh
{GENERATED_MARKER}
set -eu
export CCB_WORKBENCH_ROOT={_shell_quote(str(paths['root']))}
export PATH={path_prefix}${{PATH:+":$PATH"}}
cmd="${{1:-files}}"
case "$cmd" in
  files|yazi)
    shift || true
    exec ccb-yazi-rich "$@"
    ;;
  edit|nvim|neovim)
    shift || true
    exec ccb-nvim "$@"
    ;;
  commands|--print-commands)
    printf '%s\\n' 'ccb-yazi-rich "$PWD"' 'ccb-nvim "$PWD"'
    ;;
  terminal|wezterm)
    shift || true
    if ! command -v wezterm >/dev/null 2>&1; then
      printf '%s\\n' 'ccb-workbench terminal requires WezTerm' >&2
      exit 127
    fi
    if [ "$#" -eq 0 ]; then
      set -- "${{SHELL:-/bin/sh}}" -lc 'ccb-yazi-rich "$PWD"'
    fi
    exec wezterm --config-file {_shell_quote(str(paths['wezterm_config']))} \
      start --always-new-process --no-auto-connect --cwd "$PWD" -- env \
      -u TMUX \
      -u TMUX_PANE \
      -u CCB_TMUX_SOCKET \
      -u CCB_TMUX_SOCKET_PATH \
      CCB_WORKBENCH_PROFILE=rich \
      CCB_WORKBENCH_ROOT={_shell_quote(str(paths['root']))} \
      CCB_WORKBENCH_TERMINAL_PROGRAM=WezTerm \
      CCB_WORKBENCH_YAZI_SAFE_CONFIG={_shell_quote(str(paths['yazi_safe_profile']))} \
      CCB_WORKBENCH_YAZI_RICH_CONFIG={_shell_quote(str(paths['yazi_rich_profile']))} \
      CCB_WORKBENCH_FORCE_RICH=1 \
      "$@"
    ;;
  *)
    exec ccb-yazi-rich "$@"
    ;;
esac
''',
    )


def _write_executable(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    path.chmod(0o755)


def _write_bin_links(paths: dict[str, Path]) -> None:
    for key, link_key in (
        ('wrapper', 'wrapper_link'),
        ('yazi_wrapper', 'yazi_link'),
        ('yazi_rich_wrapper', 'yazi_rich_link'),
        ('md_preview', 'md_preview_link'),
        ('image_preview', 'image_preview_link'),
        ('pdf_preview', 'pdf_preview_link'),
        ('video_preview', 'video_preview_link'),
    ):
        _activate_link(paths[key], paths[link_key])


def _activate_link(target: Path, link: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(target)
    except Exception:
        shutil.copy2(target, link)
        link.chmod(0o755)


def _remove_bin_links(paths: dict[str, Path]) -> None:
    for link_key in (
        'wrapper_link',
        'yazi_link',
        'yazi_rich_link',
        'md_preview_link',
        'image_preview_link',
        'pdf_preview_link',
        'video_preview_link',
    ):
        link = paths[link_key]
        try:
            if link.is_symlink():
                target = link.resolve(strict=False)
                if str(target).startswith(str(paths['root'])):
                    link.unlink()
                continue
            if link.is_file() and GENERATED_MARKER in link.read_text(encoding='utf-8', errors='ignore')[:300]:
                link.unlink()
        except Exception:
            continue


def _build_status(
    paths: dict[str, Path],
    *,
    profile: str,
    neovim_result: dict[str, object],
    installed: bool,
    enabled: bool | None = None,
) -> dict[str, object]:
    manifest = _read_manifest(paths)
    component_status = _component_statuses(paths, profile=profile, manifest=manifest, neovim_result=neovim_result)
    status_value, degraded_reasons = _rollup_status(component_status)
    if not installed:
        status_value = 'missing'
    if enabled is None:
        enabled = bool(manifest.get('enabled', False))
    return {
        'schema_version': SCHEMA_VERSION,
        'status': status_value,
        'profile': profile,
        'enabled': enabled,
        'installed': installed,
        'installed_at': manifest.get('installed_at') or _now(),
        'updated_at': _now(),
        'degraded_reasons': degraded_reasons,
        'components': component_status,
        'paths': _status_paths(paths),
        **_flatten_component_status(component_status),
        **_status_paths(paths),
    }


def _component_statuses(
    paths: dict[str, Path],
    *,
    profile: str,
    manifest: dict[str, object],
    neovim_result: dict[str, object] | None = None,
) -> dict[str, dict[str, object]]:
    del profile, manifest
    yazi = _tool_component('yazi', ('yazi',))
    ya = _tool_component('ya', ('ya',))
    wezterm = _tool_component('wezterm', ('wezterm',))
    pdf_text = _tool_component('pdf_text', ('pdftotext', 'pdfinfo'), require_all=True)
    pdf_image = _tool_component('pdf_image', ('pdftoppm', 'pdftocairo'))
    image_preview = _image_component(paths)
    video_metadata = _tool_component('video_metadata', ('ffprobe',))
    video_thumbnail = _tool_component('video_thumbnail', ('ffmpeg',))
    terminal = _terminal_component()
    markdown = _markdown_component(paths)
    neovim = _neovim_component(neovim_result)
    config = _config_component(paths)
    return {
        'config': config,
        'terminal': terminal,
        'wezterm': wezterm,
        'yazi': yazi,
        'ya': ya,
        'neovim': neovim,
        'markdown': markdown,
        'image_preview': image_preview,
        'pdf_text': pdf_text,
        'pdf_image': pdf_image,
        'video_metadata': video_metadata,
        'video_thumbnail': video_thumbnail,
    }


def _tool_component(name: str, commands: tuple[str, ...], *, require_all: bool = False) -> dict[str, object]:
    found: list[str] = []
    missing: list[str] = []
    for command in commands:
        path = shutil.which(command)
        if path:
            found.append(f'{command}:{path}')
        else:
            missing.append(command)
    if require_all:
        ok = not missing
    else:
        ok = bool(found)
    status = 'ok' if ok else 'missing'
    result: dict[str, object] = {'status': status}
    if found:
        result['tools'] = ','.join(found)
    if missing:
        result['missing'] = ','.join(missing)
    if status != 'ok':
        result['reason'] = f'{name} helper not found'
    return result


def _terminal_component() -> dict[str, object]:
    term = str(os.environ.get('TERM') or '')
    term_program = str(os.environ.get('TERM_PROGRAM') or '')
    term_lower = term_program.lower()
    in_tmux = bool(os.environ.get('TMUX')) or term.startswith('tmux')
    rich_candidate = bool(os.environ.get('KITTY_WINDOW_ID')) or any(value in term_lower for value in ('wezterm', 'kitty', 'ghostty'))
    if rich_candidate and not in_tmux:
        return {
            'status': 'ok',
            'terminal_program': term_program or term or 'unknown',
            'image_protocol': 'candidate',
        }
    reason = 'tmux image passthrough is not verified' if in_tmux else 'no rich terminal image protocol detected'
    return {
        'status': 'degraded',
        'terminal_program': term_program or term or 'unknown',
        'image_protocol': 'degraded',
        'reason': reason,
    }


def _markdown_component(paths: dict[str, Path]) -> dict[str, object]:
    if shutil.which('glow'):
        return {'status': 'ok', 'tool': 'glow'}
    if shutil.which('mdcat'):
        return {'status': 'ok', 'tool': 'mdcat'}
    if shutil.which('python3') and paths['md_preview'].is_file():
        return {'status': 'ok', 'tool': 'python3-rich-or-plain'}
    return {'status': 'missing', 'reason': 'no Markdown renderer helper found'}


def _image_component(paths: dict[str, Path]) -> dict[str, object]:
    if not paths['image_preview'].is_file():
        return {'status': 'missing', 'reason': 'generated image preview helper not found'}
    found: list[str] = []
    for command in ('chafa', 'identify', 'file'):
        path = shutil.which(command)
        if path:
            found.append(f'{command}:{path}')
    if found:
        return {'status': 'ok', 'tools': ','.join(found)}
    return {'status': 'missing', 'reason': 'no image preview helper found'}


def _neovim_component(neovim_result: dict[str, object] | None) -> dict[str, object]:
    if neovim_result is None:
        neovim_result = neovim_tools.neovim_status()
    result: dict[str, object] = {
        'status': neovim_result.get('status', 'unknown'),
        'wrapper': neovim_result.get('wrapper'),
    }
    if neovim_result.get('reason'):
        result['reason'] = neovim_result.get('reason')
    return result


def _config_component(paths: dict[str, Path]) -> dict[str, object]:
    required = (
        paths['wrapper'],
        paths['yazi_wrapper'],
        paths['yazi_rich_wrapper'],
        paths['md_preview'],
        paths['image_preview'],
        paths['pdf_preview'],
        paths['video_preview'],
        paths['yazi_safe_profile'] / 'yazi.toml',
        paths['yazi_rich_profile'] / 'yazi.toml',
        paths['yazi_safe_profile'] / 'plugins' / 'piper.yazi' / 'main.lua',
        paths['yazi_rich_profile'] / 'plugins' / 'piper.yazi' / 'main.lua',
        paths['wezterm_config'],
    )
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        return {'status': 'missing', 'reason': 'generated workbench config is incomplete', 'missing': ';'.join(missing)}
    return {'status': 'ok'}


def _rollup_status(components: dict[str, dict[str, object]]) -> tuple[str, list[str]]:
    required = ('config', 'yazi', 'neovim', 'markdown')
    missing_required = [
        name
        for name in required
        if components.get(name, {}).get('status') not in {'ok', 'degraded'}
    ]
    reasons: list[str] = []
    for name, payload in components.items():
        if payload.get('status') in {'missing', 'failed', 'degraded'} and payload.get('reason'):
            reasons.append(f'{name}: {payload["reason"]}')
    if missing_required:
        return 'degraded', reasons or [f'missing required component: {",".join(missing_required)}']
    if reasons:
        return 'degraded', reasons
    return 'ok', []


def _flatten_component_status(components: dict[str, dict[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for name, payload in components.items():
        result[f'{name}_status'] = payload.get('status')
        for key in ('tool', 'tools', 'wrapper', 'terminal_program', 'image_protocol', 'reason', 'missing'):
            if payload.get(key):
                result[f'{name}_{key}'] = payload.get(key)
    return result


def _status_paths(paths: dict[str, Path]) -> dict[str, object]:
    return {
        'root': str(paths['root']),
        'manifest': str(paths['manifest']),
        'bin_dir': str(paths['bin_dir']),
        'bin_link_dir': str(paths['bin_link_dir']),
        'yazi_safe_config': str(paths['yazi_safe_profile']),
        'yazi_rich_config': str(paths['yazi_rich_profile']),
        'wezterm_config': str(paths['wezterm_config']),
        'state_root': str(paths['state_root']),
        'cache_root': str(paths['cache_root']),
    }


def _launch_commands(paths: dict[str, Path]) -> list[str]:
    return [
        f'{paths["wrapper"]} terminal',
        f'{paths["yazi_rich_wrapper"]} "$PWD"',
        'ccb-nvim "$PWD"',
    ]


def _ccb_entrypoint(script_root: Path) -> Path:
    if os.environ.get('CCB_TEST_ENTRYPOINT') == '1':
        test_wrapper = script_root / 'ccb_test'
        if test_wrapper.exists():
            return test_wrapper
    return script_root / 'ccb'


def _record_launch(paths: dict[str, Path], *, pid: int, command: list[str]) -> None:
    records = _read_launches(paths)
    records.append({'pid': pid, 'command': command, 'started_at': _now()})
    paths['launches'].parent.mkdir(parents=True, exist_ok=True)
    paths['launches'].write_text(json.dumps(records, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def _read_launches(paths: dict[str, Path]) -> list[dict[str, object]]:
    try:
        value = json.loads(paths['launches'].read_text(encoding='utf-8'))
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    except Exception:
        pass
    return []


def _close_recorded_processes(paths: dict[str, Path]) -> dict[str, object]:
    records = _read_launches(paths)
    closed = 0
    survivors: list[dict[str, object]] = []
    for record in records:
        try:
            pid = int(record.get('pid', 0))
        except Exception:
            continue
        if pid <= 0:
            continue
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            continue
        except PermissionError:
            survivors.append(record)
            continue
        try:
            os.kill(pid, signal.SIGTERM)
            closed += 1
        except ProcessLookupError:
            pass
        except PermissionError:
            survivors.append(record)
    paths['launches'].parent.mkdir(parents=True, exist_ok=True)
    paths['launches'].write_text(json.dumps(survivors, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    if survivors:
        return {'status': 'degraded', 'closed_processes': closed, 'reason': 'some recorded workbench processes could not be closed'}
    return {'status': 'ok', 'closed_processes': closed}


def _read_manifest(paths: dict[str, Path]) -> dict[str, object]:
    try:
        value = json.loads(paths['manifest'].read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _write_manifest(paths: dict[str, Path], payload: dict[str, object]) -> None:
    paths['manifest'].parent.mkdir(parents=True, exist_ok=True)
    paths['manifest'].write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def _parse_options(args: list[str]) -> dict[str, object]:
    result: dict[str, object] = {'profile': DEFAULT_PROFILE}
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == '--profile':
            if index + 1 >= len(args):
                return {'error': '--profile requires a value'}
            result['profile'] = args[index + 1]
            index += 2
            continue
        if arg.startswith('--profile='):
            result['profile'] = arg.split('=', 1)[1]
            index += 1
            continue
        if arg == '--dry-run':
            result['dry_run'] = True
            index += 1
            continue
        if arg == '--remove-cache':
            result['remove_cache'] = True
            index += 1
            continue
        return {'error': f'unknown option: {arg}'}
    if str(result.get('profile') or '') not in {'safe', 'rich'}:
        return {'error': 'profile must be safe or rich'}
    return result


def _print_status(status: dict[str, object], stdout: TextIO) -> None:
    print(f"workbench_status: {status.get('status')}", file=stdout)
    for key in (
        'reason',
        'profile',
        'enabled',
        'installed',
        'installed_at',
        'updated_at',
        'enabled_at',
        'disabled_at',
        'close_status',
        'closed_processes',
        'rich_update_status',
        'launch_status',
        'launch_pid',
        'launch_command',
        'config_status',
        'terminal_status',
        'terminal_terminal_program',
        'terminal_image_protocol',
        'terminal_reason',
        'wezterm_status',
        'wezterm_tools',
        'wezterm_reason',
        'yazi_status',
        'yazi_tools',
        'yazi_reason',
        'ya_status',
        'ya_tools',
        'neovim_status',
        'neovim_wrapper',
        'neovim_reason',
        'markdown_status',
        'markdown_tool',
        'markdown_reason',
        'image_preview_status',
        'image_preview_tools',
        'image_preview_reason',
        'pdf_text_status',
        'pdf_text_tools',
        'pdf_image_status',
        'pdf_image_tools',
        'pdf_image_reason',
        'video_metadata_status',
        'video_metadata_tools',
        'video_thumbnail_status',
        'video_thumbnail_tools',
        'root',
        'manifest',
        'bin_dir',
        'bin_link_dir',
        'yazi_safe_config',
        'yazi_rich_config',
        'wezterm_config',
        'state_root',
        'cache_root',
    ):
        value = status.get(key)
        if value not in (None, '', [], {}):
            print(f'{key}: {value}', file=stdout)
    reasons = status.get('degraded_reasons')
    if isinstance(reasons, list) and reasons:
        print('degraded_reasons: ' + ' | '.join(str(reason) for reason in reasons), file=stdout)
    commands = status.get('launch_commands')
    if isinstance(commands, list) and commands:
        for command in commands:
            print(f'launch_command: {command}', file=stdout)


def _print_help(stdout: TextIO) -> None:
    print('usage: ccb tools <doctor|install|update|enable|disable|launch|uninstall> workbench [--profile safe|rich]', file=stdout)


def _shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _shell_double_quote(value: str) -> str:
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('$', '\\$').replace('`', '\\`') + '"'


def _lua_string(value: str) -> str:
    return value.replace('\\', '\\\\').replace('"', '\\"')


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


__all__ = [
    'cmd_tools',
    'cmd_rich',
    'disable_workbench',
    'enable_workbench',
    'launch_workbench',
    'print_workbench_status',
    'provision_workbench',
    'uninstall_workbench',
    'update_rich_workbench',
    'workbench_status',
]
