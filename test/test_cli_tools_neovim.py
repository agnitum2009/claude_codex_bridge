from __future__ import annotations

from io import StringIO
from pathlib import Path
import hashlib
import io
import subprocess
import tarfile

from cli.entrypoint import run_cli_entrypoint
from cli.tools_runtime import neovim as neovim_tools


def test_neovim_provisioning_writes_isolated_wrapper(tmp_path: Path, monkeypatch) -> None:
    fake_bin = tmp_path / 'bin'
    fake_bin.mkdir()
    nvim = fake_bin / 'nvim'
    nvim.write_text('#!/usr/bin/env sh\nexit 0\n', encoding='utf-8')
    nvim.chmod(0o755)
    home = tmp_path / 'home'
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'xdg-data'))
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path / 'xdg-state'))
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'xdg-cache'))
    monkeypatch.setenv('CODEX_BIN_DIR', str(tmp_path / 'global-bin'))
    monkeypatch.setenv('PATH', f'{fake_bin}')
    sync_calls: list[dict[str, object]] = []

    def _sync(command, **kwargs):
        sync_calls.append({'command': command, **kwargs})
        if command[:2] == ['git', 'clone']:
            lazy_nvim = Path(command[-1])
            lazy_nvim.joinpath('lua', 'lazy').mkdir(parents=True, exist_ok=True)
            lazy_nvim.joinpath('lua', 'lazy', 'init.lua').write_text('return {}\n', encoding='utf-8')
            return subprocess.CompletedProcess(command, 0, stdout='cloned', stderr='')
        lazy_nvim = tmp_path / 'xdg-data' / 'ccb' / 'tools' / 'neovim' / 'lazyvim' / 'profile' / 'share' / 'nvim' / 'lazy' / 'lazy.nvim'
        lazy_nvim.joinpath('lua', 'lazy').mkdir(parents=True, exist_ok=True)
        lazy_nvim.joinpath('lua', 'lazy', 'init.lua').write_text('return {}\n', encoding='utf-8')
        lazyvim = tmp_path / 'xdg-data' / 'ccb' / 'tools' / 'neovim' / 'lazyvim' / 'profile' / 'share' / 'nvim' / 'lazy' / 'LazyVim'
        lazyvim.joinpath('lua', 'lazyvim').mkdir(parents=True, exist_ok=True)
        lazyvim.joinpath('lua', 'lazyvim', 'init.lua').write_text('return {}\n', encoding='utf-8')
        return subprocess.CompletedProcess(command, 0, stdout='synced', stderr='')

    monkeypatch.setattr(neovim_tools.subprocess, 'run', _sync)
    monkeypatch.setattr(neovim_tools, '_check_lazyvim_health', lambda _paths: {'status': 'ok'})

    result = neovim_tools.provision_neovim()

    assert result['status'] == 'ok'
    assert result['lazyvim_sync_status'] == 'ok'
    assert result['lazyvim_health_status'] == 'ok'
    assert result['lazyvim_repaired'] is False
    wrapper = Path(str(result['wrapper']))
    assert wrapper.is_file()
    text = wrapper.read_text(encoding='utf-8')
    assert text.startswith('#!/usr/bin/env sh\nset -eu\n')
    assert text.count('#!/usr/bin/env sh') == 1
    assert 'XDG_CONFIG_HOME=' in text
    assert str(home / '.config' / 'nvim') not in text
    assert 'NVIM_APPNAME=nvim' in text
    assert (tmp_path / 'global-bin' / 'ccb-nvim').exists()
    assert (tmp_path / 'xdg-data' / 'ccb' / 'tools' / 'neovim' / 'lazyvim' / 'profile' / '.ccb-managed-lazyvim').exists()
    init_lua = (
        tmp_path
        / 'xdg-data'
        / 'ccb'
        / 'tools'
        / 'neovim'
        / 'lazyvim'
        / 'profile'
        / 'config'
        / 'nvim'
        / 'init.lua'
    )
    init_text = init_lua.read_text(encoding='utf-8')
    assert 'local ccb_parser_runtimepaths = {}' in init_text
    assert 'ccb_record_parser_runtimepaths()' in init_text
    assert 'ccb_restore_parser_runtimepaths()' in init_text
    assert 'vim.g.ccb_markdown_parser_ready = ccb_has_recorded_parser("markdown") and ccb_has_recorded_parser("markdown_inline")' in init_text
    assert 'vim.opt.runtimepath:append(runtime)' in init_text
    terminal_compat = (
        tmp_path
        / 'xdg-data'
        / 'ccb'
        / 'tools'
        / 'neovim'
        / 'lazyvim'
        / 'profile'
        / 'config'
        / 'nvim'
        / 'lua'
        / 'plugins'
        / 'ccb-terminal-compat.lua'
    )
    assert terminal_compat.exists()
    terminal_text = terminal_compat.read_text(encoding='utf-8')
    assert 'local icon_style = vim.env.CCB_LAZYVIM_ICON_STYLE or "ascii"' in terminal_text
    assert 'local function ccb_terminal_image_candidate()' in terminal_text
    assert 'vim.env.CCB_LAZYVIM_IMAGE_INLINE == "1"' in terminal_text
    assert 'local function ccb_install_string_buffer_fallback()' in terminal_text
    assert 'package.preload["string.buffer"] = function()' in terminal_text
    assert 'new = function() return setmetatable({ _chunks = {} }, Buffer) end' in terminal_text
    assert '"folke/snacks.nvim"' in terminal_text
    assert 'opts.explorer.replace_netrw = true' in terminal_text
    assert 'opts.picker.sources.explorer = vim.tbl_deep_extend("force", opts.picker.sources.explorer or {}, {' in terminal_text
    assert 'watch = false' in terminal_text
    assert 'opts.image = vim.tbl_deep_extend("force", opts.image or {}, {' in terminal_text
    assert 'opts.image.formats = {}' in terminal_text
    assert 'enabled = false' in terminal_text
    assert 'inline = false' in terminal_text
    assert 'float = false' in terminal_text
    assert 'item.icon = ""' in terminal_text
    assert 'opts.style = icon_style' in terminal_text
    assert 'diagnostics = { Error = "E ", Warn = "W ", Hint = "H ", Info = "I " }' in terminal_text
    treesitter = terminal_compat.with_name('ccb-treesitter.lua')
    assert treesitter.exists()
    treesitter_text = treesitter.read_text(encoding='utf-8')
    assert 'local allow_parser_install = vim.env.CCB_LAZYVIM_TS_INSTALL == "1"' in treesitter_text
    assert 'opts.ensure_installed = {}' in treesitter_text
    assert 'opts.auto_install = false' in treesitter_text
    markdown = terminal_compat.with_name('ccb-markdown.lua')
    assert markdown.exists()
    markdown_text = markdown.read_text(encoding='utf-8')
    assert '"MeanderingProgrammer/render-markdown.nvim"' in markdown_text
    assert 'enabled = ccb_markdown_parser_ready' in markdown_text
    assert 'vim.g.ccb_markdown_parser_ready == true' in markdown_text
    assert 'parser/" .. lang .. ".so"' in markdown_text
    open_helpers = terminal_compat.with_name('ccb-open.lua')
    assert open_helpers.exists()
    open_text = open_helpers.read_text(encoding='utf-8')
    assert 'vim.api.nvim_create_user_command("CCBOpenCurrent", ccb_open_current_file, {})' in open_text
    assert 'vim.api.nvim_create_user_command("CCBOpenUnderCursor", ccb_open_under_cursor, {})' in open_text
    assert 'vim.api.nvim_create_user_command("CCBOpenImage", ccb_open_current_image, {})' in open_text
    assert 'vim.api.nvim_create_user_command("CCBRevealCurrent", ccb_reveal_current_file, {})' in open_text
    assert 'vim.api.nvim_create_augroup("ccb_image_external_open", { clear = true })' in open_text
    assert 'local function ccb_inline_image_supported()' in open_text
    assert 'Inline image rendering is not available in this terminal session.' in open_text
    assert 'vim.keymap.set("n", "<leader>co", ccb_open_current_file' in open_text
    assert 'vim.keymap.set("n", "<leader>cO", ccb_open_under_cursor' in open_text
    assert 'vim.keymap.set("n", "<leader>ci", ccb_open_current_image' in open_text
    assert 'vim.keymap.set("n", "<leader>cr", ccb_reveal_current_file' in open_text
    assert 'snacks.picker.explorer({ cwd = dir })' in open_text
    assert 'wslview", "explorer.exe", "xdg-open"' in open_text
    assert not (home / '.config' / 'nvim').exists()
    assert sync_calls
    assert any(call['command'][:2] == ['git', 'clone'] for call in sync_calls)
    sync_call = next(call for call in sync_calls if call['command'][:1] == [str(wrapper)])
    assert sync_call['command'] == [str(wrapper), '--headless', '+Lazy! sync', '+qa']
    assert sync_call['cwd'] == str(tmp_path / 'xdg-data' / 'ccb' / 'tools' / 'neovim')


