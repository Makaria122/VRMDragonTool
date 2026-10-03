import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from um import dragon_custom_targets as custom
from um.dragon_custom_targets import CustomTargetError
from um.dragon_fit import BONE_MAP
from um.dragon_targets import get_target, target_references
from um.dragon_variants import availability, replacement_ownership, run_batch, variants_for

ALL_BONES = sorted(set(BONE_MAP.values()))


def parsed(count=297, bones=None, status='loaded', foot=None):
    return {'load_status': status, 'bone_names': list(ALL_BONES if bones is None else bones),
            'bone_count': count, 'warnings': [], 'foot_support': foot}


def make_tree(root):
    """A little extracted Chara folder with one character and some unrelated files."""
    names = {'tops': ['c_cm_x_ichiban', 'c_cm_x_ichiban_date', 'c_cm_x_ichiban_naked', 'c_cm_x_ichiban_hawaii',
                      'c_cm_x_kiryu'],
             'face': ['c_cm_f_ichiban', 'c_cm_f_ichiban_age23', 'c_cm_f_kiryu'],
             'hair': ['c_cm_h_ichiban', 'c_cm_h_ichiban11j', 'c_cm_h_ichiban_haire', 'c_cm_h_kiryu']}
    for role, stems in names.items():
        for stem in stems:
            path = Path(root) / role / stem / f'{stem}.gmd'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f'GMD {stem}'.encode())
    other = Path(root) / 'misc' / 'c_xx_ichiban_thing.gmd'
    other.parent.mkdir(parents=True)
    other.write_bytes(b'x')
    (Path(root) / 'tops' / 'c_cm_x_ichiban' / 'texture.dds').write_bytes(b'dds')
    return Path(root)


class ScanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = make_tree(Path(self.temp.name) / 'chara')

    def tearDown(self):
        self.temp.cleanup()

    def test_finds_every_part_of_the_character_and_nothing_else(self):
        found = custom.scan_character(self.root, 'Ichiban')
        self.assertEqual([(c['role'], c['stem']) for c in found], [
            ('tops', 'c_cm_x_ichiban'), ('tops', 'c_cm_x_ichiban_date'), ('tops', 'c_cm_x_ichiban_hawaii'),
            ('tops', 'c_cm_x_ichiban_naked'), ('face', 'c_cm_f_ichiban'), ('face', 'c_cm_f_ichiban_age23'),
            ('hair', 'c_cm_h_ichiban'), ('hair', 'c_cm_h_ichiban11j'), ('hair', 'c_cm_h_ichiban_haire'),
            ('other', 'c_xx_ichiban_thing')])

    def test_special_models_are_flagged_and_ordinary_ones_are_not(self):
        flags = {c['stem']: c['flags'] for c in custom.scan_character(self.root, 'ichiban')}
        self.assertEqual(flags['c_cm_x_ichiban_naked'], ['undressed model'])
        self.assertEqual(flags['c_cm_f_ichiban_age23'], ['different age'])
        self.assertEqual(flags['c_cm_x_ichiban_date'], [])
        for stem, reason in (('c_cm_x_ichiban_hawaii_sit', 'special pose'), ('c_cm_x_ichiban_swim_a', 'swimwear'),
                             ('c_cm_x_ichiban_suits_test', 'test model'), ('c_cm_x_ichiban_hwnaked', 'undressed model')):
            self.assertIn(reason, custom.special_flags(stem), stem)
        self.assertEqual(custom.special_flags('c_cm_x_ichiban_suits'), [])  # "suits" is not "sit"

    def test_bad_names_missing_folders_and_huge_results_are_refused(self):
        for bad in ('', 'a', 'ichi ban', '../x', 'x' * 41):
            with self.assertRaises(CustomTargetError, msg=bad):
                custom.scan_character(self.root, bad)
        with self.assertRaises(CustomTargetError):
            custom.scan_character(self.root / 'missing', 'ichiban')
        with self.assertRaises(CustomTargetError):
            custom.scan_character(self.root, 'ichiban', limit=3)

    def test_links_are_not_followed(self):
        outside = Path(self.temp.name) / 'outside'
        (outside / 'tops' / 'c_cm_x_ichiban_linked').mkdir(parents=True)
        (outside / 'tops' / 'c_cm_x_ichiban_linked' / 'c_cm_x_ichiban_linked.gmd').write_bytes(b'x')
        link = self.root / 'linked'
        try:
            os.symlink(outside, link, target_is_directory=True)
        except (OSError, NotImplementedError):
            import subprocess
            if not (os.name == 'nt' and subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(outside)],
                                                      capture_output=True).returncode == 0):
                self.skipTest('no links here')
        self.assertNotIn('c_cm_x_ichiban_linked', [c['stem'] for c in custom.scan_character(self.root, 'ichiban')])


class ClassifyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = make_tree(Path(self.temp.name) / 'chara')
        self.candidates = custom.scan_character(self.root, 'ichiban')
        self.inspections = {}
        for c in self.candidates:
            count = 303 if c['stem'].endswith('hawaii') else 297
            self.inspections[str(c['path'].resolve())] = parsed(count)
        broken = next(c for c in self.candidates if c['stem'] == 'c_cm_h_ichiban_haire')
        self.inspections[str(broken['path'].resolve())] = parsed(status='failed')
        custom.classify(self.candidates, self.inspections)
        self.by_stem = {c['stem']: c for c in self.candidates}

    def tearDown(self):
        self.temp.cleanup()

    def test_classification_marks_unusable_files_with_a_reason(self):
        self.assertTrue(self.by_stem['c_cm_x_ichiban_date']['ok'])
        self.assertFalse(self.by_stem['c_cm_h_ichiban_haire']['ok'])
        self.assertIn('could not be read', self.by_stem['c_cm_h_ichiban_haire']['reason'])
        self.assertFalse(self.by_stem['c_xx_ichiban_thing']['ok'])
        self.assertEqual(self.by_stem['c_cm_x_ichiban_hawaii']['bone_count'], 303)

    def test_a_body_model_without_feet_is_refused_but_a_hair_model_is_not(self):
        body = self.by_stem['c_cm_x_ichiban_date']['path']
        hair = self.by_stem['c_cm_h_ichiban11j']['path']
        self.inspections[str(body.resolve())] = parsed(foot=False)
        self.inspections[str(hair.resolve())] = parsed(foot=False)
        custom.classify(self.candidates, self.inspections)
        self.assertFalse(self.by_stem['c_cm_x_ichiban_date']['ok'])
        self.assertIn('without feet', self.by_stem['c_cm_x_ichiban_date']['reason'])
        self.assertTrue(self.by_stem['c_cm_h_ichiban11j']['ok'])
        self.inspections[str(body.resolve())] = parsed(foot=True)
        custom.classify(self.candidates, self.inspections)
        self.assertTrue(self.by_stem['c_cm_x_ichiban_date']['ok'])

    def test_a_skeleton_without_core_bones_is_not_ok(self):
        path = self.by_stem['c_cm_x_ichiban_date']['path']
        self.inspections[str(path.resolve())] = parsed(bones=[b for b in ALL_BONES if b != 'ketu_c_n'])
        custom.classify(self.candidates, self.inspections)
        self.assertFalse(self.by_stem['c_cm_x_ichiban_date']['ok'])
        self.assertIn('ketu_c_n', self.by_stem['c_cm_x_ichiban_date']['reason'])

    def test_base_is_the_plainest_name_of_the_commonest_skeleton_size(self):
        base = custom.suggest_base(self.candidates)
        self.assertEqual({r: c['stem'] for r, c in base.items()},
                         {'tops': 'c_cm_x_ichiban', 'face': 'c_cm_f_ichiban', 'hair': 'c_cm_h_ichiban'})

    def test_default_selection_leaves_out_special_and_broken_files(self):
        chosen = custom.default_selection(self.candidates, custom.suggest_base(self.candidates))
        self.assertIn('c_cm_x_ichiban_date', chosen)
        self.assertIn('c_cm_x_ichiban_hawaii', chosen)
        for stem in ('c_cm_x_ichiban_naked', 'c_cm_f_ichiban_age23', 'c_cm_h_ichiban_haire', 'c_xx_ichiban_thing'):
            self.assertNotIn(stem, chosen)

    def test_no_usable_body_means_no_base(self):
        for c in self.candidates:
            c['ok'] = False
        self.assertEqual(custom.suggest_base(self.candidates), {})


class GroupFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = make_tree(Path(self.temp.name) / 'chara')
        self.store = Path(self.temp.name) / 'targets'
        self.patch = patch('um.dragon_custom_targets.custom_dir', return_value=self.store)
        self.patch.start()
        self.candidates = custom.scan_character(self.root, 'ichiban')
        self.inspections = {str(c['path'].resolve()): parsed(303 if c['stem'].endswith('hawaii') else 297)
                            for c in self.candidates}
        broken = next(c for c in self.candidates if c['stem'] == 'c_cm_h_ichiban_haire')
        self.inspections[str(broken['path'].resolve())] = parsed(status='failed')
        custom.classify(self.candidates, self.inspections)
        self.base = custom.suggest_base(self.candidates)

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def register(self, selected=None, layout_roles=('tops', 'face', 'hair')):
        files = {role: self.base[role]['path'] for role in layout_roles}
        definition = custom.build_definition(files, {r: parsed() for r in files}, label='Ichiban')
        chosen = selected if selected is not None else [
            c for c in self.candidates if c['stem'] in custom.default_selection(self.candidates, self.base)]
        definition, skipped = custom.add_parts(definition, chosen)
        part_files = {c['stem']: c['path'] for c in self.candidates}
        saved = custom.import_and_save(definition, files, part_files=part_files)
        return saved, skipped


class GroupTests(GroupFixture):
    def test_parts_become_variants_and_skipped_ones_are_explained(self):
        saved, skipped = self.register()
        stems = [p['stem'] for p in saved['parts']]
        self.assertEqual(stems, ['c_cm_x_ichiban_date', 'c_cm_x_ichiban_hawaii', 'c_cm_h_ichiban11j'])
        self.assertEqual(skipped, [])
        self.assertTrue(all(p['sha256'] for p in saved['parts']))
        keys = variants_for('custom_c_cm_x_ichiban')
        self.assertEqual(keys[0], 'custom_c_cm_x_ichiban')
        self.assertEqual(len(keys), 4)
        self.assertEqual(get_target(keys[0]).custom_parts[0]['stem'], 'c_cm_x_ichiban_date')

    def test_a_tops_part_replaces_only_the_body_slot_with_its_own_bone_count(self):
        self.register()
        base = get_target('custom_c_cm_x_ichiban')
        date = get_target('custom_c_cm_x_ichiban__c_cm_x_ichiban_date')
        self.assertEqual([(s.key, s.stem, s.source_regions) for s in date.slots],
                         [('tops', 'c_cm_x_ichiban_date', ('tops',))])
        self.assertEqual((date.bone_count, date.rig_prefix), (297, 'c_cm_x_ichiban_date'))
        self.assertEqual(date.custom_references['face'], base.custom_references['face'])
        self.assertTrue(date.custom_references['tops'].endswith('c_cm_x_ichiban_date.gmd'))
        hawaii = get_target('custom_c_cm_x_ichiban__c_cm_x_ichiban_hawaii')
        self.assertEqual((hawaii.bone_count, hawaii.slot_bone_counts), (303, {'tops': 303}))

    def test_a_hair_part_replaces_only_the_hair_slot_and_keeps_the_base_skeleton(self):
        self.register()
        hair = get_target('custom_c_cm_x_ichiban__c_cm_h_ichiban11j')
        self.assertEqual([(s.key, s.region, s.stem, s.source_regions) for s in hair.slots],
                         [('hair', 'hair', 'c_cm_h_ichiban11j', ('hair',))])
        self.assertEqual(hair.bone_count, 297)
        self.assertEqual(hair.rig_prefix, 'c_cm_x_ichiban')
        self.assertTrue(hair.custom_references['hair'].endswith('c_cm_h_ichiban11j.gmd'))
        self.assertTrue(hair.custom_references['tops'].endswith('c_cm_x_ichiban.gmd'))

    def test_every_part_owns_a_different_game_file(self):
        self.register()
        keys = variants_for('custom_c_cm_x_ichiban')
        owners = replacement_ownership(keys)
        self.assertEqual(len(owners), 3 + 3)
        self.assertEqual(owners['chara/hair/c_cm_h_ichiban11j/c_cm_h_ichiban11j.gmd']['owner'],
                         'custom_c_cm_x_ichiban__c_cm_h_ichiban11j')
        self.assertEqual(owners['chara/tops/c_cm_x_ichiban/c_cm_x_ichiban.gmd']['owner'], 'custom_c_cm_x_ichiban')

    def test_single_gmd_and_body_face_characters_only_accept_fitting_parts(self):
        saved, skipped = self.register(layout_roles=('tops',))
        self.assertEqual([p['role'] for p in saved['parts']], ['tops', 'tops'])
        self.assertEqual({s['stem'] for s in skipped}, {'c_cm_f_ichiban', 'c_cm_h_ichiban', 'c_cm_h_ichiban11j'})
        single = get_target('custom_c_cm_x_ichiban__c_cm_x_ichiban_date')
        self.assertEqual(single.slots[0].source_regions, ('tops', 'face', 'hair'))
        self.assertEqual(len(set(single.custom_references.values())), 1)
        custom.delete_target('custom_c_cm_x_ichiban')
        saved, skipped = self.register(layout_roles=('tops', 'face'))
        self.assertEqual([p['stem'] for p in saved['parts']], ['c_cm_x_ichiban_date', 'c_cm_x_ichiban_hawaii'])
        self.assertEqual({s['stem'] for s in skipped}, {'c_cm_h_ichiban', 'c_cm_h_ichiban11j'})

    def test_hashes_of_parts_are_checked_on_every_use(self):
        self.register()
        key = 'custom_c_cm_x_ichiban__c_cm_x_ichiban_date'
        self.assertEqual(len(target_references(key)), 3)
        (self.store / 'custom_c_cm_x_ichiban' / 'c_cm_x_ichiban_date.gmd').write_bytes(b'tampered')
        with self.assertRaises(ValueError):
            target_references(key)

    def test_availability_lists_every_part_and_notices_a_missing_copy(self):
        self.register()
        rows = availability('custom_c_cm_x_ichiban')
        self.assertEqual([r['ready'] for r in rows], [True] * 4)
        (self.store / 'custom_c_cm_x_ichiban' / 'c_cm_h_ichiban11j.gmd').unlink()
        rows = availability('custom_c_cm_x_ichiban')
        self.assertEqual([r['ready'] for r in rows], [True, True, True, False])

    def test_unknown_part_and_old_definitions(self):
        self.register()
        with self.assertRaises(ValueError):
            get_target('custom_c_cm_x_ichiban__nothing')
        # a schema-1 definition (no parts) still loads and has no variants
        path = self.store / 'custom_c_cm_x_ichiban.json'
        data = json.loads(path.read_text(encoding='utf-8'))
        data['schema'] = 1
        data.pop('parts')
        path.write_text(json.dumps(data), encoding='utf-8')
        self.assertEqual(variants_for('custom_c_cm_x_ichiban'), ['custom_c_cm_x_ichiban'])

    def test_deleting_the_character_removes_all_copies(self):
        self.register()
        custom.delete_target('custom_c_cm_x_ichiban')
        self.assertFalse((self.store / 'custom_c_cm_x_ichiban').exists())
        self.assertEqual(list(self.store.glob('*.json')), [])

    def test_part_originals_must_be_given(self):
        files = {role: self.base[role]['path'] for role in custom.ROLES}
        definition = custom.build_definition(files, {r: parsed() for r in files})
        definition, _ = custom.add_parts(definition, [c for c in self.candidates if c['stem'] == 'c_cm_x_ichiban_date'])
        with self.assertRaises(CustomTargetError):
            custom.import_and_save(definition, files, part_files={})


