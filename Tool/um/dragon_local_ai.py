"""Private, app-owned Ollama runtime. No global Ollama discovery or environment inheritance.

GUI contract: get_runtime().setup(progress=None), download_model(progress=None), status(),
close(). Run setup/download_model from a worker thread. request(path, payload=None,
timeout=120, progress=None) accepts API-relative paths (e.g. /api/chat).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

MODEL = 'qwen2.5-coder:7b'
# Pinned source; the GitHub Releases API must provide the asset's SHA-256 digest.
OLLAMA_RELEASE = 'v0.35.0'
OLLAMA_SHA256 = 'd6f7d3dd4f5d013553a78c1e78b2521fcf41d43dd2863e4596cdc046fe6036db'
RELEASE_API = f'https://api.github.com/repos/ollama/ollama/releases/tags/{OLLAMA_RELEASE}'
ASSET_NAME = 'ollama-windows-amd64.zip'
MAX_DOWNLOAD = 2 * 1024 * 1024 * 1024
MAX_RESPONSE = 32 * 1024 * 1024
ROOT = Path(__file__).resolve().parents[1] / 'runtime'


def _progress(callback, message, current=None, total=None):
    if callback:
        callback({'message': message, 'current': current, 'total': total})


class LocalAIError(RuntimeError):
    pass


class LocalAIRuntime:
    def __init__(self, root: Path = ROOT):
        self.root = Path(root).resolve()
        self.ollama_dir = self.root / 'ollama'
        self.models = self.root / 'models'
        self.home = self.root / 'home'
        self.cache = self.root / 'cache'
        self.logs = self.root / 'logs'
        self.executable = self.ollama_dir / 'ollama.exe'
        self._proc = None
        self._log_handle = None
        self._port = None
        self._lock = threading.RLock()
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def _environment(self):
        # Explicit allowlist, not a copy of os.environ; in particular OLLAMA_* cannot leak in.
        env = {'PATH': str(Path(os.environ.get('SYSTEMROOT', r'C:\Windows')) / 'System32'),
               'SYSTEMROOT': os.environ.get('SYSTEMROOT', r'C:\Windows'),
               'WINDIR': os.environ.get('WINDIR', r'C:\Windows'),
               'TEMP': str(self.cache), 'TMP': str(self.cache), 'HOME': str(self.home),
               'USERPROFILE': str(self.home), 'APPDATA': str(self.home / 'AppData' / 'Roaming'),
               'LOCALAPPDATA': str(self.home / 'AppData' / 'Local'),
               'OLLAMA_MODELS': str(self.models), 'OLLAMA_HOST': f'127.0.0.1:{self._port}',
               'OLLAMA_TMPDIR': str(self.cache), 'XDG_CACHE_HOME':str(self.cache),
               'CUDA_CACHE_PATH':str(self.cache/'cuda')}
        return env

    def setup(self, progress=None, *, install=False):
        with self._lock:
            for path in (self.ollama_dir,self.models,self.home,self.cache,self.logs,self.executable):
                if not path.resolve().is_relative_to(self.root):
                    raise LocalAIError('Runtime storage must not escape through symlinks/junctions')
            for path in (self.ollama_dir, self.models, self.home, self.cache, self.logs):
                path.mkdir(parents=True, exist_ok=True)
            if not self.executable.is_file():
                if not install:
                    raise LocalAIError('Ollama is not installed. Use the explicit setup button first.')
                _progress(progress, 'Downloading pinned Ollama portable runtime')
                self._install(progress)
            if self._proc is not None and self._proc.poll() is None:
                return self.status()
            sock = socket.socket(); sock.bind(('127.0.0.1', 0)); self._port = sock.getsockname()[1]; sock.close()
            self._log_handle = (self.logs / 'ollama.log').open('ab')
            try:
                self._proc = self._launch(self._log_handle)
            except OSError as exc:
                self._log_handle.close(); self._log_handle=None; self._port=None
                raise LocalAIError(f'Could not launch Tool-owned Ollama: {exc}') from exc
            if not self._wait_ready(30):
                self.close(); raise LocalAIError('Managed Ollama failed to start; see Tool/runtime/logs/ollama.log')
            return self.status()

    def _launch(self, log):
        # Use the explicit binary path; never search PATH or launch a global installation.
        return subprocess.Popen([str(self.executable), 'serve'], cwd=str(self.ollama_dir), env=self._environment(),
            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))

    def _wait_ready(self, seconds):
        import time
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if self._proc.poll() is not None: return False
            try:
                with self._opener.open(self._url('/'), timeout=.5): return True
            except Exception: time.sleep(.2)
        return False

    def _install(self, progress):
        req = urllib.request.Request(RELEASE_API, headers={'User-Agent':'VRMDragonTool-local-runtime','Accept':'application/vnd.github+json'})
        try:
            with urllib.request.urlopen(req, timeout=30) as r: release = json.loads(r.read(2_000_000))
            asset = next((a for a in release.get('assets', []) if a.get('name') == ASSET_NAME), None)
            digest = asset.get('digest') if asset else None
            if not isinstance(digest, str) or not digest.startswith('sha256:') or len(digest) != 71:
                raise LocalAIError('Pinned Ollama release lacks a SHA-256 asset digest; refusing installation')
            if digest[7:] != OLLAMA_SHA256:
                raise LocalAIError('Pinned release digest differs from the reviewed checksum')
            url = asset.get('browser_download_url', '')
            if not url.startswith('https://github.com/ollama/ollama/releases/download/'):
                raise LocalAIError('Unexpected Ollama asset URL')
            tmp = self.root / 'ollama-download.zip'; h = hashlib.sha256(); size = 0
            with urllib.request.urlopen(url, timeout=60) as r, tmp.open('wb') as out:
                total = int(r.headers.get('Content-Length', '0'))
                if total > MAX_DOWNLOAD: raise LocalAIError('Ollama archive exceeds size limit')
                while True:
                    block = r.read(1024 * 1024)
                    if not block: break
                    size += len(block)
                    if size > MAX_DOWNLOAD: raise LocalAIError('Ollama archive exceeds size limit')
                    h.update(block); out.write(block); _progress(progress, 'Downloading Ollama', size, total or None)
            if h.hexdigest() != digest[7:]: raise LocalAIError('Ollama archive SHA-256 mismatch')
            with tempfile.TemporaryDirectory(prefix='ollama-stage-',dir=self.root) as staging:
                stage=Path(staging)/'payload'
                self._extract_safe(tmp,stage)
                if not (stage/'ollama.exe').is_file():
                    raise LocalAIError('Archive did not contain ollama.exe at expected path')
                # setup created only an empty install directory. Never overlay a partial install.
                self.ollama_dir.rmdir()
                stage.replace(self.ollama_dir)
            tmp.unlink(missing_ok=True)
        except (OSError, urllib.error.URLError, zipfile.BadZipFile) as e:
            raise LocalAIError(f'Could not install the pinned portable Ollama runtime: {e}') from e

    @staticmethod
    def _extract_safe(archive, destination):
        base = Path(destination).resolve()
        with zipfile.ZipFile(archive) as z:
            if sum(info.file_size for info in z.infolist()) > MAX_DOWNLOAD*3:
                raise LocalAIError('Archive expanded size exceeds limit')
            for info in z.infolist():
                target = (base / info.filename).resolve()
                if not target.is_relative_to(base): raise LocalAIError('Unsafe path in Ollama archive')
                if info.file_size > MAX_DOWNLOAD: raise LocalAIError('Oversized file in Ollama archive')
            z.extractall(base)

    def _url(self, path): return f'http://127.0.0.1:{self._port}{path}'

    def request(self, path, payload=None, timeout=120, progress=None):
        if not isinstance(path, str) or not path.startswith('/api/') or path.startswith('//'):
            raise ValueError('Only Ollama /api/* paths are accepted')
        if self._port is None or self._proc is None or self._proc.poll() is not None:
            raise LocalAIError('Managed Ollama is not running; call setup() first')
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode('utf-8')
        req = urllib.request.Request(self._url(path), data=body, headers={'Content-Type':'application/json'} if body else {})
        try:
            with self._opener.open(req, timeout=timeout) as response:
                raw = response.read(MAX_RESPONSE + 1)
            if len(raw) > MAX_RESPONSE: raise LocalAIError('Ollama response exceeds size limit')
            return json.loads(raw)
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as e:
            raise LocalAIError(f'Managed Ollama request failed: {e}') from e

    def download_model(self, progress=None):
        self.setup(progress)
        complete=False
        # Stream NDJSON so GUI progress can report pull status.
        payload=json.dumps({'name':MODEL,'stream':True}).encode()
        req=urllib.request.Request(self._url('/api/pull'), data=payload, headers={'Content-Type':'application/json'})
        with self._opener.open(req, timeout=3600) as r:
            while True:
                line=r.readline(MAX_RESPONSE)
                if not line: break
                item=json.loads(line)
                _progress(progress, item.get('status','Downloading model'), item.get('completed'), item.get('total'))
                if item.get('error'): raise LocalAIError(item['error'])
                if item.get('status')=='success':complete=True
        result=self.status()
        if not complete or not result['model_available']:
            raise LocalAIError('Model download did not finish successfully; retry the download button')
        return result

    def status(self):
        running=self._proc is not None and self._proc.poll() is None
        available=False
        if running:
            try:available=any(m.get('name')==MODEL for m in self.request('/api/tags',timeout=1).get('models',[]))
            except LocalAIError:pass
        else:
            manifest=self.models/'manifests/registry.ollama.ai/library/qwen2.5-coder/7b'
            try:
                data=json.loads(manifest.read_text(encoding='utf-8'))
                digests=[data['config']['digest']]+[x['digest'] for x in data['layers']]
                available=bool(digests) and all(len(d)==71 and d.startswith('sha256:') and
                    all(c in '0123456789abcdef' for c in d[7:]) and
                    (self.models/'blobs'/d.replace(':','-')).is_file() for d in digests)
            except (OSError,ValueError,KeyError,TypeError):pass
        return {'installed':self.executable.is_file(),'running':running,'model':MODEL,
                'model_available':available,'port':self._port if running else None,'runtime_dir':str(self.root)}

    def close(self):
        with self._lock:
            proc=self._proc
            if proc is None: return
            if proc.poll() is None:
                try:
                    self.request('/api/generate', {'model':MODEL,'prompt':'','stream':False,'keep_alive':0}, timeout=10)
                except Exception: pass
                proc.terminate()
                try: proc.wait(timeout=5)
                except subprocess.TimeoutExpired: proc.kill(); proc.wait(timeout=5)
            self._proc=None; self._port=None
            if self._log_handle is not None:
                self._log_handle.close(); self._log_handle=None


_RUNTIME = LocalAIRuntime()
def get_runtime():
    if not _RUNTIME.root.is_relative_to(Path(__file__).resolve().parents[1]):
        raise LocalAIError('Default runtime must stay inside Tool; external junctions are not supported')
    return _RUNTIME

import atexit
atexit.register(_RUNTIME.close)
