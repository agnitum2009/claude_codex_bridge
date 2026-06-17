from __future__ import annotations

import re
from dataclasses import dataclass


_ANSI_RE = re.compile(r'\x1b\[[0-9;?]*[ -/]*[@-~]')
_PROMPT_LINE_RE = re.compile(r'^\s*>\s*$')
_BUSY_MARKERS = ('▸ Thought', '● ', 'Running…', 'Running...', 'ctrl+o to expand')


@dataclass
class AgyPaneReader:
    """Thin wrapper around a terminal backend that snapshots an agy tmux pane.

    The underlying TmuxBackend.get_pane_content already strips ANSI, but other
    backend types may not, so we strip defensively and tolerate failures by
    returning an empty string instead of raising.
    """

    backend: object
    pane_id: str
    lines: int = 200

    def snapshot(self) -> str:
        getter = getattr(self.backend, 'get_pane_content', None)
        if not callable(getter):
            getter = getattr(self.backend, 'get_text', None)
        if not callable(getter):
            return ''
        try:
            content = getter(self.pane_id, lines=self.lines)
        except Exception:
            return ''
        if not content:
            return ''
        return _ANSI_RE.sub('', content)


def agy_pane_ready_for_input(content: str) -> bool:
    """Return true when the Antigravity TUI is at an empty input prompt."""
    text = _ANSI_RE.sub('', str(content or ''))
    if not text.strip():
        return False
    lines = text.replace('\r\n', '\n').replace('\r', '\n').splitlines()
    tail = lines[-80:]
    lowered_tail = '\n'.join(tail).lower()
    if '? for shortcuts' not in lowered_tail and 'gemini' not in lowered_tail:
        return False

    for index in range(len(tail) - 1, -1, -1):
        if not _PROMPT_LINE_RE.match(tail[index]):
            continue
        if _has_busy_activity(tail[index + 1 :]):
            continue
        after = '\n'.join(tail[index:]).lower()
        if '? for shortcuts' in after or 'gemini' in after:
            return True
    return False


def _has_busy_activity(lines: list[str]) -> bool:
    for line in lines:
        stripped = line.strip()
        if any(marker in stripped for marker in _BUSY_MARKERS):
            return True
    return False


__all__ = ['AgyPaneReader', 'agy_pane_ready_for_input']
