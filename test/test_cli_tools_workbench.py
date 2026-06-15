from __future__ import annotations

from io import StringIO
import json
from pathlib import Path

from cli.tools_runtime import cmd_tools
from cli.tools_runtime import workbench as workbench_tools


def _fake_executable(path: Path, text: str = '#!/usr/bin/env sh\nexit 0\n') -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    path.chmod(0o755)
    return path


def _prepare_env(tmp_path: Path, monkeypatch) -> Path:
    fake_bin = tmp_path / 'fake-bin'
    for name in (
        'yazi',
        'ya',
        'wezterm',
        'python3',
        'chafa',
        'pdfinfo',
        'pdftotext',
        'pdftoppm',
        'ffprobe',
        'ffmpeg',
    ):
        _fake_executable(fake_bin / name)
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'xdg-data'))
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path / 'xdg-state'))
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'xdg-cache'))
    monkeypatch.setenv('CODEX_BIN_DIR', str(tmp_path / 'global-bin'))
    monkeypatch.setenv('PATH', str(fake_bin))
    monkeypatch.setenv('TERM', 'xterm-256color')
    monkeypatch.setenv('TERM_PROGRAM', 'WezTerm')
    monkeypatch.delenv('TMUX', raising=False)
    return fake_bin


def _stub_neovim(monkeypatch, tmp_path: Path) -> None:
    nvim_root = tmp_path / 'xdg-data' / 'ccb' / 'tools' / 'neovim'
    nvim_wrapper = _fake_executable(nvim_root / 'bin' / 'ccb-nvim')
    result = {
        'status': 'ok',
        'wrapper': str(nvim_wrapper),
        'lazyvim_profile': str(nvim_root / 'lazyvim' / 'profile'),
    }
    monkeypatch.setattr(workbench_tools.neovim_tools, 'provision_neovim', lambda required=False: result)
    monkeypatch.setattr(workbench_tools.neovim_tools, 'neovim_status', lambda: result)


