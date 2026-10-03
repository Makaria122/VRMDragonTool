import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from um.dragon_anatomical_fit import alias_weights, fit_points, recipe


def anchors(pose):
    standing = {'hips': (0, 0, .9), 'UpperLeg': (.1, 0, .85), 'LowerLeg': (.1, 0, .5),
                'Foot': (.1, 0, .1), 'Toes': (.1, .15, .02)}
    seated = {'hips': (0, 0, .9), 'UpperLeg': (.1, 0, .85), 'LowerLeg': (.1, .4, .85),
              'Foot': (.1, .4, .45), 'Toes': (.1, .55, .4)}
    target = standing if pose == 'standing' else seated
    result = {'hips': {'source': list(standing['hips']), 'target': list(target['hips'])}}
    for side in ('left', 'right'):
        for role in ('UpperLeg', 'LowerLeg', 'Foot', 'Toes'):
            result[side + role] = {'source_bone': side + role, 'target_bone': 't' + side + role,
                                   'source': list(standing[role]), 'target': list(target[role])}
    return result


def inventory(pose):
    floor_target = .0 if pose == 'standing' else .4
    return {'joint_anchors': anchors(pose),
            'ground_alignment': {'source_floor_m': .0, 'target_floor_m': floor_target}}


class AnatomicalFitTests(unittest.TestCase):
    def test_standing_keeps_height_remap_and_has_no_pose_mode(self):
        r = recipe(inventory('standing'))
        self.assertNotIn('mode', r)
        self.assertEqual(len(r['source_heights']), 4)

    def test_seated_target_uses_leg_pose_segments_instead_of_failing(self):
        r = recipe(inventory('seated'))
        self.assertEqual(r['mode'], 'leg-pose')
        self.assertNotIn('source_heights', r)
        for side in ('left', 'right'):
            for part in ('UpperLeg', 'LowerLeg', 'Foot', 'Toes'):
                self.assertIn(side + part, r['hand_segments'])
        # Seated shin keeps its length while pointing along the target's direction.
        shin = r['hand_segments']['leftLowerLeg']
        self.assertAlmostEqual(shin['length_ratio'], 1.0, places=6)

    def test_seated_fit_moves_shin_to_target_pose(self):
        r = recipe(inventory('seated'))
        points = [[.1, 0, .5], [.1, 0, .3], [.1, 0, .1], [0, 0, .95]]
        weights = [{'leftLowerLeg': 1.0}, {'leftLowerLeg': 1.0}, {'leftFoot': 1.0},
                   {'hips': 1.0}]
        out = fit_points(points, weights, r)
        # Knee (source .1,0,.5) lands on the target knee; the torso point is untouched.
        self.assertTrue(all(abs(a - b) < 1e-6 for a, b in zip(out[0], [.1, .4, .85])))
        self.assertEqual(out[3], points[3])
        # Shin points keep their distance from the knee (rigid rotation, ratio 1).
        self.assertAlmostEqual(math.dist(out[0], out[1]), .2, places=6)
        self.assertAlmostEqual(math.dist(out[0], out[2]), .4, places=6)

    def test_unordered_target_landmarks_still_stop_for_review(self):
        inv = inventory('standing')
        inv['ground_alignment']['target_floor_m'] = .3  # floor above the ankle
        with self.assertRaises(ValueError) as ctx:
            recipe(inv)
        self.assertIn('Unordered', str(ctx.exception))

    def test_pose_mode_without_leg_anchors_keeps_original_error(self):
        inv = inventory('seated')
        del inv['joint_anchors']['leftToes']
        with self.assertRaises(ValueError) as ctx:
            recipe(inv)
        self.assertIn('outside supported bounds', str(ctx.exception))

    def test_standing_move_limit_stays_50cm(self):
        r = recipe(inventory('standing'))
        r['hand_segments'] = {'leftFoot': {'source': [0, 0, .1], 'target': [0, 0, 1.0],
                                           'source_axis': [0, 0, 1], 'target_axis': [0, 0, 1],
                                           'length_ratio': 1.0}}
        with self.assertRaises(ValueError) as ctx:
            fit_points([[0, 0, .1]], [{'leftFoot': 1.0}], r)
        self.assertIn('50cm', str(ctx.exception))


def with_arms(inv, source_down):
    # Target arms are raised sideways (T-pose); the VRM arms either match or hang down (A-pose).
    target = {'UpperArm': (.2, 0, 1.5), 'LowerArm': (.5, 0, 1.5), 'Hand': (.8, 0, 1.5),
              'MiddleProximal': (.9, 0, 1.5)}
    hanging = {'UpperArm': (.2, 0, 1.5), 'LowerArm': (.35, 0, 1.2), 'Hand': (.45, 0, .9),
               'MiddleProximal': (.48, 0, .8)}
    for side, sign in (('left', 1), ('right', -1)):
        for role in target:
            src = hanging[role] if source_down else target[role]
            inv['joint_anchors'][side + role] = {
                'source_bone': side + role, 'target_bone': 't' + side + role,
                'source': [sign * src[0], src[1], src[2]], 'target': [sign * target[role][0], 0, target[role][2]]}
    return inv


class ArmPoseTests(unittest.TestCase):
    def test_matching_arms_keep_the_original_recipe(self):
        r = recipe(with_arms(inventory('standing'), source_down=False))
        self.assertNotIn('leftUpperArm', r['hand_segments'])
        self.assertNotIn('max_move_m', r)

    def test_hanging_arms_fit_the_upper_arm_too_and_allow_a_larger_move(self):
        r = recipe(with_arms(inventory('standing'), source_down=True))
        self.assertIn('leftUpperArm', r['hand_segments'])
        self.assertIn('rightUpperArm', r['hand_segments'])
        self.assertEqual(r['max_move_m'], 1.0)
        # The forearm segment itself is still the elbow->wrist one (not overwritten).
        fore = r['hand_segments']['leftLowerArm']
        self.assertAlmostEqual(fore['length_ratio'], 0.3 / math.dist((.1, 0, -.3), (0, 0, 0)), places=3)
        points = [[.45, 0, .9], [.35, 0, 1.2]]
        out = fit_points(points, [{'leftHand': 1.0}, {'leftLowerArm': 1.0}], r)
        self.assertTrue(math.dist(out[1], [.5, 0, 1.5]) < 1e-6)  # elbow lands on the target elbow

    def test_twist_groups_follow_the_forearm_only_when_the_pose_is_refitted(self):
        roles = [{'source_bone': 'leftLowerArm', 'target_bone': 'tleftLowerArm'}]
        hints = [{'source_group': 'lowerarm_twist', 'suggested_target': 'tleftLowerArm'},
                 {'source_group': 'jaw', 'suggested_target': 'face_c_n'}]
        weights = [{'lowerarm_twist': .5, 'leftLowerArm': .25, 'jaw': .25}]
        hanging = recipe(with_arms(inventory('standing'), source_down=True))
        out = alias_weights(weights, hanging, roles, hints)
        self.assertEqual(out, [{'leftLowerArm': .75, 'jaw': .25}])
        matching = recipe(with_arms(inventory('standing'), source_down=False))
        self.assertEqual(alias_weights(weights, matching, roles, hints), weights)

    def test_move_limit_value_is_validated(self):
        r = recipe(inventory('standing'))
        r['max_move_m'] = 5.0
        with self.assertRaises(ValueError):
            fit_points([[0, 0, 1.0]], [{'hips': 1.0}], r)


if __name__ == '__main__':
    unittest.main()