def test_neovim_provisioning_soft_degrades_when_lazyvim_sync_fails(tmp_path: Path, monkeypatch) -> None:
    fake_bin = tmp_path / 'bin'
    fake_bin.mkdir()
    nvim = fake_bin / 'nvim'
    nvim.write_text('#!/usr/bin/env sh\nexit 0\n', encoding='utf-8')
    nvim.chmod(0o755)
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'xdg-data'))
    monkeypatch.setenv('PATH', f'{fake_bin}')

    def _run(command, **kwargs):
        if command[:2] == ['git', 'clone']:
            lazy_nvim = Path(command[-1])
            lazy_nvim.joinpath('lua', 'lazy').mkdir(parents=True, exist_ok=True)
            lazy_nvim.joinpath('lua', 'lazy', 'init.lua').write_text('return {}\n', encoding='utf-8')
            return subprocess.CompletedProcess(command, 0, stdout='cloned', stderr='')
        return subprocess.CompletedProcess(command, 2, stdout='bad', stderr='network down')

    monkeypatch.setattr(neovim_tools.subprocess, 'run', _run)

    result = neovim_tools.provision_neovim()

    assert result['status'] == 'degraded'
    assert result['lazyvim_sync_status'] == 'failed'
    assert 'LazyVim sync exited with 2' in str(result['reason'])
    assert 'network down' in str(result['lazyvim_sync_error'])