def test_workbench_install_writes_independent_bundle_profiles(tmp_path: Path, monkeypatch) -> None:
    _prepare_env(tmp_path, monkeypatch)
    _stub_neovim(monkeypatch, tmp_path)

    result = workbench_tools.provision_workbench(profile='rich')

    root = tmp_path / 'xdg-data' / 'ccb' / 'tools' / 'workbench'
    assert result['status'] == 'ok'
    assert result['profile'] == 'rich'
    assert result['enabled'] is False
    assert root.exists()
    assert (root / 'manifest.json').is_file()
    assert (root / 'bin' / 'ccb-workbench').is_file()
    assert (root / 'bin' / 'ccb-yazi').is_file()
    assert (root / 'bin' / 'ccb-yazi-rich').is_file()
    assert (root / 'bin' / 'ccb-md-preview').is_file()
    assert (root / 'bin' / 'ccb-image-preview').is_file()
    assert (root / 'bin' / 'ccb-pdf-preview').is_file()
    assert (root / 'bin' / 'ccb-video-preview').is_file()
    assert (root / 'profiles' / 'yazi-safe' / 'yazi.toml').is_file()
    assert (root / 'profiles' / 'yazi-rich' / 'yazi.toml').is_file()
    assert (root / 'profiles' / 'yazi-safe' / 'plugins' / 'piper.yazi' / 'main.lua').is_file()
    assert (root / 'profiles' / 'yazi-rich' / 'plugins' / 'piper.yazi' / 'main.lua').is_file()
    assert (root / 'profiles' / 'wezterm' / 'wezterm.lua').is_file()
    assert (tmp_path / 'global-bin' / 'ccb-workbench').exists()
    assert (tmp_path / 'global-bin' / 'ccb-yazi').exists()
    assert (tmp_path / 'global-bin' / 'ccb-yazi-rich').exists()
    assert (tmp_path / 'global-bin' / 'ccb-image-preview').exists()
    assert not (tmp_path / 'home' / '.config' / 'yazi').exists()
    assert not (tmp_path / 'home' / '.config' / 'wezterm').exists()

    safe_config = (root / 'profiles' / 'yazi-safe' / 'yazi.toml').read_text(encoding='utf-8')
    rich_config = (root / 'profiles' / 'yazi-rich' / 'yazi.toml').read_text(encoding='utf-8')
    assert 'piper -- "' in safe_config
    assert '*.png' in safe_config
    assert 'ccb-image-preview' in safe_config
    assert 'previewers = [' in safe_config
    assert 'preloaders = []' in safe_config
    assert 'prepend_preloaders' not in safe_config
    assert '*.pdf' in safe_config
    assert '*.mp4' in safe_config
    assert '*.png' not in rich_config
    assert 'ccb-image-preview' not in rich_config
    assert 'run = "image"' in rich_config
    assert 'mime = "application/pdf"' in rich_config
    assert 'run = "pdf"' in rich_config
    assert 'mime = "video/*"' in rich_config
    assert 'run = "video"' in rich_config
    assert '*.mp4' not in rich_config
    wezterm_config = (root / 'profiles' / 'wezterm' / 'wezterm.lua').read_text(encoding='utf-8')
    assert 'config.warn_about_missing_glyphs = false' in wezterm_config
    assert 'config.font = wezterm.font_with_fallback' in wezterm_config
    assert 'JetBrains Mono' in wezterm_config
    assert 'Fira Code' in wezterm_config
    assert 'Noto Sans Mono CJK SC' in wezterm_config
    assert 'Noto Sans Symbols2' in wezterm_config
    assert 'Symbols Nerd Font Mono' in wezterm_config
    assert 'Symbols Nerd Font' in wezterm_config
    assert 'Unifont CSUR' in wezterm_config
    assert 'Segoe UI Emoji' in wezterm_config
    assert 'weight = "Regular"' not in wezterm_config
    assert 'config.harfbuzz_features = { "calt=0", "clig=0", "liga=0" }' in wezterm_config
    assert 'config.font_size = 10.5' in wezterm_config
    assert 'config.line_height = 1.05' in wezterm_config
    assert 'config.initial_cols = 132' in wezterm_config
    assert 'config.initial_rows = 38' in wezterm_config
    assert 'config.window_padding = {' in wezterm_config
    assert 'config.hide_tab_bar_if_only_one_tab = true' in wezterm_config
    assert 'CCB_WORKBENCH_TERMINAL_PROGRAM = "WezTerm"' in wezterm_config
    assert 'CCB_WORKBENCH_TERMINAL_PROGRAM_VERSION = wezterm.version' in wezterm_config
    assert 'default_cwd' not in wezterm_config
    assert 'return config' in wezterm_config
    wrapper = (root / 'bin' / 'ccb-yazi-rich').read_text(encoding='utf-8')
    assert 'YAZI_CONFIG_HOME=' in wrapper
    assert 'CCB_WORKBENCH_FORCE_RICH' in wrapper
    assert 'CCB_WORKBENCH_TERMINAL_PROGRAM' in wrapper
    assert 'CCB_WORKBENCH_TERMINAL_PROGRAM_VERSION' in wrapper
    assert 'export TERM_PROGRAM="${CCB_WORKBENCH_TERMINAL_PROGRAM}"' in wrapper
    assert 'export TERM_PROGRAM_VERSION="${CCB_WORKBENCH_TERMINAL_PROGRAM_VERSION}"' in wrapper
    assert str(tmp_path / 'home' / '.config') not in wrapper
    workbench = (root / 'bin' / 'ccb-workbench').read_text(encoding='utf-8')
    assert 'wezterm --config-file' in workbench
    assert '--config-file' in workbench
    assert 'start --always-new-process --no-auto-connect --cwd "$PWD"' in workbench
    assert ' --skip-config' not in workbench
    assert ' -n ' not in workbench
    assert str(root / 'profiles' / 'wezterm' / 'wezterm.lua') in workbench
    assert 'CCB_WORKBENCH_FORCE_RICH=1' in workbench
    assert 'CCB_WORKBENCH_TERMINAL_PROGRAM=WezTerm' in workbench
    assert 'CCB_WORKBENCH_TERMINAL_PROGRAM_VERSION="${TERM_PROGRAM_VERSION:-}"' not in workbench
    assert 'ccb-workbench terminal requires WezTerm' in workbench
    assert 'set -- "${SHELL:-/bin/sh}" -lc' in workbench
    assert '-u TMUX' in workbench
    assert '-u TMUX_PANE' in workbench
    assert '-u CCB_TMUX_SOCKET' in workbench
    assert '-u CCB_TMUX_SOCKET_PATH' in workbench
    md_preview = (root / 'bin' / 'ccb-md-preview').read_text(encoding='utf-8')
    assert 'color_system="256"' in md_preview
    assert 'color_system="256color"' not in md_preview
    assert 'text = path.read_text' in md_preview
    assert 'sys.stdout.write(text)' in md_preview
    image_preview = (root / 'bin' / 'ccb-image-preview').read_text(encoding='utf-8')
    assert '--format=symbols' not in image_preview
    assert '--probe=off' not in image_preview
    assert 'Inline image preview requires the rich Yazi profile' in image_preview

    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    assert manifest['schema_version'] == 1
    assert manifest['components']['yazi']['status'] == 'ok'
    assert manifest['components']['wezterm']['status'] == 'ok'
    assert manifest['components']['neovim']['status'] == 'ok'
    assert manifest['components']['markdown']['status'] == 'ok'
    assert manifest['components']['image_preview']['status'] == 'ok'


