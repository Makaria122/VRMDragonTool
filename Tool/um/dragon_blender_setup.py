"""Explicit, verified download of the pinned portable Blender into Tool/runtime/blender.

Only runs when the user asks for it (a dialog or the Blender tab). The archive comes from the
official server over HTTPS, must match a reviewed size and SHA-256, is unpacked into a staging folder
with strict path checks, and is moved into place in one step, so a failed or cancelled attempt leaves
nothing half-installed. Blender itself is GPL software that we only download, never redistribute.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import threading
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

BLENDER_VERSION = '4.5.14'
BLENDER_URL = 'https://download.blender.org/release/Blender4.5/blender-4.5.14-windows-x64.zip'
# Reviewed values: published in https://download.blender.org/release/Blender4.5/blender-4.5.14.sha256
BLENDER_SHA256 = 'b9533d2397ac1984db4466fb23a7a4649391cca93f6e84209f9bcc60d071c8b9'
BLENDER_SIZE = 398_661_046
TOP_FOLDER = 'blender-4.5.14-windows-x64'
ALLOWED_HOST = 'download.blender.org'
MIN_FREE_BYTES = 2_500_000_000      # download + unpacked copy + margin
MAX_EXPANDED = 3 * 1024 ** 3
MAX_FILES = 60_000
MARKER = '.vrmdragontool-blender.json'
ROOT = Path(__file__).resolve().parents[1] / 'runtime'


class BlenderSetupError(RuntimeError):
    pass


def _progress(callback, message, current=None, total=None):
    if callback:
        callback({'message': message, 'current': current, 'total': total})


def _writable(function, path, _info):
    os.chmod(path, stat.S_IWRITE)
    function(path)


def _default_runner(command, timeout):
    from um.dragon_log import run_logged
    return run_logged(command, 'blender --version', timeout)


class BlenderInstaller:
    def __init__(self, root: Path = ROOT, *, url: str = BLENDER_URL, sha256: str = BLENDER_SHA256,
                 size: int = BLENDER_SIZE, top_folder: str = TOP_FOLDER, version: str = BLENDER_VERSION,
                 opener: Callable | None = None, runner: Callable | None = None,
                 disk_free: Callable | None = None):
        self.root = Path(root).resolve()
        self.target = self.root / 'blender'
        self.exe = self.target / 'blender.exe'
        self.url, self.sha256, self.size = url, sha256.lower(), int(size)
        self.top_folder, self.version = top_folder, version
        self._open = opener or (lambda request: urllib.request.urlopen(request, timeout=60))
        self._run = runner or _default_runner
        self._free = disk_free or (lambda path: shutil.disk_usage(path).free)
        self._lock = threading.Lock()

    # ---- state -------------------------------------------------------------------------------
    def installed(self) -> bool:
        return self.exe.is_file()

    def status(self) -> dict:
        info = {'installed': self.installed(), 'path': str(self.exe), 'pinned_version': self.version,
                'download_bytes': self.size}
        marker = self.target / MARKER
        if marker.is_file():
            try:
                info['installed_version'] = json.loads(marker.read_text(encoding='utf-8')).get('version')
            except (OSError, ValueError):
                pass
        return info

    # ---- install -----------------------------------------------------------------------------
    def install(self, progress: Callable | None = None, cancel: threading.Event | None = None) -> Path:
        """Download, verify, unpack and verify-run Blender. Returns the path of blender.exe."""
        if not self._lock.acquire(blocking=False):
            raise BlenderSetupError('A Blender setup is already running')
        part = self.root / 'blender-download.zip.part'
        staging = self.root / 'blender-staging'
        try:
            if self.installed():
                _progress(progress, 'Blender is already installed')
                return self.exe
            self._check_target()
            self.root.mkdir(parents=True, exist_ok=True)
            if self._free(self.root) < MIN_FREE_BYTES:
                raise BlenderSetupError(
                    f'Not enough free disk space: about {MIN_FREE_BYTES / 1e9:.1f} GB is needed in {self.root}')
            self._cleanup(part, staging)
            self._download(part, progress, cancel)
            self._unpack(part, staging, progress, cancel)
            payload = staging / self.top_folder
            if not (payload / 'blender.exe').is_file():
                raise BlenderSetupError('The archive does not contain blender.exe at the expected place')
            self._place(payload)
            self._verify(progress)
            return self.exe
        except (OSError, urllib.error.URLError, zipfile.BadZipFile) as exc:
            raise BlenderSetupError(f'Could not set up Blender: {exc}') from exc
        finally:
            self._cleanup(part, staging)
            self._lock.release()

    def _check_target(self):
        if self.target.exists():
            if not self.target.is_dir() or any(self.target.iterdir()):
                raise BlenderSetupError(
                    f'{self.target} already exists and is not empty, but has no blender.exe. '
                    'Move or delete it, or select your own blender.exe instead.')

    @staticmethod
    def _cleanup(*paths: Path):
        for path in paths:
            if path.is_dir():
                shutil.rmtree(path, onerror=_writable)
            elif path.exists():
                try:
                    path.unlink()
                except OSError:
                    pass

    @staticmethod
    def _cancelled(cancel):
        if cancel is not None and cancel.is_set():
            raise BlenderSetupError('Cancelled')

    def _download(self, part: Path, progress, cancel):
        parsed = urllib.parse.urlparse(self.url)
        if parsed.scheme != 'https' or parsed.hostname != ALLOWED_HOST:
            raise BlenderSetupError('Refusing to download from anything but https://' + ALLOWED_HOST)
        request = urllib.request.Request(self.url, headers={'User-Agent': 'VRMDragonTool-blender-setup'})
        digest, received = hashlib.sha256(), 0
        _progress(progress, f'Downloading Blender {self.version}', 0, self.size)
        with self._open(request) as response:
            final = urllib.parse.urlparse(response.geturl() if hasattr(response, 'geturl') else self.url)
            if final.scheme != 'https' or final.hostname != ALLOWED_HOST:
                raise BlenderSetupError('The download was redirected away from ' + ALLOWED_HOST + '; refusing')
            length = response.headers.get('Content-Length') if getattr(response, 'headers', None) else None
            if length is not None and int(length) != self.size:
                raise BlenderSetupError(f'Unexpected download size ({length} bytes, expected {self.size})')
            with part.open('wb') as out:
                while True:
                    self._cancelled(cancel)
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    received += len(block)
                    if received > self.size:
                        raise BlenderSetupError('The download is larger than expected; refusing')
                    digest.update(block)
                    out.write(block)
                    _progress(progress, f'Downloading Blender {self.version}', received, self.size)
        if received != self.size:
            raise BlenderSetupError(f'Incomplete download ({received} of {self.size} bytes)')
        if digest.hexdigest() != self.sha256:
            raise BlenderSetupError('The downloaded file does not match the reviewed SHA-256; it was discarded')

    def _unpack(self, archive: Path, staging: Path, progress, cancel):
        staging.mkdir(parents=True)
        base = staging.resolve()
        with zipfile.ZipFile(archive) as bundle:
            members = bundle.infolist()
            if len(members) > MAX_FILES or sum(m.file_size for m in members) > MAX_EXPANDED:
                raise BlenderSetupError('The archive is larger than expected when unpacked; refusing')
            for member in members:
                name = member.filename
                mode = (member.external_attr >> 16) & 0o170000
                if (name.startswith(('/', '\\')) or ':' in name or '\\' in name
                        or '..' in Path(name).parts or mode == stat.S_IFLNK):
                    raise BlenderSetupError(f'Unsafe entry in the archive: {name!r}')
                if not (base / name).resolve().is_relative_to(base):
                    raise BlenderSetupError(f'Unsafe path in the archive: {name!r}')
            for index, member in enumerate(members, 1):
                self._cancelled(cancel)
                bundle.extract(member, base)
                if index % 200 == 0 or index == len(members):
                    _progress(progress, 'Unpacking Blender', index, len(members))

    def _place(self, payload: Path):
        if self.target.exists():
            self.target.rmdir()  # empty directory (checked before)
        os.replace(payload, self.target)
        (self.target / MARKER).write_text(json.dumps({'version': self.version, 'sha256': self.sha256}),
                                          encoding='utf-8')

    def _verify(self, progress):
        _progress(progress, 'Checking that Blender starts')
        try:
            result = self._run([str(self.exe), '--version'], 120)
            output = (getattr(result, 'stdout', '') or '') + (getattr(result, 'stderr', '') or '')
            ok = getattr(result, 'returncode', 1) == 0 and f'Blender {self.version}' in output
        except Exception:  # noqa: BLE001 - any failure means the install is not usable
            ok = False
        if not ok:
            shutil.rmtree(self.target, onerror=_writable)
            raise BlenderSetupError(f'The installed Blender did not start as Blender {self.version}; it was removed')
        _progress(progress, f'Blender {self.version} is ready')