def test_neovim_provisioning_can_skip_lazyvim_profile(tmp_path: Path, monkeypatch) -> None:
    fake_bin = tmp_path / 'bin'
    fake_bin.mkdir()
    nvim = fake_bin / 'nvim'
    nvim.write_text('#!/usr/bin/env sh\nexit 0\n', encoding='utf-8')
    nvim.chmod(0o755)
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'xdg-data'))
    monkeypatch.setenv('PATH', f'{fake_bin}')
    monkeypatch.setenv('CCB_LAZYVIM_PROFILE', '0')
    monkeypatch.setattr(
        neovim_tools.subprocess,
        'run',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError('LazyVim sync should be skipped')),
    )

    result = neovim_tools.provision_neovim()

    assert result['status'] == 'ok'
    assert result['managed_profile'] is False
    assert result['lazyvim_sync_status'] == 'skipped'
    assert not (tmp_path / 'xdg-data' / 'ccb' / 'tools' / 'neovim' / 'lazyvim' / 'profile' / '.ccb-managed-lazyvim').exists()


def test_neovim_provisioning_repairs_broken_lazy_nvim_checkout(tmp_path: Path, monkeypatch) -> None:
    fake_bin = tmp_path / 'bin'
    fake_bin.mkdir()
    nvim = fake_bin / 'nvim'
    nvim.write_text('#!/usr/bin/env sh\nexit 0\n', encoding='utf-8')
    nvim.chmod(0o755)
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'xdg-data'))
    monkeypatch.setenv('PATH', f'{fake_bin}')
    lazy_root = tmp_path / 'xdg-data' / 'ccb' / 'tools' / 'neovim' / 'lazyvim' / 'profile' / 'share' / 'nvim' / 'lazy'
    broken_lazy = lazy_root / 'lazy.nvim'
    broken_lazy.mkdir(parents=True)
    (broken_lazy / '.git').mkdir()
    (broken_lazy / '.git' / 'HEAD').write_text('ref: refs/heads/stable\n', encoding='utf-8')
    calls: list[list[str]] = []

    def _run(command, **kwargs):
        calls.append(list(command))
        if command[:2] == ['git', 'clone']:
            target = Path(command[-1])
            target.joinpath('lua', 'lazy').mkdir(parents=True, exist_ok=True)
            target.joinpath('lua', 'lazy', 'init.lua').write_text('return {}\n', encoding='utf-8')
            return subprocess.CompletedProcess(command, 0, stdout='cloned', stderr='')
        lazyvim = lazy_root / 'LazyVim'
        lazyvim.joinpath('lua', 'lazyvim').mkdir(parents=True, exist_ok=True)
        lazyvim.joinpath('lua', 'lazyvim', 'init.lua').write_text('return {}\n', encoding='utf-8')
        return subprocess.CompletedProcess(command, 0, stdout='synced', stderr='')

    monkeypatch.setattr(neovim_tools.subprocess, 'run', _run)
    monkeypatch.setattr(neovim_tools, '_check_lazyvim_health', lambda _paths: {'status': 'ok'})

    result = neovim_tools.provision_neovim()

    assert result['status'] == 'ok'
    assert result['lazyvim_repaired'] is True
    assert (broken_lazy / 'lua' / 'lazy' / 'init.lua').is_file()
    assert any(call[:2] == ['git', 'clone'] for call in calls)


