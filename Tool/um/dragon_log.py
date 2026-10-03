"""Local log files and a redacted debug report, so problems on other machines can be debugged.

Everything stays on the user's machine under Tool/userdata/logs; nothing is uploaded. User names and
home-folder paths are masked when a line is written. Logging never raises into the application: if the
log folder cannot be written the tool simply runs without a log file.
"""
from __future__ import annotations

import hashlib
import json
import logging
import logging.handlers
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

LOGGER_NAME = 'vrmdragon'
LOG_NAME = 'vrmdragon.log'
MAX_BYTES = 2 * 1024 * 1024
BACKUPS = 5
OUTPUT_LIMIT = 100_000          # characters of one subprocess output kept in the log
REPORT_LOG_BYTES = 400_000      # newest log text copied into a debug report
REPORTS_KEPT = 10

_USER_PATH = re.compile(r'(?i)[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s"\'<>|]+')
_state = {'directory': None}


def bundle_root() -> Path:
    return Path(__file__).resolve().parents[2]


def log_dir() -> Path:
    return bundle_root() / 'Tool' / 'userdata' / 'logs'


def redact(text: str) -> str:
    """Mask the user's name and home folder; keeps the rest of every path for debugging."""
    text = str(text)
    home = str(Path.home())
    for variant in {home, home.replace('\\', '/'), home.replace('/', '\\')}:
        if variant:
            text = re.sub(re.escape(variant), '<home>', text, flags=re.I)
    text = _USER_PATH.sub('<home>', text)
    user = os.environ.get('USERNAME') or os.environ.get('USER') or ''
    if len(user) >= 3:
        text = re.sub(re.escape(user), '<user>', text, flags=re.I)
    return text


class _RedactingFormatter(logging.Formatter):
    def format(self, record):
        return redact(super().format(record))


def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)


def shutdown_logging() -> None:
    logger = get_logger()
    for handler in list(logger.handlers):
        if getattr(handler, '_vrmdragon', False):
            logger.removeHandler(handler)
            handler.close()
    _state['directory'] = None


def setup_logging(directory=None, max_bytes: int = MAX_BYTES, backups: int = BACKUPS) -> logging.Logger:
    """Idempotent. Falls back to no file logging if the folder is not writable."""
    directory = Path(directory) if directory else log_dir()
    logger = get_logger()
    if _state['directory'] == directory:
        return logger
    shutdown_logging()
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    try:
        directory.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(directory / LOG_NAME, maxBytes=max_bytes,
                                                       backupCount=backups, encoding='utf-8')
    except OSError:
        handler = logging.NullHandler()
    handler._vrmdragon = True
    handler.setFormatter(_RedactingFormatter('%(asctime)s %(levelname)-7s %(message)s'))
    logger.addHandler(handler)
    _state['directory'] = directory
    return logger