class BatchTests(GroupFixture):
    """run_batch over a character group with a fake conversion (no Blender)."""

    def fake_run(self, calls, delay=0.0, fail=()):
        def run(vrm, refs, blender, addon, action, baseline, out, dummy, progress, target_id, profile_root,
                preparation_cache, profile_mode):
            calls.append((target_id, threading.current_thread().name))
            time.sleep(delay)
            out = Path(out)
            out.mkdir(parents=True)
            (out / 'source_reference.blend').write_bytes(b'b' * 100)
            (out / 'spatial_preview.blend1').write_bytes(b'b' * 100)
            if target_id in fail:
                raise ValueError('boom ' + target_id)
            mod = out / 'ReviewPack' / 'Mods' / 'fake'
            (mod / 'chara' / 'dds_hires' / '00').mkdir(parents=True)
            (mod / 'mod-meta.yaml').write_text('name: Test\n', encoding='utf-8')
            (mod / 'chara' / 'dds_hires' / '00' / 'same.dds').write_bytes(b'DDS identical')
            for slot in get_target(target_id).slots:
                gmd = mod / 'chara' / slot.region / slot.stem / f'{slot.stem}.gmd'
                gmd.parent.mkdir(parents=True, exist_ok=True)
                gmd.write_bytes(target_id.encode())
            return {'mod_folder': str(mod), 'candidate_status': 'MOTION_NOT_RUN'}
        return run

    def run_it(self, run, **kwargs):
        self.register()
        out = Path(self.temp.name) / 'batch'
        with patch('um.dragon_oneclick.run', side_effect=run):
            result = run_batch('vrm', target_references('custom_c_cm_x_ichiban'), 'b', 'a', None, None, out, None,
                               target_id='custom_c_cm_x_ichiban', source_root=None, **kwargs)
        return out, result

    def test_every_part_ends_up_in_one_combined_mod(self):
        calls = []
        out, result = self.run_it(self.fake_run(calls))
        gmds = sorted(p.relative_to(result['mod_folder']).as_posix() for p in Path(result['mod_folder']).rglob('*.gmd'))
        self.assertEqual(len(gmds), 6)
        self.assertIn('chara/hair/c_cm_h_ichiban11j/c_cm_h_ichiban11j.gmd', gmds)
        self.assertEqual([v['id'] for v in result['variants']], variants_for('custom_c_cm_x_ichiban'))
        self.assertEqual(calls[0][0], 'custom_c_cm_x_ichiban')  # the base model is converted first

    def test_parallel_workers_run_at_the_same_time_and_keep_the_report_order(self):
        calls = []
        out, result = self.run_it(self.fake_run(calls, delay=0.3), workers=3)
        threads = {name for _, name in calls[1:]}
        self.assertGreater(len(threads), 1)
        self.assertEqual([v['id'] for v in result['variants']], variants_for('custom_c_cm_x_ichiban'))
        self.assertEqual(len(list(Path(result['mod_folder']).rglob('*.gmd'))), 6)

    def test_one_failing_part_does_not_stop_the_others_in_parallel(self):
        calls = []
        bad = 'custom_c_cm_x_ichiban__c_cm_x_ichiban_hawaii'
        out, result = self.run_it(self.fake_run(calls, fail=(bad,)), workers=3)
        self.assertEqual(result['status'], 'VARIANT_PACK_PARTIAL')
        self.assertEqual([f['id'] for f in result['failed_variants']], [bad])
        self.assertEqual(len(result['variants']), 3)

    def test_working_blend_files_are_deleted_when_cleanup_is_on(self):
        calls = []
        out, result = self.run_it(self.fake_run(calls), cleanup_working_files=True)
        self.assertEqual(list((out / 'Runs').rglob('*.blend*')), [])
        self.assertEqual(len(list(Path(result['mod_folder']).rglob('*.gmd'))), 6)

    def test_intermediate_outputs_are_removed_as_the_batch_goes_but_the_mod_stays(self):
        calls = []
        out, result = self.run_it(self.fake_run(calls), cleanup_working_files=True)
        for run in (out / 'Runs').iterdir():
            for name in ('textures', 'Candidate', 'ReviewPack', 'neutral_maps'):
                self.assertFalse((run / name).exists(), f'{run.name}/{name}')
        self.assertFalse((out / 'OwnedPayloads').exists())
        self.assertEqual(len(list(Path(result['mod_folder']).rglob('*.gmd'))), 6)
        self.assertTrue((Path(result['mod_folder']) / 'mod-meta.yaml').is_file())

    def test_a_single_surviving_model_still_leaves_a_usable_mod_after_cleanup(self):
        calls = []
        keys = variants_for('custom_c_cm_x_ichiban') if False else None
        self.register()
        fail = tuple(k for k in variants_for('custom_c_cm_x_ichiban') if k != 'custom_c_cm_x_ichiban')
        out = Path(self.temp.name) / 'batch2'
        with patch('um.dragon_oneclick.run', side_effect=self.fake_run(calls, fail=fail)):
            result = run_batch('vrm', target_references('custom_c_cm_x_ichiban'), 'b', 'a', None, None, out, None,
                               target_id='custom_c_cm_x_ichiban', source_root=None, cleanup_working_files=True)
        self.assertEqual(result['status'], 'VARIANT_PACK_PARTIAL')
        mod = Path(result['mod_folder'])
        self.assertTrue(mod.is_dir())
        self.assertEqual(len(list(mod.rglob('*.gmd'))), 3)

    def test_working_blend_files_are_kept_for_small_batches_by_default(self):
        calls = []
        out, _ = self.run_it(self.fake_run(calls))
        self.assertGreater(len(list((out / 'Runs').rglob('*.blend'))), 0)


if __name__ == '__main__':
    unittest.main()