def test_neovim_provisioning_falls_back_to_lazy_nvim_tarball_when_git_clone_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fake_bin = tmp_path / 'bin'
    fake_bin.mkdir()
    nvim = fake_bin / 'nvim'
    nvim.write_text('#!/usr/bin/env sh\nexit 0\n', encoding='utf-8')
    nvim.chmod(0o755)
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'xdg-data'))
    monkeypatch.setenv('PATH', f'{fake_bin}')
    lazy_root = tmp_path / 'xdg-data' / 'ccb' / 'tools' / 'neovim' / 'lazyvim' / 'profile' / 'share' / 'nvim' / 'lazy'

    def _run(command, **kwargs):
        if command[:2] == ['git', 'clone']:
            target = Path(command[-1])
            target.mkdir(parents=True, exist_ok=True)
            (target / '.git').mkdir()
            return subprocess.CompletedProcess(command, 128, stdout='', stderr='RPC failed')
        lazyvim = lazy_root / 'LazyVim'
        lazyvim.joinpath('lua', 'lazyvim').mkdir(parents=True, exist_ok=True)
        lazyvim.joinpath('lua', 'lazyvim', 'init.lua').write_text('return {}\n', encoding='utf-8')
        return subprocess.CompletedProcess(command, 0, stdout='synced', stderr='')

    monkeypatch.setattr(neovim_tools.subprocess, 'run', _run)
    monkeypatch.setattr(
        neovim_tools,
        '_download_file',
        lambda _url, destination, **_kwargs: Path(destination).write_bytes(_lazy_nvim_archive()),
    )
    monkeypatch.setattr(neovim_tools, '_check_lazyvim_health', lambda _paths: {'status': 'ok'})

    result = neovim_tools.provision_neovim()

    assert result['status'] == 'ok'
    assert result['lazyvim_repaired'] is True
    assert (lazy_root / 'lazy.nvim' / 'lua' / 'lazy' / 'init.lua').is_file()


def test_neovim_lazy_nvim_tarball_tries_next_candidate(tmp_path: Path, monkeypatch) -> None:
    fake_bin = tmp_path / 'bin'
    fake_bin.mkdir()
    nvim = fake_bin / 'nvim'
    nvim.write_text('#!/usr/bin/env sh\nexit 0\n', encoding='utf-8')
    nvim.chmod(0o755)
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'xdg-data'))
    monkeypatch.setenv('PATH', f'{fake_bin}')
    lazy_root = tmp_path / 'xdg-data' / 'ccb' / 'tools' / 'neovim' / 'lazyvim' / 'profile' / 'share' / 'nvim' / 'lazy'
    urls: list[str] = []

    def _run(command, **kwargs):
        if command[:2] == ['git', 'clone']:
            return subprocess.CompletedProcess(command, 128, stdout='', stderr='RPC failed')
        lazyvim = lazy_root / 'LazyVim'
        lazyvim.joinpath('lua', 'lazyvim').mkdir(parents=True, exist_ok=True)
        lazyvim.joinpath('lua', 'lazyvim', 'init.lua').write_text('return {}\n', encoding='utf-8')
        return subprocess.CompletedProcess(command, 0, stdout='synced', stderr='')

    def _download(url, destination, **_kwargs):
        urls.append(url)
        if len(urls) == 1:
            raise RuntimeError('first mirror failed')
        Path(destination).write_bytes(_lazy_nvim_archive())

    monkeypatch.setattr(neovim_tools.subprocess, 'run', _run)
    monkeypatch.setattr(neovim_tools, '_download_file', _download)
    monkeypatch.setattr(neovim_tools, '_check_lazyvim_health', lambda _paths: {'status': 'ok'})

    result = neovim_tools.provision_neovim()

    assert result['status'] == 'ok'
    assert len(urls) == 2


