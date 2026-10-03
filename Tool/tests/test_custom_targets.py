import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from um import dragon_custom_targets as custom
from um.dragon_custom_targets import CustomTargetError
from um.dragon_fit import BONE_MAP
from um.dragon_targets import get_target, target_ids, target_references

ALL_BONES = sorted(set(BONE_MAP.values()))


def inspection(bones=None, count=297, status='loaded', warnings=None):
    return {'load_status': status, 'bone_names': list(ALL_BONES if bones is None else bones),
            'bone_count': count, 'warnings': warnings or []}


def files_for(root, name='c_cm_x_ichiban', roles=('tops', 'face', 'hair')):
    letters = {'tops': 'x', 'face': 'f', 'hair': 'h'}
    result = {}
    for role in roles:
        stem = name.replace('_x_', f'_{letters[role]}_', 1)
        path = Path(root) / role / stem / f'{stem}.gmd'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f'GMD {stem}'.encode())
        result[role] = path
    return result


class DefinitionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def build(self, roles=('tops', 'face', 'hair'), **kwargs):
        files = files_for(self.root / 'src', roles=roles)
        return files, custom.build_definition(files, {r: inspection() for r in roles}, **kwargs)

    def test_three_gmd_character_becomes_a_three_slot_target(self):
        files, definition = self.build()
        self.assertEqual(definition['id'], 'custom_c_cm_x_ichiban')
        self.assertEqual((definition['bone_count'], definition['layout'], definition['rig_prefix']),
                         (297, 'tops+face+hair', 'c_cm_x_ichiban'))
        target = custom.to_target(definition, self.root / 'store')
        self.assertEqual([(s.key, s.region, s.stem, s.source_regions) for s in target.slots],
                         [('tops', 'tops', 'c_cm_x_ichiban', ('tops',)),
                          ('face', 'face', 'c_cm_f_ichiban', ('face',)),
                          ('hair', 'hair', 'c_cm_h_ichiban', ('hair',))])

    def test_tops_only_becomes_a_single_gmd_target(self):
        _, definition = self.build(roles=('tops',))
        target = custom.to_target(definition, self.root / 'store')
        self.assertEqual(len(target.slots), 1)
        self.assertEqual(target.slots[0].source_regions, ('tops', 'face', 'hair'))
        self.assertEqual(len(set(target.custom_references.values())), 1)

    def test_tops_and_face_puts_hair_into_the_face_gmd(self):
        _, definition = self.build(roles=('tops', 'face'))
        target = custom.to_target(definition, self.root / 'store')
        self.assertEqual([s.source_regions for s in target.slots], [('tops',), ('face', 'hair')])
        self.assertEqual(target.custom_references['hair'], target.custom_references['face'])

    def test_missing_core_bones_are_refused_with_the_names(self):
        files = files_for(self.root / 'src')
        bones = [b for b in ALL_BONES if b not in ('ketu_c_n', 'asi3_l_n')]
        with self.assertRaises(CustomTargetError) as ctx:
            custom.build_definition(files, {'tops': inspection(bones), 'face': inspection(), 'hair': inspection()})
        self.assertIn('ketu_c_n', str(ctx.exception))

    def test_missing_fingers_only_warn(self):
        files = files_for(self.root / 'src', roles=('tops',))
        no_fingers = [b for b in ALL_BONES if b not in
                      [bone for role, bone in BONE_MAP.items() if any(w in role for w in custom.FINGER_WORDS)]]
        definition = custom.build_definition(files, {'tops': inspection(no_fingers)})
        self.assertTrue(any('finger bones are missing' in w for w in definition['warnings']))

    def test_differing_bone_counts_unreadable_files_and_odd_names_are_refused(self):
        files = files_for(self.root / 'src')
        with self.assertRaises(CustomTargetError):
            custom.build_definition(files, {'tops': inspection(), 'face': inspection(count=300), 'hair': inspection()})
        with self.assertRaises(CustomTargetError):
            custom.build_definition(files, {'tops': inspection(), 'face': inspection(status='failed'), 'hair': inspection()})
        with self.assertRaises(CustomTargetError):
            custom.build_definition({'face': files['face']}, {'face': inspection()})
        odd = self.root / 'src' / 'tops' / 'bad name!' / 'bad name!.gmd'
        odd.parent.mkdir(parents=True)
        odd.write_bytes(b'x')
        with self.assertRaises(CustomTargetError):
            custom.build_definition({'tops': odd}, {'tops': inspection()})

    def test_ids_are_clean_and_never_contain_double_underscores(self):
        self.assertEqual(custom.sanitize_id('My Hero__v2!'), 'custom_my_hero_v2')
        self.assertNotIn('__', custom.sanitize_id('a___b'))
        with self.assertRaises(CustomTargetError):
            custom.sanitize_id('!!!')

    def test_siblings_are_found_in_the_dragon_engine_layout(self):
        files = files_for(self.root / 'extracted')
        found = custom.find_siblings(files['tops'])
        self.assertEqual({k: v.name for k, v in found.items()}, {'face': 'c_cm_f_ichiban.gmd', 'hair': 'c_cm_h_ichiban.gmd'})
        self.assertEqual(custom.find_siblings(self.root / 'loose.gmd'), {})


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = self.root / 'targets'
        self.files = files_for(self.root / 'src')
        self.definition = custom.build_definition(self.files, {r: inspection() for r in self.files})
        self.patch = patch('um.dragon_custom_targets.custom_dir', return_value=self.store)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def register(self, **kwargs):
        return custom.import_and_save(self.definition, self.files, **kwargs)

    def test_import_copies_the_files_and_the_target_is_usable_everywhere(self):
        saved = self.register()
        self.assertEqual(set(saved['sha256']), {'tops', 'face', 'hair'})
        self.assertTrue((self.store / 'custom_c_cm_x_ichiban' / 'c_cm_x_ichiban.gmd').is_file())
        self.assertIn('custom_c_cm_x_ichiban', target_ids())
        target = get_target('custom_c_cm_x_ichiban')
        self.assertEqual(target.bone_count, 297)
        refs = target_references('custom_c_cm_x_ichiban')
        self.assertTrue(all(Path(p).is_file() for p in refs.values()))
        self.assertTrue(all(self.store in Path(p).parents for p in refs.values()))
        self.assertEqual(target_references('custom_c_cm_x_ichiban', source_root=self.root), refs)

    def test_originals_are_only_read_never_changed(self):
        before = {k: v.read_bytes() for k, v in self.files.items()}
        self.register()
        self.assertEqual({k: v.read_bytes() for k, v in self.files.items()}, before)

    def test_a_changed_or_missing_private_copy_is_detected(self):
        self.register()
        copy = self.store / 'custom_c_cm_x_ichiban' / 'c_cm_x_ichiban.gmd'
        copy.write_bytes(b'tampered')
        with self.assertRaises(ValueError) as ctx:
            target_references('custom_c_cm_x_ichiban')
        self.assertIn('changed', str(ctx.exception))
        copy.unlink()
        with self.assertRaises(ValueError):
            target_references('custom_c_cm_x_ichiban')

    def test_existing_target_is_not_overwritten_unless_asked(self):
        self.register()
        with self.assertRaises(CustomTargetError):
            self.register()
        self.files['tops'].write_bytes(b'new version')
        self.register(replace=True)
        self.assertEqual((self.store / 'custom_c_cm_x_ichiban' / 'c_cm_x_ichiban.gmd').read_bytes(), b'new version')
        self.assertEqual(len(list(self.store.glob('.import_*'))), 0)

    def test_unknown_or_malicious_ids_are_rejected(self):
        for bad in ('custom_../x', 'custom_a__b', 'yagami', 'custom_UPPER', 'custom_'):
            with self.assertRaises((ValueError, CustomTargetError), msg=bad):
                get_target(bad) if bad.startswith('custom_') and '__' not in bad else custom.load_definition(bad)

    def test_delete_removes_only_that_target(self):
        self.register()
        other = self.root / 'precious.txt'
        other.write_text('keep')
        custom.delete_target('custom_c_cm_x_ichiban')
        self.assertFalse((self.store / 'custom_c_cm_x_ichiban').exists())
        self.assertFalse((self.store / 'custom_c_cm_x_ichiban.json').exists())
        self.assertEqual(other.read_text(), 'keep')
        self.assertNotIn('custom_c_cm_x_ichiban', target_ids())
        with self.assertRaises(CustomTargetError):
            custom.delete_target('../precious')

    def test_texture_namespace_is_distinct_per_custom_target(self):
        from um.dragon_textures import texture_namespace
        self.register()
        other = custom.build_definition(files_for(self.root / 'src2', name='c_cm_x_other'),
                                        {r: inspection() for r in ('tops', 'face', 'hair')})
        custom.import_and_save(other, files_for(self.root / 'src2', name='c_cm_x_other'))
        vrm = self.root / 'a.vrm'
        vrm.write_bytes(b'avatar')
        a = texture_namespace(vrm, 'custom_c_cm_x_ichiban')
        b = texture_namespace(vrm, 'custom_c_cm_x_other')
        self.assertNotEqual(a, b)
        self.assertNotEqual(a, texture_namespace(vrm, 'yagami'))
        self.assertLess(len(a), 28)

    def test_availability_uses_the_private_copies_not_the_chara_folder(self):
        from um.dragon_variants import availability, variants_for
        self.register()
        self.assertEqual(variants_for('custom_c_cm_x_ichiban'), ['custom_c_cm_x_ichiban'])
        rows = availability('custom_c_cm_x_ichiban', source_root=self.root / 'unrelated')
        self.assertTrue(rows[0]['ready'])


class InspectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.blender = self.root / 'blender.exe'
        self.blender.write_bytes(b'x')

    def tearDown(self):
        self.temp.cleanup()

    def fake_runner(self, results):
        def run(command, label, timeout):
            job = json.loads(Path(command[-1]).read_text(encoding='utf-8'))
            if results is not None:
                parsed = [dict(results[e['region']], absolute_path=e['absolute_path']) for e in job['files']]
                Path(job['output']).write_text(json.dumps(parsed), encoding='utf-8')
            return SimpleNamespace(returncode=0 if results is not None else 1, stdout='', stderr='Error: boom')
        return run

    def test_results_are_matched_back_to_the_roles(self):
        files = files_for(self.root / 'src')
        runner = self.fake_runner({r: inspection(count=i) for i, r in enumerate(files, 1)})
        out = custom.inspect_files(files, self.blender, self.root, runner=runner)
        self.assertEqual({r: v['bone_count'] for r, v in out.items()}, {'tops': 1, 'face': 2, 'hair': 3})

    def test_a_blender_failure_is_reported_with_its_error_lines(self):
        files = files_for(self.root / 'src', roles=('tops',))
        with self.assertRaises(CustomTargetError) as ctx:
            custom.inspect_files(files, self.blender, self.root, runner=self.fake_runner(None))
        self.assertIn('boom', str(ctx.exception))

    def test_missing_blender_and_non_gmd_files_are_refused(self):
        files = files_for(self.root / 'src', roles=('tops',))
        with self.assertRaises(CustomTargetError):
            custom.inspect_files(files, self.root / 'nope.exe', self.root, runner=self.fake_runner({}))
        notgmd = self.root / 'a.txt'
        notgmd.write_text('x')
        with self.assertRaises(CustomTargetError):
            custom.inspect_files({'tops': notgmd}, self.blender, self.root, runner=self.fake_runner({}))


if __name__ == '__main__':
    unittest.main()
