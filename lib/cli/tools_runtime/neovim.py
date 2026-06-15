from __future__ import annotations

import hashlib
import json
import os
import platform
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
from typing import TextIO
import urllib.request


NEOVIM_RELEASE_API_URL = 'https://api.github.com/repos/neovim/neovim/releases/tags/stable'
LAZY_NVIM_TARBALL_URLS = (
    'https://codeload.github.com/folke/lazy.nvim/tar.gz/refs/heads/main',
    'https://github.com/folke/lazy.nvim/archive/refs/heads/main.tar.gz',
)
NEOVIM_DOWNLOAD_TIMEOUT_S = 30.0
LAZYVIM_SYNC_TIMEOUT_S = 180.0
LAZYVIM_BOOTSTRAP_TIMEOUT_S = 30.0


def cmd_tools(argv: list[str], *, script_root: Path | None = None, stdout: TextIO | None = None, stderr: TextIO | None = None) -> int:
    del script_root
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    if not argv or argv[0] in {'-h', '--help', 'help'}:
        _print_help(stdout)
        return 0
    print('ERROR: standalone Neovim tools are no longer supported; use `ccb update rich`.', file=stderr)
    return 2


def provision_neovim(*, required: bool = False) -> dict[str, object]:
    paths = _paths()
    paths['bin_dir'].mkdir(parents=True, exist_ok=True)
    paths['config_nvim'].mkdir(parents=True, exist_ok=True)
    paths['data'].mkdir(parents=True, exist_ok=True)
    paths['state'].mkdir(parents=True, exist_ok=True)
    paths['cache'].mkdir(parents=True, exist_ok=True)
    nvim = _resolve_nvim()
    if nvim is None:
        download = _ensure_managed_nvim(paths)
        if download.get('status') != 'ok':
            status = {
                'status': 'failed' if required else 'missing',
                'reason': download.get('reason') or 'managed Neovim download failed',
                **_status_paths(paths),
            }
            if download.get('error'):
                status['error'] = download.get('error')
            _write_manifest(paths, status)
            return status
        nvim = Path(str(download['binary']))
    lazyvim_enabled = _lazyvim_profile_enabled()
    if lazyvim_enabled:
        _write_lazyvim_profile(paths)
    _write_wrapper(paths, nvim)
    _write_bin_link(paths)
    lazyvim_sync = (
        _sync_lazyvim_profile(paths)
        if lazyvim_enabled
        else {'status': 'skipped', 'reason': 'disabled by CCB_LAZYVIM_PROFILE=0'}
    )
    manifest = _read_manifest(paths)
    status_value = 'ok'
    reason = None
    if lazyvim_enabled and lazyvim_sync.get('status') != 'ok':
        status_value = 'failed' if required else 'degraded'
        reason = lazyvim_sync.get('reason') or 'LazyVim sync failed'
    capabilities = _check_neovim_capabilities(paths) if lazyvim_enabled else _check_platform_capabilities()
    status = {
        'status': status_value,
        'binary': str(nvim),
        'wrapper': str(paths['wrapper']),
        'bin_link': str(paths['bin_link']),
        'lazyvim_profile': str(paths['profile']),
        'managed_profile': lazyvim_enabled,
        'lazyvim_profile_enabled': lazyvim_enabled,
        'lazyvim_sync_status': lazyvim_sync.get('status'),
        'lazyvim_health_status': lazyvim_sync.get('health_status'),
        'lazyvim_repaired': bool(lazyvim_sync.get('repaired')),
        'uses_system_nvim': not _is_managed_binary(paths, nvim),
        'managed_neovim_target': manifest.get('managed_neovim_target'),
        'managed_neovim_version': manifest.get('managed_neovim_version'),
        'managed_neovim_asset': manifest.get('managed_neovim_asset'),
        **capabilities,
        **_status_paths(paths),
    }
    if reason:
        status['reason'] = reason
    if lazyvim_sync.get('error'):
        status['lazyvim_sync_error'] = lazyvim_sync.get('error')
    if lazyvim_sync.get('health_error'):
        status['lazyvim_health_error'] = lazyvim_sync.get('health_error')
    _write_manifest(paths, status)
    return status


def neovim_status() -> dict[str, object]:
    paths = _paths()
    wrapper_exists = paths['wrapper'].is_file() and os.access(paths['wrapper'], os.X_OK)
    nvim = _resolve_nvim()
    manifest = _read_manifest(paths)
    if wrapper_exists:
        lazyvim_enabled = bool(manifest.get('lazyvim_profile_enabled', paths['marker'].exists()))
        health = _check_lazyvim_health(paths) if lazyvim_enabled else {'status': 'skipped'}
        status_value = 'degraded' if lazyvim_enabled and health.get('status') != 'ok' else 'ok'
        capabilities = _check_neovim_capabilities(paths) if lazyvim_enabled else _check_platform_capabilities()
        return {
            'status': status_value,
            'reason': health.get('reason') if lazyvim_enabled and health.get('status') != 'ok' else None,
            'binary': str(nvim) if nvim is not None else str(manifest.get('binary') or ''),
            'wrapper': str(paths['wrapper']),
            'bin_link': str(paths['bin_link']),
            'lazyvim_profile': str(paths['profile']),
            'managed_profile': lazyvim_enabled,
            'lazyvim_profile_enabled': lazyvim_enabled,
            'lazyvim_sync_status': manifest.get('lazyvim_sync_status'),
            'lazyvim_health_status': health.get('status'),
            'lazyvim_sync_error': manifest.get('lazyvim_sync_error'),
            'lazyvim_health_error': health.get('error') if lazyvim_enabled and health.get('status') != 'ok' else None,
            'uses_system_nvim': manifest.get('uses_system_nvim'),
            'managed_neovim_target': manifest.get('managed_neovim_target'),
            'managed_neovim_version': manifest.get('managed_neovim_version'),
            'managed_neovim_asset': manifest.get('managed_neovim_asset'),
            **capabilities,
            **_status_paths(paths),
        }
    return {
        'status': 'missing',
        'reason': 'ccb-nvim wrapper is not installed',
        'binary': str(nvim) if nvim is not None else None,
        **_check_platform_capabilities(),
        **_status_paths(paths),
    }


def _paths() -> dict[str, Path]:
    data_home = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local' / 'share')
    state_home = Path(os.environ.get('XDG_STATE_HOME') or Path.home() / '.local' / 'state')
    cache_home = Path(os.environ.get('XDG_CACHE_HOME') or Path.home() / '.cache')
    root = data_home / 'ccb' / 'tools' / 'neovim'
    profile = root / 'lazyvim' / 'profile'
    return {
        'root': root,
        'bin_dir': root / 'bin',
        'wrapper': root / 'bin' / 'ccb-nvim',
        'bin_link': Path(os.environ.get('CODEX_BIN_DIR') or Path.home() / '.local' / 'bin') / 'ccb-nvim',
        'profile': profile,
        'config_nvim': profile / 'config' / 'nvim',
        'data': profile / 'share',
        'state': state_home / 'ccb' / 'tools' / 'neovim' / 'xdg-state',
        'cache': cache_home / 'ccb' / 'tools' / 'neovim' / 'xdg-cache',
        'marker': profile / '.ccb-managed-lazyvim',
        'manifest': root / 'manifest.json',
        'downloads': root / 'downloads',
        'versions': root / 'versions',
        'managed_nvim': root / 'bin' / 'nvim',
    }


def _resolve_nvim() -> Path | None:
    managed = _paths()['managed_nvim']
    if managed.is_file() and os.access(managed, os.X_OK):
        return managed
    resolved = shutil.which('nvim')
    return Path(resolved) if resolved else None


