from __future__ import annotations

from dataclasses import dataclass
import fcntl
import os
import pty
import re
import select
import struct
import subprocess
import termios
from typing import Mapping


@dataclass(frozen=True)
class TerminalGeometry:
    columns: int = 80
    rows: int = 24
    pixel_width: int = 0
    pixel_height: int = 0

    @classmethod
    def from_mapping(cls, value: object) -> 'TerminalGeometry':
        payload = value if isinstance(value, Mapping) else {}
        return cls(
            columns=_positive_int(payload.get('columns'), 80),
            rows=_positive_int(payload.get('rows'), 24),
            pixel_width=max(0, _int(payload.get('pixel_width'), 0)),
            pixel_height=max(0, _int(payload.get('pixel_height'), 0)),
        )


@dataclass(frozen=True)
class TerminalAttachTarget:
    terminal_id: str
    socket_path: str
    session_name: str
    geometry: TerminalGeometry
    target_summary: dict[str, object]

    @property
    def command(self) -> list[str]:
        return ['tmux', '-S', self.socket_path, 'attach-session', '-t', self.session_name]


@dataclass(frozen=True)
class TerminalHistoryTarget:
    project_id: str
    namespace_epoch: int
    agent: str
    window: str
    pane_id: str
    socket_path: str
    session_name: str
    max_lines: int = 200

    @property
    def command(self) -> list[str]:
        return [
            'tmux',
            '-S',
            self.socket_path,
            'capture-pane',
            '-p',
            '-t',
            self.pane_id,
            '-S',
            f'-{max(1, int(self.max_lines))}',
        ]


def create_tmux_terminal_history(target: TerminalHistoryTarget) -> dict[str, object]:
    cp = subprocess.run(
        target.command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=2.0,
    )
    if cp.returncode != 0:
        message = (cp.stderr or '').strip() or 'tmux capture-pane failed'
        raise RuntimeError(message)
    text = _strip_ansi(cp.stdout or '')
    return {
        'agent': target.agent,
        'history_scope': 'tmux_scrollback',
        'source_pane_id': target.pane_id,
        'stale': False,
        'blocks': _readable_history_blocks(text),
    }


class TmuxTerminalSession:
    def __init__(self, target: TerminalAttachTarget) -> None:
        self.target = target
        self._master_fd, slave_fd = pty.openpty()
        try:
            self._resize(target.geometry)
            self._process = subprocess.Popen(
                target.command,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                close_fds=True,
            )
        finally:
            os.close(slave_fd)

    def read(self, timeout_seconds: float = 0.1) -> bytes | None:
        ready, _, _ = select.select([self._master_fd], [], [], max(0.0, float(timeout_seconds)))
        if not ready:
            return b''
        try:
            data = os.read(self._master_fd, 65536)
        except OSError:
            return None if self._process.poll() is not None else b''
        if not data and self._process.poll() is not None:
            return None
        return data

    def write(self, data: bytes) -> None:
        if data:
            os.write(self._master_fd, data)

    def paste(self, text: str) -> None:
        self.write(str(text).encode('utf-8'))

    def resize(self, geometry: TerminalGeometry) -> None:
        self._resize(geometry)

    def close(self) -> None:
        try:
            os.close(self._master_fd)
        except OSError:
            pass
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=1)

    def _resize(self, geometry: TerminalGeometry) -> None:
        rows = max(1, int(geometry.rows))
        columns = max(1, int(geometry.columns))
        pixels_y = max(0, int(geometry.pixel_height))
        pixels_x = max(0, int(geometry.pixel_width))
        packed = struct.pack('HHHH', rows, columns, pixels_y, pixels_x)
        fcntl.ioctl(self._master_fd, termios.TIOCSWINSZ, packed)


def create_tmux_terminal_session(target: TerminalAttachTarget) -> TmuxTerminalSession:
    return TmuxTerminalSession(target)


def _readable_history_blocks(text: str) -> list[dict[str, object]]:
    blocks: list[dict[str, object]] = []
    current_type = ''
    current: list[str] = []

    def flush() -> None:
        nonlocal current_type, current
        rendered = '\n'.join(line.rstrip() for line in current).strip()
        if not rendered:
            current_type = ''
            current = []
            return
        block_type = current_type or _classify_line(rendered)
        blocks.append(
            {
                'id': f'history-{len(blocks) + 1}',
                'type': block_type,
                'title': _block_title(block_type),
                'text': rendered,
            }
        )
        current_type = ''
        current = []

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            flush()
            continue
        line_type = _classify_line(line)
        if current and line_type != current_type and line_type in {'command', 'diff', 'error'}:
            flush()
        if not current:
            current_type = line_type
        current.append(line)
    flush()
    return blocks


def _classify_line(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith(('$ ', '> ', '# ')):
        return 'command'
    if stripped.startswith(('Traceback ', 'Error:', 'ERROR:', 'Exception:', 'FAILED')):
        return 'error'
    if stripped.startswith(('diff --git ', '+++ ', '--- ', '+ ', '- ', '@@ ')):
        return 'diff'
    if stripped.startswith(('```', 'def ', 'class ', 'import ', 'from ', 'const ', 'final ', 'Future<')):
        return 'code'
    return 'log'


def _block_title(block_type: str) -> str:
    return {
        'command': 'Command',
        'code': 'Code',
        'diff': 'Diff',
        'error': 'Error',
    }.get(block_type, 'Log')


def _strip_ansi(text: str) -> str:
    return re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', text)


def _int(value: object, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _positive_int(value: object, fallback: int) -> int:
    return max(1, _int(value, fallback))
