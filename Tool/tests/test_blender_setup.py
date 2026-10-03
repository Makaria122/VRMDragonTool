import hashlib
import io
import stat
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from um import dragon_blender_setup as setup
from um.dragon_blender_setup import BlenderInstaller, BlenderSetupError

TOP = 'blender-9.9.9-windows-x64'


def make_zip(entries=None, symlink=None):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as bundle:
        for name, data in (entries if entries is not None else
                           {f'{TOP}/blender.exe': b'MZ fake exe', f'{TOP}/9.9/scripts/x.py': b'x'}).items():
            bundle.writestr(name, data)
        if symlink:
            info = zipfile.ZipInfo(symlink)
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            bundle.writestr(info, 'target')
    return buffer.getvalue()


class FakeResponse(io.BytesIO):
    def __init__(self, data, url, length=None):
        super().__init__(data)
        self._url = url
        self.headers = {'Content-Length': str(len(data) if length is None else length)}

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class BlenderSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'runtime'
        self.root.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def installer(self, data=None, *, sha=None, length=None, final_url=None, free=10 ** 11,
                  runner=None, size=None):
        data = make_zip() if data is None else data
        url = 'https://download.blender.org/release/x/blender.zip'
        self.opened = []

        def opener(request):
            self.opened.append(request.full_url)
            return FakeResponse(data, final_url or url, length)

        def default_runner(command, timeout):
            return SimpleNamespace(returncode=0, stdout='Blender 9.9.9\n', stderr='')

        return BlenderInstaller(
            self.root, url=url, sha256=sha or hashlib.sha256(data).hexdigest(),
            size=len(data) if size is None else size, top_folder=TOP, version='9.9.9', opener=opener,
            runner=runner or default_runner, disk_free=lambda path: free)

    def leftovers(self):
        return sorted(p.name for p in self.root.iterdir())

    def test_installs_verifies_and_leaves_nothing_behind(self):
        installer = self.installer()
        events = []
        exe = installer.install(progress=events.append)
        self.assertEqual(exe, self.root / 'blender' / 'blender.exe')
        self.assertTrue((self.root / 'blender' / '9.9' / 'scripts' / 'x.py').is_file())
        self.assertEqual(self.leftovers(), ['blender'])
        self.assertTrue(installer.status()['installed'])
        self.assertEqual(installer.status()['installed_version'], '9.9.9')
        downloads = [e['current'] for e in events if e['message'].startswith('Downloading') and e['current']]
        self.assertEqual(downloads, sorted(downloads))
        self.assertEqual(events[-1]['message'], 'Blender 9.9.9 is ready')

    def test_second_call_does_not_download_again(self):
        installer = self.installer()
        installer.install()
        installer.install()
        self.assertEqual(len(self.opened), 1)

    def test_hash_mismatch_is_discarded(self):
        installer = self.installer(sha='0' * 64)
        with self.assertRaises(BlenderSetupError) as ctx:
            installer.install()
        self.assertIn('SHA-256', str(ctx.exception))
        self.assertEqual(self.leftovers(), [])

    def test_wrong_advertised_size_is_refused_before_reading(self):
        installer = self.installer(length=123)
        with self.assertRaises(BlenderSetupError):
            installer.install()
        self.assertEqual(self.leftovers(), [])

    def test_truncated_download_is_refused(self):
        data = make_zip()
        installer = self.installer(data, size=len(data) + 50, length=len(data) + 50)
        with self.assertRaises(BlenderSetupError) as ctx:
            installer.install()
        self.assertIn('Incomplete', str(ctx.exception))

    def test_redirect_to_another_host_is_refused(self):
        installer = self.installer(final_url='https://evil.example.com/blender.zip')
        with self.assertRaises(BlenderSetupError):
            installer.install()
        self.assertEqual(self.leftovers(), [])

    def test_only_the_official_https_host_is_accepted(self):
        for url in ('http://download.blender.org/x.zip', 'https://example.com/x.zip',
                    'https://download.blender.org.evil.com/x.zip'):
            installer = BlenderInstaller(self.root, url=url, sha256='0' * 64, size=1,
                                         disk_free=lambda p: 10 ** 11,
                                         opener=lambda r: self.fail('must not connect'))
            with self.assertRaises(BlenderSetupError):
                installer.install()

    def test_unsafe_archive_entries_are_rejected(self):
        for bad in ('../evil.txt', f'{TOP}/../../evil.txt', '/abs/evil.txt', 'C:/evil.txt'):
            installer = self.installer(make_zip({f'{TOP}/blender.exe': b'x', bad: b'evil'}))
            with self.assertRaises(BlenderSetupError, msg=bad):
                installer.install()
            self.assertEqual(self.leftovers(), [], bad)
            self.assertFalse((self.root.parent / 'evil.txt').exists())

    def test_symlink_entries_are_rejected(self):
        installer = self.installer(make_zip(symlink=f'{TOP}/link'))
        with self.assertRaises(BlenderSetupError):
            installer.install()
        self.assertEqual(self.leftovers(), [])

    def test_archive_without_blender_exe_is_rejected(self):
        installer = self.installer(make_zip({f'{TOP}/readme.txt': b'x'}))
        with self.assertRaises(BlenderSetupError):
            installer.install()
        self.assertEqual(self.leftovers(), [])

    def test_oversized_expansion_is_rejected(self):
        original = setup.MAX_EXPANDED
        setup.MAX_EXPANDED = 5
        try:
            installer = self.installer()
            with self.assertRaises(BlenderSetupError):
                installer.install()
        finally:
            setup.MAX_EXPANDED = original

    def test_not_enough_disk_space_stops_before_downloading(self):
        installer = self.installer(free=1000)
        with self.assertRaises(BlenderSetupError) as ctx:
            installer.install()
        self.assertIn('disk space', str(ctx.exception))
        self.assertEqual(self.opened, [])

    def test_cancel_cleans_up(self):
        installer = self.installer()
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(BlenderSetupError) as ctx:
            installer.install(cancel=cancel)
        self.assertIn('Cancelled', str(ctx.exception))
        self.assertEqual(self.leftovers(), [])

    def test_blender_that_does_not_start_is_removed(self):
        def broken(command, timeout):
            return SimpleNamespace(returncode=1, stdout='', stderr='boom')
        installer = self.installer(runner=broken)
        with self.assertRaises(BlenderSetupError):
            installer.install()
        self.assertEqual(self.leftovers(), [])
        self.assertFalse(installer.installed())

    def test_wrong_version_output_is_removed(self):
        def other(command, timeout):
            return SimpleNamespace(returncode=0, stdout='Blender 3.0.0', stderr='')
        installer = self.installer(runner=other)
        with self.assertRaises(BlenderSetupError):
            installer.install()
        self.assertFalse(installer.installed())

    def test_existing_foreign_folder_is_never_overwritten(self):
        target = self.root / 'blender'
        target.mkdir()
        (target / 'mine.txt').write_text('keep')
        installer = self.installer()
        with self.assertRaises(BlenderSetupError):
            installer.install()
        self.assertEqual((target / 'mine.txt').read_text(), 'keep')
        self.assertEqual(self.opened, [])

    def test_empty_existing_folder_is_fine(self):
        (self.root / 'blender').mkdir()
        self.installer().install()
        self.assertTrue((self.root / 'blender' / 'blender.exe').is_file())

    def test_leftovers_of_a_crashed_attempt_are_cleaned(self):
        (self.root / 'blender-staging').mkdir()
        (self.root / 'blender-staging' / 'junk').write_text('x')
        (self.root / 'blender-download.zip.part').write_bytes(b'partial')
        self.installer().install()
        self.assertEqual(self.leftovers(), ['blender'])

    def test_pinned_constants_are_consistent(self):
        self.assertEqual(len(setup.BLENDER_SHA256), 64)
        self.assertTrue(setup.BLENDER_URL.endswith(f'blender-{setup.BLENDER_VERSION}-windows-x64.zip'))
        self.assertEqual(setup.TOP_FOLDER, f'blender-{setup.BLENDER_VERSION}-windows-x64')
        self.assertEqual(setup.BLENDER_URL.split('/')[2], setup.ALLOWED_HOST)


if __name__ == '__main__':
    unittest.main()