def _ensure_managed_nvim(paths: dict[str, Path]) -> dict[str, object]:
    if paths['managed_nvim'].is_file() and os.access(paths['managed_nvim'], os.X_OK):
        manifest = _read_manifest(paths)
        return {
            'status': 'ok',
            'binary': str(paths['managed_nvim']),
            'managed_neovim_target': manifest.get('managed_neovim_target'),
            'managed_neovim_version': manifest.get('managed_neovim_version'),
            'managed_neovim_asset': manifest.get('managed_neovim_asset'),
        }
    asset = _platform_release_asset()
    if asset is None:
        return {
            'status': 'unsupported',
            'reason': f'no managed Neovim asset for {platform.system().lower()}-{platform.machine().lower()}',
        }
    try:
        release = _fetch_release_metadata()
        selected = _select_release_asset(release, asset)
        return _download_and_activate_nvim(paths, selected, release)
    except Exception as exc:
        return {
            'status': 'failed',
            'reason': 'managed Neovim download failed',
            'error': f'{type(exc).__name__}: {exc}',
        }


def _platform_release_asset() -> str | None:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == 'linux':
        if machine in {'x86_64', 'amd64'}:
            return 'nvim-linux-x86_64.tar.gz'
        if machine in {'aarch64', 'arm64'}:
            return 'nvim-linux-arm64.tar.gz'
    if system == 'darwin':
        if machine in {'arm64', 'aarch64'}:
            return 'nvim-macos-arm64.tar.gz'
        if machine in {'x86_64', 'amd64'}:
            return 'nvim-macos-x86_64.tar.gz'
    return None


def _fetch_release_metadata() -> dict[str, object]:
    with urllib.request.urlopen(NEOVIM_RELEASE_API_URL, timeout=NEOVIM_DOWNLOAD_TIMEOUT_S) as response:
        return json.loads(response.read().decode('utf-8'))


def _select_release_asset(release: dict[str, object], asset_name: str) -> dict[str, object]:
    for asset in tuple(release.get('assets') or ()):
        if not isinstance(asset, dict):
            continue
        if str(asset.get('name') or '') == asset_name:
            url = str(asset.get('browser_download_url') or '').strip()
            digest = _normalize_sha256_digest(asset.get('digest'))
            if not url:
                raise RuntimeError(f'Neovim asset {asset_name} has no download URL')
            if not digest:
                raise RuntimeError(f'Neovim asset {asset_name} has no sha256 digest')
            return {
                'name': asset_name,
                'url': url,
                'sha256': digest,
            }
    raise RuntimeError(f'Neovim release asset not found: {asset_name}')


def _normalize_sha256_digest(value: object) -> str:
    text = str(value or '').strip()
    if text.startswith('sha256:'):
        text = text.split(':', 1)[1]
    if len(text) == 64 and all(ch in '0123456789abcdefABCDEF' for ch in text):
        return text.lower()
    return ''


def _download_and_activate_nvim(
    paths: dict[str, Path],
    asset: dict[str, object],
    release: dict[str, object],
) -> dict[str, object]:
    paths['downloads'].mkdir(parents=True, exist_ok=True)
    paths['versions'].mkdir(parents=True, exist_ok=True)
    archive_path = paths['downloads'] / str(asset['name'])
    _download_file(str(asset['url']), archive_path)
    actual = _sha256_file(archive_path)
    expected = str(asset['sha256'])
    if actual != expected:
        raise RuntimeError(f'Neovim asset sha256 mismatch: expected {expected}, got {actual}')
    version_name = str(release.get('tag_name') or 'stable').strip() or 'stable'
    extract_root = paths['versions'] / _safe_version_dir(version_name, str(asset['name']))
    tmp_root = Path(tempfile.mkdtemp(prefix='ccb-nvim-', dir=str(paths['versions'])))
    try:
        with tarfile.open(archive_path, 'r:gz') as archive:
            _safe_extract_tar(archive, tmp_root)
        binary = _find_extracted_nvim(tmp_root)
        if binary is None:
            raise RuntimeError('downloaded Neovim archive did not contain bin/nvim')
        if extract_root.exists():
            shutil.rmtree(extract_root)
        tmp_root.rename(extract_root)
        binary = _find_extracted_nvim(extract_root)
        assert binary is not None
    except Exception:
        shutil.rmtree(tmp_root, ignore_errors=True)
        raise
    _activate_managed_nvim(paths, binary)
    payload = {
        'status': 'ok',
        'binary': str(paths['managed_nvim']),
        'managed_neovim_target': str(binary),
        'managed_neovim_version': version_name,
        'managed_neovim_asset': str(asset['name']),
        'managed_neovim_sha256': actual,
    }
    _write_manifest(paths, {**_read_manifest(paths), **payload})
    return payload


def _download_file(url: str, destination: Path, *, timeout_s: float = NEOVIM_DOWNLOAD_TIMEOUT_S) -> None:
    with urllib.request.urlopen(url, timeout=timeout_s) as response:
        data = response.read()
    destination.write_bytes(data)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_extract_tar(archive: tarfile.TarFile, destination: Path) -> None:
    root = destination.resolve()
    for member in archive.getmembers():
        member_path = (destination / member.name).resolve()
        if not _is_within(root, member_path):
            raise RuntimeError(f'unsafe Neovim archive member: {member.name}')
        if member.issym() or member.islnk():
            link_target = Path(member.linkname)
            if link_target.is_absolute():
                raise RuntimeError(f'unsafe Neovim archive link: {member.name}')
            resolved = ((destination / member.name).parent / member.linkname).resolve()
            if not _is_within(root, resolved):
                raise RuntimeError(f'unsafe Neovim archive link: {member.name}')
    archive.extractall(destination)


def _is_within(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def _find_extracted_nvim(root: Path) -> Path | None:
    candidates = sorted(root.glob('*/bin/nvim')) + sorted(root.glob('**/bin/nvim'))
    for candidate in candidates:
        if candidate.is_file():
            candidate.chmod(candidate.stat().st_mode | 0o755)
            return candidate
    return None


def _activate_managed_nvim(paths: dict[str, Path], binary: Path) -> None:
    target = paths['managed_nvim']
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f'.{target.name}.tmp')
    if tmp.exists() or tmp.is_symlink():
        tmp.unlink()
    try:
        tmp.symlink_to(binary)
    except OSError:
        tmp.write_text(
            '#!/usr/bin/env sh\n'
            f'exec {_shell_quote(str(binary))} "$@"\n',
            encoding='utf-8',
        )
        tmp.chmod(0o755)
    tmp.replace(target)


def _safe_version_dir(version: str, asset_name: str) -> str:
    text = f'{version}-{asset_name}'.replace('/', '-')
    return ''.join(ch if ch.isalnum() or ch in {'.', '_', '-'} else '-' for ch in text)


def _is_managed_binary(paths: dict[str, Path], nvim: Path) -> bool:
    try:
        return nvim.resolve() == paths['managed_nvim'].resolve()
    except Exception:
        return str(nvim) == str(paths['managed_nvim'])


