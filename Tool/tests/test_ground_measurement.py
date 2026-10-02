import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from um.dragon_ground_measurement import foot_weighted_minimum, support_floor


class GroundMeasurementTests(unittest.TestCase):
    def test_bandage_above_ankle_not_floor_slippers_are(self):
        candidates=[('Bandage_Foot',0.107),('Body_base',-0.1205),('Kumachan_Slippers',-0.14486)]
        floor,meshes=support_floor(candidates,-0.018336,'source')
        self.assertAlmostEqual(floor,-0.14486)
        self.assertEqual(meshes,['Kumachan_Slippers'])

    def test_hair_or_nonfoot_weights_do_not_set_floor(self):
        verts=[(-1.0,{'hair':1.0}),(-0.15,{'Foot.L':0.8,'leg':0.2}),
               (-0.9,{'Foot.L':0.01,'hair':0.99})]
        self.assertEqual(foot_weighted_minimum(verts,{'Foot.L'}),-0.15)
        self.assertIsNone(foot_weighted_minimum(verts,{'not_present'}))

    def test_no_support_cannot_silently_invent_floor(self):
        with self.assertRaises(ValueError):support_floor([('Bandage',0.107)],-0.018,'source')
        with self.assertRaises(ValueError):support_floor([('bad',float('nan'))],0.1,'source')


if __name__=='__main__':unittest.main()
