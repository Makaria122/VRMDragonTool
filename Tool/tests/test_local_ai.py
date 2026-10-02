import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from um.dragon_local_ai import LocalAIRuntime, LocalAIError


class FakeProcess:
    def __init__(self, *args, **kwargs):
        self.args, self.kwargs, self.dead = args, kwargs, False
    def poll(self): return 1 if self.dead else None
    def terminate(self): self.dead = True
    def wait(self, timeout=None): return 0


class LocalAIRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.rt = LocalAIRuntime(Path(self.tmp.name))
    def tearDown(self):
        with patch.object(self.rt,'request'):self.rt.close()
        self.tmp.cleanup()

    def test_environment_isolated_and_portable_path(self):
        self.rt._port = 43210
        with patch.dict('os.environ', {'OLLAMA_HOST':'localhost:11434','OLLAMA_MODELS':'C:/global','PATH':'global'}):
            env = self.rt._environment()
        self.assertEqual(env['OLLAMA_HOST'], '127.0.0.1:43210')
        self.assertEqual(Path(env['OLLAMA_MODELS']), self.rt.models)
        self.assertNotEqual(env['PATH'], 'global')
        self.assertNotIn('OLLAMA_ORIGINS', env)

    def test_never_accepts_non_api_route_or_unstarted(self):
        with self.assertRaises(ValueError): self.rt.request('http://127.0.0.1:11434/api/chat')
        with self.assertRaises(LocalAIError): self.rt.request('/api/chat')

    def test_owned_process_lifecycle_and_unload(self):
        self.rt.ollama_dir.mkdir(parents=True); self.rt.executable.touch()
        process = FakeProcess()
        with patch('um.dragon_local_ai.socket.socket') as sock, \
             patch('um.dragon_local_ai.subprocess.Popen', return_value=process) as popen, \
             patch.object(self.rt, '_wait_ready', return_value=True), \
             patch.object(self.rt, 'request', return_value={'models':[]}):
            sock.return_value.__enter__ = lambda s: s
            sock.return_value.bind = lambda addr: None
            sock.return_value.getsockname.return_value = ('127.0.0.1', 42001)
            sock.return_value.close = lambda: None
            self.rt.setup()
        args=popen.call_args.args[0]
        self.assertEqual(args[0], str(self.rt.executable)); self.assertEqual(args[1], 'serve')
        self.assertIn('127.0.0.1:42001', popen.call_args.kwargs['env']['OLLAMA_HOST'])
        with patch.object(self.rt, 'request') as request:
            self.rt.close()
            self.assertEqual(request.call_args.args[0], '/api/generate')
            self.assertEqual(request.call_args.args[1]['keep_alive'], 0)
        self.assertTrue(process.dead)

    def test_no_automatic_download_without_explicit_install(self):
        with patch.object(self.rt,'_install') as installer:
            with self.assertRaises(LocalAIError):self.rt.setup()
            installer.assert_not_called()

    def test_archive_traversal_refused(self):
        zpath=Path(self.tmp.name)/'bad.zip'
        with zipfile.ZipFile(zpath,'w') as z: z.writestr('../outside','bad')
        with self.assertRaises(LocalAIError): LocalAIRuntime._extract_safe(zpath, Path(self.tmp.name)/'extract')

    def test_request_uses_private_ephemeral_endpoint(self):
        self.rt._port=41234; self.rt._proc=FakeProcess()
        with patch.object(self.rt._opener, 'open') as open_url:
            open_url.return_value.__enter__.return_value.read.return_value=json.dumps({'ok':True}).encode()
            self.assertEqual(self.rt.request('/api/chat', {'x':1}), {'ok':True})
            self.assertTrue(open_url.call_args.args[0].full_url.startswith('http://127.0.0.1:41234/'))


if __name__ == '__main__': unittest.main()