def _write_lazyvim_profile(paths: dict[str, Path]) -> None:
    init_lua = paths['config_nvim'] / 'init.lua'
    if not init_lua.exists() or _is_managed_lazyvim_init(init_lua):
        init_lua.write_text(_managed_lazyvim_init_text(), encoding='utf-8')
    plugins = paths['config_nvim'] / 'lua' / 'plugins'
    plugins.mkdir(parents=True, exist_ok=True)
    terminal_compat = plugins / 'ccb-terminal-compat.lua'
    if not terminal_compat.exists() or _is_managed_lazyvim_init(terminal_compat):
        terminal_compat.write_text(_managed_lazyvim_terminal_compat_text(), encoding='utf-8')
    treesitter = plugins / 'ccb-treesitter.lua'
    if not treesitter.exists() or _is_managed_lazyvim_init(treesitter):
        treesitter.write_text(_managed_lazyvim_treesitter_text(), encoding='utf-8')
    markdown = plugins / 'ccb-markdown.lua'
    if not markdown.exists() or _is_managed_lazyvim_init(markdown):
        markdown.write_text(_managed_lazyvim_markdown_text(), encoding='utf-8')
    open_helpers = plugins / 'ccb-open.lua'
    if not open_helpers.exists() or _is_managed_lazyvim_init(open_helpers):
        open_helpers.write_text(_managed_lazyvim_open_text(), encoding='utf-8')
    keep = plugins / '.keep'
    if not keep.exists():
        keep.write_text('', encoding='utf-8')
    paths['marker'].write_text('managed_by=ccb\n', encoding='utf-8')


def _is_managed_lazyvim_init(path: Path) -> bool:
    try:
        return path.read_text(encoding='utf-8').startswith('-- Managed by CCB.')
    except Exception:
        return False


def _managed_lazyvim_init_text() -> str:
    return (
        '-- Managed by CCB. This profile is isolated from ~/.config/nvim.\n'
        'vim.g.mapleader = " "\n'
        'vim.g.maplocalleader = " "\n'
        'vim.g.have_nerd_font = false\n'
        'local ccb_parser_runtimepaths = {}\n'
        'local function ccb_record_parser_runtimepaths()\n'
        '  local seen = {}\n'
        '  for _, lang in ipairs({ "markdown", "markdown_inline", "lua", "vimdoc" }) do\n'
        '    for _, file in ipairs(vim.api.nvim_get_runtime_file("parser/" .. lang .. ".so", false)) do\n'
        '      local runtime = file:match("^(.*)[/\\\\]parser[/\\\\][^/\\\\]+$")\n'
        '      if runtime and not seen[runtime] then\n'
        '        seen[runtime] = true\n'
        '        table.insert(ccb_parser_runtimepaths, runtime)\n'
        '      end\n'
        '    end\n'
        '  end\n'
        'end\n'
        'local function ccb_restore_parser_runtimepaths()\n'
        '  for _, runtime in ipairs(ccb_parser_runtimepaths) do\n'
        '    if vim.fn.index(vim.opt.runtimepath:get(), runtime) < 0 then\n'
        '      vim.opt.runtimepath:append(runtime)\n'
        '    end\n'
        '    if vim.fn.index(vim.opt.packpath:get(), runtime) < 0 then\n'
        '      vim.opt.packpath:append(runtime)\n'
        '    end\n'
        '  end\n'
        'end\n'
        'local function ccb_has_recorded_parser(lang)\n'
        '  for _, runtime in ipairs(ccb_parser_runtimepaths) do\n'
        '    if vim.fn.filereadable(runtime .. "/parser/" .. lang .. ".so") == 1 then\n'
        '      return true\n'
        '    end\n'
        '  end\n'
        '  return false\n'
        'end\n'
        'ccb_record_parser_runtimepaths()\n'
        'vim.g.ccb_markdown_parser_ready = ccb_has_recorded_parser("markdown") and ccb_has_recorded_parser("markdown_inline")\n'
        'local function ccb_terminal_compat()\n'
        '  vim.opt.fillchars = { foldopen = "-", foldclose = "+", fold = " ", foldsep = " ", diff = "/", eob = " " }\n'
        'end\n'
        'ccb_terminal_compat()\n'
        'vim.api.nvim_create_autocmd("User", { pattern = { "VeryLazy", "LazyDone" }, callback = function()\n'
        '  ccb_terminal_compat()\n'
        '  ccb_restore_parser_runtimepaths()\n'
        'end })\n'
        'local lazypath = vim.fn.stdpath("data") .. "/lazy/lazy.nvim"\n'
        'vim.opt.rtp:prepend(lazypath)\n'
        'ccb_restore_parser_runtimepaths()\n'
        'local ok, lazy = pcall(require, "lazy")\n'
        'if not ok then\n'
        '  vim.api.nvim_err_writeln("CCB LazyVim profile is not provisioned: " .. tostring(lazy))\n'
        '  return\n'
        'end\n'
        'lazy.setup({ { "LazyVim/LazyVim", import = "lazyvim.plugins" }, { import = "plugins" } })\n'
        'ccb_restore_parser_runtimepaths()\n'
    )


