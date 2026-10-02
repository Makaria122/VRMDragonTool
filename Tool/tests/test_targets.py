import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from um.dragon_targets import get_target, target_ids, target_references
from um.dragon_textures import texture_namespace, TextureError


class TargetTests(unittest.TestCase):
    def test_existing_layouts_unchanged(self):
        self.assertEqual(get_target('yagami').bone_count, 358)
        self.assertEqual(len(get_target('yagami').slots), 3)
        self.assertEqual(get_target('kaito').bone_count, 285)
        self.assertEqual(get_target('kaito').slots[0].source_regions, ('tops', 'face', 'hair'))

    def test_all_targets_cover_avatar_once_with_real_slots(self):
        self.assertEqual(len(target_ids()), 14)
        for id in target_ids():
            target = get_target(id)
            self.assertGreater(target.bone_count, 0)
            self.assertEqual(target.slots[0].key, 'tops')
            self.assertEqual(sorted(r for s in target.slots for r in s.source_regions),
                             ['face', 'hair', 'tops'])
            self.assertEqual(len({s.stem for s in target.slots}), len(target.slots))
            with tempfile.TemporaryDirectory() as temp:
                refs = target_references(id, temp)
                self.assertEqual(set(refs), {'tops', 'face', 'hair'})
                self.assertTrue(all(Path(p).is_relative_to(Path(temp)) for p in refs.values()))
            for slot in target.slots:
                self.assertEqual(Path(target.reference_files[slot.reference_role]).stem, slot.stem)

    def test_paired_and_single_layouts_no_invented_hair_file(self):
        for id in ('sugiura', 'tsukumo', 'saori', 'higashi', 'kuwana'):
            target = get_target(id)
            self.assertEqual(len(target.slots), 2)
            self.assertEqual(target.slots[1].source_regions, ('face', 'hair'))
            self.assertEqual(target.reference_files['face'], target.reference_files['hair'])
        self.assertEqual(get_target('saori').bone_count, 211)
        self.assertEqual(len(get_target('mafuyu').slots), 3)
        for id in ('tesso', 'soma', 'akutsu', 'genda', 'hoshino', 'sawa'):
            self.assertEqual(len(get_target(id).slots), 1)

    def test_namespaces_distinct_for_same_vrm_across_all_targets(self):
        with tempfile.TemporaryDirectory() as temp:
            vrm = Path(temp) / 'same.vrm'
            vrm.write_bytes(b'same avatar bytes')
            namespaces = [texture_namespace(vrm, id) for id in target_ids()]
            self.assertEqual(len(set(namespaces)), len(namespaces))
            self.assertTrue(all(len(n + '_d00') <= 31 for n in namespaces))
            self.assertTrue(texture_namespace(vrm, 'yagami').startswith('v_y_'))
            self.assertTrue(texture_namespace(vrm, 'kaito').startswith('v_k_'))
            with self.assertRaises(TextureError):
                texture_namespace(vrm, 'unknown')
        with self.assertRaises(ValueError):
            get_target('unknown')


if __name__ == '__main__':
    unittest.main()