def test_neovim_cmd_tools_rejects_standalone_public_surface(monkeypatch) -> None:
    monkeypatch.setattr(
        neovim_tools,
        'provision_neovim',
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("standalone cmd_tools must not provision Neovim")),
    )
    stdout = StringIO()
    stderr = StringIO()

    code = neovim_tools.cmd_tools(['install', 'neovim'], stdout=stdout, stderr=stderr)

    assert code == 2
    assert stdout.getvalue() == ''
    assert 'standalone Neovim tools are no longer supported' in stderr.getvalue()
    assert 'ccb update rich' in stderr.getvalue()


def test_neovim_provisioning_cleans_partial_lazy_nvim_when_bootstrap_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fake_bin = tmp_path / 'bin'
    fake_bin.mkdir()
    nvim = fake_bin / 'nvim'
    nvim.write_text('#!/usr/bin/env sh\nexit 0\n', encoding='utf-8')
    nvim.chmod(0o755)
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'xdg-data'))
    monkeypatch.setenv('PATH', f'{fake_bin}')
    lazy_path = tmp_path / 'xdg-data' / 'ccb' / 'tools' / 'neovim' / 'lazyvim' / 'profile' / 'share' / 'nvim' / 'lazy' / 'lazy.nvim'

    def _run(command, **kwargs):
        if command[:2] == ['git', 'clone']:
            lazy_path.mkdir(parents=True, exist_ok=True)
            (lazy_path / '.git').mkdir()
            return subprocess.CompletedProcess(command, 128, stdout='', stderr='RPC failed')
        return subprocess.CompletedProcess(command, 0, stdout='synced', stderr='')

    monkeypatch.setattr(neovim_tools.subprocess, 'run', _run)
    monkeypatch.setattr(
        neovim_tools,
        '_download_file',
        lambda _url, destination, **_kwargs: (_ for _ in ()).throw(RuntimeError('tarball unavailable')),
    )

    result = neovim_tools.provision_neovim()

    assert result['status'] == 'degraded'
    assert not lazy_path.exists()
    assert 'tarball unavailable' in str(result['lazyvim_sync_error'])


def test_neovim_bootstrap_timeout_bytes_output_is_reported(tmp_path: Path, monkeypatch) -> None:
    fake_bin = tmp_path / 'bin'
    fake_bin.mkdir()
    nvim = fake_bin / 'nvim'
    nvim.write_text('#!/usr/bin/env sh\nexit 0\n', encoding='utf-8')
    nvim.chmod(0o755)
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'xdg-data'))
    monkeypatch.setenv('PATH', f'{fake_bin}')

    def _run(command, **kwargs):
        if command[:2] == ['git', 'clone']:
            raise subprocess.TimeoutExpired(command, timeout=1.0, output=b'partial', stderr=b'timed out')
        return subprocess.CompletedProcess(command, 0, stdout='synced', stderr='')

    monkeypatch.setattr(neovim_tools.subprocess, 'run', _run)
    monkeypatch.setattr(
        neovim_tools,
        '_download_file',
        lambda _url, destination, **_kwargs: (_ for _ in ()).throw(RuntimeError('tarball unavailable')),
    )

    result = neovim_tools.provision_neovim()

    assert result['status'] == 'degraded'
    assert 'partial' in str(result['lazyvim_sync_error'])
    assert 'timed out' in str(result['lazyvim_sync_error'])


def test_neovim_doctor_reports_degraded_when_lazyvim_health_fails(tmp_path: Path, monkeypatch) -> None:
    fake_bin = tmp_path / 'bin'
    fake_bin.mkdir()
    nvim = fake_bin / 'nvim'
    nvim.write_text('#!/usr/bin/env sh\nexit 0\n', encoding='utf-8')
    nvim.chmod(0o755)
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'xdg-data'))
    monkeypatch.setenv('PATH', f'{fake_bin}')
    paths = neovim_tools._paths()
    paths['wrapper'].parent.mkdir(parents=True, exist_ok=True)
    paths['wrapper'].write_text('#!/usr/bin/env sh\nexit 0\n', encoding='utf-8')
    paths['wrapper'].chmod(0o755)
    paths['marker'].parent.mkdir(parents=True, exist_ok=True)
    paths['marker'].write_text('managed_by=ccb\n', encoding='utf-8')
    neovim_tools._write_manifest(paths, {'status': 'ok', 'lazyvim_profile_enabled': True})
    monkeypatch.setattr(
        neovim_tools,
        '_check_lazyvim_health',
        lambda _paths: {'status': 'failed', 'reason': 'LazyVim plugin files missing', 'error': 'missing init.lua'},
    )

    status = neovim_tools.neovim_status()

    assert status['status'] == 'degraded'
    assert status['reason'] == 'LazyVim plugin files missing'
    assert status['lazyvim_health_status'] == 'failed'
    assert status['lazyvim_health_error'] == 'missing init.lua'