def _managed_lazyvim_terminal_compat_text() -> str:
    return (
        '-- Managed by CCB. Terminal compatibility for the isolated LazyVim profile.\n'
        'local icon_style = vim.env.CCB_LAZYVIM_ICON_STYLE or "ascii"\n'
        'local ascii_icons = {\n'
        '  misc = { dots = "..." },\n'
        '  ft = { octo = "GH ", gh = "GH ", ["markdown.gh"] = "GH " },\n'
        '  dap = {\n'
        '    Stopped = { "> ", "DiagnosticWarn", "DapStoppedLine" },\n'
        '    Breakpoint = "B ",\n'
        '    BreakpointCondition = "? ",\n'
        '    BreakpointRejected = "! ",\n'
        '    LogPoint = ".>",\n'
        '  },\n'
        '  diagnostics = { Error = "E ", Warn = "W ", Hint = "H ", Info = "I " },\n'
        '  git = { added = "+ ", modified = "~ ", removed = "- " },\n'
        '  kinds = {\n'
        '    Array = "A ", Boolean = "B ", Class = "C ", Codeium = "AI ", Color = "C ",\n'
        '    Control = "Ctrl ", Collapsed = "> ", Constant = "Const ", Constructor = "Ctor ",\n'
        '    Copilot = "AI ", Enum = "Enum ", EnumMember = "Enum ", Event = "Ev ",\n'
        '    Field = "Fld ", File = "File ", Folder = "Dir ", Function = "Fn ",\n'
        '    Interface = "Iface ", Key = "Key ", Keyword = "Kw ", Method = "Meth ",\n'
        '    Module = "Mod ", Namespace = "Ns ", Null = "Null ", Number = "Num ",\n'
        '    Object = "Obj ", Operator = "Op ", Package = "Pkg ", Property = "Prop ",\n'
        '    Reference = "Ref ", Snippet = "Snip ", String = "Str ", Struct = "Struct ",\n'
        '    Supermaven = "AI ", TabNine = "AI ", Text = "Txt ", TypeParameter = "T ",\n'
        '    Unit = "Unit ", Value = "Val ", Variable = "Var ",\n'
        '  },\n'
        '}\n'
        '\n'
        'local function apply_ascii_options()\n'
        '  vim.g.have_nerd_font = icon_style == "glyph"\n'
        '  if icon_style ~= "glyph" then\n'
        '    vim.opt.fillchars = { foldopen = "-", foldclose = "+", fold = " ", foldsep = " ", diff = "/", eob = " " }\n'
        '  end\n'
        'end\n'
        '\n'
        'local function ccb_terminal_image_candidate()\n'
        '  if vim.env.CCB_LAZYVIM_IMAGE_INLINE == "1" then return true end\n'
        '  if vim.env.KITTY_WINDOW_ID then return true end\n'
        '  local term_program = (vim.env.TERM_PROGRAM or ""):lower()\n'
        '  if term_program:find("kitty", 1, true) or term_program:find("wezterm", 1, true) or term_program:find("ghostty", 1, true) then\n'
        '    return vim.env.TMUX == nil\n'
        '  end\n'
        '  return false\n'
        'end\n'
        '\n'
        'local function ccb_install_string_buffer_fallback()\n'
        '  local ok = pcall(require, "string.buffer")\n'
        '  if ok then return end\n'
        '  if package.preload["string.buffer"] then return end\n'
        '  package.preload["string.buffer"] = function()\n'
        '    local Buffer = {}\n'
        '    Buffer.__index = Buffer\n'
        '    Buffer.__len = function(self)\n'
        '      return #table.concat(self._chunks)\n'
        '    end\n'
        '    function Buffer:put(value)\n'
        '      table.insert(self._chunks, tostring(value or ""))\n'
        '      return self\n'
        '    end\n'
        '    function Buffer:putf(fmt, ...)\n'
        '      table.insert(self._chunks, string.format(fmt, ...))\n'
        '      return self\n'
        '    end\n'
        '    function Buffer:get()\n'
        '      return table.concat(self._chunks)\n'
        '    end\n'
        '    local function encode(value)\n'
        '      local payload = value or {}\n'
        '      if vim.json and vim.json.encode then\n'
        '        local json_ok, json = pcall(vim.json.encode, payload)\n'
        '        if json_ok then return json end\n'
        '      end\n'
        '      return vim.fn.json_encode(payload)\n'
        '    end\n'
        '    local function decode(text)\n'
        '      if vim.json and vim.json.decode then\n'
        '        local json_ok, decoded = pcall(vim.json.decode, text or "{}")\n'
        '        if json_ok and type(decoded) == "table" then return decoded end\n'
        '      end\n'
        '      local fn_ok, decoded = pcall(vim.fn.json_decode, text or "{}")\n'
        '      return fn_ok and type(decoded) == "table" and decoded or {}\n'
        '    end\n'
        '    return {\n'
        '      new = function() return setmetatable({ _chunks = {} }, Buffer) end,\n'
        '      encode = encode,\n'
        '      decode = decode,\n'
        '    }\n'
        '  end\n'
        'end\n'
        'ccb_install_string_buffer_fallback()\n'
        '\n'
        'return {\n'
        '  {\n'
        '    "LazyVim/LazyVim",\n'
        '    opts = icon_style == "glyph" and {} or { icons = ascii_icons },\n'
        '    init = apply_ascii_options,\n'
        '  },\n'
        '  {\n'
        '    "folke/snacks.nvim",\n'
        '    opts = function(_, opts)\n'
        '      opts = opts or {}\n'
        '      opts.explorer = opts.explorer or {}\n'
        '      opts.explorer.enabled = true\n'
        '      opts.explorer.replace_netrw = true\n'
        '      opts.picker = opts.picker or {}\n'
        '      opts.picker.enabled = true\n'
        '      opts.picker.sources = opts.picker.sources or {}\n'
        '      opts.picker.sources.explorer = vim.tbl_deep_extend("force", opts.picker.sources.explorer or {}, {\n'
        '        watch = false,\n'
        '      })\n'
        '      opts.image = vim.tbl_deep_extend("force", opts.image or {}, {\n'
        '        enabled = true,\n'
        '        force = false,\n'
        '        doc = { enabled = true, inline = true, float = true },\n'
        '      })\n'
        '      if not ccb_terminal_image_candidate() then\n'
        '        opts.image.formats = {}\n'
        '        opts.image.doc = vim.tbl_deep_extend("force", opts.image.doc or {}, {\n'
        '          enabled = false,\n'
        '          inline = false,\n'
        '          float = false,\n'
        '        })\n'
        '      end\n'
        '      if icon_style == "glyph" then return opts end\n'
        '      opts.dashboard = opts.dashboard or {}\n'
        '      opts.dashboard.preset = opts.dashboard.preset or {}\n'
        '      opts.dashboard.preset.keys = opts.dashboard.preset.keys or {}\n'
        '      for _, item in ipairs(opts.dashboard.preset.keys) do\n'
        '        item.icon = ""\n'
        '      end\n'
        '      return opts\n'
        '    end,\n'
        '  },\n'
        '  {\n'
        '    "nvim-mini/mini.icons",\n'
        '    opts = function(_, opts)\n'
        '      opts = opts or {}\n'
        '      opts.style = icon_style\n'
        '      if icon_style ~= "glyph" then\n'
        '        opts.file = vim.tbl_deep_extend("force", opts.file or {}, {\n'
        '          [".keep"] = { glyph = "K", hl = "MiniIconsGrey" },\n'
        '          ["devcontainer.json"] = { glyph = "D", hl = "MiniIconsAzure" },\n'
        '        })\n'
        '        opts.filetype = vim.tbl_deep_extend("force", opts.filetype or {}, {\n'
        '          dotenv = { glyph = "E", hl = "MiniIconsYellow" },\n'
        '        })\n'
        '      end\n'
        '      return opts\n'
        '    end,\n'
        '  },\n'
        '  {\n'
        '    "akinsho/bufferline.nvim",\n'
        '    opts = function(_, opts)\n'
        '      if icon_style == "glyph" then return opts end\n'
        '      opts = opts or {}\n'
        '      opts.options = opts.options or {}\n'
        '      opts.options.show_buffer_icons = false\n'
        '      opts.options.show_buffer_close_icons = false\n'
        '      opts.options.show_close_icon = false\n'
        '      opts.options.get_element_icon = function() return "" end\n'
        '      return opts\n'
        '    end,\n'
        '  },\n'
        '  {\n'
        '    "nvim-lualine/lualine.nvim",\n'
        '    opts = function(_, opts)\n'
        '      if icon_style == "glyph" then return opts end\n'
        '      opts = opts or {}\n'
        '      opts.sections = opts.sections or {}\n'
        '      opts.sections.lualine_z = {}\n'
        '      return opts\n'
        '    end,\n'
        '  },\n'
        '}\n'
    )


def _managed_lazyvim_markdown_text() -> str:
    return (
        '-- Managed by CCB. Markdown enhancements for the isolated LazyVim profile.\n'
        'local function ccb_has_parser(lang)\n'
        '  if vim.g.ccb_markdown_parser_ready == true then\n'
        '    return true\n'
        '  end\n'
        '  return #vim.api.nvim_get_runtime_file("parser/" .. lang .. ".so", false) > 0\n'
        'end\n'
        '\n'
        'local function ccb_markdown_parser_ready()\n'
        '  return vim.g.ccb_markdown_parser_ready == true or (ccb_has_parser("markdown") and ccb_has_parser("markdown_inline"))\n'
        'end\n'
        '\n'
        'return {\n'
        '  {\n'
        '    "MeanderingProgrammer/render-markdown.nvim",\n'
        '    ft = { "markdown" },\n'
        '    enabled = ccb_markdown_parser_ready,\n'
        '    dependencies = { "nvim-treesitter/nvim-treesitter", "nvim-mini/mini.icons" },\n'
        '    opts = function(_, opts)\n'
        '      opts = opts or {}\n'
        '      opts.completions = opts.completions or {}\n'
        '      opts.completions.lsp = opts.completions.lsp or {}\n'
        '      opts.completions.lsp.enabled = true\n'
        '      return opts\n'
        '    end,\n'
        '  },\n'
        '}\n'
    )