def test_workbench_doctor_reports_manifest_and_component_paths(tmp_path: Path, monkeypatch) -> None:
    _prepare_env(tmp_path, monkeypatch)
    _stub_neovim(monkeypatch, tmp_path)
    workbench_tools.provision_workbench(profile='rich')
    stdout = StringIO()
    stderr = StringIO()

    code = cmd_tools(['doctor', 'workbench', '--profile', 'rich'], stdout=stdout, stderr=stderr)

    output = stdout.getvalue()
    assert code == 0
    assert stderr.getvalue() == ''
    assert 'workbench_status: ok' in output
    assert 'profile: rich' in output
    assert 'yazi_status: ok' in output
    assert 'wezterm_status: ok' in output
    assert 'neovim_status: ok' in output
    assert 'yazi_safe_config:' in output
    assert 'wezterm_config:' in output


def test_update_rich_workbench_provisions_and_enables_bundle(tmp_path: Path, monkeypatch) -> None:
    _prepare_env(tmp_path, monkeypatch)
    _stub_neovim(monkeypatch, tmp_path)

    result = workbench_tools.update_rich_workbench()

    assert result['status'] == 'ok'
    assert result['enabled'] is True
    assert result['rich_update_status'] == 'ok'
    manifest = json.loads((tmp_path / 'xdg-data' / 'ccb' / 'tools' / 'workbench' / 'manifest.json').read_text(encoding='utf-8'))
    assert manifest['enabled'] is True


def test_workbench_enable_disable_and_uninstall_are_bundle_scoped(tmp_path: Path, monkeypatch) -> None:
    _prepare_env(tmp_path, monkeypatch)
    _stub_neovim(monkeypatch, tmp_path)
    workbench_tools.provision_workbench(profile='rich')
    neovim_marker = tmp_path / 'xdg-data' / 'ccb' / 'tools' / 'neovim' / 'keep.txt'
    neovim_marker.parent.mkdir(parents=True, exist_ok=True)
    neovim_marker.write_text('keep\n', encoding='utf-8')

    enabled = workbench_tools.enable_workbench(profile='rich')
    assert enabled['enabled'] is True
    manifest_path = tmp_path / 'xdg-data' / 'ccb' / 'tools' / 'workbench' / 'manifest.json'
    assert json.loads(manifest_path.read_text(encoding='utf-8'))['enabled'] is True

    disabled = workbench_tools.disable_workbench(profile='rich')
    assert disabled['enabled'] is False
    assert json.loads(manifest_path.read_text(encoding='utf-8'))['enabled'] is False

    removed = workbench_tools.uninstall_workbench(profile='rich')
    assert removed['status'] == 'ok'
    assert not (tmp_path / 'xdg-data' / 'ccb' / 'tools' / 'workbench').exists()
    assert not (tmp_path / 'xdg-state' / 'ccb' / 'tools' / 'workbench').exists()
    assert (tmp_path / 'xdg-cache' / 'ccb' / 'tools' / 'workbench').exists()
    assert not (tmp_path / 'global-bin' / 'ccb-workbench').exists()
    assert not (tmp_path / 'global-bin' / 'ccb-yazi-rich').exists()
    assert not (tmp_path / 'global-bin' / 'ccb-image-preview').exists()
    assert neovim_marker.exists()


def test_workbench_launch_dry_run_prints_component_commands(tmp_path: Path, monkeypatch) -> None:
    _prepare_env(tmp_path, monkeypatch)
    _stub_neovim(monkeypatch, tmp_path)
    workbench_tools.provision_workbench(profile='rich')
    stdout = StringIO()

    code = cmd_tools(['launch', 'workbench', '--profile', 'rich', '--dry-run'], stdout=stdout, stderr=StringIO())

    output = stdout.getvalue()
    assert code == 0
    assert 'workbench_status: ok' in output
    assert 'launch_status: dry_run' in output
    assert 'launch_command:' in output
    assert 'ccb-yazi-rich' in output
    assert 'ccb-nvim' in output


