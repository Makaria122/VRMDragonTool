import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from um.dragon_anatomical_fit import fit_points, recipe


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


if __name__ == '__main__':
    unittest.main()