def _managed_lazyvim_open_text() -> str:
    return (
        '-- Managed by CCB. External open and reveal helpers for the isolated LazyVim profile.\n'
        'local function ccb_is_wsl()\n'
        '  return vim.env.WSL_DISTRO_NAME ~= nil or vim.env.WSL_INTEROP ~= nil\n'
        'end\n'
        '\n'
        'local function ccb_executable(name)\n'
        '  return vim.fn.executable(name) == 1\n'
        'end\n'
        '\n'
        'local function ccb_opener()\n'
        '  if vim.fn.has("mac") == 1 and ccb_executable("open") then\n'
        '    return { "open" }\n'
        '  end\n'
        '  if ccb_is_wsl() then\n'
        '    for _, candidate in ipairs({ "wslview", "explorer.exe", "xdg-open" }) do\n'
        '      if ccb_executable(candidate) then return { candidate } end\n'
        '    end\n'
        '  end\n'
        '  for _, candidate in ipairs({ "xdg-open", "gio", "kde-open", "gnome-open" }) do\n'
        '    if ccb_executable(candidate) then\n'
        '      if candidate == "gio" then return { "gio", "open" } end\n'
        '      return { candidate }\n'
        '    end\n'
        '  end\n'
        '  return nil\n'
        'end\n'
        '\n'
        'local function ccb_open(target)\n'
        '  target = vim.fn.expand(target or "")\n'
        '  if target == "" then\n'
        '    vim.notify("No path or URL to open", vim.log.levels.WARN)\n'
        '    return\n'
        '  end\n'
        '  if vim.ui and vim.ui.open then\n'
        '    local ok = pcall(vim.ui.open, target)\n'
        '    if ok then return end\n'
        '  end\n'
        '  local opener = ccb_opener()\n'
        '  if not opener then\n'
        '    vim.notify("No external opener available for " .. target, vim.log.levels.WARN)\n'
        '    return\n'
        '  end\n'
        '  local command = vim.list_extend(vim.deepcopy(opener), { target })\n'
        '  if vim.system then\n'
        '    vim.system(command, { detach = true })\n'
        '  else\n'
        '    vim.fn.jobstart(command, { detach = true })\n'
        '  end\n'
        'end\n'
        '\n'
        'local function ccb_current_file()\n'
        '  local name = vim.api.nvim_buf_get_name(0)\n'
        '  if name == "" then return "" end\n'
        '  return vim.fn.fnamemodify(name, ":p")\n'
        'end\n'
        '\n'
        'local image_extensions = {\n'
        '  png = true,\n'
        '  jpg = true,\n'
        '  jpeg = true,\n'
        '  gif = true,\n'
        '  webp = true,\n'
        '  bmp = true,\n'
        '  tif = true,\n'
        '  tiff = true,\n'
        '  avif = true,\n'
        '  heic = true,\n'
        '  svg = true,\n'
        '}\n'
        '\n'
        'local function ccb_is_image_file(path)\n'
        '  local ext = vim.fn.fnamemodify(path or "", ":e"):lower()\n'
        '  return image_extensions[ext] == true\n'
        'end\n'
        '\n'
        'local function ccb_inline_image_supported()\n'
        '  local ok_image, image = pcall(require, "snacks.image")\n'
        '  if not ok_image or type(image) ~= "table" or type(image.supports_terminal) ~= "function" then\n'
        '    return false\n'
        '  end\n'
        '  local ok_supported, supported = pcall(image.supports_terminal)\n'
        '  return ok_supported and supported == true\n'
        'end\n'
        '\n'
        'local function ccb_open_current_file()\n'
        '  ccb_open(ccb_current_file())\n'
        'end\n'
        '\n'
        'local function ccb_open_current_image()\n'
        '  local current = ccb_current_file()\n'
        '  if current == "" then\n'
        '    vim.notify("No current image to open", vim.log.levels.WARN)\n'
        '    return\n'
        '  end\n'
        '  ccb_open(current)\n'
        'end\n'
        '\n'
        'local function ccb_open_under_cursor()\n'
        '  local target = vim.fn.expand("<cfile>")\n'
        '  if target == "" then target = vim.fn.expand("<cWORD>") end\n'
        '  ccb_open(target)\n'
        'end\n'
        '\n'
        'local function ccb_reveal_current_file()\n'
        '  local current = ccb_current_file()\n'
        '  if current == "" then\n'
        '    vim.notify("No current file to reveal", vim.log.levels.WARN)\n'
        '    return\n'
        '  end\n'
        '  local dir = vim.fn.fnamemodify(current, ":h")\n'
        '  local ok_snacks, snacks = pcall(require, "snacks")\n'
        '  if ok_snacks and snacks.picker and snacks.picker.explorer then\n'
        '    snacks.picker.explorer({ cwd = dir })\n'
        '    return\n'
        '  end\n'
        '  ccb_open(dir)\n'
        'end\n'
        '\n'
        'local function ccb_prepare_image_buffer(path)\n'
        '  if not ccb_is_image_file(path) then return end\n'
        '  vim.bo.modifiable = true\n'
        '  vim.bo.readonly = false\n'
        '  vim.api.nvim_buf_set_lines(0, 0, -1, false, {\n'
        '    "CCB image file",\n'
        '    "",\n'
        '    path,\n'
        '    "",\n'
        '    "Inline image rendering is not available in this terminal session.",\n'
        '    "CCB tried to open the file with the system image viewer.",\n'
        '    "",\n'
        '    "Commands:",\n'
        '    "  :CCBOpenImage      open this image externally",\n'
        '    "  :CCBRevealCurrent  reveal it in the file explorer",\n'
        '  })\n'
        '  vim.bo.filetype = "ccbimage"\n'
        '  vim.bo.buftype = "nofile"\n'
        '  vim.bo.bufhidden = "wipe"\n'
        '  vim.bo.swapfile = false\n'
        '  vim.bo.modified = false\n'
        '  vim.bo.readonly = true\n'
        '  vim.bo.modifiable = false\n'
        'end\n'
        '\n'
        'local function ccb_maybe_open_image_buffer(args)\n'
        '  if #vim.api.nvim_list_uis() == 0 then return end\n'
        '  local path = vim.api.nvim_buf_get_name(args.buf)\n'
        '  if path == "" or not ccb_is_image_file(path) then return end\n'
        '  if ccb_inline_image_supported() then return end\n'
        '  vim.schedule(function()\n'
        '    if not vim.api.nvim_buf_is_valid(args.buf) then return end\n'
        '    vim.api.nvim_set_current_buf(args.buf)\n'
        '    ccb_prepare_image_buffer(path)\n'
        '    ccb_open(path)\n'
        '  end)\n'
        'end\n'
        '\n'
        'vim.api.nvim_create_user_command("CCBOpenCurrent", ccb_open_current_file, {})\n'
        'vim.api.nvim_create_user_command("CCBOpenUnderCursor", ccb_open_under_cursor, {})\n'
        'vim.api.nvim_create_user_command("CCBOpenImage", ccb_open_current_image, {})\n'
        'vim.api.nvim_create_user_command("CCBRevealCurrent", ccb_reveal_current_file, {})\n'
        'vim.api.nvim_create_autocmd("BufReadPost", {\n'
        '  group = vim.api.nvim_create_augroup("ccb_image_external_open", { clear = true }),\n'
        '  callback = ccb_maybe_open_image_buffer,\n'
        '})\n'
        'vim.keymap.set("n", "<leader>co", ccb_open_current_file, { desc = "CCB open current file externally" })\n'
        'vim.keymap.set("n", "<leader>cO", ccb_open_under_cursor, { desc = "CCB open path or URL under cursor" })\n'
        'vim.keymap.set("n", "<leader>ci", ccb_open_current_image, { desc = "CCB open image externally" })\n'
        'vim.keymap.set("n", "<leader>cr", ccb_reveal_current_file, { desc = "CCB reveal current file" })\n'
        '\n'
        'return {}\n'
    )