def test_neovim_doctor_uses_live_health_after_previous_degraded_manifest(tmp_path: Path, monkeypatch) -> None:
    fake_bin = tmp_path / 'bin'
    fake_bin.mkdir()
    nvim = fake_bin / 'nvim'
    nvim.write_text('#!/usr/bin/env sh\nexit 0\n', encoding='utf-8')
    nvim.chmod(0o755)
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'xdg-data'))
    monkeypatch.setenv('PATH', f'{fake_bin}')
    paths = neovim_tools._paths()
    paths['wrapper'].parent.mkdir(parents=True, exist_ok=True)
    paths['wrapper'].write_text('#!/usr/bin/env sh\nexit 0\n', encoding='utf-8')
    paths['wrapper'].chmod(0o755)
    paths['marker'].parent.mkdir(parents=True, exist_ok=True)
    paths['marker'].write_text('managed_by=ccb\n', encoding='utf-8')
    neovim_tools._write_manifest(
        paths,
        {
            'status': 'degraded',
            'reason': 'old sync failure',
            'lazyvim_profile_enabled': True,
            'lazyvim_health_error': 'old missing file',
        },
    )
    monkeypatch.setattr(neovim_tools, '_check_lazyvim_health', lambda _paths: {'status': 'ok'})

    status = neovim_tools.neovim_status()

    assert status['status'] == 'ok'
    assert status['reason'] is None
    assert status['lazyvim_health_status'] == 'ok'
    assert status['lazyvim_health_error'] is None


def test_neovim_doctor_reports_read_only_markdown_parser_capability(tmp_path: Path, monkeypatch) -> None:
    fake_bin = tmp_path / 'bin'
    fake_bin.mkdir()
    nvim = fake_bin / 'nvim'
    nvim.write_text('#!/usr/bin/env sh\nexit 0\n', encoding='utf-8')
    nvim.chmod(0o755)
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'xdg-data'))
    monkeypatch.setenv('PATH', f'{fake_bin}')
    paths = neovim_tools._paths()
    paths['wrapper'].parent.mkdir(parents=True, exist_ok=True)
    paths['wrapper'].write_text('#!/usr/bin/env sh\nexit 0\n', encoding='utf-8')
    paths['wrapper'].chmod(0o755)
    calls: list[list[str]] = []

    def _run(command, **kwargs):
        calls.append(list(command))
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=(
                'ccb_markdown_parser_status=ok\n'
                'ccb_markdown_parser_detail=markdown:ok:1,markdown_inline:ok:1\n'
            ),
            stderr='',
        )

    monkeypatch.setattr(neovim_tools.subprocess, 'run', _run)

    result = neovim_tools._check_markdown_parser_status(paths)

    assert result == {
        'markdown_parser_status': 'ok',
        'markdown_parser_detail': 'markdown:ok:1,markdown_inline:ok:1',
    }
    assert calls == [[str(paths['wrapper']), '--clean', '--headless', calls[0][3], '+qa']]
    assert calls[0][3].startswith('+lua ')
    assert 'nvim_get_runtime_file' in calls[0][3]
    assert 'TSInstall' not in calls[0][3]


def test_neovim_doctor_keeps_optional_parser_degradation_out_of_top_level_status(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fake_bin = tmp_path / 'bin'
    fake_bin.mkdir()
    nvim = fake_bin / 'nvim'
    nvim.write_text('#!/usr/bin/env sh\nexit 0\n', encoding='utf-8')
    nvim.chmod(0o755)
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'xdg-data'))
    monkeypatch.setenv('PATH', f'{fake_bin}')
    paths = neovim_tools._paths()
    paths['wrapper'].parent.mkdir(parents=True, exist_ok=True)
    paths['wrapper'].write_text('#!/usr/bin/env sh\nexit 0\n', encoding='utf-8')
    paths['wrapper'].chmod(0o755)
    paths['marker'].parent.mkdir(parents=True, exist_ok=True)
    paths['marker'].write_text('managed_by=ccb\n', encoding='utf-8')
    neovim_tools._write_manifest(paths, {'status': 'ok', 'lazyvim_profile_enabled': True})
    monkeypatch.setattr(neovim_tools, '_check_lazyvim_health', lambda _paths: {'status': 'ok'})
    monkeypatch.setattr(
        neovim_tools,
        '_check_neovim_capabilities',
        lambda _paths: {
            'markdown_parser_status': 'degraded',
            'markdown_parser_detail': 'markdown:missing:0,markdown_inline:missing:0',
        },
    )

    status = neovim_tools.neovim_status()

    assert status['status'] == 'ok'
    assert status['markdown_parser_status'] == 'degraded'
    assert status['markdown_parser_detail'] == 'markdown:missing:0,markdown_inline:missing:0'


