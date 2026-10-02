"""Safe resolver for registered GMD basenames in an extracted Chara tree."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path


class AssetCatalogError(ValueError):
    pass


def _safe_files(root: Path):
    root = root.resolve(strict=True)
    found = {}
    for current, dirs, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        dirs[:] = sorted(d for d in dirs if not (current_path / d).is_symlink())
        for name in sorted(files):
            path = current_path / name
            if path.is_symlink():
                # Symlinks are never trusted as extracted source assets.
                continue
            resolved = path.resolve(strict=True)
            if not resolved.is_relative_to(root):
                continue
            found.setdefault(name, []).append(resolved)
    return found


def resolve_references(reference_files, source_root, *, allow_missing=False):
    """Resolve role->registered path by exact basename; duplicate bytes must match."""
    root = Path(source_root).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise AssetCatalogError(f"Source root is not a directory: {root}")
    files = _safe_files(root)
    result = {}
    missing = []
    for role, registered in reference_files.items():
        basename = Path(registered).name
        candidates = sorted(files.get(basename, []), key=lambda p: p.relative_to(root).as_posix().casefold())
        if not candidates:
            missing.append(role)
            continue
        hashes = {hashlib.sha256(p.read_bytes()).digest() for p in candidates}
        if len(hashes) > 1:
            raise AssetCatalogError(f"Differing-content duplicate GMD basename: {basename}")
        result[role] = str(candidates[0])
    if missing and not allow_missing:
        raise AssetCatalogError("Missing registered GMD reference(s): " + ", ".join(missing))
    return result


def available_references(reference_files, source_root):
    return resolve_references(reference_files, source_root, allow_missing=True)
