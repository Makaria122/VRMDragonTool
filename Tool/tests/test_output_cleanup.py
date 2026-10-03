import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from um.dragon_output_cleanup import (CleanupError, delete_outputs, delete_working_blends,
                                      format_size, list_outputs)


def make_root(temp):
    root = Path(temp) / 'userdata' / 'outputs'
    root.mkdir(parents=True)
    return root


def run(root, name, blend=300, mod=40):
    folder = root / name
    (folder / 'Runs/a').mkdir(parents=True)
    (folder / 'Runs/a/source_reference.blend').write_bytes(b'b' * blend)
    (folder / 'Runs/a/source_reference.blend1').write_bytes(b'b' * blend)
    (folder / 'ReviewPack/Mods/x').mkdir(parents=True)
    (folder / 'ReviewPack/Mods/x/model.gmd').write_bytes(b'm' * mod)
    return folder


class OutputCleanupTests(unittest.TestCase):
    def test_lists_sizes_newest_first(self):
        with tempfile.TemporaryDirectory() as temp:
            root = make_root(temp)
            old = run(root, 'old'); new = run(root, 'new', blend=100)
            os.utime(old, (1000, 1000)); os.utime(new, (2000, 2000))
            rows = list_outputs(root)
            self.assertEqual([r['name'] for r in rows], ['new', 'old'])
            self.assertEqual(rows[0]['bytes'], 100 * 2 + 40)
            self.assertEqual(rows[0]['blend_bytes'], 200)

    def test_delete_removes_only_the_named_folders(self):
        with tempfile.TemporaryDirectory() as temp:
            root = make_root(temp)
            run(root, 'a'); run(root, 'b')
            result = delete_outputs(root, ['a'])
            self.assertEqual(result['deleted'], ['a'])
            self.assertEqual(result['freed_bytes'], 640)
            self.assertFalse((root / 'a').exists())
            self.assertTrue((root / 'b/ReviewPack/Mods/x/model.gmd').is_file())

    def test_blend_only_keeps_generated_mods(self):
        with tempfile.TemporaryDirectory() as temp:
            root = make_root(temp)
            run(root, 'a')
            result = delete_working_blends(root, ['a'])
            self.assertEqual(result['files_deleted'], 2)
            self.assertEqual(result['freed_bytes'], 600)
            self.assertTrue((root / 'a/ReviewPack/Mods/x/model.gmd').is_file())
            self.assertFalse(list((root / 'a').rglob('*.blend*')))

    def test_read_only_files_are_removed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = make_root(temp)
            folder = run(root, 'a')
            os.chmod(folder / 'ReviewPack/Mods/x/model.gmd', 0o444)
            self.assertEqual(delete_outputs(root, ['a'])['deleted'], ['a'])

    def test_path_tricks_are_rejected_and_nothing_outside_is_touched(self):
        with tempfile.TemporaryDirectory() as temp:
            root = make_root(temp)
            outside = Path(temp) / 'precious'; outside.mkdir()
            (outside / 'keep.txt').write_text('keep')
            run(root, 'a')
            for bad in ('..', '.', '', '../precious', '..\\precious', 'a/Runs', 'C:evil', 'missing'):
                result = delete_outputs(root, [bad])
                self.assertEqual(result['deleted'], [], bad)
                self.assertEqual(len(result['errors']), 1, bad)
            self.assertTrue((outside / 'keep.txt').is_file())
            self.assertTrue((root / 'a/Runs').is_dir())

    def test_a_link_to_another_folder_is_never_followed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = make_root(temp)
            outside = Path(temp) / 'precious'; outside.mkdir()
            (outside / 'keep.txt').write_text('keep')
            link = root / 'link'
            try:
                os.symlink(outside, link, target_is_directory=True)
            except (OSError, NotImplementedError):
                import subprocess
                made = os.name == 'nt' and subprocess.run(
                    ['cmd', '/c', 'mklink', '/J', str(link), str(outside)],
                    capture_output=True).returncode == 0
                if not made:
                    self.skipTest('neither symlinks nor junctions can be created here')
            self.assertNotIn('link', [r['name'] for r in list_outputs(root)])
            self.assertEqual(delete_outputs(root, ['link'])['deleted'], [])
            self.assertTrue((outside / 'keep.txt').is_file())

    def test_only_the_real_outputs_folder_is_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            other = Path(temp) / 'somewhere'
            other.mkdir()
            with self.assertRaises(CleanupError):
                list_outputs(other)
            with self.assertRaises(CleanupError):
                delete_outputs(other, ['x'])
            with self.assertRaises(CleanupError):
                list_outputs(Path(temp) / 'missing')

    def test_format_size(self):
        self.assertEqual(format_size(512), '512 B')
        self.assertEqual(format_size(5 * 1024 ** 3), '5.0 GB')


if __name__ == '__main__':
    unittest.main()
