from __future__ import annotations

from pathlib import Path

from cli.tools_runtime.workbench import print_workbench_status, uninstall_workbench

from ..claude_home_cleanup import cleanup_claude_files
from ..install import run_installer


def cmd_uninstall(args, *, script_root: Path) -> int:
    target = str(getattr(args, 'target', '') or '').strip().lower()
    if target:
        if target != 'rich':
            print(f"❌ Unsupported uninstall target: {target}")
            print("💡 Use: ccb uninstall rich")
            return 2
        result = uninstall_workbench(profile='rich', remove_cache=False)
        print_workbench_status(result)
        return 0 if result.get('status') in {'ok', 'missing'} else 1
    cleanup_claude_files()
    return run_installer("uninstall", script_root=script_root)


def cmd_reinstall(_args, *, script_root: Path) -> int:
    cleanup_claude_files()
    return run_installer("install", script_root=script_root)


__all__ = ['cmd_reinstall', 'cmd_uninstall']