def tool_fingerprint(root: Path | None = None) -> str:
    """Short hash of the tool's own source, so a report says which version produced it."""
    root = Path(root) if root else bundle_root()
    digest = hashlib.sha256()
    for path in sorted((root / 'Tool' / 'um').glob('*.py')):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def environment_info(settings_file: Path | None = None) -> dict:
    root = bundle_root()
    info = {'tool_fingerprint': tool_fingerprint(root),
            'python': sys.version.split()[0], 'platform': platform.platform(),
            'machine': platform.machine()}
    try:
        import tkinter
        info['tk'] = str(tkinter.TkVersion)
    except Exception:  # noqa: BLE001 - diagnostics must never fail
        info['tk'] = 'unavailable'
    try:
        import PIL
        info['pillow'] = PIL.__version__
    except Exception:  # noqa: BLE001
        info['pillow'] = 'not installed'
    try:
        info['free_disk_gb'] = round(shutil.disk_usage(root).free / 1024 ** 3, 1)
    except OSError:
        info['free_disk_gb'] = None
    settings_file = Path(settings_file) if settings_file else root / 'Tool' / 'userdata' / 'settings.json'
    try:
        settings = json.loads(settings_file.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        settings = {}
    blender = settings.get('blender') or ''
    source = settings.get('source_root') or ''
    info['settings'] = {'profile_mode': settings.get('profile_mode'),
                        'include_variants': settings.get('include_variants'),
                        'blender_found': bool(blender) and Path(blender).is_file(),
                        'source_root_found': bool(source) and Path(source).is_dir()}
    return info


def log_environment() -> None:
    logger = get_logger()
    logger.info('--- session start ---')
    for key, value in environment_info().items():
        logger.info('env %s = %s', key, value)


def log_exception(context: str, exc: BaseException) -> None:
    get_logger().error('%s: %s', context, exc, exc_info=exc)


def _clip(text: str) -> str:
    if len(text) <= OUTPUT_LIMIT:
        return text
    half = OUTPUT_LIMIT // 2
    return text[:half] + f'\n... [{len(text) - OUTPUT_LIMIT} characters omitted] ...\n' + text[-half:]


_ERROR_LINE = re.compile(r'(?i)\b(\w*Error|\w*Exception|failed|cannot|not found|no such file|denied)\b')


def failure_summary(stdout: str, stderr: str, limit: int = 1500) -> str:
    """Short text for an error dialog: the last error-looking lines, else the last lines of output."""
    lines = [line.strip() for line in ((stderr or '') + chr(10) + (stdout or '')).splitlines() if line.strip()]
    hits, seen = [], set()
    for line in reversed(lines):
        if _ERROR_LINE.search(line) and not line.startswith('File ') and line not in seen:
            seen.add(line)
            hits.append(line[:400])
        if len(hits) >= 6:
            break
    text = chr(10).join(reversed(hits)) if hits else chr(10).join(lines[-12:])
    return text[-limit:]


def run_logged(command, label: str, timeout: float) -> subprocess.CompletedProcess:
    """subprocess.run(capture_output) that records the outcome; TimeoutExpired is re-raised."""
    logger = get_logger()
    started = time.time()
    logger.info('run %s: %s', label, ' '.join(str(part) for part in command))
    try:
        proc = subprocess.run(command, capture_output=True, text=True, errors='replace', timeout=timeout)
    except subprocess.TimeoutExpired:
        logger.error('%s timed out after %ss', label, timeout)
        raise
    seconds = time.time() - started
    if proc.returncode:
        logger.error('%s exited with %s after %.1fs\n--- stdout ---\n%s\n--- stderr ---\n%s',
                     label, proc.returncode, seconds, _clip(proc.stdout or ''), _clip(proc.stderr or ''))
    else:
        tail = '\n'.join(((proc.stderr or '') + '\n' + (proc.stdout or '')).strip().splitlines()[-8:])
        logger.info('%s finished in %.1fs (exit 0); last output:\n%s', label, seconds, tail)
    return proc


def _recent_failures(outputs: Path, limit: int = 5) -> list[str]:
    rows = []
    try:
        candidates = list(outputs.glob('*/variant-coverage.json')) + list(outputs.glob('*/Runs/*/status.json'))
    except OSError:
        return rows
    for path in sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and data.get('error'):
            rows.append(f"{path.relative_to(outputs).as_posix()}: {data.get('status')}: {str(data['error'])[:600]}")
        if len(rows) >= limit:
            break
    return rows


def _log_tail(directory: Path, size: int) -> str:
    chunks, remaining = [], size
    files = [directory / LOG_NAME] + [directory / f'{LOG_NAME}.{i}' for i in range(1, BACKUPS + 1)]
    for path in files:
        if remaining <= 0 or not path.is_file():
            continue
        data = path.read_bytes()[-remaining:]
        remaining -= len(data)
        chunks.append(data.decode('utf-8', errors='replace'))
    return ''.join(reversed(chunks))


def create_debug_report(directory=None, outputs: Path | None = None) -> Path:
    """Write a redacted text report (environment, recent failures, newest log) next to the logs."""
    directory = Path(directory) if directory else log_dir()
    directory.mkdir(parents=True, exist_ok=True)
    outputs = Path(outputs) if outputs else bundle_root() / 'Tool' / 'userdata' / 'outputs'
    for handler in get_logger().handlers:
        handler.flush()
    lines = ['VRMDragonTool debug report', f'created: {datetime.now().isoformat(timespec="seconds")}',
             'User names and home-folder paths are masked. File and folder names, avatar names and error text',
             'are NOT removed: read this file before you post it anywhere.', '', '== environment ==']
    lines += [f'{key}: {value}' for key, value in environment_info().items()]
    failures = _recent_failures(outputs)
    lines += ['', '== recent failed runs =='] + (failures or ['(none found)'])
    lines += ['', '== newest log text ==', _log_tail(directory, REPORT_LOG_BYTES) or '(log is empty)']
    path = directory / f'debug-report-{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt'
    path.write_text(redact('\n'.join(lines)) + '\n', encoding='utf-8')
    reports = sorted(directory.glob('debug-report-*.txt'), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in reports[REPORTS_KEPT:]:
        try:
            old.unlink()
        except OSError:
            pass
    return path


def log_files_size(directory=None) -> int:
    directory = Path(directory) if directory else log_dir()
    return sum(p.stat().st_size for p in _own_files(directory))


def _own_files(directory: Path):
    if not directory.is_dir():
        return []
    return [p for p in directory.iterdir()
            if p.is_file() and (p.name.startswith(LOG_NAME) or re.fullmatch(r'debug-report-[\d_]+\.txt', p.name))]


def delete_logs(directory=None) -> int:
    """Delete only this tool's log files and debug reports; returns the number of files removed."""
    directory = Path(directory) if directory else log_dir()
    shutdown_logging()  # releases the open log file so it can be deleted on Windows
    count = 0
    for path in _own_files(directory):
        try:
            path.unlink()
            count += 1
        except OSError:
            pass
    return count