def _managed_lazyvim_treesitter_text() -> str:
    return (
        '-- Managed by CCB. Treesitter policy for the isolated LazyVim profile.\n'
        'local allow_parser_install = vim.env.CCB_LAZYVIM_TS_INSTALL == "1"\n'
        '\n'
        'return {\n'
        '  {\n'
        '    "nvim-treesitter/nvim-treesitter",\n'
        '    opts = function(_, opts)\n'
        '      opts = opts or {}\n'
        '      if not allow_parser_install then\n'
        '        opts.ensure_installed = {}\n'
        '        opts.auto_install = false\n'
        '        opts.sync_install = false\n'
        '      end\n'
        '      return opts\n'
        '    end,\n'
        '  },\n'
        '}\n'
    )


def _write_wrapper(paths: dict[str, Path], nvim: Path) -> None:
    wrapper = paths['wrapper']
    wrapper.write_text(
        '#!/usr/bin/env sh\n'
        'set -eu\n'
        f'export XDG_CONFIG_HOME={_shell_quote(str(paths["profile"] / "config"))}\n'
        f'export XDG_DATA_HOME={_shell_quote(str(paths["data"]))}\n'
        f'export XDG_STATE_HOME={_shell_quote(str(paths["state"]))}\n'
        f'export XDG_CACHE_HOME={_shell_quote(str(paths["cache"]))}\n'
        'export NVIM_APPNAME=nvim\n'
        'export COLORTERM="${COLORTERM:-truecolor}"\n'
        f'exec {_shell_quote(str(nvim))} "$@"\n',
        encoding='utf-8',
    )
    wrapper.chmod(0o755)


def _sync_lazyvim_profile(paths: dict[str, Path]) -> dict[str, object]:
    wrapper = paths['wrapper']
    if not wrapper.is_file():
        return {'status': 'failed', 'reason': 'ccb-nvim wrapper is missing'}
    bootstrap = _ensure_lazy_nvim(paths)
    if bootstrap.get('status') != 'ok':
        return {
            'status': 'failed',
            'reason': bootstrap.get('reason') or 'lazy.nvim bootstrap failed',
            'error': bootstrap.get('error'),
            'repaired': bool(bootstrap.get('repaired')),
        }
    first = _run_lazyvim_sync(paths)
    health = _check_lazyvim_health(paths) if first.get('status') == 'ok' else {'status': 'failed'}
    if first.get('status') == 'ok' and health.get('status') == 'ok':
        return {
            **first,
            'health_status': 'ok',
            'repaired': bool(bootstrap.get('repaired')),
        }
    _reset_lazyvim_plugin_dir(paths)
    bootstrap = _ensure_lazy_nvim(paths)
    if bootstrap.get('status') != 'ok':
        return {
            'status': 'failed',
            'reason': bootstrap.get('reason') or 'lazy.nvim repair failed',
            'error': bootstrap.get('error'),
            'repaired': True,
        }
    second = _run_lazyvim_sync(paths)
    if second.get('status') != 'ok':
        return {**second, 'repaired': True}
    health = _check_lazyvim_health(paths)
    if health.get('status') != 'ok':
        return {
            'status': 'failed',
            'reason': health.get('reason') or 'LazyVim health check failed',
            'error': health.get('error'),
            'health_status': health.get('status'),
            'health_error': health.get('error'),
            'repaired': True,
        }
    return {
        **second,
        'health_status': 'ok',
        'repaired': True,
    }


def _ensure_lazy_nvim(paths: dict[str, Path]) -> dict[str, object]:
    lazy_path = _lazy_nvim_path(paths)
    repaired = False
    if lazy_path.exists() and not _lazy_nvim_looks_usable(paths):
        _safe_rmtree(lazy_path, root=paths['root'])
        repaired = True
    if _lazy_nvim_looks_usable(paths):
        return {'status': 'ok', 'repaired': repaired}
    lazy_path.parent.mkdir(parents=True, exist_ok=True)
    git_result = _clone_lazy_nvim_with_git(paths, lazy_path)
    if git_result.get('status') != 'ok':
        if lazy_path.exists():
            repaired = True
        _safe_rmtree(lazy_path, root=paths['root'])
        tarball_result = _install_lazy_nvim_from_tarball(paths, lazy_path)
        if tarball_result.get('status') != 'ok':
            return {
                'status': 'failed',
                'reason': tarball_result.get('reason') or git_result.get('reason') or 'lazy.nvim bootstrap failed',
                'error': _join_errors(git_result.get('error'), tarball_result.get('error')),
                'repaired': repaired,
            }
    if not _lazy_nvim_looks_usable(paths):
        _safe_rmtree(lazy_path, root=paths['root'])
        return {
            'status': 'failed',
            'reason': 'lazy.nvim bootstrap did not install required Lua files',
            'repaired': repaired,
        }
    return {'status': 'ok', 'repaired': repaired}


def _clone_lazy_nvim_with_git(paths: dict[str, Path], lazy_path: Path) -> dict[str, object]:
    try:
        completed = subprocess.run(
            [
                'git',
                'clone',
                '--filter=blob:none',
                '--branch=stable',
                'https://github.com/folke/lazy.nvim.git',
                str(lazy_path),
            ],
            cwd=str(paths['root']),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=_lazyvim_bootstrap_timeout_s(),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            'status': 'failed',
            'reason': 'lazy.nvim git bootstrap timed out',
            'error': _process_output_text(exc.stdout, exc.stderr),
        }
    except Exception as exc:
        return {
            'status': 'failed',
            'reason': 'lazy.nvim git bootstrap failed',
            'error': f'{type(exc).__name__}: {exc}',
        }
    if completed.returncode != 0:
        return {
            'status': 'failed',
            'reason': f'lazy.nvim git bootstrap exited with {completed.returncode}',
            'error': _short_process_text((completed.stdout or '') + '\n' + (completed.stderr or '')),
        }
    return {'status': 'ok'}


def _install_lazy_nvim_from_tarball(paths: dict[str, Path], lazy_path: Path) -> dict[str, object]:
    archive_path = paths['downloads'] / 'lazy.nvim-main.tar.gz'
    tmp_root = Path(tempfile.mkdtemp(prefix='ccb-lazy-nvim-', dir=str(paths['root'])))
    try:
        paths['downloads'].mkdir(parents=True, exist_ok=True)
        download_error = _download_first_available(LAZY_NVIM_TARBALL_URLS, archive_path)
        if download_error is not None:
            raise RuntimeError(download_error)
        with tarfile.open(archive_path, 'r:gz') as archive:
            _safe_extract_tar(archive, tmp_root)
        extracted = _find_lazy_nvim_extract_root(tmp_root)
        if extracted is None:
            raise RuntimeError('lazy.nvim tarball did not contain lua/lazy/init.lua')
        if lazy_path.exists():
            _safe_rmtree(lazy_path, root=paths['root'])
        lazy_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(extracted), str(lazy_path))
    except Exception as exc:
        _safe_rmtree(lazy_path, root=paths['root'])
        return {
            'status': 'failed',
            'reason': 'lazy.nvim tarball bootstrap failed',
            'error': f'{type(exc).__name__}: {exc}',
        }
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    return {'status': 'ok'}


