"""List and delete generated outputs under Tool/userdata/outputs, with strict path guards.

Only direct child folders of the outputs folder can be removed; links/junctions are never
followed or removed, and nothing outside that folder is ever touched.
"""
from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path

BLEND_SUFFIXES = ('.blend', '.blend1', '.blend2')


class CleanupError(ValueError):
    pass


def _is_link(path: Path) -> bool:
    try:
        info = os.lstat(path)
    except OSError:
        return True  # unreadable: treat as unsafe
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 0x400)


def _checked_root(root) -> Path:
    path = Path(root)
    if not path.is_dir() or _is_link(path):
        raise CleanupError('Outputs folder does not exist or is a link')
    path = path.resolve()
    if path.name != 'outputs' or path.parent.name != 'userdata':
        raise CleanupError('Only Tool/userdata/outputs can be cleaned')
    return path


def _checked_child(root: Path, name: str) -> Path:
    if (not isinstance(name, str) or not name or name in ('.', '..')
            or '/' in name or '\\' in name or ':' in name):
        raise CleanupError(f'Not a plain output folder name: {name!r}')
    child = root / name
    if not child.is_dir() or _is_link(child) or child.resolve().parent != root:
        raise CleanupError(f'Not a normal output folder: {name}')
    return child


def _files(folder: Path):
    """Yield (path, size) for regular files below folder without following links."""
    stack = [folder]
    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError:
            continue
        for entry in entries:
            path = Path(entry.path)
            if _is_link(path):
                continue
            if entry.is_dir(follow_symlinks=False):
                stack.append(path)
            elif entry.is_file(follow_symlinks=False):
                try:
                    yield path, entry.stat(follow_symlinks=False).st_size
                except OSError:
                    continue


def list_outputs(root) -> list[dict]:
    """Newest first: name, total bytes, bytes in working .blend files, last modified."""
    root = _checked_root(root)
    rows = []
    for child in root.iterdir():
        if not child.is_dir() or _is_link(child):
            continue
        total = blend = 0
        for path, size in _files(child):
            total += size
            if path.suffix.lower() in BLEND_SUFFIXES:
                blend += size
        rows.append({'name': child.name, 'bytes': total, 'blend_bytes': blend,
                     'mtime': child.stat().st_mtime})
    return sorted(rows, key=lambda row: row['mtime'], reverse=True)


def _writable_then_retry(function, path, _info):
    os.chmod(path, stat.S_IWRITE)
    function(path)


def delete_outputs(root, names) -> dict:
    """Delete whole output folders. Per-folder failures are reported, not raised."""
    root = _checked_root(root)
    deleted, errors, freed = [], [], 0
    for name in names:
        try:
            child = _checked_child(root, name)
            size = sum(s for _, s in _files(child))
            shutil.rmtree(child, onerror=_writable_then_retry)
            deleted.append(name)
            freed += size
        except (CleanupError, OSError) as exc:
            errors.append({'name': name, 'error': str(exc)})
    return {'deleted': deleted, 'freed_bytes': freed, 'errors': errors}


def delete_working_blends(root, names) -> dict:
    """Delete only the working .blend files inside the folders; generated mods stay."""
    root = _checked_root(root)
    done, errors, freed, count = [], [], 0, 0
    for name in names:
        try:
            child = _checked_child(root, name)
            for path, size in list(_files(child)):
                if path.suffix.lower() in BLEND_SUFFIXES:
                    os.chmod(path, stat.S_IWRITE)
                    path.unlink()
                    freed += size
                    count += 1
            done.append(name)
        except (CleanupError, OSError) as exc:
            errors.append({'name': name, 'error': str(exc)})
    return {'cleaned': done, 'files_deleted': count, 'freed_bytes': freed, 'errors': errors}


def format_size(size: int) -> str:
    value = float(size)
    for unit in ('B', 'KB', 'MB', 'GB'):
        if value < 1024 or unit == 'GB':
            return f'{value:.0f} {unit}' if unit == 'B' else f'{value:.1f} {unit}'
        value /= 1024
    return f'{value:.1f} GB'