def test_workbench_launch_detaches_outer_tmux_environment(tmp_path: Path, monkeypatch) -> None:
    _prepare_env(tmp_path, monkeypatch)
    _stub_neovim(monkeypatch, tmp_path)
    workbench_tools.provision_workbench(profile='rich')
    workbench_tools.enable_workbench(profile='rich')
    monkeypatch.setenv('TMUX', '/tmp/tmux-1000/outer,123,0')
    monkeypatch.setenv('TMUX_PANE', '%7')
    monkeypatch.setenv('CCB_TMUX_SOCKET', 'outer')
    monkeypatch.setenv('CCB_TMUX_SOCKET_PATH', '/tmp/outer.sock')
    calls: list[tuple[list[str], dict[str, str] | None]] = []

    class _Process:
        pid = 2424

    def _popen(command, env=None):
        calls.append((list(command), dict(env) if env is not None else None))
        return _Process()

    monkeypatch.setattr(workbench_tools.subprocess, 'Popen', _popen)

    result = workbench_tools.launch_workbench(profile='rich')

    assert result['launch_status'] == 'started'
    assert calls
    command, env = calls[0]
    assert command == [str(tmp_path / 'xdg-data' / 'ccb' / 'tools' / 'workbench' / 'bin' / 'ccb-workbench'), 'terminal']
    assert env is not None
    assert 'TMUX' not in env
    assert 'TMUX_PANE' not in env
    assert 'CCB_TMUX_SOCKET' not in env
    assert 'CCB_TMUX_SOCKET_PATH' not in env


def test_rich_launch_opens_wezterm_with_source_test_entrypoint(tmp_path: Path, monkeypatch) -> None:
    _prepare_env(tmp_path, monkeypatch)
    _stub_neovim(monkeypatch, tmp_path)
    workbench_tools.provision_workbench(profile='rich')
    workbench_tools.enable_workbench(profile='rich')
    script_root = tmp_path / 'source'
    project_root = tmp_path / 'project'
    script_root.mkdir()
    project_root.mkdir()
    _fake_executable(script_root / 'ccb')
    _fake_executable(script_root / 'ccb_test')
    monkeypatch.setenv('CCB_TEST_ENTRYPOINT', '1')
    monkeypatch.setenv('TMUX', '/tmp/tmux-1000/outer,123,0')
    monkeypatch.setenv('TMUX_PANE', '%7')
    monkeypatch.setenv('CCB_TMUX_SOCKET', 'outer')
    monkeypatch.setenv('CCB_TMUX_SOCKET_PATH', '/tmp/outer.sock')
    calls: list[tuple[list[str], str | None, dict[str, str] | None]] = []

    class _Process:
        pid = 4242

    def _popen(command, cwd=None, env=None):
        calls.append((list(command), str(cwd) if cwd is not None else None, dict(env) if env is not None else None))
        return _Process()

    monkeypatch.setattr(workbench_tools.subprocess, 'Popen', _popen)

    result = workbench_tools.launch_rich_ccb(script_root=script_root, cwd=project_root)

    assert result['launch_status'] == 'started'
    assert result['launch_pid'] == 4242
    assert calls
    command, cwd, env = calls[0]
    assert cwd == str(project_root)
    assert command[:2] == [str(tmp_path / 'xdg-data' / 'ccb' / 'tools' / 'workbench' / 'bin' / 'ccb-workbench'), 'terminal']
    assert command[2:4] == ['/bin/sh', '-lc']
    assert str(script_root / 'ccb_test') in command[4]
    assert 'exec "${SHELL:-/bin/sh}" -l' in command[4]
    assert env is not None
    assert 'TMUX' not in env
    assert 'TMUX_PANE' not in env
    assert 'CCB_TMUX_SOCKET' not in env
    assert 'CCB_TMUX_SOCKET_PATH' not in env


def test_rich_launch_requires_update_rich_first(tmp_path: Path, monkeypatch) -> None:
    _prepare_env(tmp_path, monkeypatch)
    _stub_neovim(monkeypatch, tmp_path)

    result = workbench_tools.launch_rich_ccb(script_root=tmp_path / 'source', cwd=tmp_path / 'project')

    assert result['status'] == 'failed'
    assert result['launch_status'] == 'missing_rich_bundle'
    assert 'ccb update rich' in result['reason']