def _download_first_available(urls: tuple[str, ...], destination: Path) -> str | None:
    errors: list[str] = []
    for url in urls:
        try:
            _download_file(url, destination, timeout_s=_lazyvim_bootstrap_timeout_s())
            return None
        except Exception as exc:
            errors.append(f'{url}: {type(exc).__name__}: {exc}')
    return '\n'.join(errors)


def _find_lazy_nvim_extract_root(root: Path) -> Path | None:
    for candidate in sorted(root.iterdir()):
        if candidate.is_dir() and (candidate / 'lua' / 'lazy' / 'init.lua').is_file():
            return candidate
    for candidate in sorted(root.glob('**/lua/lazy/init.lua')):
        parent = candidate.parents[2]
        if parent.is_dir():
            return parent
    return None


def _lazy_nvim_looks_usable(paths: dict[str, Path]) -> bool:
    return (_lazy_nvim_path(paths) / 'lua' / 'lazy' / 'init.lua').is_file()


def _lazy_nvim_path(paths: dict[str, Path]) -> Path:
    return paths['data'] / 'nvim' / 'lazy' / 'lazy.nvim'


def _lazyvim_plugin_path(paths: dict[str, Path]) -> Path:
    return paths['data'] / 'nvim' / 'lazy' / 'LazyVim'


def _reset_lazyvim_plugin_dir(paths: dict[str, Path]) -> None:
    _safe_rmtree(paths['data'] / 'nvim' / 'lazy', root=paths['root'])


def _safe_rmtree(path: Path, *, root: Path) -> None:
    try:
        resolved_path = path.resolve()
        resolved_root = root.resolve()
        resolved_path.relative_to(resolved_root)
    except Exception:
        return
    shutil.rmtree(resolved_path, ignore_errors=True)


def _run_lazyvim_sync(paths: dict[str, Path]) -> dict[str, object]:
    wrapper = paths['wrapper']
    try:
        completed = subprocess.run(
            [str(wrapper), '--headless', '+Lazy! sync', '+qa'],
            cwd=str(paths['root']),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=_lazyvim_sync_timeout_s(),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            'status': 'failed',
            'reason': 'LazyVim sync timed out',
            'error': _process_output_text(exc.stdout, exc.stderr),
        }
    except Exception as exc:
        return {
            'status': 'failed',
            'reason': 'LazyVim sync failed',
            'error': f'{type(exc).__name__}: {exc}',
        }
    if completed.returncode == 0:
        return {'status': 'ok'}
    return {
        'status': 'failed',
        'reason': f'LazyVim sync exited with {completed.returncode}',
        'error': _short_process_text((completed.stdout or '') + '\n' + (completed.stderr or '')),
    }


def _check_lazyvim_health(paths: dict[str, Path]) -> dict[str, object]:
    wrapper = paths['wrapper']
    if not wrapper.is_file():
        return {'status': 'failed', 'reason': 'ccb-nvim wrapper is missing'}
    script = (
        'local lazypath = vim.fn.stdpath("data") .. "/lazy/lazy.nvim"; '
        'vim.opt.rtp:prepend(lazypath); '
        'local ok_lazy, lazy_err = pcall(require, "lazy"); '
        'if not ok_lazy then error("lazy.nvim not loadable: " .. tostring(lazy_err)) end; '
        'local lazyvim_init = vim.fn.stdpath("data") .. "/lazy/LazyVim/lua/lazyvim/init.lua"; '
        'if vim.fn.filereadable(lazyvim_init) ~= 1 then error("LazyVim plugin files missing: " .. lazyvim_init) end; '
        'print("ccb_lazyvim_health=ok")'
    )
    try:
        completed = subprocess.run(
            [str(wrapper), '--clean', '--headless', '+lua ' + script, '+qa'],
            cwd=str(paths['root']),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=min(_lazyvim_sync_timeout_s(), 30.0),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            'status': 'failed',
            'reason': 'LazyVim health check timed out',
            'error': _process_output_text(exc.stdout, exc.stderr),
        }
    except Exception as exc:
        return {
            'status': 'failed',
            'reason': 'LazyVim health check failed',
            'error': f'{type(exc).__name__}: {exc}',
        }
    if completed.returncode == 0 and (_lazyvim_plugin_path(paths) / 'lua' / 'lazyvim' / 'init.lua').is_file():
        return {'status': 'ok'}
    return {
        'status': 'failed',
        'reason': 'LazyVim health check failed',
        'error': _short_process_text((completed.stdout or '') + '\n' + (completed.stderr or '')),
    }


def _check_neovim_capabilities(paths: dict[str, Path]) -> dict[str, object]:
    return {
        **_check_platform_capabilities(),
        **_check_markdown_parser_status(paths),
    }


def _check_platform_capabilities() -> dict[str, object]:
    return {
        **_check_wsl_status(),
        **_check_opener_status(),
        **_check_clipboard_status(),
        **_check_image_status(),
    }


def _check_markdown_parser_status(paths: dict[str, Path]) -> dict[str, object]:
    wrapper = paths['wrapper']
    if not wrapper.is_file():
        return {
            'markdown_parser_status': 'skipped',
            'markdown_parser_detail': 'ccb-nvim wrapper is missing',
        }
    script = (
        'local missing = {}; '
        'local details = {}; '
        'for _, lang in ipairs({ "markdown", "markdown_inline" }) do '
        '  local files = vim.api.nvim_get_runtime_file("parser/" .. lang .. ".so", false); '
        '  local ok = #files > 0; '
        '  if ok and vim.treesitter and vim.treesitter.language and type(vim.treesitter.language.inspect) == "function" then '
        '    ok = pcall(vim.treesitter.language.inspect, lang); '
        '  end; '
        '  table.insert(details, lang .. ":" .. (ok and "ok" or "missing") .. ":" .. tostring(#files)); '
        '  if not ok then table.insert(missing, lang) end; '
        'end; '
        'print("ccb_markdown_parser_status=" .. (#missing == 0 and "ok" or "degraded")); '
        'print("ccb_markdown_parser_detail=" .. table.concat(details, ",")); '
    )
    try:
        completed = subprocess.run(
            [str(wrapper), '--clean', '--headless', '+lua ' + script, '+qa'],
            cwd=str(paths['root']),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=min(_lazyvim_sync_timeout_s(), 15.0),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            'markdown_parser_status': 'failed',
            'markdown_parser_detail': 'parser readiness check timed out',
            'markdown_parser_error': _process_output_text(exc.stdout, exc.stderr),
        }
    except Exception as exc:
        return {
            'markdown_parser_status': 'failed',
            'markdown_parser_detail': 'parser readiness check failed',
            'markdown_parser_error': f'{type(exc).__name__}: {exc}',
        }
    output = (completed.stdout or '') + '\n' + (completed.stderr or '')
    if completed.returncode != 0:
        return {
            'markdown_parser_status': 'failed',
            'markdown_parser_detail': f'parser readiness check exited with {completed.returncode}',
            'markdown_parser_error': _short_process_text(output),
        }
    status = _marker_value(output, 'ccb_markdown_parser_status')
    detail = _marker_value(output, 'ccb_markdown_parser_detail')
    if status:
        return {
            'markdown_parser_status': status,
            'markdown_parser_detail': detail or '',
        }
    return {
        'markdown_parser_status': 'unknown',
        'markdown_parser_detail': 'parser readiness check produced no marker output',
    }


