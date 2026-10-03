import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from um.dragon_local_profile import (LocalProfileError, create, create_deterministic,
                                     DETERMINISTIC_METHOD)
from um.dragon_profile_workflow import load_cached_profile, reference_hashes, role_mappings


def mesh(name, region, reason='x'):
    return {'object': name, 'region': region, 'reason': reason, 'materials': [],
            'vertices': 10, 'faces': 8, 'min_z_m': 0.0, 'max_z_m': 1.0, 'unweighted_vertices': 0}


def fixture(unknown=('Ribbon',), regions=('tops', 'face', 'hair', None), parents=None):
    names = ['Body', 'Face', 'Hair', 'Acc'][:len(regions)]
    inventory = {
        'meshes': [mesh(n, r) for n, r in zip(names, regions)],
        'ground_alignment': {'measured_correction_m': 0.02},
        'foot_alignment': [],
        'unknown_weight_groups': list(unknown),
        'source_bone_parents': parents if parents is not None else {
            'Ribbon': 'Ribbon.Root', 'Ribbon.Root': 'Head', 'Head': 'Hips', 'Hips': None}}
    fit_plan = {'matched_roles': [{'role': 'head', 'source_bone': 'Head', 'target_bone': 'face_c_n'},
                                  {'role': 'hips', 'source_bone': 'Hips', 'target_bone': 'ketu_c_n'}],
                'accessory_parent_hints': []}
    return inventory, fit_plan


class DeterministicProfileTests(unittest.TestCase):
    def test_regions_follow_inventory_and_ambiguous_becomes_tops(self):
        inventory, fit_plan = fixture()
        with tempfile.TemporaryDirectory() as temp:
            result = create_deterministic(inventory, fit_plan, Path(temp) / 'p.json')
            self.assertEqual(result['mesh_regions'],
                             {'Body': 'tops', 'Face': 'face', 'Hair': 'hair', 'Acc': 'tops'})
            self.assertEqual(result['profile_method'], DETERMINISTIC_METHOD)
            self.assertEqual(result['ground_alignment']['local_ai_action'], 'raise')
            self.assertTrue((Path(temp) / 'p.json').is_file())

    def test_unmatched_group_follows_nearest_matched_ancestor(self):
        inventory, fit_plan = fixture()
        with tempfile.TemporaryDirectory() as temp:
            result = create_deterministic(inventory, fit_plan, Path(temp) / 'p.json')
        self.assertEqual(result['accessory_parent_hints'],
                         [{'source_group': 'Ribbon', 'suggested_target': 'face_c_n'}])

    def test_unresolvable_group_stops_with_detailed_mode_hint(self):
        inventory, fit_plan = fixture(parents={'Ribbon': None})
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(LocalProfileError) as ctx:
                create_deterministic(inventory, fit_plan, Path(temp) / 'p.json')
            self.assertIn('詳細モード', str(ctx.exception))
            self.assertFalse((Path(temp) / 'p.json').exists())

    def test_inventory_without_parents_only_fails_when_a_group_needs_them(self):
        inventory, fit_plan = fixture(unknown=(), parents={})
        inventory.pop('source_bone_parents')
        with tempfile.TemporaryDirectory() as temp:
            create_deterministic(inventory, fit_plan, Path(temp) / 'p.json')
        inventory, fit_plan = fixture()
        inventory.pop('source_bone_parents')
        with tempfile.TemporaryDirectory() as temp, self.assertRaises(LocalProfileError):
            create_deterministic(inventory, fit_plan, Path(temp) / 'p.json')

    def test_missing_required_region_stops_with_detailed_mode_hint(self):
        inventory, fit_plan = fixture(unknown=(), regions=('tops', 'face', 'tops'))
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(LocalProfileError) as ctx:
                create_deterministic(inventory, fit_plan, Path(temp) / 'p.json')
            self.assertIn('詳細モード', str(ctx.exception))

    def test_simple_mode_never_touches_the_local_ai(self):
        inventory, fit_plan = fixture()
        with tempfile.TemporaryDirectory() as temp, patch('um.dragon_local_ai.get_runtime') as runtime:
            create(inventory, fit_plan, Path(temp) / 'p.json', 'simple')
            runtime.assert_not_called()

    def test_unknown_mode_is_rejected(self):
        inventory, fit_plan = fixture()
        with tempfile.TemporaryDirectory() as temp, self.assertRaises(LocalProfileError):
            create(inventory, fit_plan, Path(temp) / 'p.json', 'turbo')

    def test_detailed_mode_does_not_reuse_a_rule_profile(self):
        inventory, fit_plan = fixture()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            vrm = root / 'a.vrm'; vrm.write_bytes(b'avatar')
            ref = root / 'ref.gmd'; ref.write_bytes(b'ref')
            refs = {'tops': ref, 'face': ref, 'hair': ref}
            result = create_deterministic(inventory, fit_plan, root / 'p.json')
            from um.dragon_beta import _digest
            from um.dragon_profile_workflow import profile_directory
            result.update({'target_id': 'yagami', 'source_vrm_sha256': _digest(vrm),
                           'source_references': reference_hashes(refs),
                           'source_role_mappings': role_mappings(fit_plan)})
            folder = profile_directory(vrm, root / 'Profiles', 'yagami')
            folder.mkdir(parents=True)
            (folder / 'avatar-profile_1.json').write_text(json.dumps(result), encoding='utf-8')
            simple = load_cached_profile(vrm, refs, inventory, fit_plan, root / 'Profiles', 'yagami')
            detailed = load_cached_profile(vrm, refs, inventory, fit_plan, root / 'Profiles', 'yagami',
                                           require_ai=True)
            self.assertIsNotNone(simple)
            self.assertIsNone(detailed)


if __name__ == '__main__':
    unittest.main()