def test_neovim_doctor_reports_wsl_mount_status(monkeypatch) -> None:
    monkeypatch.setattr(neovim_tools, '_is_wsl', lambda: True)
    monkeypatch.setattr(neovim_tools.Path, 'cwd', classmethod(lambda cls: Path('/mnt/c/work/repo')))

    status = neovim_tools._check_wsl_status()

    assert status['wsl_status'] == 'mounted_drive'
    assert '/mnt' in status['wsl_reason']


def test_neovim_doctor_reports_non_wsl_status(monkeypatch) -> None:
    monkeypatch.setattr(neovim_tools, '_is_wsl', lambda: False)

    assert neovim_tools._check_wsl_status() == {'wsl_status': 'not_wsl'}


def test_neovim_provisioning_soft_missing_without_nvim(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'xdg-data'))
    monkeypatch.setenv('PATH', str(tmp_path / 'empty'))
    monkeypatch.setattr(neovim_tools.platform, 'system', lambda: 'Plan9')
    monkeypatch.setattr(neovim_tools.platform, 'machine', lambda: 'weird')

    result = neovim_tools.provision_neovim()

    assert result['status'] == 'missing'
    assert 'no managed Neovim asset' in str(result['reason'])


def test_neovim_provisioning_downloads_managed_binary_when_system_nvim_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    archive = _nvim_archive()
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'xdg-data'))
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path / 'xdg-state'))
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'xdg-cache'))
    monkeypatch.setenv('CODEX_BIN_DIR', str(tmp_path / 'global-bin'))
    monkeypatch.setenv('PATH', str(tmp_path / 'empty'))
    monkeypatch.setattr(neovim_tools.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(neovim_tools.platform, 'machine', lambda: 'x86_64')
    monkeypatch.setattr(
        neovim_tools,
        '_fetch_release_metadata',
        lambda: {
            'tag_name': 'v0.11.4',
            'assets': [
                {
                    'name': 'nvim-linux-x86_64.tar.gz',
                    'browser_download_url': 'https://example.test/nvim.tar.gz',
                    'digest': 'sha256:' + hashlib.sha256(archive).hexdigest(),
                }
            ],
        },
    )
    monkeypatch.setattr(
        neovim_tools,
        '_download_file',
        lambda _url, destination, **_kwargs: Path(destination).write_bytes(archive),
    )
    def _run(command, **kwargs):
        if command[:2] == ['git', 'clone']:
            lazy_nvim = Path(command[-1])
            lazy_nvim.joinpath('lua', 'lazy').mkdir(parents=True, exist_ok=True)
            lazy_nvim.joinpath('lua', 'lazy', 'init.lua').write_text('return {}\n', encoding='utf-8')
            return subprocess.CompletedProcess(command, 0, stdout='cloned', stderr='')
        lazy_root = tmp_path / 'xdg-data' / 'ccb' / 'tools' / 'neovim' / 'lazyvim' / 'profile' / 'share' / 'nvim' / 'lazy'
        lazyvim = lazy_root / 'LazyVim'
        lazyvim.joinpath('lua', 'lazyvim').mkdir(parents=True, exist_ok=True)
        lazyvim.joinpath('lua', 'lazyvim', 'init.lua').write_text('return {}\n', encoding='utf-8')
        return subprocess.CompletedProcess(command, 0, stdout='synced', stderr='')

    monkeypatch.setattr(neovim_tools.subprocess, 'run', _run)
    monkeypatch.setattr(neovim_tools, '_check_lazyvim_health', lambda _paths: {'status': 'ok'})

    result = neovim_tools.provision_neovim(required=True)

    assert result['status'] == 'ok'
    assert result['uses_system_nvim'] is False
    assert result['managed_neovim_version'] == 'v0.11.4'
    managed_nvim = tmp_path / 'xdg-data' / 'ccb' / 'tools' / 'neovim' / 'bin' / 'nvim'
    assert Path(str(result['binary'])) == managed_nvim
    assert managed_nvim.is_symlink()
    managed_target = managed_nvim.resolve()
    assert managed_target == (
        tmp_path
        / 'xdg-data'
        / 'ccb'
        / 'tools'
        / 'neovim'
        / 'versions'
        / 'v0.11.4-nvim-linux-x86_64.tar.gz'
        / 'nvim-linux-x86_64'
        / 'bin'
        / 'nvim'
    )
    assert result['managed_neovim_target'] == str(managed_target)
    assert managed_target.read_text(encoding='utf-8').startswith('#!/usr/bin/env sh')
    wrapper = Path(str(result['wrapper']))
    assert f"exec {neovim_tools._shell_quote(str(managed_nvim))}" in wrapper.read_text(encoding='utf-8')


def test_neovim_managed_activation_falls_back_to_wrapper_when_symlink_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    binary = tmp_path / 'versions' / 'nvim-linux-x86_64' / 'bin' / 'nvim'
    binary.parent.mkdir(parents=True)
    binary.write_text('#!/usr/bin/env sh\nexit 0\n', encoding='utf-8')
    binary.chmod(0o755)
    managed_nvim = tmp_path / 'root' / 'bin' / 'nvim'

    def _fail_symlink(self, target, target_is_directory=False):
        del self, target, target_is_directory
        raise OSError('symlink disabled')

    monkeypatch.setattr(Path, 'symlink_to', _fail_symlink)

    neovim_tools._activate_managed_nvim({'managed_nvim': managed_nvim}, binary)

    assert not managed_nvim.is_symlink()
    text = managed_nvim.read_text(encoding='utf-8')
    assert text.startswith('#!/usr/bin/env sh\n')
    assert f"exec {neovim_tools._shell_quote(str(binary))}" in text


def test_neovim_provisioning_keeps_missing_on_checksum_mismatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    archive = _nvim_archive()
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'xdg-data'))
    monkeypatch.setenv('PATH', str(tmp_path / 'empty'))
    monkeypatch.setattr(neovim_tools.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(neovim_tools.platform, 'machine', lambda: 'x86_64')
    monkeypatch.setattr(
        neovim_tools,
        '_fetch_release_metadata',
        lambda: {
            'tag_name': 'v0.11.4',
            'assets': [
                {
                    'name': 'nvim-linux-x86_64.tar.gz',
                    'browser_download_url': 'https://example.test/nvim.tar.gz',
                    'digest': 'sha256:' + ('0' * 64),
                }
            ],
        },
    )
    monkeypatch.setattr(
        neovim_tools,
        '_download_file',
        lambda _url, destination, **_kwargs: Path(destination).write_bytes(archive),
    )

    result = neovim_tools.provision_neovim()

    assert result['status'] == 'missing'
    assert 'download failed' in str(result['reason'])
    assert not (tmp_path / 'xdg-data' / 'ccb' / 'tools' / 'neovim' / 'bin' / 'nvim').exists()


def test_entrypoint_rejects_public_neovim_tool_route(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'xdg-data'))
    monkeypatch.setenv('PATH', str(tmp_path / 'empty'))
    stdout = StringIO()
    stderr = StringIO()

    code = run_cli_entrypoint(
        ['tools', 'doctor', 'neovim'],
        version='7.1.0',
        script_root=tmp_path,
        cwd=tmp_path,
        stdout=stdout,
        stderr=stderr,
    )

    assert code == 2
    assert stdout.getvalue() == ''
    assert 'standalone Neovim tools are no longer supported' in stderr.getvalue()
    assert 'ccb update rich' in stderr.getvalue()


def _nvim_archive() -> bytes:
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode='w:gz') as archive:
        data = b'#!/usr/bin/env sh\nexit 0\n'
        info = tarfile.TarInfo('nvim-linux-x86_64/bin/nvim')
        info.mode = 0o755
        info.size = len(data)
        archive.addfile(info, io.BytesIO(data))
    return payload.getvalue()


def _lazy_nvim_archive() -> bytes:
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode='w:gz') as archive:
        data = b'return {}\n'
        info = tarfile.TarInfo('lazy.nvim-stable/lua/lazy/init.lua')
        info.size = len(data)
        archive.addfile(info, io.BytesIO(data))
    return payload.getvalue()