def _check_opener_status() -> dict[str, object]:
    if platform.system() == 'Darwin':
        return _tool_status('opener', ('open',))
    if _is_wsl():
        result = _tool_status('opener', ('wslview', 'explorer.exe', 'xdg-open'))
        if result.get('opener_status') == 'missing':
            result['opener_reason'] = 'no WSL opener helper found'
        return result
    if platform.system() == 'Linux':
        return _tool_status('opener', ('xdg-open', 'gio', 'kde-open', 'gnome-open'))
    return {
        'opener_status': 'unknown',
        'opener_reason': f'unsupported opener platform: {platform.system() or "unknown"}',
    }


def _check_clipboard_status() -> dict[str, object]:
    if platform.system() == 'Darwin':
        if shutil.which('pbcopy') and shutil.which('pbpaste'):
            return {'clipboard_status': 'ok', 'clipboard_tool': 'pbcopy/pbpaste'}
        return {'clipboard_status': 'missing', 'clipboard_reason': 'pbcopy/pbpaste not found'}
    if _is_wsl():
        return _tool_status('clipboard', ('win32yank.exe', 'clip.exe', 'wl-copy', 'xclip', 'xsel'))
    if platform.system() == 'Linux':
        if shutil.which('wl-copy') and shutil.which('wl-paste'):
            return {'clipboard_status': 'ok', 'clipboard_tool': 'wl-clipboard'}
        return _tool_status('clipboard', ('xclip', 'xsel'))
    return {
        'clipboard_status': 'unknown',
        'clipboard_reason': f'unsupported clipboard platform: {platform.system() or "unknown"}',
    }


def _check_image_status() -> dict[str, object]:
    term = str(os.environ.get('TERM') or '')
    term_program = str(os.environ.get('TERM_PROGRAM') or '')
    term_program_lower = term_program.lower()
    in_tmux = bool(os.environ.get('TMUX')) or term.startswith('tmux')
    terminal_candidate = bool(os.environ.get('KITTY_WINDOW_ID')) or any(
        candidate in term_program_lower
        for candidate in ('kitty', 'wezterm', 'ghostty')
    )
    converter_name, converter_path = _which_first(('magick', 'convert'))
    result: dict[str, object] = {
        'image_status': 'candidate' if terminal_candidate and not in_tmux else 'degraded',
        'image_terminal': term_program or term or 'unknown',
        'imagemagick_status': 'ok' if converter_path else 'missing',
    }
    if converter_name:
        result['imagemagick_tool'] = converter_name
    if in_tmux:
        result['image_reason'] = 'tmux image passthrough must be verified before inline images are enabled'
    elif not terminal_candidate:
        result['image_reason'] = 'no Kitty/WezTerm/Ghostty-style terminal image protocol detected'
    return result


def _check_wsl_status() -> dict[str, object]:
    if not _is_wsl():
        return {'wsl_status': 'not_wsl'}
    cwd = str(Path.cwd())
    if cwd.startswith('/mnt/'):
        return {
            'wsl_status': 'mounted_drive',
            'wsl_reason': 'current project is under /mnt; Neovim plugin IO may be slower than WSL home storage',
        }
    return {'wsl_status': 'ok'}


def _tool_status(prefix: str, names: tuple[str, ...]) -> dict[str, object]:
    name, path = _which_first(names)
    if path:
        return {
            f'{prefix}_status': 'ok',
            f'{prefix}_tool': name,
        }
    return {
        f'{prefix}_status': 'missing',
    }


def _which_first(names: tuple[str, ...]) -> tuple[str | None, str | None]:
    for name in names:
        path = shutil.which(name)
        if path:
            return name, path
    return None, None


def _is_wsl() -> bool:
    if os.environ.get('WSL_DISTRO_NAME') or os.environ.get('WSL_INTEROP'):
        return True
    try:
        return 'microsoft' in Path('/proc/version').read_text(encoding='utf-8', errors='ignore').lower()
    except Exception:
        return False


def _marker_value(output: str, key: str) -> str | None:
    prefix = key + '='
    for line in output.splitlines():
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    return None


def _write_bin_link(paths: dict[str, Path]) -> None:
    link = paths['bin_link']
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(paths['wrapper'])
    except Exception:
        shutil.copy2(paths['wrapper'], link)
        link.chmod(0o755)


def _shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _read_manifest(paths: dict[str, Path]) -> dict[str, object]:
    try:
        return json.loads(paths['manifest'].read_text(encoding='utf-8'))
    except Exception:
        return {}


def _write_manifest(paths: dict[str, Path], payload: dict[str, object]) -> None:
    paths['manifest'].parent.mkdir(parents=True, exist_ok=True)
    paths['manifest'].write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def _status_paths(paths: dict[str, Path]) -> dict[str, object]:
    return {
        'root': str(paths['root']),
        'config_home': str(paths['profile'] / 'config'),
        'data_home': str(paths['data']),
        'state_home': str(paths['state']),
        'cache_home': str(paths['cache']),
    }


def _print_status(status: dict[str, object], stdout: TextIO) -> None:
    print(f"neovim_status: {status.get('status')}", file=stdout)
    for key in (
        'reason',
        'binary',
        'wrapper',
        'bin_link',
        'managed_neovim_target',
        'lazyvim_profile',
        'lazyvim_sync_status',
        'lazyvim_sync_error',
        'lazyvim_health_status',
        'lazyvim_health_error',
        'markdown_parser_status',
        'markdown_parser_detail',
        'markdown_parser_error',
        'opener_status',
        'opener_tool',
        'opener_reason',
        'clipboard_status',
        'clipboard_tool',
        'clipboard_reason',
        'wsl_status',
        'wsl_reason',
        'image_status',
        'image_terminal',
        'image_reason',
        'imagemagick_status',
        'imagemagick_tool',
        'root',
        'config_home',
        'data_home',
        'state_home',
        'cache_home',
    ):
        value = status.get(key)
        if value:
            print(f'{key}: {value}', file=stdout)


def _print_help(stdout: TextIO) -> None:
    print('Standalone Neovim tools have moved under the rich workbench bundle.', file=stdout)
    print('usage: ccb update rich', file=stdout)


def _lazyvim_profile_enabled() -> bool:
    return str(os.environ.get('CCB_LAZYVIM_PROFILE') or '').strip().lower() not in {'0', 'false', 'off'}


def _lazyvim_sync_timeout_s() -> float:
    raw = str(os.environ.get('CCB_LAZYVIM_SYNC_TIMEOUT_S') or '').strip()
    if not raw:
        return LAZYVIM_SYNC_TIMEOUT_S
    try:
        return max(0.0, float(raw))
    except ValueError:
        return LAZYVIM_SYNC_TIMEOUT_S


def _lazyvim_bootstrap_timeout_s() -> float:
    raw = str(os.environ.get('CCB_LAZYVIM_BOOTSTRAP_TIMEOUT_S') or '').strip()
    if not raw:
        return LAZYVIM_BOOTSTRAP_TIMEOUT_S
    try:
        return max(0.0, float(raw))
    except ValueError:
        return LAZYVIM_BOOTSTRAP_TIMEOUT_S


def _short_process_text(value: object, *, limit: int = 2000) -> str:
    text = str(value or '').strip()
    if len(text) <= limit:
        return text
    return text[:limit] + '...'


def _process_output_text(*values: object) -> str:
    parts = [_decode_process_output(value) for value in values]
    return _short_process_text('\n'.join(part for part in parts if part))


def _decode_process_output(value: object) -> str:
    if value is None:
        return ''
    if isinstance(value, bytes):
        return value.decode('utf-8', errors='replace')
    return str(value)


def _join_errors(*values: object) -> str:
    parts = [str(value).strip() for value in values if str(value or '').strip()]
    return '\n'.join(parts)


__all__ = ['cmd_tools', 'neovim_status', 'provision_neovim']
